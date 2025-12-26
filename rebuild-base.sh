#!/bin/bash
# Rebuild base image - run this when requirements.txt changes

set -e

echo "=========================================="
echo "Rebuilding Base Image"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}This will rebuild the base image with all dependencies.${NC}"
echo -e "${YELLOW}This takes 2-3 minutes but only needs to be done when requirements.txt changes.${NC}"
echo ""

# Enable BuildKit
export DOCKER_BUILDKIT=1

echo -e "${BLUE}Building base image...${NC}"
docker build -f docker/Dockerfile.base -t axon-base:latest --progress=plain .

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo -e "${GREEN}✓ Base Image Rebuilt Successfully!${NC}"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "  1. Rebuild services: docker compose -f docker/docker-compose.yml build"
    echo "  2. Deploy: docker compose -f docker/docker-compose.yml up -d"
    echo ""
    echo "Or run: ./deploy.sh"
else
    echo ""
    echo -e "${RED}✗ Base image build failed!${NC}"
    exit 1
fi
