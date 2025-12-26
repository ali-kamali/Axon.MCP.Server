"""Pattern detection for design patterns and architectural layers."""

from typing import List, Dict, Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, Relation
from src.config.enums import SymbolKindEnum, RelationTypeEnum, AccessModifierEnum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class Pattern:
    """Represents a detected pattern."""
    
    def __init__(
        self,
        pattern_type: str,
        pattern_name: str,
        confidence: float,
        symbols: List[int],
        description: str,
        evidence: List[str]
    ):
        self.pattern_type = pattern_type
        self.pattern_name = pattern_name
        self.confidence = confidence
        self.symbols = symbols
        self.description = description
        self.evidence = evidence


class PatternDetector:
    """Detects design patterns and architectural patterns in code."""
    
    def __init__(self, session: AsyncSession):
        """
        Initialize pattern detector.
        
        Args:
            session: Database session
        """
        self.session = session
    
    async def detect_patterns(self, repository_id: int) -> List[Pattern]:
        """
        Detect all patterns in repository.
        
        Args:
            repository_id: Repository ID
            
        Returns:
            List of detected patterns
        """
        patterns = []
        
        # Detect design patterns
        patterns.extend(await self._detect_singleton_pattern(repository_id))
        patterns.extend(await self._detect_factory_pattern(repository_id))
        patterns.extend(await self._detect_repository_pattern(repository_id))
        patterns.extend(await self._detect_builder_pattern(repository_id))
        
        # Detect architectural layers
        patterns.extend(await self._detect_architectural_layers(repository_id))
        
        # Detect anti-patterns
        patterns.extend(await self._detect_god_class(repository_id))
        patterns.extend(await self._detect_circular_dependencies(repository_id))
        
        return patterns
    
    async def _detect_singleton_pattern(self, repository_id: int) -> List[Pattern]:
        """Detect Singleton pattern."""
        patterns = []
        
        # Look for classes with:
        # 1. Private static instance field
        # 2. Private constructor
        # 3. Public static GetInstance() method
        
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS
            )
        )
        
        for class_symbol, file in result.all():
            evidence = []
            
            # Get all members of this class
            members_result = await self.session.execute(
                select(Symbol).where(
                    Symbol.parent_name == class_symbol.fully_qualified_name
                )
            )
            members = members_result.scalars().all()
            
            has_private_static_instance = False
            has_private_constructor = False
            has_get_instance = False
            
            for member in members:
                # Check for private static instance field
                if member.kind == SymbolKindEnum.VARIABLE:
                    if member.access_modifier == AccessModifierEnum.PRIVATE:
                        if 'instance' in member.name.lower():
                            has_private_static_instance = True
                            evidence.append(f"Private static instance field: {member.name}")
                
                # Check for private constructor
                if member.kind == SymbolKindEnum.METHOD:
                    if member.name == class_symbol.name:  # Constructor
                        if member.access_modifier == AccessModifierEnum.PRIVATE:
                            has_private_constructor = True
                            evidence.append(f"Private constructor")
                    
                    # Check for GetInstance method
                    if 'getinstance' in member.name.lower() or 'instance' in member.name.lower():
                        if member.access_modifier == AccessModifierEnum.PUBLIC:
                            has_get_instance = True
                            evidence.append(f"Public instance accessor: {member.name}")
            
            # If at least 2 of 3 criteria met, likely singleton
            criteria_met = sum([
                has_private_static_instance,
                has_private_constructor,
                has_get_instance
            ])
            
            if criteria_met >= 2:
                confidence = criteria_met / 3.0
                patterns.append(Pattern(
                    pattern_type='design_pattern',
                    pattern_name='Singleton',
                    confidence=confidence,
                    symbols=[class_symbol.id],
                    description=f'{class_symbol.name} implements Singleton pattern',
                    evidence=evidence
                ))
        
        return patterns
    
    async def _detect_factory_pattern(self, repository_id: int) -> List[Pattern]:
        """Detect Factory pattern."""
        patterns = []
        
        # Look for classes with:
        # 1. Name contains "Factory"
        # 2. Has Create/Make/Build methods
        
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS,
                Symbol.name.ilike('%Factory%')
            )
        )
        
        for class_symbol, file in result.all():
            evidence = [f"Class name contains 'Factory': {class_symbol.name}"]
            
            # Get methods
            methods_result = await self.session.execute(
                select(Symbol).where(
                    Symbol.parent_name == class_symbol.fully_qualified_name,
                    Symbol.kind == SymbolKindEnum.METHOD
                )
            )
            
            has_factory_method = False
            for method in methods_result.scalars():
                if any(keyword in method.name.lower() for keyword in ['create', 'make', 'build', 'get']):
                    has_factory_method = True
                    evidence.append(f"Factory method: {method.name}")
            
            if has_factory_method:
                patterns.append(Pattern(
                    pattern_type='design_pattern',
                    pattern_name='Factory',
                    confidence=0.8,
                    symbols=[class_symbol.id],
                    description=f'{class_symbol.name} implements Factory pattern',
                    evidence=evidence
                ))
        
        return patterns
    
    async def _detect_repository_pattern(self, repository_id: int) -> List[Pattern]:
        """Detect Repository pattern."""
        patterns = []
        
        # Look for classes/interfaces with:
        # 1. Name contains "Repository"
        # 2. Has CRUD methods (Add, Get, Update, Delete, Find)
        
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE]),
                Symbol.name.ilike('%Repository%')
            )
        )
        
        for symbol, file in result.all():
            evidence = [f"Name contains 'Repository': {symbol.name}"]
            
            # Get methods
            methods_result = await self.session.execute(
                select(Symbol).where(
                    Symbol.parent_name == symbol.fully_qualified_name,
                    Symbol.kind == SymbolKindEnum.METHOD
                )
            )
            
            crud_methods = {'add': False, 'get': False, 'update': False, 'delete': False, 'find': False}
            
            for method in methods_result.scalars():
                method_lower = method.name.lower()
                for crud_op in crud_methods.keys():
                    if crud_op in method_lower:
                        crud_methods[crud_op] = True
                        evidence.append(f"CRUD method: {method.name}")
            
            # If has at least 3 CRUD operations
            if sum(crud_methods.values()) >= 3:
                confidence = sum(crud_methods.values()) / 5.0
                patterns.append(Pattern(
                    pattern_type='design_pattern',
                    pattern_name='Repository',
                    confidence=confidence,
                    symbols=[symbol.id],
                    description=f'{symbol.name} implements Repository pattern',
                    evidence=evidence
                ))
        
        return patterns
    
    async def _detect_builder_pattern(self, repository_id: int) -> List[Pattern]:
        """Detect Builder pattern."""
        patterns = []
        
        # Look for classes with:
        # 1. Name contains "Builder"
        # 2. Has fluent methods (return 'this' or builder type)
        # 3. Has Build() method
        
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS,
                Symbol.name.ilike('%Builder%')
            )
        )
        
        for class_symbol, file in result.all():
            evidence = [f"Class name contains 'Builder': {class_symbol.name}"]
            
            # Get methods
            methods_result = await self.session.execute(
                select(Symbol).where(
                    Symbol.parent_name == class_symbol.fully_qualified_name,
                    Symbol.kind == SymbolKindEnum.METHOD
                )
            )
            
            has_build_method = False
            fluent_methods = 0
            
            for method in methods_result.scalars():
                if method.name.lower() == 'build':
                    has_build_method = True
                    evidence.append("Has Build() method")
                
                # Check if method returns same type (fluent interface)
                if method.return_type and class_symbol.name in method.return_type:
                    fluent_methods += 1
            
            if has_build_method and fluent_methods > 0:
                confidence = min(0.9, 0.5 + (fluent_methods * 0.1))
                evidence.append(f"Has {fluent_methods} fluent methods")
                
                patterns.append(Pattern(
                    pattern_type='design_pattern',
                    pattern_name='Builder',
                    confidence=confidence,
                    symbols=[class_symbol.id],
                    description=f'{class_symbol.name} implements Builder pattern',
                    evidence=evidence
                ))
        
        return patterns
    
    async def _detect_architectural_layers(self, repository_id: int) -> List[Pattern]:
        """Detect architectural layers (Controller, Service, Repository)."""
        patterns = []
        
        # Detect controllers
        controllers_result = await self.session.execute(
            select(func.count(Symbol.id))
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS,
                Symbol.name.ilike('%Controller%')
            )
        )
        controller_count = controllers_result.scalar()
        
        if controller_count > 0:
            patterns.append(Pattern(
                pattern_type='architectural_layer',
                pattern_name='Controller Layer',
                confidence=1.0,
                symbols=[],
                description=f'Detected {controller_count} controller classes',
                evidence=[f'{controller_count} controllers found']
            ))
        
        # Detect services
        services_result = await self.session.execute(
            select(func.count(Symbol.id))
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS,
                Symbol.name.ilike('%Service%')
            )
        )
        service_count = services_result.scalar()
        
        if service_count > 0:
            patterns.append(Pattern(
                pattern_type='architectural_layer',
                pattern_name='Service Layer',
                confidence=1.0,
                symbols=[],
                description=f'Detected {service_count} service classes',
                evidence=[f'{service_count} services found']
            ))
        
        # Detect repositories
        repos_result = await self.session.execute(
            select(func.count(Symbol.id))
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE]),
                Symbol.name.ilike('%Repository%')
            )
        )
        repo_count = repos_result.scalar()
        
        if repo_count > 0:
            patterns.append(Pattern(
                pattern_type='architectural_layer',
                pattern_name='Repository Layer',
                confidence=1.0,
                symbols=[],
                description=f'Detected {repo_count} repository classes/interfaces',
                evidence=[f'{repo_count} repositories found']
            ))
        
        return patterns
    
    async def _detect_god_class(self, repository_id: int) -> List[Pattern]:
        """Detect God Class anti-pattern (classes with too many methods)."""
        patterns = []
        
        # Find classes with > 30 methods
        result = await self.session.execute(
            select(Symbol, File, func.count(Symbol.id).label('method_count'))
            .join(File, Symbol.file_id == File.id)
            .outerjoin(
                Symbol.__table__.alias('methods'),
                Symbol.fully_qualified_name == Symbol.__table__.alias('methods').c.parent_name
            )
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS
            )
            .group_by(Symbol.id, File.id)
            .having(func.count(Symbol.id) > 30)
        )
        
        for class_symbol, file, method_count in result.all():
            if method_count and method_count > 30:
                confidence = min(1.0, method_count / 50.0)
                
                patterns.append(Pattern(
                    pattern_type='anti_pattern',
                    pattern_name='God Class',
                    confidence=confidence,
                    symbols=[class_symbol.id],
                    description=f'{class_symbol.name} has {method_count} methods (God Class)',
                    evidence=[
                        f'Class has {method_count} methods',
                        'Consider splitting into smaller classes'
                    ]
                ))
        
        return patterns
    
    async def _detect_circular_dependencies(self, repository_id: int) -> List[Pattern]:
        """Detect circular dependencies between files/symbols."""
        patterns = []
        
        # This requires graph traversal of relationships
        # Simplified version: Look for bidirectional IMPORTS relationships
        
        result = await self.session.execute(
            select(Relation)
            .join(Symbol, Relation.from_symbol_id == Symbol.id)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Relation.relation_type.in_([RelationTypeEnum.IMPORTS, RelationTypeEnum.USES])
            )
        )
        
        relations = result.scalars().all()
        
        # Build adjacency map
        adjacency = {}
        for rel in relations:
            if rel.from_symbol_id not in adjacency:
                adjacency[rel.from_symbol_id] = []
            adjacency[rel.from_symbol_id].append(rel.to_symbol_id)
        
        # Check for cycles (A -> B and B -> A)
        cycles_found = set()
        for from_id, to_ids in adjacency.items():
            for to_id in to_ids:
                # Check if reverse edge exists
                if to_id in adjacency and from_id in adjacency[to_id]:
                    cycle_key = tuple(sorted([from_id, to_id]))
                    if cycle_key not in cycles_found:
                        cycles_found.add(cycle_key)
                        
                        patterns.append(Pattern(
                            pattern_type='anti_pattern',
                            pattern_name='Circular Dependency',
                            confidence=1.0,
                            symbols=list(cycle_key),
                            description='Circular dependency detected between symbols',
                            evidence=['Bidirectional dependency found']
                        ))
        
        return patterns
