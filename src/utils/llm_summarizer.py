"""LLM-based code summarization service for Phase 2."""

import json
from typing import Dict, List, Optional
import asyncio

try:
    import openai
except ImportError:
    openai = None

from src.config.settings import settings
from src.utils.logging_config import get_logger
from src.utils.module_identifier import ModuleInfo

logger = get_logger(__name__)


class LLMSummarizer:
    """Generate AI-powered summaries of code modules."""

    def __init__(self, provider: str = None, model: str = None):
        """
        Initialize LLM summarizer.

        Args:
            provider: LLM provider to use ("openai", "openrouter", etc.)
                     If None, uses settings.llm_provider
            model: Model name to use. If None, uses settings.llm_model
        """
        self.provider = provider or settings.llm_provider
        self.model = model or settings.llm_model
        self._client = None
        
        logger.info(f"LLMSummarizer initialized with provider={self.provider}, model={self.model}")

    def _get_client(self):
        """Get or create LLM client."""
        if self._client is not None:
            return self._client

        if self.provider == "openai":
            try:
                if not settings.openai_api_key:
                    logger.warning(
                        "OpenAI API key not configured, summarization will be limited"
                    )
                    return None

                # For openai >= 1.0.0
                self._client = openai.OpenAI(api_key=settings.openai_api_key)
                logger.info("OpenAI client initialized for summarization")
                return self._client

            except ImportError:
                logger.error("OpenAI package not installed. Install with: pip install openai")
                return None
            except Exception as e:
                logger.error(f"Error initializing OpenAI client: {e}", exc_info=True)
                return None
                
        elif self.provider == "openrouter":
            try:
                if not settings.openrouter_api_key:
                    logger.warning(
                        "OpenRouter API key not configured, summarization will be limited"
                    )
                    return None

                # OpenRouter uses OpenAI-compatible API
                self._client = openai.OpenAI(
                    api_key=settings.openrouter_api_key,
                    base_url="https://openrouter.ai/api/v1"
                )
                logger.info(f"OpenRouter client initialized for summarization with model {self.model}")
                return self._client

            except ImportError:
                logger.error("OpenAI package not installed. Install with: pip install openai")
                return None
            except Exception as e:
                logger.error(f"Error initializing OpenRouter client: {e}", exc_info=True)
                return None

        elif self.provider == "ollama":
            try:
                # Ollama uses OpenAI-compatible API
                self._client = openai.OpenAI(
                    api_key="ollama",  # Dummy key required by client
                    base_url=settings.ollama_base_url
                )
                logger.info(f"Ollama client initialized for summarization with model {self.model} at {settings.ollama_base_url}")
                return self._client

            except ImportError:
                logger.error("OpenAI package not installed. Install with: pip install openai")
                return None
            except Exception as e:
                logger.error(f"Error initializing Ollama client: {e}", exc_info=True)
                return None
        else:
            logger.warning(f"Unsupported LLM provider: {self.provider}")
            return None

    async def summarize_module(
        self,
        module_info: ModuleInfo,
        symbol_list: List[Dict],
        file_contents: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict]:
        """
        Generate a comprehensive summary of a module.

        Args:
            module_info: Module information
            symbol_list: List of key symbols in the module
            file_contents: Optional dict of {file_path: content} for key files

        Returns:
            Dictionary with summary, purpose, key_components, dependencies, etc.
        """
        try:
            client = self._get_client()

            if client is None:
                # Fall back to simple heuristic-based summary
                return self._generate_fallback_summary(module_info, symbol_list)

            # Build context for LLM
            context = self._build_context(module_info, symbol_list, file_contents)

            # Generate summary using LLM
            prompt = self._create_summary_prompt(context)

            # Retry logic for rate limits
            max_retries = 5
            base_delay = 5  # Start with 5 seconds for free tier
            
            for attempt in range(max_retries):
                try:
                    # Call LLM API
                    response = client.chat.completions.create(
                        model=self.model,  # Use configured model
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert code analyst. Generate concise, accurate summaries of code modules.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,  # Lower temperature for more consistent output
                        max_tokens=1500,
                        timeout=settings.llm_request_timeout,
                    )
                    
                    # Parse LLM response
                    summary_text = response.choices[0].message.content

                    # Try to extract structured data from response
                    parsed_summary = self._parse_llm_response(summary_text, module_info)

                    logger.info(
                        f"Generated LLM summary for module {module_info.path}",
                        provider=self.provider,
                        model=self.model,
                    )

                    return parsed_summary

                except openai.RateLimitError as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Rate limit exceeded after {max_retries} attempts: {e}")
                        raise
                    
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Rate limit exceeded. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    
                except openai.APIError as e:
                    # Handle other API errors that might be transient
                    if attempt == max_retries - 1:
                        logger.error(f"API error after {max_retries} attempts: {e}")
                        raise
                        
                    if e.status_code in [500, 502, 503, 504]:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"API error {e.status_code}. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                    else:
                        raise

        except Exception as e:
            logger.error(f"Error generating LLM summary: {e}", exc_info=True)
            # Fall back to simple summary
            return self._generate_fallback_summary(module_info, symbol_list)


    async def summarize_async(self, prompt: str) -> Optional[str]:
        """
        Generate a summary/response asynchronously using the configured LLM.
        
        Args:
            prompt: The text prompt to send to the LLM
            
        Returns:
            Generated text or None if failed
        """
        try:
            client = self._get_client()
            if client is None:
                return None

            max_retries = 5
            base_delay = 5
            
            for attempt in range(max_retries):
                try:
                    # Run synchronous client in a thread pool to avoid blocking event loop
                    response = await asyncio.to_thread(
                        client.chat.completions.create,
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert code analyst. Provide clear, concise, and accurate analysis.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                        timeout=settings.llm_request_timeout,
                    )
                    
                    return response.choices[0].message.content

                except openai.RateLimitError as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Rate limit exceeded after {max_retries} attempts: {e}")
                        raise
                    
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Rate limit exceeded. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    
                except openai.APIError as e:
                    if attempt == max_retries - 1:
                        logger.error(f"API error after {max_retries} attempts: {e}")
                        raise
                        
                    if e.status_code in [500, 502, 503, 504]:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"API error {e.status_code}. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                    else:
                        raise

        except Exception as e:
            logger.error(f"Error generating LLM summary: {e}", exc_info=True)
            return None

    def _build_context(

        self,
        module_info: ModuleInfo,
        symbol_list: List[Dict],
        file_contents: Optional[Dict[str, str]],
    ) -> Dict:
        """Build context information for LLM."""
        # Primary language
        primary_lang = "unknown"
        if module_info.languages:
            primary_lang = max(module_info.languages.items(), key=lambda x: x[1])[0]

        context = {
            "module_name": module_info.name,
            "module_path": module_info.path,
            "module_type": module_info.module_type,
            "is_package": module_info.is_package,
            "file_count": module_info.file_count,
            "symbol_count": module_info.symbol_count,
            "line_count": module_info.line_count,
            "primary_language": primary_lang,
            "languages": module_info.languages,
            "entry_points": module_info.entry_points,
            "has_tests": module_info.has_tests,
            "key_symbols": symbol_list[:15],  # Limit to top 15
        }

        # Add file contents if provided (limited to prevent token explosion)
        if file_contents:
            context["sample_code"] = {}
            for file_path, content in list(file_contents.items())[:3]:  # Max 3 files
                # Limit content length
                max_chars = 2000
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n... (truncated)"
                context["sample_code"][file_path] = content

        return context

    def _create_summary_prompt(self, context: Dict) -> str:
        """Create prompt for LLM summarization."""
        prompt = f"""Analyze the following code module and provide a structured summary:

**Module Information:**
- Name: {context['module_name']}
- Path: {context['module_path']}
- Type: {context['module_type']}
- Primary Language: {context['primary_language']}
- Files: {context['file_count']}
- Symbols: {context['symbol_count']}
- Lines of Code: {context['line_count']}
- Entry Points: {', '.join(context['entry_points']) if context['entry_points'] else 'None'}

**Key Symbols:**
"""

        for i, symbol in enumerate(context["key_symbols"], 1):
            prompt += f"{i}. {symbol['kind']}: {symbol['name']}"
            if symbol.get("signature"):
                prompt += f" - {symbol['signature'][:100]}"
            prompt += "\n"

        if context.get("sample_code"):
            prompt += "\n**Sample Code:**\n"
            for file_path, content in context["sample_code"].items():
                prompt += f"\n--- {file_path} ---\n{content}\n"

        prompt += """

Please provide a structured summary in the following JSON format:
{
  "summary": "A concise 2-3 sentence overview of what this module does",
  "purpose": "The main purpose/responsibility of this module",
  "key_components": [
    {"name": "ComponentName", "description": "Brief description", "type": "class|function|service"}
  ],
  "dependencies": {
    "internal": ["list of internal modules this depends on"],
    "external": ["list of external packages/libraries used"]
  },
  "complexity_score": 1-10 (estimated complexity),
  "use_cases": ["Primary use case 1", "Primary use case 2"]
}

Respond with ONLY the JSON, no additional text."""

        return prompt

    def _parse_llm_response(
        self, response_text: str, module_info: ModuleInfo
    ) -> Dict:
        """Parse LLM response into structured format."""
        try:
            # Try to extract JSON from response
            # Sometimes LLM adds markdown code fences
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            parsed = json.loads(response_text)

            return {
                "summary": parsed.get("summary", ""),
                "purpose": parsed.get("purpose", ""),
                "key_components": parsed.get("key_components", []),
                "dependencies": parsed.get("dependencies", {}),
                "complexity_score": parsed.get("complexity_score"),
                "use_cases": parsed.get("use_cases", []),
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            # Try to extract summary from free-form text
            return {
                "summary": response_text[:500],  # Use raw text as summary
                "purpose": f"Module at {module_info.path}",
                "key_components": [],
                "dependencies": {},
            }

    def _generate_fallback_summary(
        self, module_info: ModuleInfo, symbol_list: List[Dict]
    ) -> Dict:
        """Generate a simple heuristic-based summary when LLM is unavailable."""
        # Build summary from available information
        primary_lang = (
            max(module_info.languages.items(), key=lambda x: x[1])[0]
            if module_info.languages
            else "unknown"
        )

        summary_parts = []

        if module_info.is_package:
            summary_parts.append(
                f"A {primary_lang} package containing {module_info.file_count} files"
            )
        else:
            summary_parts.append(
                f"A directory containing {module_info.file_count} {primary_lang} files"
            )

        if module_info.symbol_count > 0:
            summary_parts.append(
                f"with {module_info.symbol_count} code symbols ({module_info.line_count} lines)"
            )

        summary = ". ".join(summary_parts) + "."

        # Extract key components from symbols
        key_components = []
        for symbol in symbol_list[:10]:
            key_components.append(
                {
                    "name": symbol["name"],
                    "description": symbol.get("documentation", "")[:100] or "No description",
                    "type": symbol["kind"],
                }
            )

        return {
            "functional_summary": summary,
            "business_purpose": f"Module at {module_info.path}",
            "key_components": key_components,
            "dependencies": {"internal": [], "external": []},
            "complexity_score": min(10, max(1, module_info.file_count // 2)),
            "use_cases": [],
        }

