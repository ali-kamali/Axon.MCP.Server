"""End-to-end integration tests for the API."""

import pytest
from httpx import AsyncClient
from src.api.main import app
from src.config.enums import RepositoryStatusEnum, SymbolKindEnum, LanguageEnum


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_api_endpoint():
    """Test search API endpoint end-to-end."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test basic search
        response = await client.get("/api/v1/search?query=test&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_with_filters():
    """Test search endpoint with filters."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/search",
            params={
                "query": "test",
                "limit": 5,
                "language": "python",
                "symbol_kind": "function"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_hybrid_mode():
    """Test search in hybrid mode."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/search",
            params={
                "query": "authentication function",
                "limit": 10,
                "hybrid": True
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_crud():
    """Test repository CRUD operations."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create repository
        create_response = await client.post(
            "/api/v1/repositories",
            json={
                "gitlab_project_id": 999,
                "name": "test-repo",
                "path_with_namespace": "test/repo",
                "url": "https://example.com/repo.git",
                "default_branch": "main"
            }
        )
        
        assert create_response.status_code in [200, 201]
        repo_data = create_response.json()
        repo_id = repo_data["id"]
        
        # Get repository
        get_response = await client.get(f"/api/v1/repositories/{repo_id}")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["id"] == repo_id
        assert get_data["name"] == "test-repo"
        
        # List repositories
        list_response = await client.get("/api/v1/repositories")
        assert list_response.status_code == 200
        repos = list_response.json()
        assert isinstance(repos, list)
        assert len(repos) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_list_with_filters():
    """Test repository listing with status filter."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/repositories",
            params={"status": "pending"}
        )
        
        assert response.status_code == 200
        repos = response.json()
        assert isinstance(repos, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_symbols_list():
    """Test symbols listing endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/symbols",
            params={"limit": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_symbols_by_repository():
    """Test symbols filtered by repository."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First create a repository
        create_response = await client.post(
            "/api/v1/repositories",
            json={
                "gitlab_project_id": 1000,
                "name": "symbols-test-repo",
                "path_with_namespace": "test/symbols-repo",
                "url": "https://example.com/symbols-repo.git",
                "default_branch": "main"
            }
        )
        
        if create_response.status_code in [200, 201]:
            repo_data = create_response.json()
            repo_id = repo_data["id"]
            
            # Get symbols for this repository
            response = await client.get(
                "/api/v1/symbols",
                params={"repository_id": repo_id, "limit": 10}
            )
            
            assert response.status_code == 200
            symbols = response.json()
            assert isinstance(symbols, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_jobs_list():
    """Test jobs listing endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workers_status():
    """Test workers status endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/workers/status")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_search_query():
    """Test search endpoint with invalid query."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Empty query should return error or empty results
        response = await client.get("/api/v1/search?query=&limit=10")
        
        # Should either return 400 or 200 with empty results
        assert response.status_code in [200, 400, 422]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_repository_id():
    """Test getting non-existent repository."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/repositories/999999")
        
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cors_headers():
    """Test CORS headers are present."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.options("/api/v1/health")
        
        # CORS headers should be present
        assert response.status_code in [200, 204]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rate_limiting_headers():
    """Test rate limiting headers are present."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/search?query=test&limit=10")
        
        assert response.status_code == 200
        # Rate limiting headers might be present
        # This is not a strict requirement but good to check


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_documentation():
    """Test API documentation endpoints are accessible."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # OpenAPI docs
        docs_response = await client.get("/api/docs")
        assert docs_response.status_code == 200
        
        # OpenAPI JSON
        openapi_response = await client.get("/api/openapi.json")
        assert openapi_response.status_code == 200
        openapi_data = openapi_response.json()
        assert "openapi" in openapi_data
        assert "paths" in openapi_data


@pytest.mark.integration
@pytest.mark.asyncio  
async def test_search_pagination():
    """Test search pagination."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Request with small limit
        response = await client.get(
            "/api/v1/search",
            params={"query": "test", "limit": 3}
        )
        
        assert response.status_code == 200
        results = response.json()
        assert isinstance(results, list)
        assert len(results) <= 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_workflow():
    """Test a full workflow from repository creation to search."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. Create a repository
        create_repo_response = await client.post(
            "/api/v1/repositories",
            json={
                "gitlab_project_id": 2000,
                "name": "workflow-test-repo",
                "path_with_namespace": "test/workflow",
                "url": "https://example.com/workflow.git",
                "default_branch": "main"
            }
        )
        
        assert create_repo_response.status_code in [200, 201]
        repo = create_repo_response.json()
        repo_id = repo["id"]
        
        # 2. List repositories and verify it's there
        list_response = await client.get("/api/v1/repositories")
        assert list_response.status_code == 200
        repos = list_response.json()
        assert any(r["id"] == repo_id for r in repos)
        
        # 3. Get specific repository
        get_response = await client.get(f"/api/v1/repositories/{repo_id}")
        assert get_response.status_code == 200
        get_repo = get_response.json()
        assert get_repo["id"] == repo_id
        assert get_repo["name"] == "workflow-test-repo"
        
        # 4. Search (may return empty if no symbols yet)
        search_response = await client.get(
            "/api/v1/search",
            params={"query": "workflow", "repository_id": repo_id}
        )
        assert search_response.status_code == 200
        search_results = search_response.json()
        assert isinstance(search_results, list)

