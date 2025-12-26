"""Authentication endpoints."""
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, status, Response, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import secrets

from src.api.auth import create_access_token
from src.config.settings import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

class LoginRequest(BaseModel):
    password: str

@router.post("/auth/login")
async def login(request: LoginRequest, response: Response):
    """
    Login with password to get session cookie.
    Used by UI to avoid exposing API keys in browser.
    """
    if not settings.admin_password:
        raise HTTPException(status_code=500, detail="Login disabled: ADMIN_PASSWORD not configured.")
        
    if not secrets.compare_digest(request.password, settings.admin_password):
        logger.warning("failed_login_attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    # Create token
    access_token = create_access_token(data={"sub": "admin", "role": "admin"})
    
    # Determine cookie security based on environment
    is_production = settings.environment.lower() == "production"
    
    # Set cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        path="/",  # Explicit: cookie sent to all paths
        httponly=True,
        secure=is_production,  # True in prod, False in dev
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60
    )
    
    logger.info("login_successful", user="admin")
    return {"message": "Logged in successfully"}

@router.post("/auth/logout")
async def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}
