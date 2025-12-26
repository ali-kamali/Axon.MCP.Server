#!/usr/bin/env python3
"""
Standalone migration runner for Docker containers.
This script applies all necessary database migrations including Azure DevOps support.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.auto_migrate import run_all_migrations
from src.utils.logging_config import configure_logging

async def main():
    """Run all database migrations."""
    # Setup logging
    configure_logging()
    
    print("🚀 Starting database migrations...")
    
    try:
        # Run all migrations
        success = await run_all_migrations()
        
        if success:
            print("✅ All migrations completed successfully!")
            return 0
        else:
            print("❌ Some migrations failed!")
            return 1
            
    except Exception as e:
        print(f"💥 Migration failed with error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
