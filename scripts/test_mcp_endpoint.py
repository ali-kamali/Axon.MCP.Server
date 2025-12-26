#!/usr/bin/env python3
"""
Test script for MCP HTTP endpoint.
This script tests the MCP server HTTP transport functionality.
"""

import json
import requests
import sys
from typing import Dict, Any


def test_mcp_endpoint(base_url: str = "http://localhost:8001") -> bool:
    """Test MCP HTTP endpoint functionality."""
    
    print(f"Testing MCP HTTP endpoint at {base_url}")
    print("=" * 50)
    
    mcp_url = f"{base_url}/mcp"
    
    # Test 1: Initialize
    print("1. Testing initialize...")
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }
    
    try:
        response = requests.post(mcp_url, json=init_request, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                print("   ✅ Initialize successful")
                print(f"   📋 Server: {result['result']['serverInfo']['name']}")
            else:
                print(f"   ❌ Initialize failed: {result}")
                return False
        else:
            print(f"   ❌ HTTP error: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Request failed: {e}")
        return False
    
    # Test 2: List tools
    print("2️⃣  Testing tools/list...")
    list_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    try:
        response = requests.post(mcp_url, json=list_request, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if "result" in result and "tools" in result["result"]:
                tools = result["result"]["tools"]
                print(f"   ✅ Found {len(tools)} tools")
                for tool in tools:
                    print(f"      🔧 {tool['name']}: {tool['description']}")
            else:
                print(f"   ❌ List tools failed: {result}")
                return False
        else:
            print(f"   ❌ HTTP error: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Request failed: {e}")
        return False
    
    # Test 3: Call a tool (search_code)
    print("3️⃣  Testing tools/call (search_code)...")
    call_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "search_code",
            "arguments": {
                "query": "test",
                "limit": 5
            }
        }
    }
    
    try:
        response = requests.post(mcp_url, json=call_request, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                print("   ✅ Tool call successful")
                content = result["result"].get("content", [])
                print(f"   📄 Response content length: {len(content)} items")
            else:
                print(f"   ❌ Tool call failed: {result}")
                return False
        else:
            print(f"   ❌ HTTP error: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Request failed: {e}")
        return False
    
    print("")
    print("🎉 All tests passed! MCP HTTP endpoint is working correctly.")
    return True


def test_health_endpoint(base_url: str = "http://localhost:8001") -> bool:
    """Test health endpoint."""
    print(f"🏥 Testing health endpoint at {base_url}")
    
    try:
        response = requests.get(f"{base_url}/api/v1/health", timeout=10)
        if response.status_code == 200:
            print("   ✅ Health endpoint is working")
            return True
        else:
            print(f"   ❌ Health endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False


def main():
    """Main test function."""
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = "http://localhost:8001"
    
    print("MCP Server HTTP Transport Test")
    print("=" * 40)
    print(f"Target URL: {base_url}")
    print("")
    
    # Test health first
    if not test_health_endpoint(base_url):
        print("❌ Health check failed. Is the server running?")
        sys.exit(1)
    
    print("")
    
    # Test MCP functionality
    if test_mcp_endpoint(base_url):
        print("✅ All tests completed successfully!")
        print("")
        print("🤖 Your MCP server is ready for AI integration!")
        print(f"   Use this URL: {base_url}/mcp")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the server logs.")
        sys.exit(1)


if __name__ == "__main__":
    main()
