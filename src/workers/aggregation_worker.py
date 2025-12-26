"""
Celery task for Repository Aggregation (The "Service Manifesto").
"""
import asyncio
import re
import json
from typing import List, Dict, Optional
import sqlalchemy as sa
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from src.workers.celery_app import celery_app
from src.workers.utils import _run_with_engine_cleanup
from src.database.session import AsyncSessionLocal
from src.database.models import Repository, Symbol, File, Service
from src.utils.logging_config import get_logger
from src.utils.llm_summarizer import LLMSummarizer
from src.config.settings import settings
from src.config.enums import SymbolKindEnum

logger = get_logger(__name__)

@celery_app.task(bind=True, name="src.workers.aggregation_worker.aggregate_repository_summary", max_retries=3)
def aggregate_repository_summary(self, repository_id: int):
    """
    Aggregate repository insights into a high-level "Repository Manifesto".
    
    Triggered after enrichment completes.
    """
    try:
        return asyncio.run(_run_with_engine_cleanup(_aggregate_repository_summary_async(self, repository_id)))
    except Exception as e:
        logger.error(f"Repository Aggregation failed: {e}")
        raise self.retry(exc=e, countdown=60)


async def _aggregate_repository_summary_async(task, repository_id: int):
    """Async implementation of repository aggregation."""
    logger.info("repository_aggregation_started", repository_id=repository_id)
    
    llm = LLMSummarizer()
    
    async with AsyncSessionLocal() as session:
        session.expire_on_commit = False  # Prevent detached instance errors
        
        # 1. Fetch Repository
        repo = await session.get(Repository, repository_id)
        if not repo:
            logger.error("repository_not_found", repository_id=repository_id)
            return
            
        # 2. Fetch Top 50 Significant Symbols
        # Strategy: Prioritize Controllers, Aggregate Roots, Handlers
        # We filter for symbols that successfully got enriched
        # 2. Fetch Top 50 Significant Symbols
        # Strategy: Prioritize Controllers, Services, Aggregate Roots, Handlers
        # We assign a synthetic priority score based on SymbolKind and name patterns
        
        # Priority mapping (lower is better, used for fallback sorting if score is equal)
        # We mainly use complexity_score, but we want to filter OUT "DTOs" and "Utils" 
        # and prioritize specific kinds.
        
        # Assuming we can't easily do complex CASE/WHEN in pure SQLAlchemy comfortably without much boilerplate,
        # we'll fetch a slightly larger batch and filter/sort in Python, 
        # OR we can improve the query. Let's try to improve the query with weighting.
        
        # We want to select symbols that:
        # 1. Have ai_enrichment
        # 2. Are not DTOs or Utils (by name convention or kind)
        # 3. Are high complexity
        
        stmt = (
            select(Symbol)
            .join(Symbol.file)
            .where(
                Symbol.file.has(File.repository_id == repository_id),
                Symbol.ai_enrichment.is_not(None),
                # Exclude obvious noise
                sa.not_(Symbol.name.ilike("%DTO%")),
                sa.not_(Symbol.name.ilike("%Request%")),
                sa.not_(Symbol.name.ilike("%Response%")),
                sa.not_(Symbol.name.ilike("%Utility%")),
                sa.not_(Symbol.name.ilike("%Helper%")),
                sa.not_(Symbol.name.ilike("%Test%"))
            )
            .order_by(
                # Prioritize specific kinds via a case statement if possible, 
                # but simplest is just complexity * weight or just descending complexity 
                # filtered by the exclusions above.
                desc(Symbol.complexity_score)
            )
            .limit(200) # Fetch more, refine in memory
            .options(selectinload(Symbol.file))
        )
        
        result = await session.execute(stmt)
        all_symbols = result.scalars().all()
        
        if not all_symbols:
            logger.warning("no_enriched_symbols_found", repository_id=repository_id)
            return

        # Refine Selection in Python
        # Priority: Controllers/Endpoints > Services/AggregateRoots > Others
        prioritized_symbols = []
        for s in all_symbols:
            # High priority
            is_high_priority = (
                s.kind == SymbolKindEnum.ENDPOINT or 
                "Controller" in s.name or 
                "Service" in s.name or
                "Handler" in s.name or
                "Manager" in s.name
            )
            
            p_score = s.complexity_score or 0
            if is_high_priority:
                p_score += 1000 # Boost
            
            prioritized_symbols.append((p_score, s))
        
        # Sort by boosted score and take top 50
        prioritized_symbols.sort(key=lambda x: x[0], reverse=True)
        symbols = [s for _, s in prioritized_symbols[:50]]
        
        if not symbols:
            logger.warning("no_enriched_symbols_found", repository_id=repository_id)
            return
            
        # 3. Prepare Context for LLM
        context_lines = []
        total_chars = 0
        MAX_CONTEXT_CHARS = 30000  # Increased from 15000 to allow ~70-80 symbols vs ~37
        
        for sym in symbols:
            enrichment = sym.ai_enrichment
            if isinstance(enrichment, str):
                try:
                    enrichment = json.loads(enrichment)
                except:
                    continue
            
            if not isinstance(enrichment, dict): 
                continue
                
            summary = enrichment.get("functional_summary", "No summary")
            business_purpose = enrichment.get("business_purpose", "No purpose")
            
            # Truncate individual entries to prevent extremely long summaries
            # Increased limits to preserve more context while still preventing overflow
            summary = summary[:800] if summary else "No summary"  # Increased from 500
            business_purpose = business_purpose[:500] if business_purpose else "No purpose"  # Increased from 300
            
            line = f"- {sym.name} ({sym.kind.value}): {business_purpose}. {summary}"
            
            # Check if adding this would overflow
            if total_chars + len(line) > MAX_CONTEXT_CHARS:
                logger.warning("context_size_limit_reached", repository_id=repository_id, symbols_included=len(context_lines))
                break
                
            context_lines.append(line)
            total_chars += len(line) + 1  # +1 for newline
            
        if not context_lines:
            logger.error("no_valid_enrichment_data", repository_id=repository_id)
            return
            
        context_str = "\n".join(context_lines)
        
        # 4. Construct Prompt
        system_prompt = """You are the Lead Systems Architect. Your goal is to write a "Repository Manifesto" for the repository based on the provided file summaries. 

CRITICAL INSTRUCTIONS:
- Focus on the "Forest", not the "Trees".
- NEGATIVE CONSTRAINT: Do not list specific files, classes, or functions. Do not explain class structures or coding patterns.
- POSITIVE CONSTRAINT: Explain Business Capabilities (e.g., 'Handles Checkout'), Data Ownership (e.g., 'Source of Truth for Orders'), and External Dependencies.
- Tone: Strategic, High-Level, Professional.

Output must strictly follow the required Markdown structure."""

        user_prompt = f"""
Repository Context:
{context_str}

Generate the REPOSITORY_MANIFESTO.md now. The format must be:

# Repository Name & Role
[One sentence pitch describing what this repository does]

## Primary Capabilities
- [Capability 1]
- [Capability 2]

## Domain Boundaries
**Owns Data**: [List of data entities this service is the Single Source of Truth for]
**Reads Data**: [List of data entities this service reads from others]

## Infrastructure Dependencies
- [Dependency 1] (e.g., SQL Server)
- [Dependency 2] (e.g., Redis)

## Key Workflows
- [Workflow A]: [Description]
- [Workflow B]: [Description]
"""

        # 5. Call LLM
        # Note: LLMSummarizer internals should handle model selection/fallback
        manifesto_md = await llm.summarize_async(f"{system_prompt}\n\n{user_prompt}")
        
        if not manifesto_md:
            logger.error("llm_aggregation_failed", repository_id=repository_id)
            return

        # 6. Parse Output (Simple extraction)
        ai_summary = _parse_manifesto(manifesto_md)
        
        # 7. Save to DB
        try:
            repo.manifesto = manifesto_md
            repo.ai_summary = ai_summary
            
            await session.commit()
            
            logger.info("repository_aggregation_completed", repository_id=repository_id)
            
            # 8. Trigger service documentation regeneration (now with enriched data)
            await _regenerate_service_docs(session, repository_id)
            
            return {"status": "success", "repository_id": repository_id}
        except Exception as e:
            await session.rollback()
            logger.error("aggregation_commit_failed", repository_id=repository_id, error=str(e))
            raise

