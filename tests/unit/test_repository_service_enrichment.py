import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from src.api.services.repository_service import RepositoryService
from src.api.schemas.repositories import RepositoryResponse
from src.database.models import File, Commit
from src.config.enums import RepositoryStatusEnum, SourceControlProviderEnum, LanguageEnum

@pytest.mark.asyncio
async def test_enrich_repository_response():
    # Setup
    session = AsyncMock()
    service = RepositoryService(session)
    
    # Create a dummy repository object (not a DB model, but an object with attributes)
    class DummyRepo:
        id = 1
        provider = SourceControlProviderEnum.GITLAB
        name = "test-repo"
        path_with_namespace = "group/test-repo"
        url = "http://example.com"
        clone_url = "http://example.com.git"
        default_branch = "main"
        status = RepositoryStatusEnum.COMPLETED
        total_files = 10
        total_symbols = 100
        size_bytes = 1000
        created_at = datetime.now()
        updated_at = datetime.now()
        gitlab_project_id = 123
        azuredevops_project_name = None
        azuredevops_repo_id = None
        last_synced_at = datetime.now()
        last_commit_sha = "abc"

    repo_obj = DummyRepo()
    repo_response = RepositoryResponse.model_validate(repo_obj)
    
    # Mock language stats result
    # select(File.language, func.sum(File.size_bytes))...
    stats_result = MagicMock()
    # Return list of (language, size) tuples
    stats_result.all.return_value = [
        (LanguageEnum.PYTHON, 600),
        (LanguageEnum.TYPESCRIPT, 400)
    ]
    
    # Mock last commit result
    # select(Commit)...
    commit_result = MagicMock()
    commit_obj = MagicMock()
    commit_obj.sha = "abc1234"
    commit_obj.message = "feat: test commit"
    commit_obj.author_name = "Test User"
    commit_obj.committed_date = datetime.now()
    
    commit_result.scalar_one_or_none.return_value = commit_obj
    
    # Configure session.execute side effects
    # First call is for stats, second for commit
    session.execute.side_effect = [stats_result, commit_result]
    
    # Execute
    await service._enrich_repository_response(repo_response)
    
    # Verify
    assert repo_response.languages["PYTHON"] == 60.0
    assert repo_response.languages["TYPESCRIPT"] == 40.0
    assert repo_response.primary_language == "PYTHON"
    assert repo_response.last_commit is not None
    assert repo_response.last_commit.sha == "abc1234"
    assert repo_response.last_commit.message == "feat: test commit"
    assert repo_response.last_commit.author_name == "Test User"
