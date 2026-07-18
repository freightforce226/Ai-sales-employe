"""
Purpose of this file.
Client for interacting with Microsoft Graph API.
Responsibility of this file.
Handling email delivery, API retries, rate limits, and Microsoft Graph specific errors.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import GraphApiError
from app.core.logging import get_logger

logger = get_logger(__name__)


class MicrosoftGraphClient:
    async def send_email(
        self, access_token: str, subject: str, html_content: str, to_email: str, attachments: list = None
    ) -> str:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_content
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email
                        }
                    }
                ]
            },
            "saveToSentItems": True
        }

        if attachments:
            payload["message"]["attachments"] = attachments

        logger.info("Executing Graph API request", to_email=to_email, subject=subject, attachment_count=len(attachments) if attachments else 0)

        # Configure extended timeout to avoid ReadTimeout on large attachments or slow requests
        timeout_config = httpx.Timeout(
            connect=10.0,
            read=60.0,
            write=60.0,
            pool=60.0
        )
        url = "https://graph.microsoft.com/v1.0/me/sendMail"

        async with httpx.AsyncClient(timeout=timeout_config) as client:
            try:
                logger.info("Executing Graph API request", url=url, has_attachments=bool(attachments))
                from app.core.debug_logger import log_to_request_file
                log_to_request_file(f"Executing Graph API request to: {url} | Headers: {headers}")

                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
                
                # GRAPH API COMPLETION LOGGING
                log_msg = (
                    f"POST completed\n"
                    f"Status Code: {response.status_code}\n"
                    f"Headers: {dict(response.headers)}\n"
                    f"Response Body: {response.text}"
                )
                log_to_request_file(log_msg)
                logger.info("Graph API response received", status_code=response.status_code, text=response.text, headers=dict(response.headers))

                if response.status_code == 202:
                    # Graph sendMail endpoint returns 202 Accepted on success
                    # Since it returns empty body, we parse header or return dummy message ID
                    # If response contains client-request-id in headers, return it
                    message_id = response.headers.get("client-request-id", "ACCEPTED")
                    return message_id

                # Handle client-side and server-side errors directly (no retry)
                logger.error("Graph API error response", status_code=response.status_code, response_text=response.text)
                raise GraphApiError(f"Graph API error {response.status_code}: {response.text}")
                
            except httpx.RequestError as e:
                logger.error("Network error communicating with Graph API", error=str(e))
                raise e

    async def fetch_inbox_messages_delta(self, access_token: str, delta_link: str = None) -> dict:
        """
        Fetch inbox messages using Microsoft Graph Delta Query API.
        If delta_link is provided, queries the delta link directly.
        Otherwise, starts a new delta synchronization.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        url = delta_link
        if not url:
            since_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            url = (
                f"https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?"
                f"$filter=receivedDateTime ge {since_date}"
                f"&$select=id,subject,body,conversationId,internetMessageId,replyTo,from,toRecipients,receivedDateTime,hasAttachments"
            )
            
        messages = []
        next_link = url
        new_delta_link = None
        
        timeout_config = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)
        
        # Simple retry loop for transient failures
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    while next_link:
                        logger.info("Executing Graph Delta API query", url=next_link)
                        res = await client.get(next_link, headers=headers)
                        if res.status_code == 410 or (res.status_code == 400 and "token" in res.text.lower()):
                            # Delta token expired. Discard token and restart delta sync from scratch
                            logger.warning("Graph Delta token expired/invalid. Restarting initial delta sync.")
                            since_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                            next_link = (
                                f"https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?"
                                f"$filter=receivedDateTime ge {since_date}"
                                f"&$select=id,subject,body,conversationId,internetMessageId,replyTo,from,toRecipients,receivedDateTime,hasAttachments"
                            )
                            messages = []
                            continue
                        elif res.status_code != 200:
                            logger.error("Graph Delta API error response", status_code=res.status_code, response_text=res.text)
                            raise GraphApiError(f"Graph Delta API error {res.status_code}: {res.text}")
                            
                        data = res.json()
                        if "value" in data:
                            messages.extend(data["value"])
                            
                        next_link = data.get("@odata.nextLink")
                        new_delta_link = data.get("@odata.deltaLink")
                        
                        if new_delta_link:
                            break
                    
                    # Fetch singleValueExtendedProperties for each message individually since delta does not support expand
                    for msg in messages:
                        msg_id = msg.get("id")
                        if msg_id:
                            logger.info("Fetching singleValueExtendedProperties for delta message", message_id=msg_id)
                            detail_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}?$expand=singleValueExtendedProperties($filter=id eq 'String 0x1042' or id eq 'String 0x1039')"
                            try:
                                detail_res = await client.get(detail_url, headers=headers)
                                if detail_res.status_code == 200:
                                    detail_data = detail_res.json()
                                    msg["singleValueExtendedProperties"] = detail_data.get("singleValueExtendedProperties", [])
                                else:
                                    logger.warning("Failed to fetch extended properties for message", message_id=msg_id, status_code=detail_res.status_code)
                            except Exception as detail_err:
                                logger.warning("Error fetching extended properties for message", message_id=msg_id, error=str(detail_err))
                                
                break # Success, exit retry loop
            except (httpx.RequestError, GraphApiError) as e:
                if attempt == max_retries - 1:
                    logger.error("Failed to query Graph Delta API after maximum retries", error=str(e))
                    raise e
                wait_time = 2 ** attempt
                logger.warning(f"Graph API transient error, retrying in {wait_time}s...", error=str(e))
                await asyncio.sleep(wait_time)
                
        return {
            "messages": messages,
            "delta_link": new_delta_link
        }


