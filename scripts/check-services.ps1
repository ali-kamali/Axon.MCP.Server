# PowerShell script to check Axon MCP Server services
# Usage: .\scripts\check-services.ps1

Write-Host "🔍 Checking Axon MCP Server Services..." -ForegroundColor Cyan
Write-Host ""

$services = @(
    @{Name="UI"; Url="http://localhost:80/health"},
    @{Name="API"; Url="http://localhost:8080/api/v1/health"},
    @{Name="Grafana"; Url="http://localhost:3000/api/health"},
    @{Name="Prometheus"; Url="http://localhost:9090/-/healthy"}
)

foreach ($service in $services) {
    try {
        $response = Invoke-WebRequest -Uri $service.Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ $($service.Name): UP" -ForegroundColor Green
        } else {
            Write-Host "❌ $($service.Name): DOWN (Status: $($response.StatusCode))" -ForegroundColor Red
        }
    } catch {
        Write-Host "❌ $($service.Name): DOWN (Not responding)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "🌐 Service URLs:" -ForegroundColor Yellow
Write-Host "   React Dashboard: http://localhost:80"
Write-Host "   API Swagger:     http://localhost:8080/api/docs"
Write-Host "   Grafana:         http://localhost:3000 (admin/admin)"
Write-Host "   Prometheus:      http://localhost:9090"
Write-Host ""
Write-Host "🎉 Visit the main UI at: http://localhost:80" -ForegroundColor Green

