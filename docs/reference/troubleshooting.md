# Troubleshooting Guide

## Common Issues

### API won't start
1. Check database connection: `DATABASE_URL` is correct
2. Verify PostgreSQL is running with pgvector extension
3. Check port 8080 is not in use: `netstat -an | grep 8080`
4. Review logs for specific errors

### Search returns no results
1. Ensure repositories are synced
2. Check data exists: `curl http://localhost:8080/api/v1/repositories`
3. Try simpler queries first
4. Check embeddings are generated

### Rate limiting too strict
1. Adjust `API_RATE_LIMIT` in settings
2. Modify rate limits in route decorators
3. Use multiple IPs for higher throughput

### Slow search performance
1. Check database indexes are created
2. Verify pgvector extension is installed
3. Review query complexity
4. Consider adding more workers

## Azure DevOps Authentication

### Issue: "No credentials were supplied" for Negotiate
**Cause**: System doesn't have Kerberos credentials.
**Fix**: Use PAT or Basic auth (disable NTLM configuration).

### Issue: "Authentication failed"
**Causes**:
- Wrong username/password
- Account locked or disabled
- Insufficient permissions
- PAT expired
**Fix**: Verify credentials, check account status, create new PAT.

### Issue: "SSL certificate problem"
**Cause**: Self-signed certificate.
**Fix**: Set `AZUREDEVOPS_SSL_VERIFY=false` (only for trusted networks!).

### Recommended Configuration for Azure DevOps

```bash
# Using Personal Access Token (RECOMMENDED)
AZUREDEVOPS_URL=https://dev.azure.com/your-organization/
AZUREDEVOPS_USERNAME=pat
AZUREDEVOPS_PASSWORD=your_personal_access_token_here
AZUREDEVOPS_USE_NTLM=false
AZUREDEVOPS_SSL_VERIFY=false
```

## Debug Mode

Enable debug logging:

```bash
LOG_LEVEL=DEBUG python -m src.mcp_server
```
