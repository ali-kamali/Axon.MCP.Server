"""File exclusion rules for filtering unwanted files during sync."""

import re
from pathlib import Path
from typing import List, Set
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class FileExclusionRules:
    """Manages file exclusion patterns."""
    
    # Default exclusion patterns
    DEFAULT_EXCLUSIONS = [
        # Build artifacts
        "**/node_modules/**",
        "**/bin/**",
        "**/obj/**",
        "**/dist/**",
        "**/build/**",
        "**/out/**",
        "**/.next/**",
        "**/.nuxt/**",
        "**/target/**",
        
        # Generated code
        "**/*.g.cs",
        "**/*.Designer.cs",
        "**/*.designer.cs",
        "**/*.generated.cs",
        "**/*.generated.js",
        "**/*.generated.ts",
        
        # Minified code
        "**/*.min.js",
        "**/*.min.css",
        "**/*.bundle.js",
        
        # Package manager
        "**/packages/**",
        "**/vendor/**",
        "**/.pnpm/**",
        "**/bower_components/**",
        "**/vendor*.js",
        "**/vendor*.css",
        
        # IDE and system
        "**/.vs/**",
        "**/.vscode/**",
        "**/.idea/**",
        "**/__pycache__/**",
        "**/.git/**",
        
        # Test coverage
        "**/coverage/**",
        "**/htmlcov/**",
        "**/.coverage/**",
        "**/.nyc_output/**",
        
        # Temporary files
        "**/*.tmp",
        "**/*.temp",
        "**/*.swp",
        "**/*.bak",
        
        # Dependencies lock files that are auto-generated
        "**/package-lock.json",
        "**/yarn.lock",
        "**/pnpm-lock.yaml",
    ]
    
    # Test file patterns (optional separate indexing)
    TEST_PATTERNS = [
        "**/test/**",
        "**/tests/**",
        "**/__tests__/**",
        "**/spec/**",
        "**/specs/**",
        "**/*.test.js",
        "**/*.test.ts",
        "**/*.spec.js",
        "**/*.spec.ts",
        "**/*.test.tsx",
        "**/*.spec.tsx",
        "**/Test*.cs",
        "**/*Test.cs",
        "**/*Tests.cs",
    ]
    
    def __init__(self, custom_exclusions: List[str] = None, exclude_tests: bool = False):
        """
        Initialize exclusion rules.
        
        Args:
            custom_exclusions: Additional exclusion patterns
            exclude_tests: Whether to exclude test files
        """
        self.exclusions = self.DEFAULT_EXCLUSIONS.copy()
        
        if custom_exclusions:
            self.exclusions.extend(custom_exclusions)
        
        if exclude_tests:
            self.exclusions.extend(self.TEST_PATTERNS)
        
        # Compile patterns for efficiency
        self._compiled_patterns = [self._glob_to_regex(p) for p in self.exclusions]
    
    def should_exclude(self, file_path: str) -> bool:
        """
        Check if file should be excluded.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file should be excluded, False otherwise
        """
        # Normalize path separators
        normalized_path = file_path.replace('\\', '/')
        
        # Check against all patterns
        for pattern in self._compiled_patterns:
            if pattern.match(normalized_path):
                logger.debug("file_excluded", path=file_path, pattern=pattern.pattern)
                return True
        
        return False
    
    def filter_files(self, file_paths: List[str]) -> List[str]:
        """
        Filter a list of files, removing excluded ones.
        
        Args:
            file_paths: List of file paths
            
        Returns:
            Filtered list
        """
        return [f for f in file_paths if not self.should_exclude(f)]
    
    def is_test_file(self, file_path: str) -> bool:
        """
        Check if file is a test file.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if test file, False otherwise
        """
        normalized_path = file_path.replace('\\', '/')
        
        for pattern in self.TEST_PATTERNS:
            regex = self._glob_to_regex(pattern)
            if regex.match(normalized_path):
                return True
        
        return False
    
    def is_generated_file(self, file_path: str) -> bool:
        """
        Check if file is generated code.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if generated, False otherwise
        """
        generated_patterns = [
            r'\.g\.cs$',
            r'\.Designer\.cs$',
            r'\.designer\.cs$',
            r'\.generated\.(cs|js|ts)$',
            r'\.min\.(js|css)$',
            r'\.bundle\.js$',
        ]
        
        for pattern in generated_patterns:
            if re.search(pattern, file_path, re.IGNORECASE):
                return True
        
        return False
    
    def _glob_to_regex(self, pattern: str) -> re.Pattern:
        """
        Convert glob pattern to regex.
        
        Args:
            pattern: Glob pattern
            
        Returns:
            Compiled regex pattern
        """
        # Convert glob to regex
        # ** matches any directory depth
        # * matches any characters except /
        # ? matches single character
        
        regex = pattern
        
        # Escape special regex characters except *, ?, and **
        for char in r'\.+^$[]{}()':
            regex = regex.replace(char, '\\' + char)
        
        # Replace ** with special marker
        regex = regex.replace('**', '<DOUBLE_STAR>')
        
        # Replace * with regex (match anything except /)
        regex = regex.replace('*', '[^/]*')
        
        # Replace <DOUBLE_STAR> with regex (match any depth)
        regex = regex.replace('<DOUBLE_STAR>', '.*')
        
        # Replace ? with single character
        regex = regex.replace('?', '.')
        
        # Ensure pattern matches from start
        if not regex.startswith('.*'):
            regex = '.*' + regex
        
        # Compile and return
        return re.compile(regex)
    
    @classmethod
    def parse_gitignore(cls, gitignore_path: Path) -> List[str]:
        """
        Parse .gitignore file and extract patterns.
        
        Args:
            gitignore_path: Path to .gitignore file
            
        Returns:
            List of exclusion patterns
        """
        patterns = []
        
        if not gitignore_path.exists():
            return patterns
        
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Remove leading / (means root of repo)
                    if line.startswith('/'):
                        line = line[1:]
                    
                    # Convert to our pattern format
                    if not line.startswith('**/'):
                        line = '**/' + line
                    
                    patterns.append(line)
            
            logger.info("gitignore_parsed", path=str(gitignore_path), patterns=len(patterns))
        except Exception as e:
            logger.error("gitignore_parse_failed", path=str(gitignore_path), error=str(e))
        
        return patterns

