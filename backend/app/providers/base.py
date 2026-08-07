import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

async def run_blocking_operation(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Runs a blocking I/O operation (like SMTP/IMAP network requests)
    in a separate thread to prevent blocking the FastAPI event loop.
    """
    return await asyncio.to_thread(func, *args, **kwargs)


from app.schemas.inbound_message import InboundSyncResult

class BaseEmailProvider(ABC):
    @abstractmethod
    async def send_email(
        self,
        org_id: UUID,
        recipient: str,
        subject: str,
        html_body: str,
        cc_emails: List[str],
        bcc_emails: List[str],
        attachments: List[Dict[str, Any]],
        db_session: AsyncSession,
        sender_display_name: Optional[str] = None
    ) -> str:
        """
        Sends a standard outbound email and returns the message ID.
        """
        pass

    @abstractmethod
    async def send_reply(
        self,
        org_id: UUID,
        parent_message_id: str,
        html_body: str,
        cc_emails: List[str],
        bcc_emails: List[str],
        attachments: List[Dict[str, Any]],
        db_session: AsyncSession,
        sender_display_name: Optional[str] = None
    ) -> str:
        """
        Sends a reply threaded under a parent message.
        """
        pass

    @abstractmethod
    async def get_sent_metadata(
        self,
        org_id: UUID,
        subject: str,
        to_email: str,
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Retrieves sent message metadata from sent logs.
        """
        pass

    @abstractmethod
    async def sync_inbound_emails(
        self,
        org_id: UUID,
        sync_state: Optional[str],
        db_session: AsyncSession
    ) -> InboundSyncResult:
        """
        Polls new inbox emails using a generic sync state token.
        """
        pass
