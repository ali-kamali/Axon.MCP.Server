#!/bin/bash
# Bash script to build the base image with all dependencies
# Run this once, or whenever requirements.txt changes

set -e

echo "Building base image with all dependencies (including PyTorch)..."
echo "This will take a while the first time, but subsequent builds will be much faster."

export DOCKER_BUILDKIT=1

docker build \
    -f docker/Dockerfile.base \
    -t axon-base:latest \
    --progress=plain \
    .

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Base image built successfully!"
    echo "You can now use 'docker compose build' which will be much faster."
else
    echo ""
    echo "✗ Base image build failed!"
    exit 1
fi
