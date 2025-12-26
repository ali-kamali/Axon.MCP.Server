# Deployment Guide

This guide will help you deploy the Axon MCP Server for remote AI access via HTTP.

## Deployment Options

### Option 1: Quick Deployment (Recommended)

Use the provided deployment script:

**Linux/macOS:**
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

**Windows:**
```powershell
.\scripts\deploy.ps1
```

### Option 2: Manual Deployment

```bash
# Build and start services
docker-compose -f docker/docker-compose.yml build
docker-compose -f docker/docker-compose.yml up -d

# Wait for services to start
sleep 30

# Check service health
curl http://localhost:8080/api/v1/health
curl http://localhost:8001/api/v1/health
```

## Remote Server Deployment

### 1. Cloud Server Setup

Deploy to your cloud server (AWS, GCP, Azure, etc.):

```bash
# Clone repository on server
git clone https://your-gitlab-instance.com/axon/devops/axon.mcp.server.git
cd axon.mcp.server

# Configure environment
cp .env.example .env
# Edit .env with your configuration

# Deploy
./scripts/deploy.sh
```

### 2. Firewall Configuration

Ensure these ports are open:

- **8001**: MCP HTTP transport (for AI connections)
- **8080**: REST API (optional, for management)
- **80**: UI Dashboard (optional)

### 3. Domain Setup (Optional)

For production, set up a domain with SSL:

```nginx
# Nginx configuration example
server {
    listen 443 ssl;
    server_name your-mcp-server.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /mcp {
        proxy_pass http://localhost:8001/mcp;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Kubernetes Deployment

```bash
# Apply Kubernetes manifests
kubectl apply -f k8s/

# Check deployment status
kubectl get pods -l app=axon-mcp-server

# View logs
kubectl logs -f deployment/axon-mcp-server
```

## Environment-Specific Configuration

- **Development**: Use Docker Compose with hot reload
- **Staging**: Kubernetes with limited resources
- **Production**: Kubernetes with auto-scaling, load balancing, and monitoring
