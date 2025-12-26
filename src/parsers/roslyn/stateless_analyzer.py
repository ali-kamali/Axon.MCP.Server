from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from .process_manager import RoslynProcessManager
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class RoslynSymbol:
    """Symbol information from Roslyn analysis."""
    name: str
    fully_qualified_name: str
    kind: str
    file_path: Optional[str] = None
    position: Optional[int] = None
    line: Optional[int] = None
    character: Optional[int] = None
    
    # Semantic info
    return_type: Optional[str] = None
    base_type: Optional[str] = None
    interfaces: Optional[List[str]] = None
    modifiers: Optional[List[str]] = None
    attributes: Optional[List[str]] = None
    is_definition: bool = True
    
    # Method specific
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
    using_adhoc: bool = False

class StatelessRoslynAnalyzer:
    """
    Stateless wrapper around RoslynProcessManager.
    
    Key Principles:
    - Every project load is explicit and scoped to the request
    - No persistent project state assumptions in Python
    - Uses RoslynProcessManager for robust lifecycle
    """
    
    def __init__(self, analyzer_path: Optional[Path] = None):
        if analyzer_path is None:
            # Default location
            base_dir = Path(__file__).parent.parent.parent.parent / "roslyn_analyzer"
            
            # Define search paths in order of preference
            search_paths = [
                base_dir,
                base_dir / "bin" / "Release" / "net9.0",
                base_dir / "bin" / "Debug" / "net9.0",
                base_dir / "bin" / "Release" / "net8.0",
                base_dir / "bin" / "Debug" / "net8.0"
            ]
            
            # Define filenames to look for
            filenames = [
                "RoslynAnalyzer",      # Linux binary
                "RoslynAnalyzer.dll",  # Cross-platform DLL
                "RoslynAnalyzer.exe"   # Windows executable
            ]
            
            # Try all combinations
            for search_path in search_paths:
                for filename in filenames:
                    candidate = search_path / filename
                    if candidate.exists():
                        analyzer_path = candidate
                        break
                if analyzer_path:
                    break
            
            if not analyzer_path:
                # Fallback to default for logging
                analyzer_path = base_dir / "RoslynAnalyzer.exe"
        
        self.manager = RoslynProcessManager(analyzer_path)
    
    async def analyze_file(
        self,
        code: str,
        file_path: str,
        project_path: Optional[str] = None
    ) -> RoslynResult:
        """
        Analyze a file with explicit project context (if provided).
        """
        if not await self.manager.start():
            return RoslynResult(success=False, error="Failed to start Roslyn process")
        
        request = {
            "command": "analyze_file",
            "file_path": file_path,
            "code": code,
            "project_path": project_path # Optional, analyzer handles null
        }
        
        try:
            response = await self.manager.send_request(request, timeout=60) # Longer timeout for compilation
            
            if not response.get("success"):
                return RoslynResult(
                    success=False, 
                    error=response.get("error"),
                    using_adhoc=response.get("using_adhoc", False)
                )
                
            symbols = []
            for s in response.get("symbols", []):
                symbols.append(self._parse_symbol_dict(s, file_path))
                
            return RoslynResult(
                success=True,
                file_path=file_path,
                symbols=symbols
            )
            
        except Exception as e:
            logger.error("stateless_analysis_failed", error=str(e), file_path=file_path)
            # Process manager handles restarts on timeout/error
            return RoslynResult(success=False, error=str(e))
    
    async def resolve_reference(
        self,
        code: str,
        file_path: str,
        position: int,
        project_path: Optional[str] = None
    ) -> Optional[RoslynSymbol]:
        """Resolve a reference with explicit project context."""
        if not await self.manager.start():
            return None
        
        request = {
            "command": "resolve_reference",
            "file_path": file_path,
            "code": code,
            "position": position,
            "project_path": project_path
        }
        
        try:
            response = await self.manager.send_request(request, timeout=15)
            
            if response.get("success") and response.get("symbol"):
                return self._parse_symbol_dict(response["symbol"], file_path)
            return None
            
        except Exception as e:
            logger.error("stateless_resolution_failed", error=str(e), file_path=file_path)
            return None

    def _parse_symbol_dict(self, data: Dict[str, Any], file_path: str) -> RoslynSymbol:
        """Convert dictionary to RoslynSymbol."""
        return RoslynSymbol(
            name=data.get("name", ""),
            fully_qualified_name=data.get("fully_qualified_name", ""),
            kind=data.get("kind", "Unknown"),
            file_path=file_path,
            position=data.get("location", {}).get("start_line", 0), # Approx
            line=data.get("location", {}).get("start_line", 0),
            character=data.get("location", {}).get("start_character", 0),
            return_type=data.get("return_type"),
            base_type=data.get("base_type"),
            interfaces=data.get("interfaces"),
            modifiers=data.get("modifiers"),
            attributes=data.get("attributes"),
            is_definition=data.get("is_definition", True),
            is_virtual=data.get("is_virtual", False),
            is_override=data.get("is_override", False),
            is_external=data.get("is_external", False),
            assembly_name=data.get("assembly_name"),
            parameters=data.get("parameters"),
            generic_parameters=data.get("generic_parameters")
        )
