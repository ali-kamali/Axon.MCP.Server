# Axon MCP Server Deployment Script (PowerShell)
# This script helps deploy the MCP server for remote AI access

Write-Host "🚀 Axon MCP Server Deployment Script" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "❌ .env file not found. Creating from .env.example..." -ForegroundColor Red
    Copy-Item ".env.example" ".env"
    Write-Host "✅ Created .env file. Please edit it with your configuration." -ForegroundColor Green
    Write-Host "📝 Required variables to set:" -ForegroundColor Yellow
    Write-Host "   - GITLAB_TOKEN"
    Write-Host "   - OPENAI_API_KEY (if using OpenAI embeddings)"
    Write-Host "   - API_SECRET_KEY"
    Write-Host "   - JWT_SECRET_KEY"
    Write-Host ""
    Write-Host "🔧 Generate secure keys with:" -ForegroundColor Cyan
    Write-Host "   python -c 'import secrets; print(f`"API_SECRET_KEY={secrets.token_urlsafe(32)}`")'"
    Write-Host "   python -c 'import secrets; print(f`"JWT_SECRET_KEY={secrets.token_urlsafe(64)}`")'"
    Write-Host ""
    Read-Host "Press Enter after updating .env file"
}

# Build and start services
Write-Host "🏗️  Building Docker images..." -ForegroundColor Blue
docker-compose -f docker/docker-compose.yml build

Write-Host "🚀 Starting services..." -ForegroundColor Blue
docker-compose -f docker/docker-compose.yml up -d

Write-Host "⏳ Waiting for services to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Check service health
Write-Host "🔍 Checking service health..." -ForegroundColor Blue

# Check API health
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080/api/v1/health" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ API server is healthy" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ API server is not responding" -ForegroundColor Red
    exit 1
}

# Check MCP HTTP endpoint
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8001/api/v1/health" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ MCP HTTP server is healthy" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ MCP HTTP server is not responding" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🎉 Deployment successful!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Service URLs:" -ForegroundColor Cyan
Write-Host "   🔗 API Server:        http://localhost:8080"
Write-Host "   🔗 MCP HTTP Endpoint: http://localhost:8001/mcp"
Write-Host "   🔗 API Documentation: http://localhost:8080/api/docs"
Write-Host "   🔗 UI Dashboard:      http://localhost:80"
Write-Host "   🔗 Grafana:          http://localhost:3000 (admin/admin)"
Write-Host "   🔗 Prometheus:       http://localhost:9090"
Write-Host ""
Write-Host "🤖 For AI Integration:" -ForegroundColor Magenta
Write-Host "   Use this URL in your AI client: http://your-server-ip:8001/mcp"
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Yellow
Write-Host "   1. Configure your GitLab token and sync repositories"
Write-Host "   2. Test the MCP endpoint with your AI client"
Write-Host "   3. Monitor logs: docker-compose -f docker/docker-compose.yml logs -f"
Write-Host ""
