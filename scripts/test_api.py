#!/usr/bin/env python3
"""Test script to verify FastAPI REST API functionality."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from src.config.settings import settings


async def test_health_endpoints():
    """Test health check endpoints."""
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    
    async with httpx.AsyncClient() as client:
        print("Testing Health Endpoints...")
        print("-" * 50)
        
        # Test basic health check
        try:
            response = await client.get(f"{base_url}/api/v1/health", timeout=5.0)
            print(f"✓ Health check: {response.status_code}")
            print(f"  Response: {response.json()}")
        except Exception as e:
            print(f"✗ Health check failed: {e}")
            return False
        
        # Test readiness probe
        try:
            response = await client.get(f"{base_url}/api/v1/health/ready", timeout=5.0)
            print(f"✓ Readiness check: {response.status_code}")
        except Exception as e:
            print(f"✗ Readiness check failed: {e}")
        
        # Test liveness probe
        try:
            response = await client.get(f"{base_url}/api/v1/health/live", timeout=5.0)
            print(f"✓ Liveness check: {response.status_code}")
        except Exception as e:
            print(f"✗ Liveness check failed: {e}")
        
        # Test metrics endpoint
        try:
            response = await client.get(f"{base_url}/api/v1/metrics", timeout=5.0)
            print(f"✓ Metrics endpoint: {response.status_code}")
            print(f"  Content-Type: {response.headers.get('content-type')}")
        except Exception as e:
            print(f"✗ Metrics endpoint failed: {e}")
        
        print()
        return True


async def test_openapi_docs():
    """Test OpenAPI documentation endpoints."""
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    
    async with httpx.AsyncClient() as client:
        print("Testing OpenAPI Documentation...")
        print("-" * 50)
        
        # Test OpenAPI JSON
        try:
            response = await client.get(f"{base_url}/api/openapi.json", timeout=5.0)
            print(f"✓ OpenAPI JSON: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"  Title: {data.get('info', {}).get('title')}")
                print(f"  Version: {data.get('info', {}).get('version')}")
                print(f"  Paths: {len(data.get('paths', {}))}")
        except Exception as e:
            print(f"✗ OpenAPI JSON failed: {e}")
        
        # Test Swagger UI
        try:
            response = await client.get(f"{base_url}/api/docs", timeout=5.0)
            print(f"✓ Swagger UI: {response.status_code}")
        except Exception as e:
            print(f"✗ Swagger UI failed: {e}")
        
        # Test ReDoc
        try:
            response = await client.get(f"{base_url}/api/redoc", timeout=5.0)
            print(f"✓ ReDoc: {response.status_code}")
        except Exception as e:
            print(f"✗ ReDoc failed: {e}")
        
        print()


async def test_search_endpoint():
    """Test search endpoint (requires data)."""
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    
    async with httpx.AsyncClient() as client:
        print("Testing Search Endpoint...")
        print("-" * 50)
        
        try:
            response = await client.get(
                f"{base_url}/api/v1/search",
                params={"query": "test", "limit": 5},
                timeout=10.0
            )
            print(f"✓ Search endpoint: {response.status_code}")
            if response.status_code == 200:
                results = response.json()
                print(f"  Results: {len(results)}")
            elif response.status_code == 422:
                print(f"  Validation error (expected if no data): {response.json()}")
        except Exception as e:
            print(f"✗ Search endpoint failed: {e}")
        
        print()


async def test_repository_endpoints():
    """Test repository endpoints."""
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    
    async with httpx.AsyncClient() as client:
        print("Testing Repository Endpoints...")
        print("-" * 50)
        
        # Test list repositories
        try:
            response = await client.get(
                f"{base_url}/api/v1/repositories",
                params={"skip": 0, "limit": 10},
                timeout=5.0
            )
            print(f"✓ List repositories: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"  Total: {data.get('total', 0)}")
                print(f"  Items: {len(data.get('items', []))}")
        except Exception as e:
            print(f"✗ List repositories failed: {e}")
        
        print()


async def test_rate_limiting():
    """Test rate limiting (requires multiple requests)."""
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    
    async with httpx.AsyncClient() as client:
        print("Testing Rate Limiting...")
        print("-" * 50)
        
        # Make multiple rapid requests to trigger rate limiting
        try:
            success_count = 0
            rate_limited = False
            
            for i in range(35):  # Limit is 30/minute
                response = await client.get(
                    f"{base_url}/api/v1/search",
                    params={"query": "test", "limit": 1},
                    timeout=5.0
                )
                if response.status_code == 429:
                    rate_limited = True
                    print(f"✓ Rate limiting triggered after {i+1} requests")
                    break
                elif response.status_code in [200, 422]:
                    success_count += 1
            
            if not rate_limited:
                print(f"  Made {success_count} requests (rate limit not reached)")
        except Exception as e:
            print(f"✗ Rate limiting test failed: {e}")
        
        print()


async def main():
    """Run all API tests."""
    print("\n" + "=" * 50)
    print("FastAPI REST API Verification")
    print("=" * 50 + "\n")
    
    print(f"API URL: http://{settings.api_host}:{settings.api_port}")
    print(f"Environment: {settings.environment}")
    print()
    
    # Check if API is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{settings.api_host}:{settings.api_port}/api/v1/health",
                timeout=5.0
            )
            if response.status_code != 200:
                print("❌ API is not responding correctly!")
                print("   Please start the API server with:")
                print("   python -m src.api.main")
                return
    except Exception as e:
        print("❌ Cannot connect to API server!")
        print(f"   Error: {e}")
        print()
        print("   Please start the API server with:")
        print("   python -m src.api.main")
        print("   or")
        print("   uvicorn src.api.main:app --host 0.0.0.0 --port 8080")
        return
    
    print("✓ API server is running!\n")
    
    # Run tests
    await test_health_endpoints()
    await test_openapi_docs()
    await test_repository_endpoints()
    await test_search_endpoint()
    await test_rate_limiting()
    
    print("=" * 50)
    print("Verification Complete!")
    print("=" * 50)
    print()
    print("📚 Documentation available at:")
    print(f"   Swagger UI: http://{settings.api_host}:{settings.api_port}/api/docs")
    print(f"   ReDoc:      http://{settings.api_host}:{settings.api_port}/api/redoc")
    print(f"   OpenAPI:    http://{settings.api_host}:{settings.api_port}/api/openapi.json")
    print()


if __name__ == "__main__":
    asyncio.run(main())

