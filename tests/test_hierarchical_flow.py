import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
from src.database.models import Repository, Project, Symbol, Service
from src.analyzers.service_boundary_analyzer import ServiceBoundaryAnalyzer
from src.generators.service_doc_generator import ServiceDocGenerator
from src.mcp_server.tools.service_tools import list_services, get_service_details, get_service_documentation
from src.config.enums import SymbolKindEnum

@pytest.mark.asyncio
async def test_hierarchical_flow():
    """
    Test the complete flow:
    1. Service Detection (Analyzer)
    2. Documentation Generation (Generator)
    3. Tool Access (MCP Tools)
    """
    print("\nStarting End-to-End Integration Test...")
    
    # --- Setup Mocks ---
    mock_session = AsyncMock()
    mock_repo = Repository(id=1, name="Axon.IntegrationTest")
    
    # Mock Project (The "Service")
    project = Project(
        id=101,
        repository_id=1,
        name="Axon.Orders.API",
        file_path="/src/Axon.Orders.API/Axon.Orders.API.csproj",
        root_namespace="Axon.Orders.API",
        target_framework="net8.0"
    )
    
    # Mock Controller (The Signal)
    controller = Symbol(name="OrdersController", kind=SymbolKindEnum.CLASS, service_id=None) # service_id set later
    
    # --- Step 1: Service Detection ---
    print("Step 1: Running Service Detection...")
    analyzer = ServiceBoundaryAnalyzer()
    
    # Mock DB queries for Analyzer
    # session.query() returns a Query object (synchronous), which is then executed or iterated.
    # However, in async SQLAlchemy, we usually use select() and session.execute().
    # The analyzer uses session.query(Symbol).filter(...).all() which is synchronous style but often supported in some async shims.
    # But wait, our analyzer code uses session.query().
    # If session is AsyncSession, query() is not available directly unless using sync style or specific setup.
    # Let's check the analyzer code again. It uses session.query(Symbol)...
    
    # If the real code uses session.query, then session must be treated as having a synchronous query method that returns a mock.
    # The error 'coroutine object has no attribute filter' suggests session.query returned a coroutine (AsyncMock default).
    
    # We need to make session.query return a MagicMock (synchronous), not an AsyncMock.
    mock_session.query = MagicMock()
    
    def query_side_effect(model):
        query_mock = MagicMock()
        if model == Project:
            query_mock.filter.return_value.all.return_value = [project]
        elif model == Symbol:
            query_mock.filter.return_value.all.return_value = [controller]
        return query_mock
    mock_session.query.side_effect = query_side_effect
    
    # Mock file ops
    with patch("builtins.open", mock_open(read_data='<Project Sdk="Microsoft.NET.Sdk.Web">')):
        with patch("os.path.exists", return_value=True):
            detected_services = analyzer.detect_services(mock_repo, mock_session)
            
    assert len(detected_services) == 1
    service = detected_services[0]
    service.id = 500 # Simulate DB ID assignment
    print(f"  -> Detected Service: {service.name} ({service.service_type})")
    
    # Link Controller to Service (Simulate DB persistence)
    controller.service_id = service.id
    
    # --- Step 2: Documentation Generation ---
    print("Step 2: Generating Documentation...")
    
    # Mock DB queries for Generator
    # We need to return the controller when querying symbols for the service
    mock_session.query.side_effect = None # Reset side effect
    mock_session.query.return_value.filter.return_value.all.return_value = [controller]
    
    generator = ServiceDocGenerator(mock_session)
    
    # Mock LLM
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Manages customer orders."
    mock_client.chat.completions.create.return_value = mock_response
    
    with patch.object(generator.llm, '_get_client', return_value=mock_client):
        doc = await generator.generate_service_doc(service)
        
    assert "# Axon.Orders.API" in doc
    assert "Manages customer orders" in doc
    print("  -> Documentation generated successfully.")
    
    # --- Step 3: MCP Tool Access ---
    print("Step 3: Verifying MCP Tools...")
    
    # Mock DB session context manager for tools
    mock_db_ctx = MagicMock()
    mock_db_ctx.__aenter__.return_value = mock_session
    mock_db_ctx.__aexit__.return_value = None
    
    # Mock DB results for tools
    # list_services
    # session.execute is async, so we need to set the return_value of the AsyncMock to be the result object
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = [service]
    mock_session.execute.return_value = mock_execute_result
    
    with patch("src.mcp_server.tools.service_tools.get_db_session", return_value=mock_db_ctx):
        # Test list_services
        tools_result = await list_services()
        assert "Axon.Orders.API" in tools_result[0].text
        print("  -> list_services: OK")
        
        # Test get_service_details
        # Need to handle the specific query flow in get_service_details
        # session.execute is async, so it should return a coroutine that resolves to the result.
        # AsyncMock handles the coroutine part, but the return_value should be the result object.
        
        async def execute_side_effect(query):
            mock_result = MagicMock()
            if "FROM services" in str(query):
                 mock_result.scalars.return_value.all.return_value = [service]
                 mock_result.scalar_one_or_none.return_value = service
            elif "FROM symbols" in str(query):
                 mock_result.scalars.return_value.all.return_value = [controller]
            return mock_result
        mock_session.execute.side_effect = execute_side_effect
        
        details_result = await get_service_details("Axon.Orders.API")
        assert "OrdersController" in details_result[0].text
        print("  -> get_service_details: OK")
        
        # Test get_service_documentation
        # We need to mock ServiceDocGenerator inside the tool or mock the generator result
        with patch("src.mcp_server.tools.service_tools.ServiceDocGenerator") as MockGen:
            mock_gen_instance = MockGen.return_value
            mock_gen_instance.generate_service_doc = AsyncMock(return_value=doc)
            
            doc_result = await get_service_documentation("Axon.Orders.API")
            assert "Manages customer orders" in doc_result[0].text
            print("  -> get_service_documentation: OK")

    print("\nIntegration Test Completed Successfully! ✅")
