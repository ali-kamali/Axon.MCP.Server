# PowerShell script to start MCP UI Testing environment
# Run this script from the project root directory

Write-Host "🚀 Starting MCP Server UI Testing Environment" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 60) -ForegroundColor Cyan

# Check if we're in the project root
if (-not (Test-Path "src\mcp_server\server.py")) {
    Write-Host "❌ Error: Please run this script from the project root directory" -ForegroundColor Red
    exit 1
}

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  Warning: .env file not found. Make sure to configure your environment variables." -ForegroundColor Yellow
    Write-Host "   See docs/env.example.txt for reference" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "📋 Pre-flight Checks:" -ForegroundColor Yellow

# Check if Docker is running
Write-Host "  Checking Docker..." -NoNewline
try {
    docker ps | Out-Null
    Write-Host " ✅" -ForegroundColor Green
} catch {
    Write-Host " ❌" -ForegroundColor Red
    Write-Host "     Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check if Python is available
Write-Host "  Checking Python..." -NoNewline
try {
    python --version | Out-Null
    Write-Host " ✅" -ForegroundColor Green
} catch {
    Write-Host " ❌" -ForegroundColor Red
    Write-Host "     Python is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# Check if Node.js is available
Write-Host "  Checking Node.js..." -NoNewline
try {
    node --version | Out-Null
    Write-Host " ✅" -ForegroundColor Green
} catch {
    Write-Host " ❌" -ForegroundColor Red
    Write-Host "     Node.js is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🐳 Starting Docker Services..." -ForegroundColor Cyan

# Start Docker services
docker-compose -f docker/docker-compose.yml up -d postgres redis

# Wait for services to be ready
Write-Host "  Waiting for PostgreSQL to be ready..." -NoNewline
Start-Sleep -Seconds 3
Write-Host " ✅" -ForegroundColor Green

Write-Host ""
Write-Host "📦 Installing Dependencies..." -ForegroundColor Cyan

# Install Python dependencies if needed
if (-not (Test-Path "venv")) {
    Write-Host "  Creating virtual environment..."
    python -m venv venv
}

Write-Host "  Activating virtual environment..."
.\venv\Scripts\Activate.ps1

Write-Host "  Installing Python packages..."
pip install -r requirements.txt -q

# Install UI dependencies if needed
if (-not (Test-Path "ui\node_modules")) {
    Write-Host "  Installing UI packages..."
    Push-Location ui
    npm install
    Pop-Location
}

Write-Host ""
Write-Host "🎨 Starting Services..." -ForegroundColor Cyan

# Start API server in background
Write-Host "  Starting API server on http://localhost:8000..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; .\venv\Scripts\Activate.ps1; uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000"

# Wait a bit for API to start
Start-Sleep -Seconds 3

# Start UI in background
Write-Host "  Starting UI on http://localhost:5173..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD\ui'; npm run dev"

# Wait for UI to start
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "=" -ForegroundColor Green -NoNewline; Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "✅ MCP UI Testing Environment Started!" -ForegroundColor Green
Write-Host "=" -ForegroundColor Green -NoNewline; Write-Host ("=" * 60) -ForegroundColor Green
Write-Host ""
Write-Host "📍 Access Points:" -ForegroundColor Cyan
Write-Host "   🌐 UI:           http://localhost:5173" -ForegroundColor White
Write-Host "   🎯 MCP Test:     http://localhost:5173/mcp-test" -ForegroundColor White
Write-Host "   🔧 API:          http://localhost:8000" -ForegroundColor White
Write-Host "   📚 API Docs:     http://localhost:8000/api/docs" -ForegroundColor White
Write-Host ""
Write-Host "💡 Tips:" -ForegroundColor Yellow
Write-Host "   • Navigate to the 'MCP Test' page in the UI" -ForegroundColor White
Write-Host "   • Start by testing 'list_repositories' (no params needed)" -ForegroundColor White
Write-Host "   • Then try 'search_code' with query like 'function' or 'class'" -ForegroundColor White
Write-Host "   • Use symbol IDs from search results to test 'get_symbol_context'" -ForegroundColor White
Write-Host ""
Write-Host "📖 Documentation: See MCP_UI_TESTING_GUIDE.md" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the script. Services will continue running in separate windows." -ForegroundColor Gray
Write-Host ""

# Keep script running
while ($true) {
    Start-Sleep -Seconds 1
}


