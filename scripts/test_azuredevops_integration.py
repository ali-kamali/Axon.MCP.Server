#!/usr/bin/env python3
"""
Test script for Azure DevOps integration.

This script tests the Azure DevOps client and integration components
to ensure they work correctly with your on-premises instance.

Usage:
    python scripts/test_azuredevops_integration.py
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import settings
from src.azuredevops.client import AzureDevOpsClient
from src.azuredevops.repository_manager import AzureDevOpsRepositoryManager
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def test_azure_devops_client():
    """Test Azure DevOps client functionality."""
    print("🔧 Testing Azure DevOps Client...")
    
    try:
        # Initialize client
        client = AzureDevOpsClient()
        print(f"✅ Client initialized for: {settings.azuredevops_url}")
        
        # Test connection
        if client.test_connection():
            print("✅ Connection test successful")
        else:
            print("❌ Connection test failed")
            return False
        
        # Test project listing (if project is configured)
        if settings.azuredevops_project:
            print(f"📋 Testing project: {settings.azuredevops_project}")
            
            try:
                project = client.get_project(settings.azuredevops_project)
                print(f"✅ Project found: {project['name']}")
                
                # Test repository listing
                repos = client.list_project_repositories(settings.azuredevops_project)
                print(f"✅ Found {len(repos)} repositories")
                
                if repos:
                    # Test first repository details
                    first_repo = repos[0]
                    repo_details = client.get_repository(
                        settings.azuredevops_project, 
                        first_repo['name']
                    )
                    print(f"✅ Repository details retrieved: {repo_details['name']}")
                    
                    # Test latest commit
                    commit = client.get_latest_commit(
                        settings.azuredevops_project,
                        first_repo['name']
                    )
                    if commit:
                        print(f"✅ Latest commit: {commit['sha'][:8]}")
                    
                    # Test file listing
                    files = client.list_repository_files(
                        settings.azuredevops_project,
                        first_repo['name'],
                        recursive=False
                    )
                    print(f"✅ Found {len(files)} files in root")
                
            except Exception as e:
                print(f"❌ Project operations failed: {str(e)}")
                return False
        else:
            print("⚠️  No default project configured, skipping project tests")
        
        return True
        
    except Exception as e:
        print(f"❌ Client test failed: {str(e)}")
        return False


def test_repository_manager():
    """Test Azure DevOps repository manager."""
    print("\n🗂️  Testing Azure DevOps Repository Manager...")
    
    try:
        manager = AzureDevOpsRepositoryManager()
        print("✅ Repository manager initialized")
        
        # Test cache directory creation
        cache_dir = manager.cache_dir
        if cache_dir.exists():
            print(f"✅ Cache directory exists: {cache_dir}")
        else:
            print(f"✅ Cache directory will be created: {cache_dir}")
        
        # Test path generation
        test_path = manager.get_repository_path("TestProject", "TestRepo")
        expected_path = cache_dir / "azuredevops" / "TestProject" / "TestRepo"
        if test_path == expected_path:
            print("✅ Repository path generation works correctly")
        else:
            print(f"❌ Path generation failed: {test_path} != {expected_path}")
            return False
        
        # Test cached repositories listing
        cached = manager.list_cached_repositories()
        print(f"✅ Found {len(cached)} cached repositories")
        
        return True
        
    except Exception as e:
        print(f"❌ Repository manager test failed: {str(e)}")
        return False


async def test_database_migration():
    """Test database migration for Azure DevOps support."""
    print("\n🗄️  Testing Database Migration...")
    
    try:
        from scripts.auto_migrate import migrate_azuredevops_support
        
        # Test migration
        success = await migrate_azuredevops_support()
        if success:
            print("✅ Azure DevOps migration completed successfully")
        else:
            print("❌ Azure DevOps migration failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Migration test failed: {str(e)}")
        return False


def test_configuration():
    """Test configuration settings."""
    print("\n⚙️  Testing Configuration...")
    
    required_settings = [
        ('azuredevops_url', settings.azuredevops_url),
        ('azuredevops_username', settings.azuredevops_username),
        ('azuredevops_password', settings.azuredevops_password),
    ]
    
    all_configured = True
    for setting_name, setting_value in required_settings:
        if setting_value:
            print(f"✅ {setting_name}: configured")
        else:
            print(f"❌ {setting_name}: not configured")
            all_configured = False
    
    if settings.azuredevops_project:
        print(f"✅ azuredevops_project: {settings.azuredevops_project}")
    else:
        print("⚠️  azuredevops_project: not configured (optional)")
    
    return all_configured


async def main():
    """Main test function."""
    print("🚀 Azure DevOps Integration Test Suite")
    print("=" * 50)
    
    tests = [
        ("Configuration", test_configuration),
        ("Azure DevOps Client", test_azure_devops_client),
        ("Repository Manager", test_repository_manager),
        ("Database Migration", test_database_migration),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} test crashed: {str(e)}")
            results[test_name] = False
    
    # Summary
    print("\n📊 Test Results Summary")
    print("=" * 30)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Azure DevOps integration is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the configuration and setup.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
