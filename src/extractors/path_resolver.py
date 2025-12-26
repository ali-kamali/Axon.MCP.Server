"""Path resolution utilities for imports."""

from pathlib import Path
from typing import Optional, Dict, List
import json

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class PathResolver:
    """Resolves import paths to actual file paths."""
    
    def __init__(self, repository_root: Path):
        """
        Initialize path resolver.
        
        Args:
            repository_root: Root directory of repository
        """
        self.repository_root = repository_root
        self.path_aliases = self._load_path_aliases()
    
    def _load_path_aliases(self) -> Dict[str, str]:
        """Load path aliases from tsconfig.json or similar."""
        aliases = {}
        
        # Try to load tsconfig.json for TypeScript path aliases
        tsconfig_path = self.repository_root / "tsconfig.json"
        if tsconfig_path.exists():
            try:
                with open(tsconfig_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                compiler_options = config.get('compilerOptions', {})
                paths = compiler_options.get('paths', {})
                base_url = compiler_options.get('baseUrl', '.')
                
                # Convert TypeScript paths to aliases
                for alias, targets in paths.items():
                    # Remove /* from alias if present
                    clean_alias = alias.replace('/*', '')
                    if targets:
                        # Take first target
                        target = targets[0].replace('/*', '')
                        # Resolve relative to baseUrl
                        resolved = Path(base_url) / target
                        aliases[clean_alias] = str(resolved)
                        
            except Exception as e:
                logger.debug(f"Failed to load tsconfig.json: {str(e)}")
        
        # Try to load package.json for module aliases
        package_json = self.repository_root / "package.json"
        if package_json.exists():
            try:
                with open(package_json, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Check for common alias configurations
                if '_moduleAliases' in config:
                    aliases.update(config['_moduleAliases'])
                    
            except Exception as e:
                logger.debug(f"Failed to load package.json: {str(e)}")
        
        return aliases
    
    def resolve_import_path(
        self,
        import_path: str,
        importing_file: Path,
        language: str
    ) -> Optional[Path]:
        """
        Resolve an import path to actual file path.
        
        Args:
            import_path: Import string (e.g., "./utils/helper", "@/components/Button")
            importing_file: File that contains the import
            language: Language (for resolution strategy)
            
        Returns:
            Resolved file path or None if not resolvable
        """
        # Handle relative imports
        if import_path.startswith('.'):
            return self._resolve_relative_path(import_path, importing_file, language)
        
        # Handle aliased imports (e.g., @/components)
        if import_path.startswith('@/') or import_path.startswith('@'):
            return self._resolve_aliased_path(import_path, language)
        
        # Handle absolute/package imports
        return self._resolve_package_path(import_path, language)
    
    def _resolve_relative_path(
        self,
        import_path: str,
        importing_file: Path,
        language: str
    ) -> Optional[Path]:
        """Resolve relative import path."""
        # Get directory of importing file
        import_dir = importing_file.parent
        
        # Resolve relative path
        resolved = (import_dir / import_path).resolve()
        
        # Try common extensions based on language
        extensions = self._get_extensions_for_language(language)
        
        for ext in extensions:
            candidate = resolved.with_suffix(ext)
            if candidate.exists() and candidate.is_relative_to(self.repository_root):
                # Return path relative to repository root
                return candidate.relative_to(self.repository_root)
            
            # Also try /index.ext pattern
            index_candidate = resolved / f"index{ext}"
            if index_candidate.exists() and index_candidate.is_relative_to(self.repository_root):
                return index_candidate.relative_to(self.repository_root)
        
        return None
    
    def _resolve_aliased_path(
        self,
        import_path: str,
        language: str
    ) -> Optional[Path]:
        """Resolve aliased import path (e.g., @/components)."""
        # Common alias patterns
        if import_path.startswith('@/'):
            # @/ usually maps to src/
            path_without_alias = import_path[2:]  # Remove @/
            
            # Check if we have a specific alias mapping
            if '@' in self.path_aliases:
                base = self.path_aliases['@']
            else:
                # Try common patterns
                for base_dir in ['src', '.', 'app']:
                    base = base_dir
                    resolved = self.repository_root / base / path_without_alias
                    
                    extensions = self._get_extensions_for_language(language)
                    for ext in extensions:
                        candidate = resolved.with_suffix(ext)
                        if candidate.exists():
                            return candidate.relative_to(self.repository_root)
                    
                    # Try index file
                    for ext in extensions:
                        index_candidate = resolved / f"index{ext}"
                        if index_candidate.exists():
                            return index_candidate.relative_to(self.repository_root)
        
        # Check other aliases
        for alias, target in self.path_aliases.items():
            if import_path.startswith(alias):
                path_without_alias = import_path[len(alias):].lstrip('/')
                resolved = self.repository_root / target / path_without_alias
                
                extensions = self._get_extensions_for_language(language)
                for ext in extensions:
                    candidate = resolved.with_suffix(ext)
                    if candidate.exists():
                        return candidate.relative_to(self.repository_root)
        
        return None
    
    def _resolve_package_path(
        self,
        import_path: str,
        language: str
    ) -> Optional[Path]:
        """
        Resolve package import path.
        
        For internal packages, tries to find in src/ or other common locations.
        For external packages (node_modules, nuget), returns None.
        """
        # Check if it's an external package (contains no path separators)
        if '/' not in import_path:
            # Likely external package (react, lodash, etc.)
            return None
        
        # Try to resolve as internal package
        for base_dir in ['src', 'lib', 'app', 'packages']:
            resolved = self.repository_root / base_dir / import_path
            
            extensions = self._get_extensions_for_language(language)
            for ext in extensions:
                candidate = resolved.with_suffix(ext)
                if candidate.exists():
                    return candidate.relative_to(self.repository_root)
        
        return None
    
    def _get_extensions_for_language(self, language: str) -> List[str]:
        """Get possible file extensions for language."""
        extensions_map = {
            'javascript': ['.js', '.jsx', '.mjs'],
            'typescript': ['.ts', '.tsx', '.d.ts'],
            'csharp': ['.cs'],
            'vue': ['.vue'],
            'python': ['.py'],
            'markdown': ['.md', '.markdown']
        }
        
        return extensions_map.get(language.lower(), [''])

