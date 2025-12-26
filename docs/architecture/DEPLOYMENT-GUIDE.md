# Deployment Guide

## 🚀 Quick Start

After `git pull`, run the appropriate script based on what changed:

### For Most Changes (Code + Permissions)
```bash
chmod +x deploy.sh
./deploy.sh
```

### For Code Changes Only (Fastest)
```bash
chmod +x quick-deploy.sh
./quick-deploy.sh
```

### For requirements.txt Changes
```bash
chmod +x rebuild-base.sh
./rebuild-base.sh
./deploy.sh
```

---

## 📝 Deployment Scripts

### 1. `deploy.sh` - Full Deployment
**Use when:** After git pull with code or config changes

**What it does:**
1. Sets directory permissions (755)
2. Sets ownership (1000:1000)
3. Sets SELinux context
4. Fixes specific file permissions
5. Builds Docker images (with base image caching)
6. Deploys services

**Time:** ~10-20 seconds (if base image exists)

```bash
./deploy.sh
```

---

### 2. `quick-deploy.sh` - Quick Restart
**Use when:** Only code changed, no dependency changes

**What it does:**
1. Sets basic permissions
2. Fixes specific files
3. Restarts services (no rebuild)

**Time:** ~2-5 seconds

```bash
./quick-deploy.sh
```

---

### 3. `rebuild-base.sh` - Rebuild Base Image
**Use when:** requirements.txt changed

**What it does:**
1. Rebuilds base image with all dependencies
2. Includes PyTorch and all pip packages

**Time:** ~2-3 minutes (only when requirements change)

```bash
./rebuild-base.sh
./deploy.sh
```

---

## 🔄 Common Workflows

### After Git Pull (Normal Changes)
```bash
git pull
./deploy.sh
```

### Quick Code Update
```bash
git pull
./quick-deploy.sh
```

### After Dependency Update
```bash
git pull
./rebuild-base.sh
./deploy.sh
```

### First Time Setup
```bash
git clone <repo>
cd Axon.MCP.Server
chmod +x *.sh docker/build-scripts/*.sh
./rebuild-base.sh  # Build base image first
./deploy.sh        # Deploy everything
```

---

## 📦 What Each Script Does

### `deploy.sh` - Full Deployment
- ✅ Permission fixes (chmod 755)
- ✅ Ownership fixes (chown 1000:1000)
- ✅ SELinux context (chcon)
- ✅ Specific file fixes (sysadmin:sysadmin)
- ✅ Docker build with BuildKit
- ✅ Base image check (builds if missing)
- ✅ Service deployment
- ✅ Status display

### `quick-deploy.sh` - Quick Restart
- ✅ Basic permission fixes
- ✅ Specific file fixes
- ✅ Service restart (no rebuild)
- ✅ Status display

### `rebuild-base.sh` - Base Image Rebuild
- ✅ Rebuilds base image
- ✅ Includes all dependencies
- ✅ Uses BuildKit for caching

---

## ⚡ Performance Comparison

| Scenario | Old Method | New Method | Time Saved |
|----------|-----------|------------|------------|
| **Code changes** | `docker compose build` (2-3 min) | `./quick-deploy.sh` (2-5 sec) | 99% |
| **Full deployment** | Manual commands (3-5 min) | `./deploy.sh` (10-20 sec) | 90% |
| **Dependency changes** | Full rebuild (2-3 min) | Base rebuild (2-3 min once) | Cached |

---

## 🔧 Manual Commands (If Needed)

### View Logs
```bash
docker compose -f docker/docker-compose.yml logs -f
docker compose -f docker/docker-compose.yml logs -f api
```

### Restart Specific Service
```bash
docker compose -f docker/docker-compose.yml restart api
```

### Stop All Services
```bash
docker compose -f docker/docker-compose.yml down
```

### Check Status
```bash
docker compose -f docker/docker-compose.yml ps
```

### Rebuild Everything from Scratch
```bash
docker compose -f docker/docker-compose.yml down -v
docker builder prune -a
./rebuild-base.sh
./deploy.sh
```

---

## 🐛 Troubleshooting

### Permission Denied
```bash
chmod +x deploy.sh quick-deploy.sh rebuild-base.sh
chmod +x docker/build-scripts/*.sh
```

### Base Image Not Found
```bash
./rebuild-base.sh
```

### Services Not Starting
```bash
# Check logs
docker compose -f docker/docker-compose.yml logs

# Rebuild everything
docker compose -f docker/docker-compose.yml down
./deploy.sh
```

### SELinux Issues
```bash
# Disable SELinux temporarily (for testing)
sudo setenforce 0

# Re-run deployment
./deploy.sh

# Re-enable SELinux
sudo setenforce 1
```

### Cache Issues
```bash
# Clear Docker cache
docker builder prune -a

# Rebuild base
./rebuild-base.sh
./deploy.sh
```

---

## 💡 Best Practices

1. **After git pull**: Always run `./deploy.sh` or `./quick-deploy.sh`
2. **For code changes only**: Use `./quick-deploy.sh` (fastest)
3. **For requirements.txt changes**: Run `./rebuild-base.sh` first
4. **Check logs**: Use `docker compose logs -f api` to monitor
5. **Keep base image updated**: Rebuild when dependencies change

---

## 📋 Checklist

### First Time Setup
- [ ] Clone repository
- [ ] Make scripts executable: `chmod +x *.sh docker/build-scripts/*.sh`
- [ ] Build base image: `./rebuild-base.sh`
- [ ] Deploy: `./deploy.sh`
- [ ] Verify: Check `docker compose ps`

### Regular Deployment
- [ ] Git pull latest changes
- [ ] Run `./deploy.sh` or `./quick-deploy.sh`
- [ ] Check logs: `docker compose logs -f`
- [ ] Verify services are running

### After Dependency Changes
- [ ] Update requirements.txt
- [ ] Run `./rebuild-base.sh`
- [ ] Run `./deploy.sh`
- [ ] Verify all services start correctly

---

## 🎯 Summary

**Three simple scripts for all deployment needs:**

1. **`./deploy.sh`** - Full deployment after git pull
2. **`./quick-deploy.sh`** - Quick restart for code changes
3. **`./rebuild-base.sh`** - Rebuild when requirements change

**No more manual permission fixes or long build times!** 🚀
