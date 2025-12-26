import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_gitlab():
    """Mock GitLab client."""
    with patch("src.gitlab.client.gitlab.Gitlab") as mock:
        yield mock


def test_gitlab_client_initialization(mock_gitlab):
    """Test GitLab client initialization."""
    # Late import to ensure patching applies
    from src.gitlab.client import GitLabClient

    client = GitLabClient(token="dummy", url="https://gitlab.example.com")
    assert client is not None
    mock_gitlab.assert_called_once()


def test_get_project(mock_gitlab):
    """Test getting project details with default branch."""
    from src.gitlab.client import GitLabClient

    mock_branch = Mock()
    mock_branch.name = "main"

    mock_project = Mock()
    mock_project.id = 123
    mock_project.name = "test-repo"
    mock_project.path_with_namespace = "group/test-repo"
    mock_project.http_url_to_repo = "https://gitlab.example.com/group/test-repo.git"
    mock_project.default_branch = "main"
    mock_project.description = "A test repo"
    mock_project.visibility = "private"
    mock_project.created_at = "2025-01-01T00:00:00Z"
    mock_project.last_activity_at = "2025-01-02T00:00:00Z"
    mock_project.archived = False
    mock_project.branches.list.return_value = [mock_branch]

    mock_gitlab.return_value.projects.get.return_value = mock_project

    client = GitLabClient(token="dummy", url="https://gitlab.example.com")
    project = client.get_project(123)

    assert project["id"] == 123
    assert project["name"] == "test-repo"
    assert project["default_branch"] == "main"


def test_get_project_with_prd_branch(mock_gitlab):
    """Test getting project details when prd branch exists."""
    from src.gitlab.client import GitLabClient

    mock_branch_main = Mock()
    mock_branch_main.name = "main"
    mock_branch_prd = Mock()
    mock_branch_prd.name = "prd"

    mock_project = Mock()
    mock_project.id = 123
    mock_project.name = "test-repo"
    mock_project.path_with_namespace = "group/test-repo"
    mock_project.http_url_to_repo = "https://gitlab.example.com/group/test-repo.git"
    mock_project.default_branch = "main"
    mock_project.description = "A test repo"
    mock_project.visibility = "private"
    mock_project.created_at = "2025-01-01T00:00:00Z"
    mock_project.last_activity_at = "2025-01-02T00:00:00Z"
    mock_project.archived = False
    mock_project.branches.list.return_value = [mock_branch_main, mock_branch_prd]

    mock_gitlab.return_value.projects.get.return_value = mock_project

    client = GitLabClient(token="dummy", url="https://gitlab.example.com")
    project = client.get_project(123)

    assert project["id"] == 123
    assert project["name"] == "test-repo"
    assert project["default_branch"] == "prd"


def test_get_project_with_production_branch(mock_gitlab):
    """Test getting project details when production branch exists."""
    from src.gitlab.client import GitLabClient

    mock_branch_main = Mock()
    mock_branch_main.name = "main"
    mock_branch_production = Mock()
    mock_branch_production.name = "production"

    mock_project = Mock()
    mock_project.id = 123
    mock_project.name = "test-repo"
    mock_project.path_with_namespace = "group/test-repo"
    mock_project.http_url_to_repo = "https://gitlab.example.com/group/test-repo.git"
    mock_project.default_branch = "main"
    mock_project.description = "A test repo"
    mock_project.visibility = "private"
    mock_project.created_at = "2025-01-01T00:00:00Z"
    mock_project.last_activity_at = "2025-01-02T00:00:00Z"
    mock_project.archived = False
    mock_project.branches.list.return_value = [mock_branch_main, mock_branch_production]

    mock_gitlab.return_value.projects.get.return_value = mock_project

    client = GitLabClient(token="dummy", url="https://gitlab.example.com")
    project = client.get_project(123)

    assert project["id"] == 123
    assert project["name"] == "test-repo"
    assert project["default_branch"] == "production"


def test_get_project_prd_priority_over_production(mock_gitlab):
    """Test that prd branch has priority over production branch."""
    from src.gitlab.client import GitLabClient

    mock_branch_main = Mock()
    mock_branch_main.name = "main"
    mock_branch_prd = Mock()
    mock_branch_prd.name = "prd"
    mock_branch_production = Mock()
    mock_branch_production.name = "production"

    mock_project = Mock()
    mock_project.id = 123
    mock_project.name = "test-repo"
    mock_project.path_with_namespace = "group/test-repo"
    mock_project.http_url_to_repo = "https://gitlab.example.com/group/test-repo.git"
    mock_project.default_branch = "main"
    mock_project.description = "A test repo"
    mock_project.visibility = "private"
    mock_project.created_at = "2025-01-01T00:00:00Z"
    mock_project.last_activity_at = "2025-01-02T00:00:00Z"
    mock_project.archived = False
    mock_project.branches.list.return_value = [mock_branch_main, mock_branch_prd, mock_branch_production]

    mock_gitlab.return_value.projects.get.return_value = mock_project

    client = GitLabClient(token="dummy", url="https://gitlab.example.com")
    project = client.get_project(123)

    assert project["id"] == 123
    assert project["name"] == "test-repo"
    assert project["default_branch"] == "prd"


