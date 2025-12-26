# UI Deployment Guide

This guide explains how to deploy the Axon MCP Server UI dashboard.

## Quick Start with Docker Compose

The UI is now integrated into the main `docker-compose.yml` file. To deploy:

```bash
# From the project root directory
cd docker
docker-compose up -d

# Or using Make
make docker-up
```

The UI will be available at: **http://localhost:80**

## Available UIs After Deployment

| Service | URL | Credentials |
|---------|-----|-------------|
| **React Dashboard** | http://localhost:80 | N/A |
| **Grafana** | http://localhost:3000 | admin/admin |
| **Prometheus** | http://localhost:9090 | N/A |
| **API Docs (Swagger)** | http://localhost:8080/api/docs | N/A |
| **API (Backend)** | http://localhost:8080 | N/A |

## Architecture

The UI service:
- Runs on **port 80** (default HTTP)
- Uses nginx to serve the static built files
- Proxies `/api/*` requests to the backend API service
- Has a health check endpoint at `/health`
- Automatically connects to the backend via Docker network

## Configuration

### Environment Variables

The UI uses build-time environment variables. If you need to change the API URL:

1. **For Docker deployment**, edit `docker/docker-compose.yml`:

```yaml
ui:
  build:
    context: ../ui
    dockerfile: Dockerfile
    args:
      - VITE_API_BASE_URL=http://api:8080
```

2. **For local development**, create `ui/.env`:

```env
VITE_API_BASE_URL=http://localhost:8080
```

### API Proxy

The nginx configuration automatically proxies API requests:
- Browser request: `http://localhost:80/api/v1/health`
- Proxied to: `http://api:8080/api/v1/health`

This eliminates CORS issues and provides a unified endpoint.

## Building the UI

### Docker Build

```bash
# Build the UI Docker image
cd ui
docker build -t axon-ui:latest .

# Run standalone
docker run -p 80:80 axon-ui:latest
```

### Local Build

```bash
cd ui
npm install
npm run build

# The built files will be in ui/dist/
# You can serve them with any static file server
```

## Deployment Options

### Option 1: Docker Compose (Recommended)

Already configured! Just run:

```bash
docker-compose -f docker/docker-compose.yml up -d
```

### Option 2: Standalone Docker

```bash
# Build
docker build -t axon-ui:latest ./ui

# Run (make sure backend is accessible)
docker run -d \
  --name axon-ui \
  -p 80:80 \
  --network axon-network \
  axon-ui:latest
```

### Option 3: Static Hosting

Build and deploy to any static hosting service:

```bash
cd ui
npm run build

# Deploy the dist/ folder to:
# - Vercel
# - Netlify
# - AWS S3 + CloudFront
# - Azure Static Web Apps
# - GitHub Pages
```

**Note**: For static hosting, you'll need to configure the API URL to point to your backend server.

## Production Considerations

### 1. HTTPS/SSL

For production, add SSL certificates:

```yaml
ui:
  ports:
    - "443:443"
  volumes:
    - ./ssl/cert.pem:/etc/nginx/ssl/cert.pem:ro
    - ./ssl/key.pem:/etc/nginx/ssl/key.pem:ro
```

Update `nginx.conf` to listen on 443.

### 2. Custom Domain

Point your domain to the server and update nginx:

```nginx
server_name yourdomain.com www.yourdomain.com;
```

### 3. Port Conflicts

If port 80 is already in use, change the mapping in `docker-compose.yml`:

```yaml
ui:
  ports:
    - "8888:80"  # Access at http://localhost:8888
```

### 4. Performance

The nginx configuration includes:
- Gzip compression for text files
- Cache headers for static assets (1 year)
- Health checks every 30 seconds

## Troubleshooting

### UI Container Won't Start

```bash
# Check logs
docker-compose logs ui

# Common issues:
# 1. Port 80 already in use - change port mapping
# 2. Build failed - check Node.js/npm versions
```

### Cannot Connect to API

```bash
# Verify backend is running
docker-compose ps

# Check if API is healthy
curl http://localhost:8080/api/v1/health

# Check nginx proxy configuration
docker exec axon-ui cat /etc/nginx/conf.d/default.conf
```

### Build Errors

```bash
# Clear Docker build cache
docker-compose build --no-cache ui

# Or rebuild from scratch
docker-compose down
docker-compose up -d --build
```

### CORS Issues

The nginx proxy should eliminate CORS issues. If you still see them:

1. Verify nginx is proxying correctly: check `ui/nginx.conf`
2. Ensure the backend API service name is `api` in Docker network
3. Check browser console for actual error messages

## Health Checks

The UI service includes health checks:

```bash
# Docker health check
docker inspect axon-ui | grep -A 10 Health

# Manual health check
curl http://localhost:80/health
```

## Monitoring

UI service logs:

```bash
# View logs
docker-compose logs -f ui

# Nginx access logs
docker exec axon-ui tail -f /var/log/nginx/access.log

# Nginx error logs
docker exec axon-ui tail -f /var/log/nginx/error.log
```

## Updating the UI

To deploy updates:

```bash
# 1. Pull latest code
git pull origin main

# 2. Rebuild and restart UI service only
docker-compose up -d --build ui

# 3. Verify deployment
curl http://localhost:80/health
```

## Uninstalling

```bash
# Stop and remove UI container
docker-compose stop ui
docker-compose rm -f ui

# Remove UI image
docker rmi axon-ui:latest
```

## Development vs Production

| Aspect | Development | Production (Docker) |
|--------|-------------|---------------------|
| Server | Vite dev server | nginx |
| Port | 5173 | 80 |
| Hot Reload | Yes | No |
| Source Maps | Yes | No |
| Minification | No | Yes |
| API Proxy | Vite proxy | nginx proxy |

## Support

For issues or questions:
- Check logs: `docker-compose logs ui`
- Review nginx config: `docker exec axon-ui cat /etc/nginx/conf.d/default.conf`
- API connectivity: `docker exec axon-ui wget -O- http://api:8080/api/v1/health`

