# Security Defaults Migration Notes (2026-02-26)

This release hardens default runtime settings for safer out-of-the-box behavior.

## Changed defaults

1. `API_CORS_ORIGINS`
   - **Before:** `["*"]`
   - **Now:** `["http://localhost:3000", "http://127.0.0.1:3000"]`
   - **Why:** Browsers reject `Access-Control-Allow-Origin: *` when credentials are enabled. Explicit origins are required for cookie/header auth.

2. `MCP_AUTH_ENABLED`
   - **Before:** `false`
   - **Now:** `true`
   - **Why:** Prevent accidental unauthenticated MCP HTTP deployments.

3. `AZUREDEVOPS_SSL_VERIFY`
   - **Before:** `false`
   - **Now:** `true`
   - **Why:** TLS verification should be secure by default to reduce MITM risk.

## Runtime behavior changes

- CORS middleware now automatically disables credentialed CORS when `API_CORS_ORIGINS` contains `"*"`.
- Startup logs now emit warnings when:
  - wildcard CORS is configured (credentialed browser requests disabled), or
  - MCP HTTP transport is enabled while `MCP_AUTH_ENABLED=false`.

## Required operator actions

If your deployment depends on previous behavior, set explicit overrides:

- Legacy broad CORS (not recommended):
  - `API_CORS_ORIGINS=["*"]`
  - Note: Browser credentialed requests will still not work with wildcard origin by spec.

- Unauthenticated MCP HTTP for local/trusted use only:
  - `MCP_AUTH_ENABLED=false`

- Self-signed Azure DevOps instance with no trusted CA chain:
  - `AZUREDEVOPS_SSL_VERIFY=false`
  - Prefer importing your internal CA cert to restore verification.

## Safe onboarding checklist

1. Keep `MCP_AUTH_ENABLED=true` for any non-local environment.
2. Configure `API_CORS_ORIGINS` to exact frontend origins (scheme + host + port).
3. Keep `AZUREDEVOPS_SSL_VERIFY=true`; only disable as an explicit, temporary exception.
