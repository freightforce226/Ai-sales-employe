"""
Purpose of this file.
Pydantic schemas for OAuth flow.
Responsibility of this file.
Validating requests to initiate OAuth or handling the callback.
"""

from pydantic import BaseModel


class OAuthConnectResponse(BaseModel):
    authorization_url: str


class OAuthCallbackResponse(BaseModel):
    success: bool
    message: str
