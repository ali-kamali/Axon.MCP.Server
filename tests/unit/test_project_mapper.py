"""Unit tests for project mapper (Phase 1 implementation)."""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from src.utils.project_mapper import ProjectMapper, DirectoryNode
from src.database.models import File, Repository
from src.config.enums import LanguageEnum, SourceControlProviderEnum, RepositoryStatusEnum


class TestDirectoryNode:
    """Test DirectoryNode data class."""

    def test_node_initialization(self):
        """Test basic node creation."""
        node = DirectoryNode(name="src", path="src", depth=1)
        assert node.name == "src"
        assert node.path == "src"
        assert node.depth == 1
        assert node.file_count == 0
        assert node.languages == {}
        assert node.children == []
        assert node.dominant_files == []

    def test_node_with_stats(self):
        """Test node with statistics."""
        node = DirectoryNode(
            name="api",
            path="src/api",
            depth=2,
            file_count=5,
            line_count=200,
            languages={"python": 3, "javascript": 2},
        )
        assert node.file_count == 5
        assert node.line_count == 200
        assert node.languages["python"] == 3


class TestProjectMapper:
    """Test ProjectMapper class."""

    def test_directory_purpose_mapping(self):
        """Test that directory purposes are mapped correctly."""
        mapper = ProjectMapper(Mock())
        
        # Test common directory patterns
        assert "api" in mapper.DIRECTORY_PURPOSES
        assert "models" in mapper.DIRECTORY_PURPOSES
        assert "tests" in mapper.DIRECTORY_PURPOSES
        assert "utils" in mapper.DIRECTORY_PURPOSES
        
        # Verify purpose descriptions
        assert mapper.DIRECTORY_PURPOSES["api"] == "API Endpoints & Controllers"
        assert mapper.DIRECTORY_PURPOSES["models"] == "Data Models & Entities"
        assert mapper.DIRECTORY_PURPOSES["tests"] == "Test Suite"

    def test_dominant_files(self):
        """Test dominant file identification."""
        mapper = ProjectMapper(Mock())
        
        # Test that common entry-point files are identified
        assert "__init__.py" in mapper.DOMINANT_FILES
        assert "main.py" in mapper.DOMINANT_FILES
        assert "index.ts" in mapper.DOMINANT_FILES
        assert "README.md" in mapper.DOMINANT_FILES
        assert "package.json" in mapper.DOMINANT_FILES

    def test_build_directory_tree_simple(self):
        """Test building a simple directory tree."""
        mapper = ProjectMapper(Mock())
        
        # Create mock files
        files = [
            Mock(
                path="src/main.py",
                line_count=50,
                language=LanguageEnum.PYTHON,
            ),
            Mock(
                path="src/utils.py",
                line_count=30,
                language=LanguageEnum.PYTHON,
            ),
            Mock(
                path="tests/test_main.py",
                line_count=40,
                language=LanguageEnum.PYTHON,
            ),
        ]
        
        root = mapper._build_directory_tree(files, max_depth=2)
        
        # Verify root structure
        assert root.name == "<root>"
        assert root.depth == 0
        assert len(root.children) == 2  # src and tests
        
        # Find src directory
        src_node = next((c for c in root.children if c.name == "src"), None)
        assert src_node is not None
        assert src_node.file_count == 2
        assert src_node.line_count == 80
        assert src_node.languages.get("python") == 2

    def test_build_directory_tree_with_depth_limit(self):
        """Test that max_depth is respected."""
        mapper = ProjectMapper(Mock())
        
        files = [
            Mock(
                path="src/api/controllers/user_controller.py",
                line_count=100,
                language=LanguageEnum.PYTHON,
            ),
        ]
        
        # Test with depth 1
        root = mapper._build_directory_tree(files, max_depth=1)
        src_node = next((c for c in root.children if c.name == "src"), None)
        assert src_node is not None
        assert src_node.file_count == 1
        
        # Test with depth 2
        root = mapper._build_directory_tree(files, max_depth=2)
        src_node = next((c for c in root.children if c.name == "src"), None)
        api_node = next((c for c in src_node.children if c.name == "api"), None)
        assert api_node is not None
        assert api_node.file_count == 1

    def test_annotate_purposes(self):
        """Test directory purpose annotation."""
        mapper = ProjectMapper(Mock())
        
        # Create a tree
        root = DirectoryNode(name="<root>", path="", depth=0)
        api_node = DirectoryNode(name="api", path="api", depth=1)
        models_node = DirectoryNode(name="models", path="models", depth=1)
        custom_node = DirectoryNode(name="mycustom", path="mycustom", depth=1)
        
        root.children = [api_node, models_node, custom_node]
        
        mapper._annotate_purposes(root)
        
        # Verify annotations
        assert api_node.purpose == "API Endpoints & Controllers"
        assert models_node.purpose == "Data Models & Entities"
        assert custom_node.purpose is None  # No matching pattern

    def test_sort_children(self):
        """Test that children are sorted alphabetically."""
        mapper = ProjectMapper(Mock())
        
        root = DirectoryNode(name="<root>", path="", depth=0)
        root.children = [
            DirectoryNode(name="utils", path="utils", depth=1),
            DirectoryNode(name="api", path="api", depth=1),
            DirectoryNode(name="models", path="models", depth=1),
        ]
        
        mapper._sort_children(root)
        
        # Verify sorted order
        names = [c.name for c in root.children]
        assert names == ["api", "models", "utils"]

    def test_format_size(self):
        """Test file size formatting."""
        mapper = ProjectMapper(Mock())
        
        # Test various sizes
        assert mapper._format_size(500) == "500.0 B"
        assert mapper._format_size(2048) == "2.0 KB"
        assert mapper._format_size(1048576) == "1.0 MB"
        assert mapper._format_size(1073741824) == "1.0 GB"

    def test_render_tree_structure(self):
        """Test tree rendering structure."""
        mapper = ProjectMapper(Mock())
        
        # Create a simple tree
        root = DirectoryNode(name="<root>", path="", depth=0)
        src = DirectoryNode(name="src", path="src", depth=1, file_count=5, line_count=200)
        src.purpose = "Source Code"
        src.languages = {"python": 5}
        root.children = [src]
        
        lines = []
        mapper._render_tree(root, lines, "", True, max_depth=2)
        
        # Verify rendering
        assert len(lines) > 0
        output = "\n".join(lines)
        assert "src/" in output
        assert "Source Code" in output
        assert "5 files" in output

    @pytest.mark.asyncio
    async def test_generate_project_map_no_repository(self):
        """Test handling of non-existent repository."""
        # Mock session
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        
        async_mock_execute = AsyncMock(return_value=mock_result)
        session.execute = async_mock_execute
        
        mapper = ProjectMapper(session)
        result = await mapper.generate_project_map(repository_id=999, max_depth=2)
        
        assert "not found" in result.lower()
        assert "999" in result

    @pytest.mark.asyncio
    async def test_generate_project_map_no_files(self):
        """Test handling of repository with no files."""
        # Mock session
        session = MagicMock()
        
        # Mock repository
        repo = Mock(spec=Repository)
        repo.id = 1
        repo.name = "test-repo"
        repo.description = "Test repository"
        
        mock_repo_result = MagicMock()
        mock_repo_result.scalar_one_or_none.return_value = repo
        
        # Mock empty files
        mock_files_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_files_result.scalars.return_value = mock_scalars
        
        async def mock_execute(*args, **kwargs):
            # First call returns repo, second returns files
            if not hasattr(mock_execute, 'call_count'):
                mock_execute.call_count = 0
            mock_execute.call_count += 1
            if mock_execute.call_count == 1:
                return mock_repo_result
            else:
                return mock_files_result
        
        session.execute = mock_execute
        
        mapper = ProjectMapper(session)
        result = await mapper.generate_project_map(repository_id=1, max_depth=2)
        
        assert "test-repo" in result
        assert "No files indexed" in result or "pending indexing" in result.lower()

    def test_dominant_files_detection(self):
        """Test dominant file detection in tree building."""
        mapper = ProjectMapper(Mock())
        
        files = [
            Mock(
                path="src/__init__.py",
                line_count=10,
                language=LanguageEnum.PYTHON,
            ),
            Mock(
                path="src/main.py",
                line_count=50,
                language=LanguageEnum.PYTHON,
            ),
        ]
        
        root = mapper._build_directory_tree(files, max_depth=2)
        src_node = next((c for c in root.children if c.name == "src"), None)
        
        assert src_node is not None
        assert "__init__.py" in src_node.dominant_files
        assert "main.py" in src_node.dominant_files

    def test_language_distribution(self):
        """Test language distribution tracking."""
        mapper = ProjectMapper(Mock())
        
        files = [
            Mock(path="src/app.py", line_count=100, language=LanguageEnum.PYTHON),
            Mock(path="src/utils.py", line_count=50, language=LanguageEnum.PYTHON),
            Mock(path="src/script.js", line_count=30, language=LanguageEnum.JAVASCRIPT),
        ]
        
        root = mapper._build_directory_tree(files, max_depth=2)
        src_node = next((c for c in root.children if c.name == "src"), None)
        
        assert src_node is not None
        assert src_node.languages["python"] == 2
        assert src_node.languages["javascript"] == 1
        assert src_node.file_count == 3
        assert src_node.line_count == 180

