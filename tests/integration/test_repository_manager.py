import pytest
from pathlib import Path

from src.gitlab.repository_manager import RepositoryManager
from src.config.enums import LanguageEnum


@pytest.fixture
def repo_manager(tmp_path):
    """Create repository manager with temp directory."""
    return RepositoryManager(cache_dir=str(tmp_path))


def test_detect_language(repo_manager):
    """Test language detection from file extension."""
    assert repo_manager.detect_language(Path("test.cs")) == LanguageEnum.CSHARP
    assert repo_manager.detect_language(Path("test.js")) == LanguageEnum.JAVASCRIPT
    assert repo_manager.detect_language(Path("test.ts")) == LanguageEnum.TYPESCRIPT
    assert repo_manager.detect_language(Path("test.vue")) == LanguageEnum.VUE
    assert repo_manager.detect_language(Path("test.txt")) == LanguageEnum.UNKNOWN


@pytest.mark.integration
def test_clone_repository(repo_manager):
    """Test cloning a real repository."""
    # Use a small public repository for testing
    repo_url = "https://github.com/octocat/Hello-World.git"
    repo_name = "hello-world"

    repo_path = repo_manager.clone_or_update(repo_url, repo_name)

    assert repo_path.exists()
    assert (repo_path / ".git").exists()


