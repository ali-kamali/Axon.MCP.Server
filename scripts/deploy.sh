#!/bin/bash

# Axon MCP Server Deployment Script
# This script helps deploy the MCP server for remote AI access

set -e

echo "🚀 Axon MCP Server Deployment Script"
echo "======================================"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file. Please edit it with your configuration."
    echo "📝 Required variables to set:"
    echo "   - GITLAB_TOKEN"
    echo "   - OPENAI_API_KEY (if using OpenAI embeddings)"
    echo "   - API_SECRET_KEY"
    echo "   - JWT_SECRET_KEY"
    echo ""
    echo "🔧 Generate secure keys with:"
    echo "   python -c 'import secrets; print(f\"API_SECRET_KEY={secrets.token_urlsafe(32)}\")'"
    echo "   python -c 'import secrets; print(f\"JWT_SECRET_KEY={secrets.token_urlsafe(64)}\")'"
    echo ""
    read -p "Press Enter after updating .env file..."
fi

# Build and start services
echo "🏗️  Building Docker images..."
docker-compose -f docker/docker-compose.yml build

echo "🚀 Starting services..."
docker-compose -f docker/docker-compose.yml up -d

echo "⏳ Waiting for services to be ready..."
sleep 30

# Check service health
echo "🔍 Checking service health..."

# Check API health
if curl -f http://localhost:8080/api/v1/health > /dev/null 2>&1; then
    echo "✅ API server is healthy"
else
    echo "❌ API server is not responding"
    exit 1
fi

# Check MCP HTTP endpoint
if curl -f http://localhost:8001/api/v1/health > /dev/null 2>&1; then
    echo "✅ MCP HTTP server is healthy"
else
    echo "❌ MCP HTTP server is not responding"
    exit 1
fi

# Check if Roslyn analyzer is available
echo "🔍 Checking Roslyn analyzer..."
if docker exec axon-api test -f /app/roslyn_analyzer/bin/Release/net9.0/RoslynAnalyzer.exe; then
    echo "✅ Roslyn analyzer is available (Hybrid mode enabled)"
else
    echo "⚠️  Roslyn analyzer not found (Tree-sitter only mode)"
    echo "   This is not critical - system will work with Tree-sitter only"
fi

echo ""
echo "🎉 Deployment successful!"
echo ""
echo "📋 Service URLs:"
echo "   🔗 API Server:        http://localhost:8080"
echo "   🔗 MCP HTTP Endpoint: http://localhost:8001/mcp"
echo "   🔗 API Documentation: http://localhost:8080/api/docs"
echo "   🔗 UI Dashboard:      http://localhost:80"
echo "   🔗 Grafana:          http://localhost:3000 (admin/admin)"
echo "   🔗 Prometheus:       http://localhost:9090"
echo ""
echo "🤖 For AI Integration:"
echo "   Use this URL in your AI client: http://your-server-ip:8001/mcp"
echo ""
echo "📝 Next steps:"
echo "   1. Configure your GitLab token and sync repositories"
echo "   2. Test the MCP endpoint with your AI client"
echo "   3. Monitor logs: docker-compose -f docker/docker-compose.yml logs -f"
echo ""
