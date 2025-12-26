import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.extractors.config_extractor import ConfigExtractor
from src.database.models import Repository, File
from src.config.enums import SourceControlProviderEnum

@pytest.mark.asyncio
async def test_config_extractor_types():
    # Mock session
    session = AsyncMock()
    
    # Mock repository
    repo = Repository(id=1, provider=SourceControlProviderEnum.GITLAB, path_with_namespace="test/repo")
    # First execute call is for Repository
    # Second execute call is for delete
    # Third execute call is for File
    
    # We need to mock the results of execute differently based on the query or order
    # simpler way: mock the return values of execute to return a mock that behaves as needed
    
    mock_result_repo = MagicMock()
    mock_result_repo.scalar_one_or_none.return_value = repo
    
    mock_result_delete = MagicMock()
    
    file_obj = File(id=1, path="appsettings.json", repository_id=1)
    mock_result_files = MagicMock()
    mock_result_files.scalars.return_value.all.return_value = [file_obj]
    
    session.execute.side_effect = [mock_result_repo, mock_result_delete, mock_result_files, MagicMock()] # Extra mock for commit if needed
    
    # Mock RepositoryManager and file system
    with patch("src.gitlab.repository_manager.RepositoryManager") as MockRepoManager:
        mock_repo_manager = MockRepoManager.return_value
        
        # Mock the path operations
        mock_repo_path = MagicMock()
        mock_repo_manager.cache_dir.__truediv__.return_value = mock_repo_path
        
        # Mock full_path
        mock_full_path = MagicMock()
        mock_repo_path.__truediv__.return_value = mock_full_path
        
        mock_full_path.exists.return_value = True
        mock_full_path.read_text.return_value = '{"Integer": 301, "Boolean": true, "String": "text"}'
        
        extractor = ConfigExtractor(session)
        await extractor.extract_configuration(1)
        
        # Verify session.add was called
        assert session.add.call_count == 3
        
        calls = session.add.call_args_list
        
        # Helper to find entry by key
        def get_entry(key):
            for call in calls:
                entry = call[0][0]
                if entry.config_key == key:
                    return entry
            return None
            
        int_entry = get_entry("Integer")
        assert int_entry is not None
        assert int_entry.config_value == "301"
        assert int_entry.config_type == "number"
        assert isinstance(int_entry.config_value, str)
        
        bool_entry = get_entry("Boolean")
        assert bool_entry is not None
        assert bool_entry.config_value == "true"
        assert bool_entry.config_type == "boolean"
        assert isinstance(bool_entry.config_value, str)
        
        str_entry = get_entry("String")
        assert str_entry is not None
        assert str_entry.config_value == "text"
        assert str_entry.config_type == "string"
        assert isinstance(str_entry.config_value, str)
