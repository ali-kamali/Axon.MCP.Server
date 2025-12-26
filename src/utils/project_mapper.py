"""Project mapping utilities for generating hierarchical project views."""

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.enums import LanguageEnum
from src.database.models import File, Repository, Symbol
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class DirectoryNode:
    """Represents a directory node in the project tree."""

    name: str
    path: str
    depth: int
    file_count: int = 0
    line_count: int = 0
    languages: Dict[str, int] = None
    children: List["DirectoryNode"] = None
    purpose: Optional[str] = None
    dominant_files: List[str] = None

    def __post_init__(self):
        if self.languages is None:
            self.languages = {}
        if self.children is None:
            self.children = []
        if self.dominant_files is None:
            self.dominant_files = []


class ProjectMapper:
    """Generates hierarchical project maps with annotations."""

    # Directory naming patterns and their purposes
    DIRECTORY_PURPOSES = {
        "api": "API Endpoints & Controllers",
        "apis": "API Endpoints & Controllers",
        "controllers": "API Controllers",
        "models": "Data Models & Entities",
        "database": "Database Layer",
        "db": "Database Layer",
        "schemas": "Database Schemas",
        "migrations": "Database Migrations",
        "services": "Business Logic Services",
        "service": "Business Logic Services",
        "utils": "Utility Functions",
        "utilities": "Utility Functions",
        "helpers": "Helper Functions",
        "lib": "Shared Libraries",
        "libs": "Shared Libraries",
        "core": "Core Framework",
        "common": "Common/Shared Code",
        "shared": "Common/Shared Code",
        "components": "UI Components",
        "views": "View Templates",
        "pages": "Page Components",
        "routes": "Routing Logic",
        "router": "Routing Logic",
        "middleware": "Middleware",
        "middlewares": "Middleware",
        "auth": "Authentication & Authorization",
        "authentication": "Authentication & Authorization",
        "security": "Security Layer",
        "config": "Configuration",
        "configuration": "Configuration",
        "settings": "Settings & Config",
        "tests": "Test Suite",
        "test": "Test Suite",
        "__tests__": "Test Suite",
        "spec": "Test Specifications",
        "fixtures": "Test Fixtures",
        "mocks": "Test Mocks",
        "workers": "Background Workers",
        "tasks": "Async Tasks",
        "jobs": "Background Jobs",
        "queue": "Queue Processing",
        "parsers": "Parsing Logic",
        "extractors": "Data Extraction",
        "embeddings": "Vector Embeddings",
        "vector_store": "Vector Storage",
        "mcp_server": "MCP Server Integration",
        "gitlab": "GitLab Integration",
        "azuredevops": "Azure DevOps Integration",
        "scripts": "Utility Scripts",
        "docs": "Documentation",
        "documentation": "Documentation",
        "ui": "User Interface",
        "frontend": "Frontend Code",
        "backend": "Backend Code",
        "client": "Client Application",
        "server": "Server Application",
        "public": "Public Assets",
        "static": "Static Files",
        "assets": "Application Assets",
        "images": "Image Assets",
        "styles": "Stylesheets",
        "css": "CSS Styles",
        "types": "Type Definitions",
        "interfaces": "Interface Definitions",
        "dto": "Data Transfer Objects",
        "entities": "Domain Entities",
        "repositories": "Repository Pattern",
        "domain": "Domain Logic",
        "infrastructure": "Infrastructure Layer",
        "presentation": "Presentation Layer",
    }

    # Dominant files that indicate module purpose
    DOMINANT_FILES = [
        "__init__.py",
        "main.py",
        "app.py",
        "index.ts",
        "index.js",
        "index.tsx",
        "index.jsx",
        "server.py",
        "server.js",
        "routes.py",
        "router.ts",
        "README.md",
        "package.json",
        "requirements.txt",
        "setup.py",
        "pyproject.toml",
    ]

    def __init__(self, session: AsyncSession):
        """Initialize project mapper."""
        self.session = session

    async def generate_project_map(
        self, repository_id: int, max_depth: int = 2
    ) -> str:
        """
        Generate a hierarchical, annotated project map.

        Args:
            repository_id: Repository ID to map
            max_depth: Maximum directory depth to traverse (default: 2)

        Returns:
            Markdown-formatted project map
        """
        try:
            # Get repository details
            logger.debug(f"Fetching repository {repository_id}")
            repo_result = await self.session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repository = repo_result.scalar_one_or_none()

            if not repository:
                logger.warning(f"Repository {repository_id} not found")
                return f"❌ Repository with ID {repository_id} not found."

            logger.debug(f"Found repository: {repository.name}")

            # Get all files for this repository
            files_result = await self.session.execute(
                select(File)
                .where(File.repository_id == repository_id)
                .order_by(File.path)
            )
            files = files_result.scalars().all()

            if not files:
                logger.info(f"No files found for repository {repository_id}")
                return (
                    f"📂 **{repository.name}**\n\n"
                    f"No files indexed yet. Repository may be pending indexing.\n"
                )

            logger.debug(f"Found {len(files)} files for repository {repository_id}")

            # Build directory tree
            logger.debug(f"Building directory tree with max_depth={max_depth}")
            root = self._build_directory_tree(files, max_depth)

            # Get overall statistics
            logger.debug("Fetching repository statistics")
            stats = await self._get_repository_stats(repository_id)

            # Format as markdown
            logger.debug("Formatting project map")
            markdown = self._format_project_map(repository, root, stats, max_depth)

            logger.debug(f"Successfully generated project map for repository {repository_id}")
            return markdown

        except Exception as e:
            logger.error(
                f"Error generating project map for repository {repository_id}: {e}",
                exc_info=True,
                extra={"repository_id": repository_id, "max_depth": max_depth}
            )
            return f"❌ Error generating project map: {str(e)}"

    def _build_directory_tree(
        self, files: List[File], max_depth: int
    ) -> DirectoryNode:
        """Build hierarchical directory tree from files."""
        # Create root node
        root = DirectoryNode(name="<root>", path="", depth=0)

        # Track directories
        directories: Dict[str, DirectoryNode] = {"": root}

        for file in files:
            parts = file.path.split("/")
            current_path = ""

            # Process each directory level
            for i, part in enumerate(parts[:-1]):  # Exclude filename
                if i >= max_depth:
                    break

                parent_path = current_path
                current_path = os.path.join(current_path, part).replace("\\", "/")

                if current_path not in directories:
                    # Create new directory node
                    node = DirectoryNode(
                        name=part, path=current_path, depth=i + 1
                    )
                    directories[current_path] = node

                    # Add to parent
                    if parent_path in directories:
                        directories[parent_path].children.append(node)

            # Add file stats to deepest directory within max_depth
            target_depth = min(len(parts) - 1, max_depth)
            if target_depth > 0:
                dir_path = "/".join(parts[:target_depth])
            else:
                dir_path = ""

            if dir_path in directories:
                node = directories[dir_path]
                node.file_count += 1
                node.line_count += file.line_count or 0

                # Track language distribution (defensive: handle None language)
                try:
                    lang = file.language.value.lower() if file.language else "unknown"
                except (AttributeError, ValueError) as e:
                    logger.warning(f"Invalid language for file {file.path}: {e}")
                    lang = "unknown"
                node.languages[lang] = node.languages.get(lang, 0) + 1

                # Track dominant files
                filename = parts[-1]
                if filename in self.DOMINANT_FILES:
                    node.dominant_files.append(filename)

        # Annotate directories with purposes
        self._annotate_purposes(root)

        # Sort children by name
        self._sort_children(root)

        return root

    def _annotate_purposes(self, node: DirectoryNode):
        """Annotate directories with their likely purpose."""
        # Check naming patterns
        name_lower = node.name.lower()
        if name_lower in self.DIRECTORY_PURPOSES:
            node.purpose = self.DIRECTORY_PURPOSES[name_lower]

        # Recursively process children
        for child in node.children:
            self._annotate_purposes(child)

    def _sort_children(self, node: DirectoryNode):
        """Sort children alphabetically."""
        node.children.sort(key=lambda x: x.name.lower())
        for child in node.children:
            self._sort_children(child)

    async def _get_repository_stats(self, repository_id: int) -> Dict:
        """Get overall repository statistics."""
        # File and line counts
        file_stats = await self.session.execute(
            select(
                func.count(File.id).label("total_files"),
                func.sum(File.line_count).label("total_lines"),
                func.sum(File.size_bytes).label("total_size"),
            ).where(File.repository_id == repository_id)
        )
        stats_row = file_stats.one()

        # Language distribution (defensive: handle None language)
        lang_stats = await self.session.execute(
            select(File.language, func.count(File.id).label("count"))
            .where(File.repository_id == repository_id)
            .group_by(File.language)
            .order_by(func.count(File.id).desc())
        )
        languages = {}
        for row in lang_stats.all():
            try:
                lang_key = row.language.value.lower() if row.language else "unknown"
            except (AttributeError, ValueError):
                lang_key = "unknown"
            languages[lang_key] = row.count

        # Symbol count
        symbol_count = await self.session.execute(
            select(func.count(Symbol.id)).where(
                Symbol.file_id.in_(
                    select(File.id).where(File.repository_id == repository_id)
                )
            )
        )
        total_symbols = symbol_count.scalar()

        return {
            "total_files": stats_row.total_files or 0,
            "total_lines": stats_row.total_lines or 0,
            "total_size": stats_row.total_size or 0,
            "total_symbols": total_symbols or 0,
            "languages": languages,
        }

    def _format_project_map(
        self,
        repository: Repository,
        root: DirectoryNode,
        stats: Dict,
        max_depth: int,
    ) -> str:
        """Format project map as markdown."""
        lines = []

        # Header
        lines.append(f"# 📂 Project Map: **{repository.name}**\n")
        lines.append(f"**Repository**: {repository.path_with_namespace}")
        lines.append(f"**Default Branch**: {repository.default_branch}")
        if repository.description:
            lines.append(f"**Description**: {repository.description}")
        lines.append("")

        # Overall statistics
        lines.append("## 📊 Repository Statistics\n")
        lines.append(f"- **Total Files**: {stats['total_files']:,}")
        lines.append(f"- **Total Lines**: {stats['total_lines']:,}")
        lines.append(
            f"- **Total Size**: {self._format_size(stats['total_size'])}"
        )
        lines.append(f"- **Total Symbols**: {stats['total_symbols']:,}")
        lines.append("")

        # Language distribution
        if stats["languages"]:
            lines.append("**Language Distribution**:")
            for lang, count in sorted(
                stats["languages"].items(), key=lambda x: x[1], reverse=True
            ):
                percentage = (count / stats["total_files"]) * 100
                lines.append(f"- {lang}: {count} files ({percentage:.1f}%)")
            lines.append("")

        # Directory tree
        lines.append(f"## 🗂️  Directory Structure (depth ≤ {max_depth})\n")
        lines.append(
            "*Annotated with purpose, file counts, and dominant languages*\n"
        )

        # Render tree
        self._render_tree(root, lines, "", True, max_depth)

        # Footer with usage tips
        lines.append("\n---\n")
        lines.append("## 💡 Tips\n")
        lines.append(
            "- Use `get_file_tree(repository_id, path, depth)` to explore specific directories"
        )
        lines.append(
            "- Use `search_by_path(repository_id, path_pattern)` to find files by path"
        )
        lines.append(
            "- Use `get_file_content(repository_id, file_path)` to read file contents"
        )
        lines.append(
            "- Use `list_symbols_in_file(repository_id, file_path)` to see symbols in a file"
        )

        return "\n".join(lines)

    def _render_tree(
        self,
        node: DirectoryNode,
        lines: List[str],
        prefix: str,
        is_last: bool,
        max_depth: int,
    ):
        """Recursively render directory tree."""
        if node.depth > max_depth:
            return

        # Skip root node in output
        if node.depth > 0:
            # Tree characters
            connector = "└── " if is_last else "├── "
            current_prefix = prefix + connector

            # Build node display
            display_parts = [f"{node.name}/"]

            # Add purpose annotation
            if node.purpose:
                display_parts.append(f" *{node.purpose}*")

            # Add statistics
            stats_parts = []
            if node.file_count > 0:
                stats_parts.append(f"{node.file_count} files")
            if node.line_count > 0:
                stats_parts.append(f"{node.line_count:,} lines")

            # Add dominant language
            if node.languages:
                top_lang = max(node.languages.items(), key=lambda x: x[1])
                if node.file_count > 0:
                    lang_pct = (top_lang[1] / node.file_count) * 100
                    if lang_pct > 50:  # Only show if dominant (>50%)
                        stats_parts.append(f"mostly {top_lang[0]}")

            if stats_parts:
                display_parts.append(f" `[{', '.join(stats_parts)}]`")

            # Add dominant files
            if node.dominant_files:
                display_parts.append(
                    f" 📌 {', '.join(sorted(node.dominant_files))}"
                )

            lines.append(current_prefix + "".join(display_parts))

            # Update prefix for children
            extension = "    " if is_last else "│   "
            child_prefix = prefix + extension
        else:
            child_prefix = prefix

        # Render children
        for i, child in enumerate(node.children):
            is_last_child = i == len(node.children) - 1
            self._render_tree(child, lines, child_prefix, is_last_child, max_depth)

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

