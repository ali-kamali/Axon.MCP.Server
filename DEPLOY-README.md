# 🚀 Quick Deployment Reference

## After Git Pull - Run One Command:

```bash
# Make executable (first time only)
chmod +x deploy.sh quick-deploy.sh rebuild-base.sh

# Full deployment (recommended)
./deploy.sh

# OR for code changes only (fastest)
./quick-deploy.sh
```

---

## 📋 Scripts Overview

| Script | Use Case | Time |
|--------|----------|------|
| `./deploy.sh` | After git pull (normal) | 10-20s |
| `./quick-deploy.sh` | Code changes only | 2-5s |
| `./rebuild-base.sh` | requirements.txt changed | 2-3min |

---

## 🎯 What `deploy.sh` Does

✅ Fixes all permissions (chmod, chown)  
✅ Sets SELinux context (chcon)  
✅ Fixes specific files (sysadmin ownership)  
✅ Builds Docker images (with caching)  
✅ Deploys all services  
✅ Shows service status  

**All your manual commands in one script!**

---

## 📚 Full Documentation

- **Deployment Guide**: `DEPLOYMENT-GUIDE.md`
- **Docker Optimization**: `docker/OPTIMIZATION-SUMMARY.md`
- **Quick Start**: `docker/QUICK-START.md`

---

## ⚡ Performance

**Before:** Manual commands + 2-3 min build = 3-5 minutes  
**After:** `./deploy.sh` = 10-20 seconds  

**90% faster!** 🎉
