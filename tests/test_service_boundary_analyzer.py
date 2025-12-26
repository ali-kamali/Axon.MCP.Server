import pytest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from src.analyzers.service_boundary_analyzer import ServiceBoundaryAnalyzer
from src.database.models import Repository, Project, Symbol
from src.config.enums import SymbolKindEnum

@pytest.fixture
def analyzer():
    return ServiceBoundaryAnalyzer()

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.fixture
def mock_repo():
    return Repository(id=1, name="Axon.Backend.Core")

@pytest.mark.asyncio
async def test_detect_web_sdk_project(analyzer, mock_session, mock_repo):
    # Setup
    project = Project(
        id=101,
        repository_id=1,
        name="Axon.Appointment.Service",
        file_path="/src/Axon.Appointment.Service/Axon.Appointment.Service.csproj",
        root_namespace="Axon.Appointment.Service",
        target_framework="net8.0"
    )
    
    # Mock async session.execute() for Project query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [project]
    mock_session.execute.return_value = mock_result
    
    # Mock file content
    with patch("builtins.open", mock_open(read_data='<Project Sdk="Microsoft.NET.Sdk.Web">')):
        with patch("os.path.exists", return_value=True):
            services = await analyzer.detect_services(mock_repo, mock_session)
            
    assert len(services) == 1
    assert services[0].name == "Axon.Appointment.Service"
    assert services[0].service_type == "API"
    assert "Web SDK detected" in services[0].description

@pytest.mark.asyncio
async def test_detect_controller_project(analyzer, mock_session, mock_repo):
    # Setup
    project = Project(
        id=102,
        repository_id=1,
        name="Axon.Users.API",
        file_path="/src/Axon.Users.API/Axon.Users.API.csproj",
        root_namespace="Axon.Users.API"
    )
    
    mock_controller = Symbol(name="UsersController", kind=SymbolKindEnum.CLASS)
    
    # Mock async session.execute() with side_effect for different queries
    async def execute_side_effect(query):
        mock_result = MagicMock()
        # Check if this is a Project query or Symbol query based on the query string
        query_str = str(query)
        if "FROM projects" in query_str or "projects" in query_str.lower():
            mock_result.scalars.return_value.all.return_value = [project]
        else:  # Symbol query
            mock_result.scalars.return_value.all.return_value = [mock_controller]
        return mock_result
        
    mock_session.execute.side_effect = execute_side_effect
    
    # Mock file content (empty, so no SDK detection)
    with patch("builtins.open", mock_open(read_data='<Project Sdk="Microsoft.NET.Sdk">')):
        with patch("os.path.exists", return_value=True):
            services = await analyzer.detect_services(mock_repo, mock_session)
            
    assert len(services) == 1
    assert services[0].name == "Axon.Users.API"
    assert "Found 1 Controllers" in services[0].description

@pytest.mark.asyncio
async def test_ignore_class_library(analyzer, mock_session, mock_repo):
    # Setup
    project = Project(
        id=103,
        repository_id=1,
        name="Axon.Domain",
        file_path="/src/Axon.Domain/Axon.Domain.csproj",
        root_namespace="Axon.Domain"
    )
    
    async def execute_side_effect(query):
        mock_result = MagicMock()
        query_str = str(query)
        if "FROM projects" in query_str or "projects" in query_str.lower():
            mock_result.scalars.return_value.all.return_value = [project]
        else:  # Symbol query
            mock_result.scalars.return_value.all.return_value = []  # No controllers
        return mock_result
        
    mock_session.execute.side_effect = execute_side_effect
    
    with patch("builtins.open", mock_open(read_data='<Project Sdk="Microsoft.NET.Sdk">')):
        with patch("os.path.exists", return_value=True):
            services = await analyzer.detect_services(mock_repo, mock_session)
            
    assert len(services) == 0

@pytest.mark.asyncio
async def test_detect_cqrs_host_project(analyzer, mock_session, mock_repo):
    # Setup: A project that doesn't have controllers but has DI/CQRS (e.g. Worker or Host)
    project = Project(
        id=104,
        repository_id=1,
        name="Axon.Worker.Host",
        file_path="/src/Axon.Worker.Host/Axon.Worker.Host.csproj",
        root_namespace="Axon.Worker.Host"
    )
    
    async def execute_side_effect(query):
        mock_result = MagicMock()
        query_str = str(query)
        if "FROM projects" in query_str or "projects" in query_str.lower():
            mock_result.scalars.return_value.all.return_value = [project]
        else:  # Symbol query
            mock_result.scalars.return_value.all.return_value = []  # No controllers
        return mock_result
        
    mock_session.execute.side_effect = execute_side_effect
    
    # Mock Program.cs content with DI and MediatR
    program_cs_content = """
    var builder = Host.CreateApplicationBuilder(args);
    builder.Services.AddMediatR(cfg => cfg.RegisterServicesFromAssembly(typeof(Program).Assembly));
    builder.Services.AddMassTransit(x => x.UsingRabbitMq());
    var host = builder.Build();
    host.Run();
    """
    
    # We need to mock os.path.dirname and os.path.join to simulate finding Program.cs
    with patch("os.path.dirname", return_value="/src/Axon.Worker.Host"):
        with patch("os.path.join", return_value="/src/Axon.Worker.Host/Program.cs"):
            with patch("os.path.exists", side_effect=lambda p: True): # All files exist
                with patch("builtins.open", mock_open(read_data=program_cs_content)):
                    services = await analyzer.detect_services(mock_repo, mock_session)
            
    assert len(services) == 1
    assert services[0].name == "Axon.Worker.Host"
    assert "Host Builder detected" in services[0].description
    assert "CQRS (MediatR) detected" in services[0].description
    assert "Message Bus detected" in services[0].description
