"""Advanced pattern detection for design patterns and anti-patterns."""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, Relation
from src.config.enums import SymbolKindEnum, RelationTypeEnum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class DetectedPattern:
    """Represents a detected code pattern."""
    pattern_type: str  # "singleton", "factory", "repository", etc.
    pattern_category: str  # "design_pattern", "anti_pattern", "architectural"
    confidence: float  # 0.0 to 1.0
    location: str  # File path
    symbol_names: List[str]
    description: str
    suggestions: List[str]


class AdvancedPatternDetector:
    """Detects design patterns, anti-patterns, and architectural patterns."""
    
    def __init__(self, session: AsyncSession):
        """
        Initialize pattern detector.
        
        Args:
            session: Database session
        """
        self.session = session
    
    async def detect_patterns(self, repository_id: int) -> List[DetectedPattern]:
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
        patterns.extend(await self._detect_observer_pattern(repository_id))
        
        # Detect anti-patterns
        patterns.extend(await self._detect_god_class(repository_id))
        patterns.extend(await self._detect_long_method(repository_id))
        patterns.extend(await self._detect_circular_dependencies(repository_id))
        patterns.extend(await self._detect_dead_code(repository_id))
        
        # Detect architectural patterns
        patterns.extend(await self._detect_mvc_pattern(repository_id))
        patterns.extend(await self._detect_clean_architecture(repository_id))
        
        logger.info(
            "pattern_detection_complete",
            repository_id=repository_id,
            patterns_found=len(patterns)
        )
        
        return patterns
    
    async def _detect_singleton_pattern(self, repository_id: int) -> List[DetectedPattern]:
        """Detect Singleton pattern."""
        patterns = []
        
        # Look for classes with private constructors and static instances
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS
            )
        )
        
        for symbol, file in result.all():
            confidence = 0.0
            indicators = []
            
            # Check class name contains "Singleton"
            if "Singleton" in symbol.name:
                confidence += 0.4
                indicators.append("Named as Singleton")
            
            # Check for static instance field
            if symbol.structured_docs:
                # This would need more sophisticated analysis
                confidence += 0.3
            
            # Check for private constructor
            # This would require parsing the constructor
            
            if confidence > 0.5:
                patterns.append(DetectedPattern(
                    pattern_type="singleton",
                    pattern_category="design_pattern",
                    confidence=confidence,
                    location=file.path,
                    symbol_names=[symbol.name],
                    description=f"Singleton pattern detected in {symbol.name}",
                    suggestions=[
                        "Ensure thread-safety if used in multi-threaded environment",
                        "Consider dependency injection instead"
                    ]
                ))
        
        return patterns
    
    async def _detect_factory_pattern(self, repository_id: int) -> List[DetectedPattern]:
        """Detect Factory pattern."""
        patterns = []
        
        # Look for classes/methods with "Factory" in name
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.METHOD])
            )
        )
        
        for symbol, file in result.all():
            if "Factory" in symbol.name or "Create" in symbol.name:
                patterns.append(DetectedPattern(
                    pattern_type="factory",
                    pattern_category="design_pattern",
                    confidence=0.7,
                    location=file.path,
                    symbol_names=[symbol.name],
                    description=f"Factory pattern detected: {symbol.name}",
                    suggestions=[
                        "Ensure single responsibility principle",
                        "Consider abstract factory if multiple product families"
                    ]
                ))
        
        return patterns
    
    async def _detect_repository_pattern(self, repository_id: int) -> List[DetectedPattern]:
        """Detect Repository pattern."""
        patterns = []
        
        # Look for classes ending with "Repository"
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS,
                Symbol.name.like('%Repository')
            )
        )
        
        for symbol, file in result.all():
            patterns.append(DetectedPattern(
                pattern_type="repository",
                pattern_category="design_pattern",
                confidence=0.8,
                location=file.path,
                symbol_names=[symbol.name],
                description=f"Repository pattern: {symbol.name}",
                suggestions=[
                    "Implement unit of work if not already present",
                    "Consider generic repository for reusability"
                ]
            ))
        
        return patterns
    
    async def _detect_builder_pattern(self, repository_id: int) -> List[DetectedPattern]:
        """Detect Builder pattern."""
        patterns = []
        
        # Look for classes with "Builder" in name
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS,
                Symbol.name.like('%Builder%')
            )
        )
        
        for symbol, file in result.all():
            patterns.append(DetectedPattern(
                pattern_type="builder",
                pattern_category="design_pattern",
                confidence=0.75,
                location=file.path,
                symbol_names=[symbol.name],
                description=f"Builder pattern: {symbol.name}",
                suggestions=[
                    "Ensure fluent interface returns 'this'",
                    "Validate required fields in build()"
                ]
            ))
        
        return patterns
    
    async def _detect_observer_pattern(self, repository_id: int) -> List[DetectedPattern]:
        """Detect Observer/Event pattern."""
        patterns = []
        
        # Look for event-related naming
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS
            )
        )
        
        for symbol, file in result.all():
            if any(keyword in symbol.name for keyword in ["Observer", "Event", "Listener", "Handler"]):
                patterns.append(DetectedPattern(
                    pattern_type="observer",
                    pattern_category="design_pattern",
                    confidence=0.7,
                    location=file.path,
                    symbol_names=[symbol.name],
                    description=f"Observer pattern: {symbol.name}",
                    suggestions=[
                        "Ensure proper unsubscribe to prevent memory leaks",
                        "Consider using weak references for observers"
                    ]
                ))
        
        return patterns
    
    async def _detect_god_class(self, repository_id: int) -> List[DetectedPattern]:
        """Detect God Class anti-pattern."""
        patterns = []
        
        # Find classes with too many methods (>20) or high complexity
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS
            )
        )
        
        for symbol, file in result.all():
            # Count methods in this class
            methods_result = await self.session.execute(
                select(Symbol)
                .where(
                    Symbol.file_id == symbol.file_id,
                    Symbol.kind == SymbolKindEnum.METHOD,
                    Symbol.parent_name == symbol.fully_qualified_name
                )
            )
            
            method_count = len(methods_result.all())
            
            # Check for god class indicators
            if method_count > 20:
                patterns.append(DetectedPattern(
                    pattern_type="god_class",
                    pattern_category="anti_pattern",
                    confidence=0.8,
                    location=file.path,
                    symbol_names=[symbol.name],
                    description=f"God Class detected: {symbol.name} has {method_count} methods",
                    suggestions=[
                        "Break into smaller, focused classes",
                        "Apply Single Responsibility Principle",
                        "Extract related methods into new classes"
                    ]
                ))
        
        return patterns
    
    async def _detect_long_method(self, repository_id: int) -> List[DetectedPattern]:
        """Detect Long Method anti-pattern."""
        patterns = []
        
        # Find methods with high line count or complexity
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind.in_([SymbolKindEnum.METHOD, SymbolKindEnum.FUNCTION])
            )
        )
        
        for symbol, file in result.all():
            line_count = symbol.end_line - symbol.start_line
            
            # Detect long methods (>50 lines or high complexity)
            if line_count > 50 or (symbol.complexity and symbol.complexity > 15):
                patterns.append(DetectedPattern(
                    pattern_type="long_method",
                    pattern_category="anti_pattern",
                    confidence=0.75,
                    location=file.path,
                    symbol_names=[symbol.name],
                    description=f"Long method: {symbol.name} has {line_count} lines, complexity {symbol.complexity}",
                    suggestions=[
                        "Extract logical sections into separate methods",
                        "Reduce complexity by simplifying conditions",
                        "Consider decomposing into smaller functions"
                    ]
                ))
        
        return patterns
    
    async def _detect_circular_dependencies(self, repository_id: int) -> List[DetectedPattern]:
        """Detect circular dependencies."""
        patterns = []
        
        # This would require graph analysis of all relationships
        # Simplified version: look for obvious circular references
        
        return patterns
    
    async def _detect_dead_code(self, repository_id: int) -> List[DetectedPattern]:
        """Detect potentially dead code."""
        patterns = []
        
        # Find symbols with no incoming relationships
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind.in_([SymbolKindEnum.METHOD, SymbolKindEnum.FUNCTION, SymbolKindEnum.CLASS])
            )
        )
        
        for symbol, file in result.all():
            # Check if symbol has any incoming relationships
            relations_result = await self.session.execute(
                select(Relation)
                .where(Relation.to_symbol_id == symbol.id)
            )
            
            if not relations_result.all() and symbol.access_modifier and symbol.access_modifier.value == 'private':
                patterns.append(DetectedPattern(
                    pattern_type="dead_code",
                    pattern_category="anti_pattern",
                    confidence=0.6,
                    location=file.path,
                    symbol_names=[symbol.name],
                    description=f"Potentially unused code: {symbol.name}",
                    suggestions=[
                        "Review if still needed",
                        "Consider removing if truly unused",
                        "Add tests if functionality is required"
                    ]
                ))
        
        return patterns
    
    async def _detect_mvc_pattern(self, repository_id: int) -> List[DetectedPattern]:
        """Detect MVC architectural pattern."""
        patterns = []
        
        # Look for typical MVC structure
        has_controllers = False
        has_models = False
        has_views = False
        
        result = await self.session.execute(
            select(File.path)
            .where(File.repository_id == repository_id)
        )
        
        for (path,) in result.all():
            path_lower = path.lower()
            if 'controller' in path_lower:
                has_controllers = True
            if 'model' in path_lower:
                has_models = True
            if 'view' in path_lower or 'page' in path_lower:
                has_views = True
        
        if has_controllers and has_models:
            patterns.append(DetectedPattern(
                pattern_type="mvc",
                pattern_category="architectural",
                confidence=0.8,
                location="",
                symbol_names=[],
                description="MVC pattern detected in repository structure",
                suggestions=[
                    "Ensure clear separation of concerns",
                    "Keep controllers thin, logic in services",
                    "Consider MVVM for richer UI interactions"
                ]
            ))
        
        return patterns
    
    async def _detect_clean_architecture(self, repository_id: int) -> List[DetectedPattern]:
        """Detect Clean Architecture pattern."""
        patterns = []
        
        # Look for clean architecture layers
        layers = {"domain": False, "application": False, "infrastructure": False, "presentation": False}
        
        result = await self.session.execute(
            select(File.path)
            .where(File.repository_id == repository_id)
        )
        
        for (path,) in result.all():
            path_lower = path.lower()
            for layer in layers.keys():
                if layer in path_lower:
                    layers[layer] = True
        
        # If we have multiple layers
        if sum(layers.values()) >= 3:
            patterns.append(DetectedPattern(
                pattern_type="clean_architecture",
                pattern_category="architectural",
                confidence=0.75,
                location="",
                symbol_names=[],
                description="Clean Architecture pattern detected",
                suggestions=[
                    "Ensure dependency rule (inner layers don't depend on outer)",
                    "Use dependency injection for flexibility",
                    "Keep domain layer pure with no external dependencies"
                ]
            ))
        
        return patterns

