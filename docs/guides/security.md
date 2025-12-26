# Security Guide

## Security Features

- ✅ **JWT-based authentication** with token rotation
- ✅ **API rate limiting** (100 requests/minute default)
- ✅ **Secret scanning** before code indexing
- ✅ **Encrypted database connections** (SSL/TLS)
- ✅ **Comprehensive audit logging**
- ✅ **RBAC** for repository access
- ✅ **CORS protection** with origin whitelisting
- ✅ **Input validation** and sanitization

## Best Practices

1. **Never commit secrets**: Use environment variables or secret managers
2. **Rotate credentials**: Update tokens every 90 days
3. **Use SSH keys**: Prefer SSH over HTTPS for GitLab access
4. **Enable SSL**: Always use HTTPS in production
5. **Monitor audit logs**: Review security events regularly
6. **Update dependencies**: Run `safety check` weekly

## Secret Management

### Generate Secure Secrets

```bash
# Generate API secret key
python -c 'import secrets; print(f"API_SECRET_KEY={secrets.token_urlsafe(32)}")'

# Generate JWT secret key
python -c 'import secrets; print(f"JWT_SECRET_KEY={secrets.token_urlsafe(64)}")'
```

## Reporting Security Issues

Please report security vulnerabilities to: security@example.org
