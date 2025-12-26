#!/bin/bash
# Quick deployment script - for code changes only (no rebuild)
# Use this when you've only changed code and don't need to rebuild

set -e

echo "=========================================="
echo "Axon MCP - Quick Deploy (No Rebuild)"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Fix Permissions
echo -e "${BLUE}[1/4] Setting permissions...${NC}"
chmod -R 755 src/ docker/ cache/ 2>/dev/null || true
chown -R 1000:1000 src/ docker/ cache/ 2>/dev/null || true

if command -v chcon &> /dev/null; then
    chcon -Rt svirt_sandbox_file_t src/ docker/ cache/ 2>/dev/null || true
fi
echo -e "${GREEN}✓ Permissions set${NC}"
echo ""

# Step 2: Fix Specific Files
echo -e "${BLUE}[2/4] Fixing specific files...${NC}"
[ -f "src/__init__.py" ] && sudo chown sysadmin:sysadmin src/__init__.py 2>/dev/null || true
[ -f "docker/alerts.yml" ] && sudo chown sysadmin:sysadmin docker/alerts.yml 2>/dev/null || true
[ -f "docker/prometheus.yml" ] && sudo chown sysadmin:sysadmin docker/prometheus.yml 2>/dev/null || true
echo -e "${GREEN}✓ Files fixed${NC}"
echo ""

# Step 3: Restart Services (no rebuild)
echo -e "${BLUE}[3/4] Restarting services...${NC}"
docker compose -f docker/docker-compose.yml restart
echo -e "${GREEN}✓ Services restarted${NC}"
echo ""

# Step 4: Show Status
echo -e "${BLUE}[4/4] Service status:${NC}"
docker compose -f docker/docker-compose.yml ps
echo ""

echo "=========================================="
echo -e "${GREEN}Quick Deploy Complete!${NC}"
echo "=========================================="
echo ""
echo "Note: This script only restarts services."
echo "For dependency changes, use: ./deploy.sh"
echo ""
