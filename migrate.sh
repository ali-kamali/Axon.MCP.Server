#!/bin/bash
# Migration script for Docker containers
# This script applies Azure DevOps database migrations

set -e

echo "🔄 Running Azure DevOps database migrations..."

# Run the migration script
python scripts/run_migrations.py

echo "✅ Migration completed!"