def _parse_manifesto(markdown: str) -> Dict:
    """Extract structured data from the generated markdown."""
    data = {
        "one_sentence_pitch": None,
        "primary_capabilities": [],
        "domain_boundaries": {"owns": [], "reads": []},
        "infrastructure_dependencies": [],
        "key_workflows": []
    }
    
    try:
        # Extract Pitch (First non-header line)
        lines = markdown.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                data["one_sentence_pitch"] = line
                break
                
        # Simple Section Parsing
        # Allow optional space after ##
        sections = re.split(r'^##\s*', markdown, flags=re.MULTILINE)
        
        for section in sections:
            lines = section.strip().split('\n')
            header = lines[0].lower()
            content_lines = [l.strip() for l in lines[1:] if l.strip()]
            
            if "capabilities" in header:
                data["primary_capabilities"] = [l.lstrip('-* ').strip() for l in content_lines if l.startswith('-') or l.startswith('*')]
            
            elif "dependencies" in header:
                data["infrastructure_dependencies"] = [l.lstrip('-* ').strip() for l in content_lines if l.startswith('-') or l.startswith('*')]

            elif "boundaries" in header or "domain" in header:
                # Parse Owns/Reads Data
                for l in content_lines:
                    if "owns data" in l.lower():
                        # Extract after colon
                        parts = l.split(':', 1)
                        if len(parts) > 1:
                            data["domain_boundaries"]["owns"] = [x.strip() for x in parts[1].split(',') if x.strip()]
                    elif "reads data" in l.lower():
                        parts = l.split(':', 1)
                        if len(parts) > 1:
                            data["domain_boundaries"]["reads"] = [x.strip() for x in parts[1].split(',') if x.strip()]

            elif "workflows" in header:
                 data["key_workflows"] = [l.lstrip('-* ').strip() for l in content_lines if l.startswith('-') or l.startswith('*')]
                 
    except Exception as e:
        logger.warning(f"manifesto_parsing_partial_failure: {e}")
        
    return data


async def _regenerate_service_docs(session, repository_id: int):
    """Regenerate service documentation after enrichment to use enriched symbol context."""
    try:
        from src.generators.service_doc_generator import ServiceDocGenerator
        from src.config.enums import SymbolKindEnum
        
        # Fetch all services for this repository
        result = await session.execute(
            select(Service).filter(Service.repository_id == repository_id)
        )
        services = result.scalars().all()
        
        if not services:
            logger.debug("no_services_to_regenerate", repository_id=repository_id)
            return
        
        generator = ServiceDocGenerator(session)
        regenerated_count = 0
        
        for service in services:
            try:
                doc_content = await generator.generate_service_doc(service)
                await generator.save_documentation(service, doc_content)
                regenerated_count += 1
            except Exception as e:
                logger.warning(f"service_doc_regeneration_failed: {service.name}: {e}")
        
        await session.commit()
        logger.info("service_docs_regenerated", repository_id=repository_id, count=regenerated_count)
        
    except Exception as e:
        logger.error(f"service_doc_regeneration_error: {e}")
        # Don't raise - this is optional enhancement, aggregation already succeeded
