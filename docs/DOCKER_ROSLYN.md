# Docker Deployment with Roslyn Analyzer

## Overview

The Axon MCP Server now includes hybrid C# parsing using both Tree-sitter and Roslyn for enhanced semantic analysis.

## Docker Setup

### Automatic Build

The Roslyn analyzer is **automatically built** during Docker image creation. No manual steps required!

```bash
# Build and start all services
docker-compose -f docker/docker-compose.yml up --build
```

### What Happens During Build

1. **Install .NET SDK 9.0** - Required to build and run Roslyn analyzer
2. **Build Roslyn Analyzer** - Compiles the C# semantic analysis tool
3. **Make Available** - Analyzer executable placed at `/app/roslyn_analyzer/bin/Release/net9.0/RoslynAnalyzer.exe`

### Hybrid Parsing Behavior

**Automatic Fallback:**
- If Roslyn analyzer is available → Hybrid mode (Tree-sitter + Roslyn)
- If Roslyn analyzer fails → Tree-sitter only mode
- System always works, Roslyn is an enhancement

**Check Status:**
```python
from src.parsers.roslyn_integration import RoslynAnalyzer

analyzer = RoslynAnalyzer()
if analyzer.is_available():
    print("Hybrid mode enabled")
else:
    print("Tree-sitter only mode")
```

## Performance Impact

**Image Size:**
- Base image: ~500MB
- With .NET SDK: ~700MB
- Trade-off: +200MB for significantly better C# analysis

**Build Time:**
- First build: +2-3 minutes (downloads .NET SDK)
- Subsequent builds: +30 seconds (cached layers)

**Runtime:**
- No performance impact
- Roslyn analyzer runs as subprocess only when needed

## Troubleshooting

### Roslyn Not Available in Container

Check if analyzer was built:
```bash
docker exec axon-api ls -la /app/roslyn_analyzer/bin/Release/net9.0/
```

Should see `RoslynAnalyzer.exe` and `RoslynAnalyzer.dll`

### Build Failures

If .NET SDK installation fails:
```bash
# Check logs
docker-compose -f docker/docker-compose.yml logs api

# Rebuild without cache
docker-compose -f docker/docker-compose.yml build --no-cache api
```

### Disable Roslyn (Fallback to Tree-sitter Only)

If you want to skip Roslyn:
1. Comment out the Roslyn build steps in `docker/Dockerfile.fast`
2. System will automatically use Tree-sitter only mode

## Verification

After deployment, verify hybrid mode is working:

```bash
# Enter container
docker exec -it axon-api bash

# Run test
python tests/test_roslyn_integration.py
```

Expected output:
```
[OK] Roslyn analyzer found at: /app/roslyn_analyzer/bin/Release/net9.0/RoslynAnalyzer.exe
[OK] Analysis successful!
```

## Production Deployment

For production, the Roslyn analyzer is included in the Docker image. No additional configuration needed.

**Environment Variables:**
- No special environment variables required
- Roslyn integration is automatic

**Resource Requirements:**
- Memory: +50MB per Roslyn analysis (temporary)
- CPU: Minimal impact (subprocess runs only when needed)
- Disk: +200MB for .NET SDK in image
