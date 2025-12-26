"""Unit tests for module identifier (Phase 2)."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from src.utils.module_identifier import ModuleIdentifier, ModuleInfo
from src.database.models import File
from src.config.enums import LanguageEnum, SymbolKindEnum


class TestModuleInfo:
    """Test ModuleInfo dataclass."""

    def test_module_info_creation(self):
        """Test basic ModuleInfo creation."""
        module = ModuleInfo(
            path="src/api",
            name="api",
            module_type="python_package",
            is_package=True,
            files=["src/api/__init__.py", "src/api/routes.py"],
            file_count=2,
            symbol_count=15,
            line_count=300,
            languages={"python": 2},
            entry_points=["__init__.py"],
            has_tests=False,
            depth=2
        )

        assert module.path == "src/api"
        assert module.name == "api"
        assert module.is_package is True
        assert module.file_count == 2
        assert module.depth == 2


class TestModuleIdentifier:
    """Test ModuleIdentifier class."""

    def test_module_indicators(self):
        """Test that module indicators are properly defined."""
        identifier = ModuleIdentifier(Mock())

        assert "python_package" in identifier.MODULE_INDICATORS
        assert "__init__.py" in identifier.MODULE_INDICATORS["python_package"]
        assert "typescript_module" in identifier.MODULE_INDICATORS
        assert "package.json" in identifier.MODULE_INDICATORS["typescript_module"]

    def test_entry_point_files(self):
        """Test entry point file patterns."""
        identifier = ModuleIdentifier(Mock())

        assert "__init__.py" in identifier.ENTRY_POINT_FILES
        assert "main.py" in identifier.ENTRY_POINT_FILES
        assert "index.ts" in identifier.ENTRY_POINT_FILES
        assert "App.tsx" in identifier.ENTRY_POINT_FILES

    def test_build_directory_structure(self):
        """Test building directory structure from files."""
        identifier = ModuleIdentifier(Mock())

        files = [
            Mock(
                path="src/api/routes.py",
                line_count=100,
                language=LanguageEnum.PYTHON,
            ),
            Mock(
                path="src/api/controllers.py",
                line_count=150,
                language=LanguageEnum.PYTHON,
            ),
            Mock(
                path="src/utils/helpers.py",
                line_count=50,
                language=LanguageEnum.PYTHON,
            ),
        ]

        directories = identifier._build_directory_structure(files, max_depth=3)

        assert "src" in directories
        assert "src/api" in directories
        assert "src/utils" in directories

        # Check src/api statistics
        api_dir = directories["src/api"]
        assert api_dir["file_count"] == 2
        assert api_dir["line_count"] == 250
        assert api_dir["languages"]["python"] == 2

    def test_build_directory_structure_depth_limit(self):
        """Test that max_depth is respected."""
        identifier = ModuleIdentifier(Mock())

        files = [
            Mock(
                path="src/api/v1/users/controller.py",
                line_count=100,
                language=LanguageEnum.PYTHON,
            ),
        ]

        # Test with depth 2
        directories = identifier._build_directory_structure(files, max_depth=2)
        assert "src" in directories
        assert "src/api" in directories
        assert "src/api/v1" not in directories

    @pytest.mark.asyncio
    async def test_identify_modules_empty(self):
        """Test identifying modules with no files."""
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        async def mock_execute(*args, **kwargs):
            return mock_result

        session.execute = mock_execute

        identifier = ModuleIdentifier(session)
        modules = await identifier.identify_modules(repository_id=1, min_depth=1, max_depth=3)

        assert modules == []

    @pytest.mark.asyncio
    async def test_analyze_directory_python_package(self):
        """Test analyzing a Python package directory."""
        session = MagicMock()

        # Mock symbol count query
        mock_symbol_result = MagicMock()
        mock_symbol_result.scalar.return_value = 10

        async def mock_execute(*args, **kwargs):
            return mock_symbol_result

        session.execute = mock_execute

        identifier = ModuleIdentifier(session)

        # Create mock files
        files = [
            Mock(id=1, path="src/api/__init__.py", line_count=20, language=LanguageEnum.PYTHON),
            Mock(id=2, path="src/api/routes.py", line_count=100, language=LanguageEnum.PYTHON),
            Mock(id=3, path="src/api/models.py", line_count=80, language=LanguageEnum.PYTHON),
        ]

        dir_info = {
            "files": files,
            "file_count": 3,
            "line_count": 200,
            "languages": {"python": 3},
        }

        module = await identifier._analyze_directory(
            repository_id=1,
            dir_path="src/api",
            dir_info=dir_info,
            all_files=files
        )

        assert module is not None
        assert module.path == "src/api"
        assert module.name == "api"
        assert module.module_type == "python_package"
        assert module.is_package is True
        assert module.file_count == 3
        assert module.symbol_count == 10
        assert "__init__.py" in module.entry_points

    @pytest.mark.asyncio
    async def test_analyze_directory_typescript_module(self):
        """Test analyzing a TypeScript module directory."""
        session = MagicMock()

        # Mock symbol count query
        mock_symbol_result = MagicMock()
        mock_symbol_result.scalar.return_value = 15

        async def mock_execute(*args, **kwargs):
            return mock_symbol_result

        session.execute = mock_execute

        identifier = ModuleIdentifier(session)

        files = [
            Mock(id=1, path="src/components/index.ts", line_count=50, language=LanguageEnum.TYPESCRIPT),
            Mock(id=2, path="src/components/Button.tsx", line_count=100, language=LanguageEnum.TYPESCRIPT),
        ]

        dir_info = {
            "files": files,
            "file_count": 2,
            "line_count": 150,
            "languages": {"typescript": 2},
        }

        module = await identifier._analyze_directory(
            repository_id=1,
            dir_path="src/components",
            dir_info=dir_info,
            all_files=files
        )

        assert module is not None
        assert module.module_type == "typescript_module"
        assert module.is_package is True
        assert "index.ts" in module.entry_points

    @pytest.mark.asyncio
    async def test_analyze_directory_skips_empty(self):
        """Test that empty directories are skipped."""
        session = MagicMock()
        identifier = ModuleIdentifier(session)

        dir_info = {
            "files": [],
            "file_count": 0,
            "line_count": 0,
            "languages": {},
        }

        module = await identifier._analyze_directory(
            repository_id=1,
            dir_path="empty",
            dir_info=dir_info,
            all_files=[]
        )

        assert module is None

    @pytest.mark.asyncio
    async def test_analyze_directory_requires_minimum_size(self):
        """Test that small non-package directories are filtered."""
        session = MagicMock()

        # Mock symbol count query - returns small count
        mock_symbol_result = MagicMock()
        mock_symbol_result.scalar.return_value = 1

        async def mock_execute(*args, **kwargs):
            return mock_symbol_result

        session.execute = mock_execute

        identifier = ModuleIdentifier(session)

        # Single file, no package indicator, few symbols
        files = [
            Mock(id=1, path="src/util.py", line_count=10, language=LanguageEnum.PYTHON),
        ]

        dir_info = {
            "files": files,
            "file_count": 1,
            "line_count": 10,
            "languages": {"python": 1},
        }

        module = await identifier._analyze_directory(
            repository_id=1,
            dir_path="src",
            dir_info=dir_info,
            all_files=files
        )

        # Should be filtered out (1 file, 1 symbol, not a package)
        assert module is None

    def test_module_depth_calculation(self):
        """Test that module depth is calculated correctly."""
        identifier = ModuleIdentifier(Mock())

        files = [
            Mock(path="root.py", line_count=10, language=LanguageEnum.PYTHON),
            Mock(path="level1/file.py", line_count=10, language=LanguageEnum.PYTHON),
            Mock(path="level1/level2/file.py", line_count=10, language=LanguageEnum.PYTHON),
        ]

        directories = identifier._build_directory_structure(files, max_depth=5)

        # Root directory has depth 0 (will be calculated in _analyze_directory)
        # level1 should be depth 1
        # level1/level2 should be depth 2
        assert "level1" in directories
        assert "level1/level2" in directories

