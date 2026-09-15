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
from typing import Callable, Optional, List, Dict
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

    async def _execute_http_call_for_model(
        self, client: httpx.AsyncClient, payload: dict, endpoint_url: str
    ) -> httpx.Response:
        """
        Executes the raw HTTP request with tenacity retry rules.
        """
        # Bounded tenacity retries for 429 and transient errors
        @retry(
            retry=retry_if_exception(is_temporary_error),
            stop=stop_after_attempt(2),  # 1 initial attempt + 1 retry
            wait=wait_exponential(multiplier=1, min=1, max=3),
            reraise=True
        )
        async def _call_with_retry():
            res = await client.post(
                endpoint_url,
                json=payload,
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"}
            )
            res.raise_for_status()
            return res

        return await _call_with_retry()

    async def generate_text(
        self, 
        prompt: str, 
        org_id: str = "N/A", 
        thread_id: str = "N/A", 
        raise_on_error: bool = False,
        validator: Optional[Callable[[str], bool]] = None
    ) -> str:
        """
        Sends the completed prompt to Gemini and returns the generated text.
        Implements a fallback chain: gemini-2.5-flash -> gemini-2.5-pro.
        If generation fails or API key is not configured, falls back to a template reply (unless raise_on_error=True).
        """
        if not self.api_key:
            logger.warning(
                "Gemini API key is not configured. Falling back to local draft generator.",
                org_id=org_id,
                thread_id=thread_id,
                prompt_version=PROMPT_VERSION
            )
            if raise_on_error:
                raise ValueError("Gemini API key is not configured.")
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

        # Bounded fallback chain
        models_to_try = ["gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-pro-latest"]
        last_exception = None

        # Verbose logging of prompt only under explicit debug level
        if settings.log_level.upper() == "DEBUG":
            logger.debug(
                "Sending prompt to Gemini API",
                prompt=prompt,
                prompt_version=PROMPT_VERSION
            )

        for attempt_idx, model_name in enumerate(models_to_try):
            start_time = time.time()
            success = False
            endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

            logger.info(
                "AI_GENERATION_ATTEMPT",
                provider="Google",
                model=model_name,
                attempt=attempt_idx + 1,
                organization_id=org_id,
                thread_id=thread_id
            )

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await self._execute_http_call_for_model(client, payload, endpoint_url)
                    data = res.json()
                    
                    generated_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    text_out = generated_text.strip()

                    # Run validator hook if provided
                    if validator is not None:
                        if not validator(text_out):
                            raise ValueError(f"AI response failed custom structural/constraint validation rules for model: {model_name}")
                    
                    success = True
                    response_time = (time.time() - start_time) * 1000  # ms
                    
                    logger.info(
                        "LLM generation successful",
                        organization_id=org_id,
                        thread_id=thread_id,
                        provider="Google",
                        model=model_name,
                        response_time_ms=response_time,
                        success=success,
                        prompt_version=PROMPT_VERSION
                    )
                    return text_out
                    
            except Exception as e:
                response_time = (time.time() - start_time) * 1000  # ms
                last_exception = e
                status_code = getattr(e, "response", None)
                if status_code:
                    status_code = status_code.status_code

                logger.error(
                    "AI_GENERATION_ATTEMPT_FAILED",
                    provider="Google",
                    model=model_name,
                    attempt=attempt_idx + 1,
                    status_code=status_code,
                    duration_ms=response_time,
                    error=str(e),
                    prompt_version=PROMPT_VERSION
                )
                # Continue loop to try next model in fallback chain

        # If all models in the chain failed
        if raise_on_error:
            raise RuntimeError(f"All AI models in the chain failed. Last error: {str(last_exception)}")

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

    async def generate_multimodal(
        self,
        prompt: str,
        images: List[Dict[str, str]],
        org_id: str = "N/A",
        thread_id: str = "N/A",
        raise_on_error: bool = False
    ) -> str:
        """
        Sends the text prompt along with image inputs (in base64 format) to Gemini Vision.
        """
        if not self.api_key:
            if raise_on_error:
                raise ValueError("Gemini API key is not configured.")
            return "[]"

        parts = [{"text": prompt}]
        for img in images:
            parts.append({
                "inlineData": {
                    "mimeType": img["mime_type"],
                    "data": img["data"]
                }
            })

        payload = {
            "contents": [
                {
                    "parts": parts
                }
            ]
        }

        models_to_try = ["gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-pro-latest"]
        last_exception = None

        for attempt_idx, model_name in enumerate(models_to_try):
            start_time = time.time()
            success = False
            endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

            logger.info(
                "AI_MULTIMODAL_ATTEMPT",
                provider="Google",
                model=model_name,
                attempt=attempt_idx + 1,
                organization_id=org_id,
                thread_id=thread_id
            )

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    res = await self._execute_http_call_for_model(client, payload, endpoint_url)
                    data = res.json()
                    generated_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    text_out = generated_text.strip()
                    success = True
                    response_time = (time.time() - start_time) * 1000  # ms
                    
                    logger.info(
                        "LLM multimodal generation successful",
                        organization_id=org_id,
                        thread_id=thread_id,
                        provider="Google",
                        model=model_name,
                        response_time_ms=response_time,
                        success=success
                    )
                    return text_out
            except Exception as e:
                response_time = (time.time() - start_time) * 1000  # ms
                last_exception = e
                status_code = getattr(e, "response", None)
                if status_code:
                    status_code = status_code.status_code

                logger.error(
                    "AI_MULTIMODAL_ATTEMPT_FAILED",
                    provider="Google",
                    model=model_name,
                    attempt=attempt_idx + 1,
                    status_code=status_code,
                    duration_ms=response_time,
                    error=str(e)
                )

        if raise_on_error:
            raise RuntimeError(f"All AI vision models failed content extraction. Last error: {str(last_exception)}")
        return "[]"
