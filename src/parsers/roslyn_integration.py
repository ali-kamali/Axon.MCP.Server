"""
Roslyn Integration Module

Provides Python wrapper for the Roslyn C# semantic analyzer.
Delegates to StatelessRoslynAnalyzer for actual analysis, while maintaining
compatibility with the existing stateful API (managing current_project context).
"""
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any, Set
from dataclasses import dataclass
import hashlib
from src.utils.logging_config import get_logger
from src.parsers.roslyn.stateless_analyzer import StatelessRoslynAnalyzer, RoslynSymbol as StatelessSymbol

logger = get_logger(__name__)

# Re-export RoslynSymbol and RoslynResult for compatibility
@dataclass
class RoslynSymbol:
    """Symbol information from Roslyn analysis."""
    name: str
    fully_qualified_name: str
    kind: str
    return_type: Optional[str] = None
    base_type: Optional[str] = None
    interfaces: Optional[List[str]] = None
    is_static: bool = False
    is_abstract: bool = False
    is_virtual: bool = False
    is_override: bool = False
    is_external: bool = False
    assembly_name: Optional[str] = None
    parameters: Optional[List[Dict[str, Any]]] = None
    generic_parameters: Optional[List[Dict[str, Any]]] = None

@dataclass
class RoslynResult:
    """Result from Roslyn analysis."""
    success: bool
    file_path: Optional[str] = None
    symbols: Optional[List[RoslynSymbol]] = None
    error: Optional[str] = None

class RoslynAnalyzer:
    """
    Python wrapper for Roslyn C# semantic analyzer.
    
    Now refactored to use StatelessRoslynAnalyzer backend.
    Maintains 'current_project' state to support legacy API usage.
    """
    
    def __init__(self, analyzer_path: Optional[str] = None):
        """
        Initialize Roslyn analyzer.
        """
        self.analyzer = StatelessRoslynAnalyzer(Path(analyzer_path) if analyzer_path else None)
        self.analyzer_path = self.analyzer.manager.analyzer_path # Expose for info
        
        # State compatibility
        self._current_project: Optional[str] = None
        self._bad_projects: Set[str] = set()
        
        # Cache (legacy support)
        self._cache: Dict[str, RoslynResult] = {}
        self._cache_enabled = False 
        self._failure_count = 0 
        self._max_failures = 5

    def is_available(self) -> bool:
        """Check if analyzer is available."""
        # Check if executable exists
        if not self.analyzer_path.exists():
            return False
            
        # Check process manager state?
        # StatelessAnalyzer manages this implicitly.
        # We can expose specific check if needed.
        return True

    async def stop(self):
        """Stop the analyzer process."""
        await self.analyzer.manager.stop()

    async def open_project(self, project_path: str) -> bool:
        """
        Set the current project context.
        Does not spin up process immediately, just validates and sets state.
        """
        path = Path(project_path).resolve()
        if not path.exists():
            logger.warning("roslyn_project_not_found", path=str(path))
            return False
            
        self._current_project = str(path)
        logger.info("roslyn_context_set_project", project=self._current_project)
        return True

    async def open_solution(self, solution_path: str) -> bool:
        """
        Set the current solution context.
        """
        path = Path(solution_path).resolve()
        if not path.exists():
            logger.warning("roslyn_solution_not_found", path=str(path))
            return False
            
        self._current_project = str(path)
        logger.info("roslyn_context_set_solution", solution=self._current_project)
        return True

    async def analyze_file(
        self,
        code: str,
        file_path: str,
        use_cache: bool = True
    ) -> RoslynResult:
        """
        Analyze C# code using Roslyn.
        Passes current_project to stateless backend.
        """
        if not self.is_available():
            return RoslynResult(success=False, error="Roslyn analyzer not available")

        # Cache check
        if use_cache and self._cache_enabled:
            cache_key = self._get_cache_key(code, file_path)
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Use stateless analyzer
        result = await self.analyzer.analyze_file(
            code=code,
            file_path=file_path,
            project_path=self._current_project
        )
        
        # Convert result types
        if result.success:
            symbols = [self._convert_symbol(s) for s in result.symbols] if result.symbols else []
            roslyn_result = RoslynResult(
                success=True,
                file_path=result.file_path,
                symbols=symbols
            )
        else:
            roslyn_result = RoslynResult(
                success=False,
                error=result.error
            )
            
        # Cache store
        if use_cache and self._cache_enabled and roslyn_result.success:
            cache_key = self._get_cache_key(code, file_path)
            self._cache[cache_key] = roslyn_result
            
        return roslyn_result

    async def resolve_reference(
        self,
        code: str,
        file_path: str,
        position: int
    ) -> Optional[Dict[str, Any]]:
        """Resolve a symbol reference."""
        if not self.is_available():
            return None

        symbol = await self.analyzer.resolve_reference(
            code=code, 
            file_path=file_path, 
            position=position,
            project_path=self._current_project
        )
        
        if symbol:
            return self._convert_symbol_to_dict(symbol)
        return None

    async def analyze_ef_entities(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Analyze EF entities."""
        # Access process manager directly for custom command?
        # StatelessAnalyzer doesn't expose generic send_request yet.
        # But we can access manager.
        if not await self.analyzer.manager.start():
            return None
            
        request = {
            "command": "analyze_ef_entities", 
            "file_path": project_path,
            "project_path": project_path
        }
        
        try:
            response = await self.analyzer.manager.send_request(request, timeout=60)
            if response.get("success"):
                return response
            return None
        except Exception as e:
            logger.error("ef_analysis_failed", error=str(e))
            return None

    def _convert_symbol(self, s: StatelessSymbol) -> RoslynSymbol:
        """Convert StatelessSymbol to local RoslynSymbol."""
        return RoslynSymbol(
            name=s.name,
            fully_qualified_name=s.fully_qualified_name,
            kind=s.kind,
            return_type=s.return_type,
            base_type=s.base_type,
            interfaces=s.interfaces,
            is_static="Static" in (s.modifiers or []),
            is_abstract="Abstract" in (s.modifiers or []),
            is_virtual=s.is_virtual,
            is_override=s.is_override,
            is_external=s.is_external,
            assembly_name=s.assembly_name,
            parameters=s.parameters,
            generic_parameters=s.generic_parameters
        )

    def _convert_symbol_to_dict(self, s: StatelessSymbol) -> Dict[str, Any]:
        """Convert to dictionary format expected by callers."""
        return {
            "name": s.name,
            "fully_qualified_name": s.fully_qualified_name,
            "kind": s.kind,
            "containing_type": None, # TODO: StatelessSymbol might need this
            "containing_namespace": None,
            "locations": [{"file_path": s.file_path, "line": s.line, "column": s.character}]
        }

    def _get_cache_key(self, code: str, file_path: str) -> str:
        content = f"{file_path}:{code}"
        return hashlib.sha256(content.encode()).hexdigest()

    def clear_cache(self):
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        return {"cached_files": len(self._cache), "cache_enabled": self._cache_enabled}
