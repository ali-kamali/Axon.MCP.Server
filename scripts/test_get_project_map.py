#!/usr/bin/env python3
"""
Test script to debug get_project_map MCP tool.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.mcp_server.tools.exploration import get_project_map


async def test_get_project_map():
    """Test get_project_map with a repository ID."""
    
    # Test with repository ID 65 (from the audit document)
    repository_id = 65
    
    print(f"Testing get_project_map with repository_id={repository_id}")
    print("=" * 60)
    
    try:
        result = await get_project_map(repository_id=repository_id, max_depth=2)
        
        print("\n✅ SUCCESS!")
        print("\nResult:")
        print("-" * 60)
        for content in result:
            print(content.text)
        print("-" * 60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_get_project_map())
    sys.exit(0 if success else 1)
