# 🌐 Axon MCP Server - Access URLs

Quick reference card for all service URLs after deployment.

---

## 🎨 User Interfaces

### 1. React Dashboard (Main UI) ⭐
```
🔗 http://localhost:80
```
**The primary interface** - Modern React dashboard for monitoring and management
- Service health status
- Repository management  
- System metrics
- Dark theme UI

---

### 2. Grafana Dashboards
```
🔗 http://localhost:3000
👤 Username: admin
🔑 Password: admin
```
Pre-configured monitoring dashboards
- API performance
- Repository sync status
- Search analytics
- System health

---

### 3. Prometheus
```
🔗 http://localhost:9090
```
Metrics collection and queries
- Raw metrics data
- Custom PromQL queries
- Alert management

---

### 4. API Documentation (Swagger)
```
🔗 http://localhost:8080/api/docs
```
Interactive REST API documentation
- Try API endpoints
- See request/response schemas
- Authentication testing

---

### 5. API Documentation (ReDoc)
```
🔗 http://localhost:8080/api/redoc
```
Alternative API documentation view
- Clean, readable format
- Searchable
- Printable

---

## 🔌 API Endpoints

### Health Check
```bash
GET http://localhost:8080/api/v1/health

# Example:
curl http://localhost:8080/api/v1/health
```

### Metrics
```bash
GET http://localhost:8080/api/v1/metrics

# Example:
curl http://localhost:8080/api/v1/metrics
```

### Search
```bash
GET http://localhost:8080/api/v1/search?query=YOUR_QUERY

# Example:
curl "http://localhost:8080/api/v1/search?query=authentication&limit=10"
```

### Repositories
```bash
GET  http://localhost:8080/api/v1/repositories
POST http://localhost:8080/api/v1/repositories/sync

# Example:
curl http://localhost:8080/api/v1/repositories
```

---

## 🤖 MCP Server

```
🔗 http://localhost:8000
```
Model Context Protocol server for ChatGPT integration

---

## 💾 Databases

### PostgreSQL
```
Host: localhost
Port: 5432
Database: axon_mcp
Username: axon
Password: password

# Connection String:
postgresql://axon:password@localhost:5432/axon_mcp
```

### Redis
```
Host: localhost
Port: 6379
Database: 0

# Connection String:
redis://localhost:6379/0
```

---

## 🏥 Health Check Endpoints

| Service | Health Endpoint |
|---------|----------------|
| UI | http://localhost:80/health |
| API | http://localhost:8080/api/v1/health |
| Prometheus | http://localhost:9090/-/healthy |
| Grafana | http://localhost:3000/api/health |

---

## 📊 Quick Check Script

Save this as `check-services.sh`:

```bash
#!/bin/bash

echo "🔍 Checking Axon MCP Server Services..."
echo ""

services=(
  "UI:http://localhost:80/health"
  "API:http://localhost:8080/api/v1/health"
  "Grafana:http://localhost:3000/api/health"
  "Prometheus:http://localhost:9090/-/healthy"
)

for service in "${services[@]}"; do
  name="${service%%:*}"
  url="${service#*:}"
  
  if curl -s -f "$url" > /dev/null 2>&1; then
    echo "✅ $name: UP"
  else
    echo "❌ $name: DOWN"
  fi
done

echo ""
echo "🎉 Visit the main UI at: http://localhost:80"
```

---

## 🚀 Deployment Command

```bash
# Start all services
make docker-up

# Or
docker-compose -f docker/docker-compose.yml up -d

# Wait 30-60 seconds for services to be ready
```

---

## 📱 Bookmark These URLs

**For Daily Use:**
- Main Dashboard: http://localhost:80
- API Docs: http://localhost:8080/api/docs

**For Monitoring:**
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090

**For Development:**
- API Health: http://localhost:8080/api/v1/health
- Swagger UI: http://localhost:8080/api/docs

---

## 🔄 Port Conflicts?

If any port is already in use, edit `docker/docker-compose.yml`:

```yaml
# Change port mapping (HOST:CONTAINER)
ui:
  ports:
    - "8888:80"  # Instead of "80:80"

api:
  ports:
    - "8081:8080"  # Instead of "8080:8080"
```

---

## 📞 Quick Support

**Service not accessible?**
```bash
# Check if services are running
docker-compose -f docker/docker-compose.yml ps

# View logs
docker-compose -f docker/docker-compose.yml logs -f [service-name]

# Restart a service
docker-compose -f docker/docker-compose.yml restart [service-name]
```

**Examples:**
```bash
docker logs axon-ui
docker logs axon-api
docker logs axon-postgres
```

---

## 🎯 Start Here!

**First time?** Visit these in order:

1. ✅ **http://localhost:80** - Main UI Dashboard
2. 📚 **http://localhost:8080/api/docs** - Explore the API
3. 📊 **http://localhost:3000** - Check monitoring in Grafana

---

**Need help?** See [QUICK_START.md](QUICK_START.md) for detailed setup instructions.

