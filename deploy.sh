#!/bin/bash
# Axon MCP Server - Complete Deployment Script
# Run this after git pull to set permissions, build, and deploy

set -e

echo "=========================================="
echo "Axon MCP Server - Deployment Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Fix Permissions
echo -e "${BLUE}[1/6] Setting directory permissions (755)...${NC}"
chmod -R 755 assets/ 2>/dev/null || true
chmod -R 755 scripts/ 2>/dev/null || true
chmod -R 755 src/
chmod -R 755 docker/
chmod -R 755 cache/ 2>/dev/null || mkdir -p cache && chmod -R 755 cache/
chmod -R 755 ui/ 2>/dev/null || true
echo -e "${GREEN}✓ Permissions set${NC}"
echo ""

# Step 2: Set Ownership
echo -e "${BLUE}[2/6] Setting directory ownership (1000:1000)...${NC}"
chown -R 1000:1000 assets/ 2>/dev/null || true
chown -R 1000:1000 scripts/ 2>/dev/null || true
chown -R 1000:1000 src/
chown -R 1000:1000 docker/
chown -R 1000:1000 cache/
chown -R 1000:1000 ui/ 2>/dev/null || true
echo -e "${GREEN}✓ Ownership set${NC}"
echo ""

# Step 3: Set SELinux Context
echo -e "${BLUE}[3/6] Setting SELinux context...${NC}"
if command -v chcon &> /dev/null; then
    chcon -Rt svirt_sandbox_file_t assets/ 2>/dev/null || true
    chcon -Rt svirt_sandbox_file_t scripts/ 2>/dev/null || true
    chcon -Rt svirt_sandbox_file_t src/
    chcon -Rt svirt_sandbox_file_t docker/
    chcon -Rt svirt_sandbox_file_t cache/
    chcon -Rt svirt_sandbox_file_t ui/ 2>/dev/null || true
    echo -e "${GREEN}✓ SELinux context set${NC}"
else
    echo -e "${YELLOW}⚠ SELinux not available, skipping...${NC}"
fi
echo ""

# Step 4: Fix Specific Files
echo -e "${BLUE}[4/6] Fixing specific file permissions...${NC}"
if [ -f "src/__init__.py" ]; then
    sudo chown sysadmin:sysadmin src/__init__.py 2>/dev/null || chown $(whoami):$(whoami) src/__init__.py
fi

if [ -f "docker/alerts.yml" ]; then
    sudo chown sysadmin:sysadmin docker/alerts.yml 2>/dev/null || chown $(whoami):$(whoami) docker/alerts.yml
    if command -v chcon &> /dev/null; then
        sudo chcon -Rt svirt_sandbox_file_t docker/alerts.yml 2>/dev/null || true
    fi
fi

if [ -f "docker/prometheus.yml" ]; then
    sudo chown sysadmin:sysadmin docker/prometheus.yml 2>/dev/null || chown $(whoami):$(whoami) docker/prometheus.yml
    if command -v chcon &> /dev/null; then
        sudo chcon -Rt svirt_sandbox_file_t docker/prometheus.yml 2>/dev/null || true
    fi
fi
echo -e "${GREEN}✓ Specific files fixed${NC}"
echo ""

# Step 5: Build with BuildKit
echo -e "${BLUE}[5/6] Building Docker images with BuildKit...${NC}"
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Check if base image exists
if ! docker images | grep -q "axon-base"; then
    echo -e "${YELLOW}⚠ Base image not found. Building base image first...${NC}"
    echo -e "${YELLOW}  This will take 2-3 minutes but only needs to be done once.${NC}"
    docker build -f docker/Dockerfile.base -t axon-base:latest .
    echo -e "${GREEN}✓ Base image built${NC}"
fi

echo "Building application images..."
docker compose --env-file .env -f docker/docker-compose.yml build
echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Step 6: Deploy
echo -e "${BLUE}[6/6] Deploying services...${NC}"
docker compose --env-file .env -f docker/docker-compose.yml down
docker compose --env-file .env -f docker/docker-compose.yml up -d
echo -e "${GREEN}✓ Services deployed${NC}"
echo ""

# Verify Roslyn analyzer
echo -e "${BLUE}Verifying Roslyn analyzer...${NC}"
sleep 5  # Wait for containers to start
if docker exec axon-api test -f /app/roslyn_analyzer/bin/Release/net9.0/RoslynAnalyzer.dll 2>/dev/null; then
    echo -e "${GREEN}✓ Roslyn analyzer available (Hybrid mode)${NC}"
else
    echo -e "${YELLOW}⚠ Roslyn analyzer not found (Tree-sitter only mode)${NC}"
fi
echo ""

# Show status
echo "=========================================="
echo -e "${GREEN}Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Service Status:"
docker compose --env-file .env -f docker/docker-compose.yml ps
echo ""
echo "Useful commands:"
echo "  View logs:    docker compose --env-file .env -f docker/docker-compose.yml logs -f"
echo "  View API logs: docker compose --env-file .env -f docker/docker-compose.yml logs -f api"
echo "  Stop all:     docker compose --env-file .env -f docker/docker-compose.yml down"
echo "  Restart API:  docker compose --env-file .env -f docker/docker-compose.yml restart api"
echo ""
