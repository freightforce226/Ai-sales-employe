"""
Purpose of this file.
Client for interacting with Microsoft's OAuth endpoints.
Responsibility of this file.
Encapsulating all HTTP calls for generating URLs, exchanging codes, and refreshing tokens.
"""

from urllib.parse import urlencode

import httpx

from app.core.config import get_settings


class MicrosoftOAuthClient:
    def __init__(self):
        self.settings = get_settings()

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.ms_client_id,
            "response_type": "code",
            "redirect_uri": self.settings.ms_redirect_uri,
            "scope": self.settings.ms_scopes,
            "state": state,
            "response_mode": "query",
            "prompt": "consent",
        }
        return f"{self.settings.ms_authorize_url}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict:
        data = {
            "client_id": self.settings.ms_client_id,
            "client_secret": self.settings.ms_client_secret,
            "code": code,
            "redirect_uri": self.settings.ms_redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(self.settings.ms_token_url, data=data)
            response.raise_for_status()
            return response.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        data = {
            "client_id": self.settings.ms_client_id,
            "client_secret": self.settings.ms_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(self.settings.ms_token_url, data=data)
            response.raise_for_status()
            return response.json()

    async def get_user_email(self, access_token: str) -> str:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("mail") or data.get("userPrincipalName")
