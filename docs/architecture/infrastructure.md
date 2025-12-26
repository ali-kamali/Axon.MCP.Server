# Infrastructure & Service Architecture

This document details the infrastructure setup, service orchestration, and networking of the Axon MCP Server, based on the `docker-compose.yml` and `nginx.conf` configurations.

## Service Map

The system is composed of the following containerized services, orchestrating via Docker Compose on the `axon-network`.

```mermaid
graph TD
    User[User / Browser] -->|HTTP :80| UI[UI (Nginx + React)]
    User -->|HTTP :8001| MCP[MCP Server]
    
    subgraph "Docker Network (axon-network)"
        UI -->|/api/*| API[API Server :8080]
        
        API --> DB[(PostgreSQL :5432)]
        API --> Redis[(Redis :6379)]
        
        MCP --> DB
        MCP --> Redis
        
        Worker[Celery Worker] --> DB
        Worker --> Redis
        
        Beat[Celery Beat] --> Redis
        
        Prometheus -->|Scrape| API
        Prometheus -->|Scrape| PostgresExp[Postgres Exporter]
        Prometheus -->|Scrape| RedisExp[Redis Exporter]
        
        Grafana -->|Query| Prometheus
    end
```

## Service Details

### 1. Frontend (`ui`)
- **Container**: `axon-ui`
- **Port**: Exposed on host `:80`.
- **Configuration**: `ui/nginx.conf`
- **Routing Logic**:
    - **Static Content**: Serves React/Vue assets from `/usr/share/nginx/html`.
    - **API Proxy**: Forwards requests matching `/api/*` to the backend service `http://api:8080`.
    - **SPA Fallback**: Redirects all non-file requests to `index.html` to support client-side routing.

### 2. Backend API (`api`)
- **Container**: `axon-api`
- **Port**: Internal `:8080`, Exposed `:8080`.
- **Command**: `uvicorn src.api.main:app`
- **Dependencies**: Waits for `postgres` and `redis` to be healthy.
- **Environment**:
    - `DATABASE_URL`: Connection to Postgres container.
    - `REDIS_URL`: Connection to Redis container.

### 3. MCP Server (`mcp-server`)
- **Container**: `axon-mcp-server`
- **Port**: Exposed `:8001`.
- **Transport**: HTTP (SSE).
- **Purpose**: Exposes the Model Context Protocol for AI agents (Claude, Cursor, etc.).

### 4. Background Workers
- **Worker (`worker`)**: Executes async tasks (repo syncing, parsing, embedding).
    - Queues: `repository_sync`, `file_parsing`, `embeddings`, `default`.
- **Beat (`beat`)**: Scheduler for periodic tasks.

### 5. Data Stores
- **PostgreSQL (`postgres`)**:
    - Image: `pgvector/pgvector:pg15` (Supports vector similarity search).
    - Volume: `postgres_data` (Persistent storage).
- **Redis (`redis`)**:
    - Image: `redis:7-alpine`.
    - Purpose: Caching and Celery message broker.

### 6. Observability
- **Prometheus**: Collects metrics from services and exporters.
- **Grafana**: Visualizes metrics (Dashboards on port `:3000`).
- **Exporters**: Sidecars for Postgres and Redis metrics.

## Networking
- **Network Name**: `axon-network` (Bridge driver).
- **Service Discovery**: Services communicate using their container names as hostnames (e.g., `api`, `postgres`, `redis`).

## Configuration Files
- **Docker Compose**: `docker/docker-compose.yml` - Defines the entire stack.
- **Nginx Config**: `ui/nginx.conf` - Defines frontend routing and API reverse proxying.
