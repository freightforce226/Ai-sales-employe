from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import BaseEmailProvider
from app.clients.microsoft_graph_client import MicrosoftGraphClient
from app.services.token_service import TokenService

class MicrosoftGraphProvider(BaseEmailProvider):
    def __init__(self):
        self.graph_client = MicrosoftGraphClient()

    async def _get_access_token(self, org_id: UUID, db_session: AsyncSession) -> str:
        token_service = TokenService(db_session)
        return await token_service.get_valid_access_token(org_id)

    async def send_email(
        self,
        org_id: UUID,
        recipient: str,
        subject: str,
        html_body: str,
        cc_emails: List[str],
        bcc_emails: List[str],
        attachments: List[Dict[str, Any]],
        db_session: AsyncSession
    ) -> str:
        access_token = await self._get_access_token(org_id, db_session)
        return await self.graph_client.send_email(
            access_token=access_token,
            subject=subject,
            html_content=html_body,
            to_email=recipient,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            attachments=attachments
        )

    async def send_reply(
        self,
        org_id: UUID,
        parent_message_id: str,
        html_body: str,
        cc_emails: List[str],
        bcc_emails: List[str],
        attachments: List[Dict[str, Any]],
        db_session: AsyncSession
    ) -> str:
        import asyncio
        import httpx
        from app.core.logging import get_logger
        from app.core.debug_logger import log_to_request_file
        
        logger = get_logger(__name__)
        access_token = await self._get_access_token(org_id, db_session)
        
        draft_id = None
        max_attempts = 3
        last_err = None
        
        for attempt in range(max_attempts):
            try:
                # 1. Create draft reply
                draft_id = await self.graph_client.create_reply_draft(access_token, parent_message_id)
                
                # 2. Update draft body and CC/BCC list
                await self.graph_client.update_message_draft(
                    access_token=access_token,
                    draft_id=draft_id,
                    html_content=html_body,
                    cc_emails=cc_emails,
                    bcc_emails=bcc_emails
                )
                
                # 3. Add attachments if present
                if attachments:
                    for attachment in attachments:
                        attach_url = f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}/attachments"
                        headers_att = {
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        }
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            res_att = await client.post(attach_url, headers=headers_att, json=attachment)
                            if res_att.status_code not in (200, 201):
                                raise Exception(f"Failed to upload attachment: {res_att.text}")
                                
                # 4. Send draft reply
                await self.graph_client.send_draft(access_token, draft_id)
                
                logger.info("Successfully executed Graph reply flow")
                log_to_request_file("Successfully executed Graph reply flow")
                return draft_id
            except Exception as attempt_err:
                last_err = attempt_err
                logger.warning(f"Threaded reply attempt {attempt+1} failed: {str(attempt_err)}")
                log_to_request_file(f"Threaded reply attempt {attempt+1} failed: {str(attempt_err)}")
                
                # Cleanup draft if created
                if draft_id:
                    try:
                        await self.graph_client.delete_draft(access_token, draft_id)
                        log_to_request_file(f"Successfully cleaned up draft: {draft_id}")
                    except Exception as del_err:
                        logger.warning("Failed to delete failed draft during cleanup", error=str(del_err))
                    draft_id = None
                    
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2 ** attempt)
        else:
            logger.error("All threaded reply attempts failed. Aborting dispatch.")
            raise last_err

    async def get_sent_metadata(
        self,
        org_id: UUID,
        subject: str,
        to_email: str,
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        access_token = await self._get_access_token(org_id, db_session)
        return await self.graph_client.get_sent_message_metadata(
            access_token=access_token,
            subject=subject,
            to_email=to_email
        )

    async def sync_inbound_emails(
        self,
        org_id: UUID,
        sync_state: Optional[str],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        access_token = await self._get_access_token(org_id, db_session)
        return await self.graph_client.fetch_inbox_messages_delta(access_token, sync_state)
