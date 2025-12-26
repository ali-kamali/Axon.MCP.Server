"""Context builder for creating rich chunks."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, Relation
from src.config.enums import RelationTypeEnum


@dataclass
class ChunkContext:
    """Rich context for creating symbol chunks."""
    
    # File-level context
    file_path: str
    namespace: Optional[str] = None
    imports: List[str] = field(default_factory=list)
    
    # Symbol hierarchy
    parent_class: Optional[Dict[str, Any]] = None  # Parent class info if this is a method
    parent_namespace: Optional[str] = None
    
    # Relationships
    calls: List[str] = field(default_factory=list)  # Functions this symbol calls
    called_by: List[str] = field(default_factory=list)  # Functions that call this
    implements: List[str] = field(default_factory=list)  # Interfaces this implements
    inherits_from: List[str] = field(default_factory=list)  # Classes this inherits from
    
    # Additional metadata
    complexity: Optional[int] = None
    is_test: bool = False
    is_public: bool = True


class ChunkContextBuilder:
    """Builder for extracting context for symbol chunks."""
    
    def __init__(self, session: AsyncSession):
        """
        Initialize context builder.
        
        Args:
            session: Database session
        """
        self.session = session
    
    async def build_context(
        self,
        symbol: Symbol,
        file: File
    ) -> ChunkContext:
        """
        Build rich context for a symbol.
        
        Args:
            symbol: Symbol to build context for
            file: File containing the symbol
            
        Returns:
            ChunkContext with extracted information
        """
        context = ChunkContext(file_path=file.path)
        
        # Extract namespace from symbol's fully qualified name
        if symbol.fully_qualified_name and '.' in symbol.fully_qualified_name:
            parts = symbol.fully_qualified_name.rsplit('.', 1)
            context.namespace = parts[0]
        
        # Get parent class info if this is a method
        if symbol.parent_name:
            parent = await self._get_parent_symbol(symbol)
            if parent:
                context.parent_class = {
                    'name': parent.name,
                    'kind': parent.kind.value,
                    'signature': parent.signature
                }
        
        # Get imports from file
        # Note: This could be enhanced by parsing file.content if available
        # For now, we'll extract from related symbols
        context.imports = await self._extract_imports(file.id)
        
        # Get relationships
        await self._extract_relationships(symbol, context)
        
        # Determine if public (from access modifier)
        if symbol.access_modifier:
            context.is_public = symbol.access_modifier.value in ['public', 'protected']
        
        # Check if it's a test (heuristic based on name/path)
        context.is_test = self._is_test_symbol(symbol, file)
        
        # Get complexity if available
        if symbol.complexity_score:
            context.complexity = symbol.complexity_score
        
        return context
    
    async def _get_parent_symbol(self, symbol: Symbol) -> Optional[Symbol]:
        """Get the parent symbol (e.g., class for a method)."""
        if not symbol.parent_name:
            return None
        
        result = await self.session.execute(
            select(Symbol).where(
                Symbol.file_id == symbol.file_id,
                Symbol.fully_qualified_name == symbol.parent_name
            )
        )
        return result.scalars().first()
    
    async def _extract_imports(self, file_id: int) -> List[str]:
        """Extract import statements from file."""
        # This would ideally parse the file content
        # For now, return empty list as imports are stored separately
        # TODO: Enhance by storing file imports in database
        return []
    
    async def _extract_relationships(self, symbol: Symbol, context: ChunkContext):
        """Extract symbol relationships."""
        # Get outgoing relationships (what this symbol uses/calls/implements)
        result_from = await self.session.execute(
            select(Relation, Symbol)
            .join(Symbol, Relation.to_symbol_id == Symbol.id)
            .where(Relation.from_symbol_id == symbol.id)
        )
        
        for relation, target in result_from.all():
            if relation.relation_type == RelationTypeEnum.CALLS:
                context.calls.append(target.name)
            elif relation.relation_type == RelationTypeEnum.IMPLEMENTS:
                context.implements.append(target.name)
            elif relation.relation_type == RelationTypeEnum.INHERITS:
                context.inherits_from.append(target.name)
        
        # Get incoming relationships (what calls/uses this symbol)
        result_to = await self.session.execute(
            select(Relation, Symbol)
            .join(Symbol, Relation.from_symbol_id == Symbol.id)
            .where(Relation.to_symbol_id == symbol.id)
        )
        
        for relation, source in result_to.all():
            if relation.relation_type == RelationTypeEnum.CALLS:
                context.called_by.append(source.name)
    
    def _is_test_symbol(self, symbol: Symbol, file: File) -> bool:
        """Determine if symbol is a test (heuristic)."""
        name_lower = symbol.name.lower()
        file_lower = file.path.lower()
        
        # Check for test keywords in name
        test_keywords = ['test', 'spec', 'should', 'when', 'given']
        if any(keyword in name_lower for keyword in test_keywords):
            return True
        
        # Check for test path patterns
        test_paths = ['test/', 'tests/', '__tests__/', 'spec/', 'specs/']
        if any(path in file_lower for path in test_paths):
            return True
        
        return False

