"""
Purpose of this file.
Provides security dependencies for FastAPI endpoints.
Responsibility of this file.
Validating the X-API-Key header to ensure only authorized clients (like n8n) can access protected endpoints.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings, Settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key(
    api_key: str = Depends(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """
    Verify that the provided API key matches the configured N8N_SERVICE_API_KEY.
    """
    if api_key != settings.n8n_service_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API key",
        )
    return api_key
