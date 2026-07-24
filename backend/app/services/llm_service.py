"""
===========================================================

File:
llm_service.py

Purpose:
Generates raw text outputs using Google Gemini API.

Why this file exists:
Serves as the single backend entry point for all AI prompt generation across the application.

Used By:
AIReplyService
Other future AI features

Responsibilities:
- Call Gemini model via HTTP POST using httpx
- Implement exponential backoff retries for transient errors (429, 5xx) using tenacity
- Securely fetch API key from configuration settings
- Handle API exceptions and supply a safe fallback text response
- Log structured telemetry data while redacting sensitive content

===========================================================
"""

import time
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

PROMPT_VERSION = "1.0"

def is_temporary_error(exception: Exception) -> bool:
    """
    Determines if the exception is a transient HTTP error that should be retried.
    """
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in [429, 500, 502, 503, 504]
    if isinstance(exception, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    return False

class LLMService:
    """
    Centralized service for invoking LLM generations.
    """
    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model_name = "gemini-2.5-flash"
        self.endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"

    @retry(
        retry=retry_if_exception(is_temporary_error),
        stop=stop_after_attempt(3),  # 1 initial attempt + 2 retries
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def _execute_http_call(self, client: httpx.AsyncClient, payload: dict) -> httpx.Response:
        """
        Executes the raw HTTP request with tenacity retry rules.
        """
        res = await client.post(
            self.endpoint_url,
            json=payload,
            params={"key": self.api_key},
            headers={"Content-Type": "application/json"}
        )
        res.raise_for_status()
        return res

    async def generate_text(self, prompt: str, org_id: str = "N/A", thread_id: str = "N/A") -> str:
        """
        Sends the completed prompt to Gemini and returns the generated text.
        If generation fails or API key is not configured, falls back to a template reply.
        """
        if not self.api_key:
            logger.warning(
                "Gemini API key is not configured. Falling back to local draft generator.",
                org_id=org_id,
                thread_id=thread_id,
                prompt_version=PROMPT_VERSION
            )
            return self._get_fallback_reply()

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        start_time = time.time()
        success = False

        try:
            # Verbose logging of prompt only under explicit debug level
            if settings.log_level.upper() == "DEBUG":
                logger.debug(
                    "Sending prompt to Gemini API",
                    prompt=prompt,
                    prompt_version=PROMPT_VERSION
                )

            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await self._execute_http_call(client, payload)
                data = res.json()
                
                generated_text = data["candidates"][0]["content"]["parts"][0]["text"]
                text_out = generated_text.strip()
                
                success = True
                response_time = (time.time() - start_time) * 1000  # ms
                
                logger.info(
                    "LLM generation successful",
                    organization_id=org_id,
                    thread_id=thread_id,
                    provider="Google",
                    model=self.model_name,
                    response_time_ms=response_time,
                    success=success,
                    prompt_version=PROMPT_VERSION
                )
                return text_out
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000  # ms
            logger.error(
                "LLM generation failed",
                organization_id=org_id,
                thread_id=thread_id,
                provider="Google",
                model=self.model_name,
                response_time_ms=response_time,
                success=success,
                error=str(e),
                prompt_version=PROMPT_VERSION
            )

        return self._get_fallback_reply()

    def _get_fallback_reply(self) -> str:
        """
        Returns a high-quality human-sounding email draft as a fallback when Gemini is unavailable.
        """
        return (
            "Hi there,\n\n"
            "Thank you for the update. Our logistics team is currently reviewing your shipment details "
            "and we will get back to you shortly with the update. Let us know if there is anything "
            "else we should know in the meantime."
        )
