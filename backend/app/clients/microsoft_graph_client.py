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
        self,
        access_token: str,
        subject: str,
        html_content: str,
        to_email: str,
        cc_emails: list = None,
        bcc_emails: list = None,
        attachments: list = None
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

        if cc_emails:
            payload["message"]["ccRecipients"] = [
                {"emailAddress": {"address": str(email)}} for email in cc_emails
            ]

        if bcc_emails:
            payload["message"]["bccRecipients"] = [
                {"emailAddress": {"address": str(email)}} for email in bcc_emails
            ]

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

    async def get_sent_message_metadata(
        self, access_token: str, subject: str, to_email: str, max_retries: int = 4, delay_seconds: float = 0.5
    ) -> dict:
        """
        Polls the Sent Items folder for the most recently sent message matching the given subject
        to resolve conversationId, internetMessageId, conversationIndex, and Graph message ID.
        """
        import asyncio
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        # Escape subject quotes for the OData filter
        safe_subject = subject.replace("'", "''")
        
        # Filter by subject and order by receivedDateTime desc to get the latest
        url = f"https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages?$filter=subject eq '{safe_subject}'&$orderby=receivedDateTime desc&$select=id,conversationId,internetMessageId,conversationIndex&$top=5"
        
        start_time = time.perf_counter()
        
        for attempt in range(max_retries):
            try:
                # Add delay before polling to allow Graph to process
                await asyncio.sleep(delay_seconds)
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.get(url, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        messages = data.get("value", [])
                        
                        if messages:
                            msg = messages[0]
                            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                            logger.info(
                                "Sent Items retrieval completed successfully",
                                attempt=attempt + 1,
                                elapsed_ms=elapsed_ms,
                                conversation_id=msg.get("conversationId"),
                                internet_message_id=msg.get("internetMessageId")
                            )
                            return {
                                "id": msg.get("id"),
                                "conversation_id": msg.get("conversationId"),
                                "internet_message_id": msg.get("internetMessageId"),
                                "conversation_index": msg.get("conversationIndex"),
                                "retrieval_success": True,
                                "retrieval_time_ms": elapsed_ms
                            }
                            
                logger.info(f"Sent message not found in Sent Items on attempt {attempt + 1}, retrying...")
            except Exception as e:
                logger.warning(f"Error on Sent Items retrieval attempt {attempt + 1}: {str(e)}")
                
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.warning(f"Failed to retrieve sent message metadata from Sent Items", elapsed_ms=elapsed_ms)
        return {
            "id": None,
            "conversation_id": None,
            "internet_message_id": None,
            "conversation_index": None,
            "retrieval_success": False,
            "retrieval_time_ms": elapsed_ms
        }

    async def get_message_html(self, access_token: str, message_id: str) -> str:
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                body = res.json().get("body", {})
                return body.get("content", "")
        return "ERROR_FETCHING"

    async def create_reply_draft(self, access_token: str, parent_message_id: str) -> str:
        """
        Creates a draft reply to a specific parent message inside Outlook.
        Returns the draft message ID.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        url = f"https://graph.microsoft.com/v1.0/me/messages/{parent_message_id}/createReply"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            logger.info("Executing Graph API createReply draft request", parent_message_id=parent_message_id)
            res = await client.post(url, headers=headers, json={})
            if res.status_code in (200, 201):
                draft_id = res.json().get("id")
                logger.info("Successfully created reply draft", draft_id=draft_id)
                
                # Log Stage: Draft HTML immediately after createReply()
                draft_html = await self.get_message_html(access_token, draft_id)
                logger.info("Draft HTML immediately after createReply()", html_content=draft_html)
                
                return draft_id
            
            logger.error("Failed to create Graph reply draft", status_code=res.status_code, text=res.text)
            raise GraphApiError(f"Graph API createReply error {res.status_code}: {res.text}")

    async def update_message_draft(
        self,
        access_token: str,
        draft_id: str,
        html_content: str,
        cc_emails: list = None,
        bcc_emails: list = None
    ) -> None:
        """
        Updates a draft message's body content and CC/BCC recipients list.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        url = f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}"
        
        payload = {
            "body": {
                "contentType": "HTML",
                "content": html_content
            }
        }
        if cc_emails:
            payload["ccRecipients"] = [
                {"emailAddress": {"address": str(email)}} for email in cc_emails
            ]
        if bcc_emails:
            payload["bccRecipients"] = [
                {"emailAddress": {"address": str(email)}} for email in bcc_emails
            ]
            
        async with httpx.AsyncClient(timeout=15.0) as client:
            logger.info("Executing Graph API update draft request", draft_id=draft_id)
            res = await client.patch(url, headers=headers, json=payload)
            if res.status_code in (200, 204):
                logger.info("Successfully updated reply draft content", draft_id=draft_id)
                
                # Log Stage: Draft HTML immediately after PATCH
                draft_html = await self.get_message_html(access_token, draft_id)
                logger.info("Draft HTML immediately after PATCH", html_content=draft_html)
                
                return
                
            logger.error("Failed to update Graph reply draft", status_code=res.status_code, text=res.text)
            raise GraphApiError(f"Graph API patch draft error {res.status_code}: {res.text}")

    async def send_draft(self, access_token: str, draft_id: str) -> None:
        """
        Sends a prepared draft message.
        """
        # Log Stage: Draft HTML immediately before send
        draft_html = await self.get_message_html(access_token, draft_id)
        logger.info("Draft HTML immediately before send", html_content=draft_html)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Length": "0"
        }
        url = f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}/send"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("Executing Graph API send draft request", draft_id=draft_id)
            res = await client.post(url, headers=headers)
            if res.status_code in (202, 204):
                logger.info("Successfully sent reply draft", draft_id=draft_id)
                return
                
            logger.error("Failed to send Graph reply draft", status_code=res.status_code, text=res.text)
            raise GraphApiError(f"Graph API send draft error {res.status_code}: {res.text}")

    async def delete_draft(self, access_token: str, draft_id: str) -> None:
        """
        Deletes a draft message.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        url = f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            logger.info("Executing Graph API delete draft request", draft_id=draft_id)
            res = await client.delete(url, headers=headers)
            if res.status_code in (204, 404):
                logger.info("Successfully deleted draft", draft_id=draft_id)
                return
                
            logger.error("Failed to delete Graph draft", status_code=res.status_code, text=res.text)
            raise GraphApiError(f"Graph API delete draft error {res.status_code}: {res.text}")




