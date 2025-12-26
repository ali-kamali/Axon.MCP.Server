#!/bin/bash
# Bash script for fast development builds
# This uses BuildKit and only rebuilds what changed

set -e

SERVICE=""
NO_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--service)
            SERVICE="$2"
            shift 2
            ;;
        -n|--no-build)
            NO_BUILD=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [-s|--service SERVICE] [-n|--no-build]"
            exit 1
            ;;
    esac
done

# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "=== Axon MCP Fast Build ==="

if [ "$NO_BUILD" = true ]; then
    echo "Restarting services without rebuild (code changes via volume mounts)..."
    if [ -n "$SERVICE" ]; then
        docker compose -f docker/docker-compose.yml restart "$SERVICE"
    else
        docker compose -f docker/docker-compose.yml restart
    fi
else
    echo "Building with BuildKit cache (much faster!)..."
    if [ -n "$SERVICE" ]; then
        echo "Building only: $SERVICE"
        docker compose -f docker/docker-compose.yml build "$SERVICE"
        docker compose -f docker/docker-compose.yml up -d "$SERVICE"
    else
        docker compose -f docker/docker-compose.yml build
        docker compose -f docker/docker-compose.yml up -d
    fi
fi

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Done!"
    echo ""
    echo "Useful commands:"
    echo "  View logs: docker compose -f docker/docker-compose.yml logs -f $SERVICE"
    echo "  Restart only: ./docker/build-scripts/quick-build.sh --service $SERVICE --no-build"
else
    echo ""
    echo "✗ Build failed!"
    exit 1
fi
