"""
Partial Class Merger - Merges partial class definitions across files.

Phase 2.1: Handles C# partial classes, interfaces, and structs.
"""
from typing import List, Dict, Optional, Set
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from src.database.models import Symbol
from src.config.enums import SymbolKindEnum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class PartialClassMerger:
    """
    Merges partial class/interface/struct definitions into single symbols.
    
    Strategy:
    1. Group symbols by (fully_qualified_name, kind) where is_partial=True
    2. For each group with multiple definitions:
       - Keep the first symbol as the "primary"
       - Merge members from other definitions
       - Track all source files
       - Update line ranges to span all definitions
       - Mark merged symbols
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def merge_partial_classes(self, repository_id: int) -> int:
        """
        Merge partial class definitions across repository.
        
        Args:
            repository_id: Repository ID to process
            
        Returns:
            Number of merged symbol groups
        """
        # Find all partial symbols in repository
        query = select(Symbol).where(
            Symbol.file.has(repository_id=repository_id)
        )
        result = await self.session.execute(query)
        all_symbols = result.scalars().all()
        
        # Filter to only partial symbols
        partial_symbols = []
        for symbol in all_symbols:
            if symbol.structured_docs and symbol.structured_docs.get('is_partial'):
                partial_symbols.append(symbol)
        
        if not partial_symbols:
            logger.info("no_partial_classes_found", repository_id=repository_id)
            return 0
        
        logger.info(
            "found_partial_symbols",
            repository_id=repository_id,
            count=len(partial_symbols)
        )
        
        # Group by (FQN, kind)
        groups = defaultdict(list)
        for symbol in partial_symbols:
            # Only merge classes, interfaces, and structs
            if symbol.kind in [SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE, SymbolKindEnum.STRUCT]:
                key = (symbol.fully_qualified_name, symbol.kind)
                groups[key].append(symbol)
        
        # Merge each group with multiple definitions
        merged_count = 0
        for (fqn, kind), symbols_list in groups.items():
            if len(symbols_list) > 1:
                await self._merge_symbol_group(symbols_list, fqn, kind)
                merged_count += 1
        
        logger.info(
            "partial_classes_merged",
            repository_id=repository_id,
            merged_groups=merged_count
        )
        
        return merged_count
    
    async def _merge_symbol_group(
        self,
        symbols: List[Symbol],
        fqn: str,
        kind: SymbolKindEnum
    ):
        """
        Merge a group of partial symbol definitions.
        
        Strategy:
        - Keep first symbol as primary
        - Collect all file_ids
        - Update line ranges to span all definitions
        - Mark as merged
        
        Args:
            symbols: List of partial symbols to merge
            fqn: Fully qualified name
            kind: Symbol kind
        """
        # Sort by file_id for consistency
        symbols.sort(key=lambda s: s.file_id)
        
        primary = symbols[0]
        others = symbols[1:]
        
        # Collect all file IDs
        all_file_ids = [s.file_id for s in symbols]
        
        # Collect all symbol IDs being merged
        merged_ids = [s.id for s in others]
        
        # Calculate combined line range
        min_line = min(s.start_line for s in symbols)
        max_line = max(s.end_line for s in symbols)
        
        # Update primary symbol
        primary.is_partial = 1
        primary.partial_definition_files = all_file_ids
        primary.merged_from_partial_ids = merged_ids
        primary.start_line = min_line
        primary.end_line = max_line
        
        # Merge documentation (combine from all parts)
        docs = []
        for s in symbols:
            if s.documentation:
                docs.append(s.documentation)
        if docs:
            primary.documentation = "\n\n".join(docs)
        
        # Update structured_docs to indicate merge
        if primary.structured_docs is None:
            primary.structured_docs = {}
        primary.structured_docs['is_partial'] = True
        primary.structured_docs['partial_count'] = len(symbols)
        primary.structured_docs['merged_files'] = all_file_ids
        
        logger.debug(
            "merged_partial_symbol",
            fqn=fqn,
            kind=kind.name,
            primary_id=primary.id,
            merged_count=len(others),
            file_count=len(all_file_ids)
        )
        
        # Note: We keep the other symbols in the database for reference
        # They can be filtered out in queries using merged_from_partial_ids
        # Or we could mark them as "merged" with a flag
        
        # Mark other symbols as merged into primary
        for other in others:
            if other.structured_docs is None:
                other.structured_docs = {}
            other.structured_docs['merged_into'] = primary.id
            other.structured_docs['is_partial_fragment'] = True
        
        await self.session.flush()
    
    async def get_merged_symbol(self, symbol_id: int) -> Optional[Symbol]:
        """
        Get the primary symbol if this is a partial fragment.
        
        Args:
            symbol_id: Symbol ID to check
            
        Returns:
            Primary symbol if this is a fragment, otherwise the symbol itself
        """
        query = select(Symbol).where(Symbol.id == symbol_id)
        result = await self.session.execute(query)
        symbol = result.scalar_one_or_none()
        
        if not symbol:
            return None
        
        # Check if this is a merged fragment
        if symbol.structured_docs and symbol.structured_docs.get('merged_into'):
            primary_id = symbol.structured_docs['merged_into']
            query = select(Symbol).where(Symbol.id == primary_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        
        return symbol
