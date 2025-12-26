#!/bin/bash

echo "🔍 Checking Axon MCP Server Services..."
echo ""

services=(
  "UI:http://localhost:80/health"
  "API:http://localhost:8080/api/v1/health"
  "Grafana:http://localhost:3000/api/health"
  "Prometheus:http://localhost:9090/-/healthy"
)

for service in "${services[@]}"; do
  name="${service%%:*}"
  url="${service#*:}"
  
  if curl -s -f "$url" > /dev/null 2>&1; then
    echo "✅ $name: UP"
  else
    echo "❌ $name: DOWN"
  fi
done

echo ""
echo "🌐 Service URLs:"
echo "   React Dashboard: http://localhost:80"
echo "   API Swagger:     http://localhost:8080/api/docs"
echo "   Grafana:         http://localhost:3000 (admin/admin)"
echo "   Prometheus:      http://localhost:9090"
echo ""
echo "🎉 Visit the main UI at: http://localhost:80"

