# Migration script for Docker containers (PowerShell)
# This script applies Azure DevOps database migrations

Write-Host "🔄 Running Azure DevOps database migrations..." -ForegroundColor Cyan

try {
    # Run the migration script
    python scripts/run_migrations.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Migration completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "❌ Migration failed!" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} catch {
    Write-Host "💥 Migration failed with error: $_" -ForegroundColor Red
    exit 1
}
