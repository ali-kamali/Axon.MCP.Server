from typing import List, Dict, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import Symbol, Relation, File
from src.config.enums import RelationTypeEnum, SymbolKindEnum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class RelationshipBuilder:
    """Builds advanced relationships across symbols and files."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def build_cross_file_relationships(
        self,
        repository_id: int
    ) -> int:
        """
        Build relationships across files in a repository.
        
        Args:
            repository_id: Repository ID
            
        Returns:
            Number of relationships created
        """
        relationships_created = 0
        
        # Get all symbols in repository
        result = await self.session.execute(
            select(Symbol)
            .join(File)
            .where(File.repository_id == repository_id)
        )
        symbols = result.scalars().all()
        
        # Build symbol index by name and fully qualified name
        symbol_index: Dict[str, List[Symbol]] = {}
        for symbol in symbols:
            symbol_index.setdefault(symbol.name, []).append(symbol)
            if symbol.fully_qualified_name:
                symbol_index.setdefault(symbol.fully_qualified_name, []).append(symbol)
        
        # Build inheritance relationships (Phase 2.4)
        relationships_created += await self._build_inheritance_chains(symbols, symbol_index)
        
        # Track overrides (Phase 2.4)
        relationships_created += await self._track_virtual_overrides(symbols, symbol_index)
        
        # Build references (Phase 3.5)
        relationships_created += await self._build_reference_relationships(symbols, symbol_index)
        
        # Build USES relationships (Phase 3.5 Fix)
        relationships_created += await self._build_uses_relationships(symbols, symbol_index)
        
        await self.session.flush()
        
        logger.info(
            "cross_file_relationships_built",
            repository_id=repository_id,
            relationships_created=relationships_created
        )
        
        return relationships_created
    
    async def _build_inheritance_chains(self, symbols: List[Symbol], symbol_index: Dict[str, List[Symbol]]) -> int:
        """Build inheritance relationships (extends/implements)."""
        count = 0
        
        for symbol in symbols:
            if symbol.kind not in [SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE]:
                continue
                
            base_classes = []
            interfaces = []
            
            # Use Roslyn data if available
            if symbol.structured_docs and symbol.structured_docs.get('roslyn'):
                roslyn = symbol.structured_docs['roslyn']
                if roslyn.get('base_type') and roslyn['base_type'] != 'object':
                    base_classes.append(roslyn['base_type'])
                if roslyn.get('interfaces'):
                    interfaces.extend(roslyn['interfaces'])
            else:
                # Fallback to signature parsing
                extracted = self._extract_base_classes(symbol.signature or "")
                base_classes.extend(extracted)
            
            # Process base classes
            for base_name in base_classes:
                targets = self._resolve_type(base_name, symbol_index)
                for target in targets:
                    if target.id == symbol.id: continue
                    
                    # Target is guaranteed to exist as it comes from the loaded symbols list
                    relation = Relation(
                        from_symbol_id=symbol.id,
                        to_symbol_id=target.id,
                        relation_type=RelationTypeEnum.INHERITS
                    )
                    self.session.add(relation)
                    count += 1
            
            # Process interfaces
            for interface_name in interfaces:
                targets = self._resolve_type(interface_name, symbol_index)
                for target in targets:
                    if target.id == symbol.id: continue
                    
                    # Target is guaranteed to exist
                    relation = Relation(
                        from_symbol_id=symbol.id,
                        to_symbol_id=target.id,
                        relation_type=RelationTypeEnum.IMPLEMENTS
                    )
                    self.session.add(relation)
                    count += 1
                    
        return count

    async def _track_virtual_overrides(self, symbols: List[Symbol], symbol_index: Dict[str, List[Symbol]]) -> int:
        """Link override methods to their base virtual methods."""
        count = 0
        
        for symbol in symbols:
            if symbol.kind != SymbolKindEnum.METHOD:
                continue
                
            is_override = False
            if symbol.structured_docs:
                if symbol.structured_docs.get('roslyn', {}).get('is_override'):
                    is_override = True
                elif symbol.structured_docs.get('is_override'):
                    is_override = True
            
            if is_override:
                # Simplified: Find any method with same name in potential base classes
                # A robust implementation would require traversing the inheritance graph
                potential_bases = symbol_index.get(symbol.name, [])
                for base_method in potential_bases:
                    if base_method.id == symbol.id: continue
                    
                    is_virtual = False
                    if base_method.structured_docs:
                        if base_method.structured_docs.get('roslyn', {}).get('is_virtual') or \
                           base_method.structured_docs.get('roslyn', {}).get('is_abstract') or \
                           base_method.structured_docs.get('is_virtual') or \
                           base_method.structured_docs.get('is_abstract'):
                            is_virtual = True
                    
                    if is_virtual:
                        # Target is guaranteed to exist
                        relation = Relation(
                            from_symbol_id=symbol.id,
                            to_symbol_id=base_method.id,
                            relation_type=RelationTypeEnum.OVERRIDES
                        )
                        self.session.add(relation)
                        count += 1
                        
        return count

    async def _build_uses_relationships(self, symbols: List[Symbol], symbol_index: Dict[str, List[Symbol]]) -> int:
        """Build USES relationships from detailed parser data (DI, variables)."""
        count = 0
        
        for symbol in symbols:
            if not symbol.structured_docs or 'references' not in symbol.structured_docs:
                continue
                
            references = symbol.structured_docs['references']
            processed_targets = set()
            
            for ref in references:
                ref_type = ref.get('type')
                ref_name = ref.get('name')
                
                if not ref_name:
                    continue
                
                # We care about: di_registration, variable_usage, property_access, field_access
                # Note: 'variable_usage' isn't explicitly in CSharpParser yet, but 'di_registration' and 'type_reference' (used as variable type) are.
                # Actually, specialized USES logic is best for:
                # 1. DI Registrations (A uses B)
                # 2. Variable declarations (A uses type B) -> This is also REFERENCES, but can be stronger USES if method body
                
                relation_type = None
                
                if ref_type == 'di_registration':
                    relation_type = RelationTypeEnum.USES
                
                # If we have a valid relation type to create
                if relation_type:
                    # Clean/resolve target
                    clean_name = ref_name.split('<')[0].strip()
                    targets = self._resolve_type(clean_name, symbol_index)
                    
                    for target in targets:
                        if target.id == symbol.id: continue
                        if target.id in processed_targets: continue
                        
                        # Target is guaranteed to exist
                        relation = Relation(
                            from_symbol_id=symbol.id,
                            to_symbol_id=target.id,
                            relation_type=relation_type,
                            relation_metadata={
                                'source': 'parser_extraction',
                                'ref_type': ref_type,
                                'line': ref.get('line')
                            }
                        )
                        self.session.add(relation)
                        count += 1
                        processed_targets.add(target.id)
            
        return count

    async def _build_reference_relationships(self, symbols: List[Symbol], symbol_index: Dict[str, List[Symbol]]) -> int:
        """Build reference relationships (types used in signatures/variables)."""
        count = 0
        
        for symbol in symbols:
            referenced_types = set()
            processed_targets = set()
            
            # 1. Signature-based (Legacy/Fallback)
            if symbol.return_type:
                referenced_types.add(symbol.return_type)
            if symbol.parameters:
                for param in symbol.parameters:
                    if isinstance(param, dict) and param.get('type'):
                        referenced_types.add(param['type'])
            if symbol.kind == SymbolKindEnum.PROPERTY and symbol.return_type:
                referenced_types.add(symbol.return_type)
            
            # 2. Rich Parser Data (New)
            if symbol.structured_docs and 'references' in symbol.structured_docs:
                for ref in symbol.structured_docs['references']:
                    ref_type = ref.get('type')
                    ref_name = ref.get('name')
                    
                    if not ref_name: continue
                    
                    # Map parser reference types to REFERENCES relation
                    # instantiations, type_references, attribute_usage, casts, type_arguments
                    if ref_type in ['instantiation', 'type_reference', 'attribute_usage', 'cast', 'type_argument']:
                        referenced_types.add(ref_name)

            # Process references
            for type_name in referenced_types:
                # Clean up type name (remove arrays [], generics <>)
                clean_name = type_name.split('[')[0].split('<')[0].strip()
                if not clean_name or clean_name in ['void', 'string', 'int', 'bool', 'var', 'object', 'Task', 'List', 'IEnumerable', 'IQueryable']:
                    continue
                    
                targets = self._resolve_type(clean_name, symbol_index)
                for target in targets:
                    if target.id == symbol.id: continue
                    if target.id in processed_targets: continue
                    
                    # Target is guaranteed to exist
                    relation = Relation(
                        from_symbol_id=symbol.id,
                        to_symbol_id=target.id,
                        relation_type=RelationTypeEnum.REFERENCES
                    )
                    self.session.add(relation)
                    count += 1
                    processed_targets.add(target.id)
                    
        return count

    def _resolve_type(self, type_name: str, symbol_index: Dict[str, List[Symbol]]) -> List[Symbol]:
        """Resolve type name to symbols."""
        if type_name in symbol_index:
            return symbol_index[type_name]
        
        # Try simple name if FQN not found
        simple_name = type_name.split('.')[-1]
        if simple_name in symbol_index:
            return symbol_index[simple_name]
            
        return []

    def _extract_base_classes(self, signature: str) -> List[str]:
        """Extract base class names from signature."""
        base_classes = []
        
        # C# style: class Derived : Base
        if ':' in signature:
            parts = signature.split(':')
            if len(parts) > 1:
                base_part = parts[1].split('{')[0].strip()
                base_classes = [b.strip() for b in base_part.split(',')]
        
        # JavaScript/TypeScript style: class Derived extends Base
        elif 'extends' in signature:
            parts = signature.split('extends')
            if len(parts) > 1:
                base_class = parts[1].split('{')[0].split('implements')[0].strip()
                if base_class:
                    base_classes.append(base_class)
        
        # TypeScript implements
        if 'implements' in signature:
            parts = signature.split('implements')
            if len(parts) > 1:
                interfaces = parts[1].split('{')[0].strip()
                base_classes.extend([i.strip() for i in interfaces.split(',')])
        
        return [bc for bc in base_classes if bc]  # Filter empty strings
    
    async def build_import_relationships(
        self,
        repository_id: int,
        imports_map: Dict[int, List[str]]
    ) -> int:
        """
        Build import/export relationships.
        
        Args:
            repository_id: Repository ID
            imports_map: Map of file_id to list of import paths
            
        Returns:
            Number of relationships created
        """
        relationships_created = 0
        
        # Get all files in repository
        result = await self.session.execute(
            select(File).where(File.repository_id == repository_id)
        )
        files = result.scalars().all()
        
        # Build file path index
        file_index: Dict[str, File] = {f.path: f for f in files}
        
        # For each file's imports, try to find matching files
        for file_id, import_paths in imports_map.items():
            for import_path in import_paths:
                # Try to resolve import path to actual file
                # This is simplified - real implementation would handle relative paths, aliases, etc.
                if import_path in file_index:
                    target_file = file_index[import_path]
                    
                    # Get symbols from both files
                    source_symbols = await self.session.execute(
                        select(Symbol).where(Symbol.file_id == file_id)
                    )
                    target_symbols = await self.session.execute(
                        select(Symbol).where(Symbol.file_id == target_file.id)
                    )
                    
                    # Create IMPORTS relationship between exported symbols
                    for source_sym in source_symbols.scalars():
                        for target_sym in target_symbols.scalars():
                            # Simplified: just create import relationship
                            relation = Relation(
                                from_symbol_id=source_sym.id,
                                to_symbol_id=target_sym.id,
                                relation_type=RelationTypeEnum.IMPORTS
                            )
                            self.session.add(relation)
                            relationships_created += 1
        
        await self.session.flush()
        
        logger.info(
            "import_relationships_built",
            repository_id=repository_id,
            relationships_created=relationships_created
        )
        
        return relationships_created

