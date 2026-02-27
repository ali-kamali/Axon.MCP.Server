import secrets
from datetime import UTC, datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import Security, HTTPException, status, Depends, Request
from fastapi.security import APIKeyHeader
from fastapi.openapi.models import APIKey, APIKeyIn
from starlette.requests import HTTPConnection
from jose import jwt, JWTError

from src.config.settings import get_settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class CustomAPIKeyHeader(APIKeyHeader):
    """
    Custom APIKeyHeader that supports both Request and WebSocket connections.
    Includes the 'request' argument in __call__ which is missing in the base class when strict typing is enforced
    or when FastAPI injects dependencies into WebSockets.
    """
    async def __call__(self, request: HTTPConnection) -> Optional[str]:
        api_key = request.headers.get(self.model.name)
        if not api_key:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated"
                )
            else:
                return None
        return api_key

api_key_header = CustomAPIKeyHeader(name="X-API-Key", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a new JWT access token."""
    to_encode = data.copy()
    now_utc = datetime.now(UTC)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(minutes=get_settings().jwt_access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_settings().jwt_secret_key, algorithm=get_settings().jwt_algorithm)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[get_settings().jwt_algorithm])
        return payload
    except JWTError:
        return None


def get_token_from_cookie(request: HTTPConnection) -> Optional[str]:
    """Extract access token from secure cookie (works for Request and WebSocket)."""
    return request.cookies.get("access_token")


async def get_current_user(
    api_key: Optional[str] = Security(api_key_header),
    cookie_token: Optional[str] = Depends(get_token_from_cookie)
) -> Dict[str, Any]:
    """
    Validate Authentication (API Key OR Cookie).
    
    Raises:
        HTTPException: 401 if not authenticated
    """
    # Allow bypass in dev/test environments
    if not get_settings().auth_enabled:
        return {"user": "anonymous", "role": "admin"}
    
    # 1. Check API Key (Header) - Priority for CLI/MCP
    if api_key:
        if get_settings().admin_api_key and secrets.compare_digest(api_key, get_settings().admin_api_key):
             return {"user": "admin", "role": "admin"}
        
        for key in get_settings().read_only_api_keys:
            if secrets.compare_digest(api_key, key):
                 return {"user": "readonly", "role": "readonly"}
        
        # If key provided but invalid, log warning
        logger.warning("invalid_api_key_attempt", key_prefix=api_key[:8] if len(api_key) > 8 else "too_short")
    
    # 2. Check Cookie (Browser)
    if cookie_token:
        payload = verify_token(cookie_token)
        if payload:
            return {"user": payload.get("sub"), "role": payload.get("role", "admin")}
    
    # 3. Fail
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide X-API-Key header or login."
    )


async def get_current_user_mcp(
    api_key: Optional[str] = Security(api_key_header),
    cookie_token: Optional[str] = Depends(get_token_from_cookie)
) -> Dict[str, Any]:
    """
    MCP-specific auth that allows bypass via configuration.
    Used for MCP clients (like Claude Desktop) that may not support headers.
    """
    if not get_settings().mcp_auth_enabled:
        # Bypass auth for MCP if disabled
        return {"user": "mcp_client", "role": "admin"}
        
    return await get_current_user(api_key, cookie_token)
