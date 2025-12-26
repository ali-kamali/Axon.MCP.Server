"""Module identification and analysis utilities for Phase 2."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.enums import LanguageEnum, SymbolKindEnum
from src.database.models import File, Symbol
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ModuleInfo:
    """Information about an identified module."""

    path: str
    name: str
    module_type: str  # "python_package", "typescript_module", "directory", etc.
    is_package: bool
    files: List[str]
    file_count: int
    symbol_count: int
    line_count: int
    languages: Dict[str, int]
    entry_points: List[str]  # Key files like __init__.py, index.ts
    has_tests: bool
    depth: int


class ModuleIdentifier:
    """Identifies and analyzes code modules in a repository."""

    # Files that indicate a module/package
    MODULE_INDICATORS = {
        "python_package": ["__init__.py"],
        "typescript_module": ["package.json", "tsconfig.json", "index.ts", "index.tsx"],
        "javascript_module": ["package.json", "index.js", "index.jsx"],
        "csharp_namespace": [".csproj", "AssemblyInfo.cs"],
        "go_package": ["go.mod", "main.go"],
        "rust_crate": ["Cargo.toml", "lib.rs", "main.rs"],
    }

    # Entry point file patterns
    ENTRY_POINT_FILES = [
        "__init__.py",
        "__main__.py",
        "main.py",
        "app.py",
        "server.py",
        "index.ts",
        "index.tsx",
        "index.js",
        "index.jsx",
        "main.ts",
        "main.js",
        "App.tsx",
        "App.jsx",
    ]

    def __init__(self, session: AsyncSession):
        """Initialize module identifier."""
        self.session = session

    async def identify_modules(
        self, repository_id: int, min_depth: int = 1, max_depth: int = 10
    ) -> List[ModuleInfo]:
        """
        Identify all modules in a repository.

        Args:
            repository_id: Repository ID to analyze
            min_depth: Minimum directory depth to consider as module
            max_depth: Maximum directory depth to analyze

        Returns:
            List of identified modules
        """
        try:
            # Get all files for this repository
            files_result = await self.session.execute(
                select(File)
                .where(File.repository_id == repository_id)
                .order_by(File.path)
            )
            files = files_result.scalars().all()

            if not files:
                logger.warning(f"No files found for repository {repository_id}")
                return []

            # Build directory structure
            directories = self._build_directory_structure(files, max_depth)
            
            logger.debug(
                f"Built directory structure for repository {repository_id}: "
                f"{len(directories)} directories found"
            )

            # Identify modules
            modules = []
            filtered_by_depth = 0
            analyzed_count = 0
            rejected_count = 0
            
            for dir_path, dir_info in directories.items():
                depth = dir_path.count("/") + 1 if dir_path else 0

                if depth < min_depth or depth > max_depth:
                    filtered_by_depth += 1
                    logger.debug(
                        f"Filtered directory by depth: {dir_path} (depth={depth}, "
                        f"min={min_depth}, max={max_depth})"
                    )
                    continue

                analyzed_count += 1
                # Check if this directory is a module
                module_info = await self._analyze_directory(
                    repository_id, dir_path, dir_info, files
                )

                if module_info:
                    modules.append(module_info)
                else:
                    rejected_count += 1

            # Sort by path depth then name
            modules.sort(key=lambda m: (m.depth, m.path))

            logger.info(
                f"Identified {len(modules)} modules in repository {repository_id}: "
                f"total_dirs={len(directories)}, filtered_by_depth={filtered_by_depth}, "
                f"analyzed={analyzed_count}, rejected={rejected_count}, accepted={len(modules)}"
            )
            return modules

        except Exception as e:
            logger.error(f"Error identifying modules: {e}", exc_info=True)
            return []

    def _build_directory_structure(
        self, files: List[File], max_depth: int
    ) -> Dict[str, Dict]:
        """Build directory structure from files."""
        directories: Dict[str, Dict] = {}

        for file in files:
            parts = file.path.split("/")

            # Process each directory level
            for i in range(len(parts) - 1):  # Exclude filename
                if i >= max_depth:
                    break

                dir_path = "/".join(parts[: i + 1])

                if dir_path not in directories:
                    directories[dir_path] = {
                        "files": [],
                        "file_count": 0,
                        "line_count": 0,
                        "languages": {},
                    }

                # Add file to this directory if it's directly in it
                if len(parts) - 1 == i + 1:
                    directories[dir_path]["files"].append(file)
                    directories[dir_path]["file_count"] += 1
                    directories[dir_path]["line_count"] += file.line_count or 0

                    lang = file.language.value.lower() if file.language else "unknown"
                    directories[dir_path]["languages"][lang] = (
                        directories[dir_path]["languages"].get(lang, 0) + 1
                    )

        return directories

    async def _analyze_directory(
        self,
        repository_id: int,
        dir_path: str,
        dir_info: Dict,
        all_files: List[File],
    ) -> Optional[ModuleInfo]:
        """Analyze a directory to determine if it's a module."""
        if dir_info["file_count"] == 0:
            logger.debug(f"Skipping empty directory: {dir_path}")
            return None  # Skip empty directories

        # Get list of filenames in this directory
        filenames = [os.path.basename(f.path) for f in dir_info["files"]]

        # Determine module type
        module_type = "directory"
        is_package = False

        for mod_type, indicators in self.MODULE_INDICATORS.items():
            if any(indicator in filenames for indicator in indicators):
                module_type = mod_type
                is_package = True
                logger.debug(
                    f"Directory {dir_path} identified as {mod_type} package"
                )
                break

        # Find entry point files
        entry_points = [f for f in filenames if f in self.ENTRY_POINT_FILES]

        # Check if has tests subdirectory or test files
        has_tests = any(
            "test" in f.lower() or "spec" in f.lower() for f in filenames
        )

        # Get symbols count for this directory's files
        file_ids = [f.id for f in dir_info["files"]]
        if file_ids:
            symbol_count_result = await self.session.execute(
                select(func.count(Symbol.id)).where(Symbol.file_id.in_(file_ids))
            )
            symbol_count = symbol_count_result.scalar() or 0
        else:
            symbol_count = 0

        # Calculate depth
        depth = dir_path.count("/") + 1 if dir_path else 0

        # Get module name (last part of path)
        module_name = os.path.basename(dir_path) if dir_path else "<root>"

        # Only consider as module if it has reasonable size or is marked as package
        meets_criteria = is_package or dir_info["file_count"] >= 2 or symbol_count >= 5
        
        logger.debug(
            f"Analyzing directory: {dir_path} - "
            f"files={dir_info['file_count']}, symbols={symbol_count}, "
            f"is_package={is_package}, meets_criteria={meets_criteria}"
        )
        
        if meets_criteria:
            logger.debug(f"Accepted as module: {dir_path}")
            return ModuleInfo(
                path=dir_path,
                name=module_name,
                module_type=module_type,
                is_package=is_package,
                files=[f.path for f in dir_info["files"]],
                file_count=dir_info["file_count"],
                symbol_count=symbol_count,
                line_count=dir_info["line_count"],
                languages=dir_info["languages"],
                entry_points=entry_points,
                has_tests=has_tests,
                depth=depth,
            )
        else:
            logger.debug(
                f"Rejected directory: {dir_path} - "
                f"Reason: not a package and file_count ({dir_info['file_count']}) < 2 "
                f"and symbol_count ({symbol_count}) < 5"
            )

        return None

    async def get_module_symbols(
        self, repository_id: int, module_path: str, limit: int = 50
    ) -> List[Dict]:
        """
        Get key symbols from a module.

        Args:
            repository_id: Repository ID
            module_path: Path to module
            limit: Maximum number of symbols to return

        Returns:
            List of symbol dictionaries with key information
        """
        try:
            # Get files in this module (including subdirectories)
            files_result = await self.session.execute(
                select(File)
                .where(
                    File.repository_id == repository_id,
                    File.path.like(f"{module_path}%"),
                )
                .order_by(File.path)
            )
            files = files_result.scalars().all()

            if not files:
                return []

            file_ids = [f.id for f in files]

            # Get symbols, prioritizing entry points and public symbols
            symbols_result = await self.session.execute(
                select(Symbol)
                .where(Symbol.file_id.in_(file_ids))
                .where(
                    Symbol.kind.in_(
                        [
                            SymbolKindEnum.CLASS,
                            SymbolKindEnum.FUNCTION,
                            SymbolKindEnum.METHOD,
                            SymbolKindEnum.INTERFACE,
                        ]
                    )
                )
                .order_by(
                    # Prioritize public symbols
                    Symbol.access_modifier.asc(),
                    # Then by symbol kind (classes first)
                    Symbol.kind.asc(),
                    # Then by name
                    Symbol.name.asc(),
                )
                .limit(limit)
            )
            symbols = symbols_result.scalars().all()

            # Convert to dictionaries
            symbol_list = []
            for symbol in symbols:
                symbol_list.append(
                    {
                        "id": symbol.id,
                        "name": symbol.name,
                        "kind": symbol.kind.value if symbol.kind else "unknown",
                        "signature": symbol.signature or "",
                        "documentation": symbol.documentation or "",
                        "access_modifier": symbol.access_modifier.value
                        if symbol.access_modifier
                        else "public",
                        "file_path": next(
                            (f.path for f in files if f.id == symbol.file_id), ""
                        ),
                    }
                )

            return symbol_list

        except Exception as e:
            logger.error(f"Error getting module symbols: {e}", exc_info=True)
            return []

