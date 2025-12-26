# Setup Guide

## Prerequisites

**Required:**
- Python 3.11 or higher
- PostgreSQL 15+ with pgvector extension
- Redis 7+
- Git 2.30+

**Optional:**
- Docker & Docker Compose (recommended for local development)
- Kubernetes 1.24+ (for production deployment)
- OpenAI API key (for embeddings) OR local GPU for sentence-transformers

**System Requirements:**
- 8GB RAM minimum (16GB recommended)
- 20GB disk space for caching
- Network access to GitLab instance

## Installation

### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://devops.example.org/axon/devops/axon.mcp.server.git
cd axon.mcp.server

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Check service health
docker-compose logs -f api
```

### Option 2: Local Development

```bash
# Clone repository
git clone https://gitlab.example.org/axon/devops/axon.mcp.server.git
cd axon.mcp.server

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
make dev-install

# Start PostgreSQL and Redis (or use Docker for just these)
docker-compose -f docker/docker-compose.yml up -d postgres redis

# Run database migrations
alembic upgrade head

# Start API server
uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload

# In another terminal, start Celery worker
celery -A src.workers.celery_app.celery_app worker --loglevel=info
```

## Quick Start

Get up and running in 5 minutes:

```bash
# Clone the repository
git clone https://github.com/ali-kamali/Axon.MCP.Server.git
cd axon.mcp.server

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your GitLab token, OpenAI key, and database URL

# Start services with Docker Compose
make docker-up

# Run database migrations
make migrate

# Verify installation
curl http://localhost:8080/api/v1/health
```
