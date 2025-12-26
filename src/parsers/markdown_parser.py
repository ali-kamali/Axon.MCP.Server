import re
from typing import List, Optional, Dict, Any
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


class MarkdownParser(BaseParser):
    """Markdown documentation parser."""
    
    def __init__(self):
        self.language = LanguageEnum.MARKDOWN
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a Markdown file."""
        return file_path.suffix.lower() in ['.md', '.markdown']
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse markdown content and extract:
        - Headings (H1-H6) as document sections
        - Code blocks as code examples
        - Links to other files
        """
        import time
        start_time = time.time()
        
        symbols = []
        errors = []
        
        try:
            # Extract headings as document sections
            symbols.extend(self._extract_headings(code, file_path))
            
            # Extract code blocks as examples
            symbols.extend(self._extract_code_blocks(code, file_path))
            
        except Exception as e:
            errors.append(f"Markdown parsing error: {str(e)}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Extract links (for potential cross-references)
        links = self._extract_links(code)
        
        return ParseResult(
            language=self.language,
            file_path=file_path or "unknown",
            symbols=symbols,
            imports=links,  # Use links as imports for cross-references
            exports=[],
            parse_errors=errors,
            parse_duration_ms=duration_ms
        )
    
    def _extract_headings(self, code: str, file_path: Optional[str]) -> List[ParsedSymbol]:
        """
        Extract markdown headings as document sections.
        
        Matches:
        # Heading 1
        ## Heading 2
        ### Heading 3
        etc.
        """
        symbols = []
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, start=1):
            # Match markdown headings
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if heading_match:
                level = len(heading_match.group(1))  # Count # symbols
                title = heading_match.group(2).strip()
                
                # Extract the content under this heading (until next heading or end)
                content_lines = []
                for i in range(line_num, len(lines)):
                    next_line = lines[i].strip()
                    # Stop at next heading
                    if next_line.startswith('#') and i != line_num - 1:
                        break
                    content_lines.append(lines[i])
                
                content = '\n'.join(content_lines[:50])  # Limit to first 50 lines
                
                symbols.append(ParsedSymbol(
                    kind=SymbolKindEnum.DOCUMENT_SECTION,
                    name=title,
                    start_line=line_num,
                    end_line=line_num + len(content_lines),
                    start_column=0,
                    end_column=len(line),
                    signature=f"{'#' * level} {title}",
                    documentation=content,
                    structured_docs={
                        'level': level,
                        'title': title,
                        'content_preview': content[:500] if content else None
                    }
                ))
        
        return symbols
    
    def _extract_code_blocks(self, code: str, file_path: Optional[str]) -> List[ParsedSymbol]:
        """
        Extract code blocks from markdown.
        
        Matches:
        ```language
        code here
        ```
        """
        symbols = []
        lines = code.split('\n')
        
        in_code_block = False
        block_start = 0
        block_language = None
        block_lines = []
        
        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            
            if stripped.startswith('```'):
                if not in_code_block:
                    # Start of code block
                    in_code_block = True
                    block_start = line_num
                    # Extract language hint (e.g., ```python)
                    lang_match = re.match(r'^```(\w+)', stripped)
                    block_language = lang_match.group(1) if lang_match else 'unknown'
                    block_lines = []
                else:
                    # End of code block
                    in_code_block = False
                    
                    if block_lines:
                        code_content = '\n'.join(block_lines)
                        
                        symbols.append(ParsedSymbol(
                            kind=SymbolKindEnum.CODE_EXAMPLE,
                            name=f"Code Example ({block_language})",
                            start_line=block_start,
                            end_line=line_num,
                            start_column=0,
                            end_column=len(line),
                            signature=f"```{block_language}",
                            documentation=code_content,
                            structured_docs={
                                'language': block_language,
                                'code': code_content,
                                'line_count': len(block_lines)
                            }
                        ))
            elif in_code_block:
                block_lines.append(line)
        
        return symbols
    
    def _extract_links(self, code: str) -> List[str]:
        """
        Extract markdown links for cross-references.
        
        Matches:
        [text](url)
        [text][ref]
        """
        links = []
        
        # Match [text](url) style links
        link_matches = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', code)
        for text, url in link_matches:
            links.append(url)
        
        # Match [text][ref] style links
        ref_matches = re.findall(r'\[([^\]]+)\]\[([^\]]+)\]', code)
        for text, ref in ref_matches:
            links.append(ref)
        
        return links

