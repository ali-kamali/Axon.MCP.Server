"""
Tests for Library Service Detection in ServiceBoundaryAnalyzer.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy import select, func
from src.analyzers.service_boundary_analyzer import ServiceBoundaryAnalyzer
from src.database.models import Repository, Project, Symbol, Service
from src.config.enums import SymbolKindEnum


@pytest.mark.asyncio
async def test_library_detection_feature_flag_enabled():
    """Test that library detection works when feature flag is enabled."""
    # Setup
    analyzer = ServiceBoundaryAnalyzer()
    mock_session = AsyncMock()
    mock_repo = Repository(id=1, name="Test Repo")
    
    # Create a library project
    library_project = Project(
        id=101,
        repository_id=1,
        name="Axon.Test.Domain",
        file_path="/src/Domain/Domain.csproj",
        output_type="Library",
        root_namespace="Axon.Test.Domain",
        target_framework="net8.0"
    )
    
    # Mock database queries
    async def execute_side_effect(query):
        mock_result = MagicMock()
        query_str = str(query)
        
        if "COUNT" in query_str.upper():
            # Symbol count query
            mock_result.scalar.return_value = 50  # Has 50 symbols
        elif "FROM projects" in query_str or "projects" in query_str.lower():
            # Project list query
            mock_result.scalars.return_value.all.return_value = [library_project]
        elif "FROM symbols" in query_str and "WHERE" in query_str.upper():
            # Controller query
            mock_result.scalars.return_value.all.return_value = []  # No controllers
        elif "FROM services" in query_str:
            # Existing service query
            mock_result.scalar_one_or_none.return_value = None  # No existing service
        else:
            mock_result.scalars.return_value.all.return_value = []
            
        return mock_result
    
    mock_session.execute.side_effect = execute_side_effect
    
    # Run detection
    services = await analyzer.detect_services(mock_repo, mock_session)
    
    # Verify
    assert len(services) == 1
    assert services[0].name == "Axon.Test.Domain"
    assert services[0].service_type == "Library"
    assert "Class library with 50 symbols" in services[0].description
    assert "Domain layer detected" in services[0].description


@pytest.mark.asyncio
async def test_library_detection_below_threshold():
    """Test that libraries with few symbols are not detected."""
    analyzer = ServiceBoundaryAnalyzer()
    mock_session = AsyncMock()
    mock_repo = Repository(id=1, name="Test Repo")
    
    # Library with only 5 symbols (below threshold of 10)
    small_library = Project(
        id=102,
        repository_id=1,
        name="Axon.Test.Small",
        file_path="/src/Small/Small.csproj",
        output_type="Library",
        root_namespace="Axon.Test.Small"
    )
    
    async def execute_side_effect(query):
        mock_result = MagicMock()
        query_str = str(query)
        
        if "COUNT" in query_str.upper():
            mock_result.scalar.return_value = 5  # Only 5 symbols
        elif "projects" in query_str.lower():
            mock_result.scalars.return_value.all.return_value = [small_library]
        else:
            mock_result.scalars.return_value.all.return_value = []
            
        return mock_result
    
    mock_session.execute.side_effect = execute_side_effect
    
    # Run detection
    services = await analyzer.detect_services(mock_repo, mock_session)
    
    # Should not detect - below threshold
    assert len(services) == 0


@pytest.mark.asyncio
async def test_library_categorization():
    """Test that libraries are correctly categorized by layer."""
    analyzer = ServiceBoundaryAnalyzer()
    
    test_cases = [
        ("Axon.Test.Domain", "Domain layer detected"),
        ("Axon.Test.Application", "Application layer detected"),
        ("Axon.Test.Infrastructure", "Infrastructure layer detected"),
        ("Axon.Test.Persistence", "Infrastructure layer detected"),
        ("Axon.Test.Shared", "Shared library detected"),
        ("Axon.Test.Common", "Shared library detected"),
        ("Axon.Test.Core", "Core library detected"),
    ]
    
    for project_name, expected_reason in test_cases:
        mock_session = AsyncMock()
        mock_repo = Repository(id=1, name="Test Repo")
        
        project = Project(
            id=200,
            repository_id=1,
            name=project_name,
            file_path=f"/src/{project_name}.csproj",
            output_type="Library"
        )
        
        async def execute_side_effect(query):
            mock_result = MagicMock()
            if "COUNT" in str(query).upper():
                mock_result.scalar.return_value = 20  # Above threshold
            elif "projects" in str(query).lower():
                mock_result.scalars.return_value.all.return_value = [project]
            else:
                mock_result.scalars.return_value.all.return_value = []
            return mock_result
        
        mock_session.execute.side_effect = execute_side_effect
        
        services = await analyzer.detect_services(mock_repo, mock_session)
        
        assert len(services) == 1
        assert expected_reason in services[0].description, f"Expected '{expected_reason}' in description for {project_name}"


@pytest.mark.asyncio
async def test_api_detection_unaffected():
    """Test that API detection still works and takes precedence."""
    analyzer = ServiceBoundaryAnalyzer()
    mock_session = AsyncMock()
    mock_repo = Repository(id=1, name="Test Repo")
    
    # API project with controllers
    api_project = Project(
        id=300,
        repository_id=1,
        name="Axon.Test.Api",
        file_path="/src/Api/Api.csproj",
        output_type="Exe",
        root_namespace="Axon.Test.Api"
    )
    
    controller = Symbol(
        id=1001,
        project_id=300,
        name="UsersController",
        kind=SymbolKindEnum.CLASS
    )
    
    async def execute_side_effect(query):
        mock_result = MagicMock()
        query_str = str(query)
        
        if "COUNT" in query_str.upper():
            mock_result.scalar.return_value = 100
        elif "projects" in query_str.lower():
            mock_result.scalars.return_value.all.return_value = [api_project]
        elif "Controller" in query_str or "ApiController" in query_str or "Route" in query_str:
            # Controller query
            mock_result.scalars.return_value.all.return_value = [controller]
        else:
            mock_result.scalars.return_value.all.return_value = []
            
        return mock_result
    
    mock_session.execute.side_effect = execute_side_effect
    
    services = await analyzer.detect_services(mock_repo, mock_session)
    
    # Should detect as API, not Library
    assert len(services) == 1
    assert services[0].service_type == "API"
    assert "Controller" in services[0].description


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
