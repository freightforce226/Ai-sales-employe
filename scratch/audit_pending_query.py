import asyncio
import sys
import json
from uuid import UUID
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal
from app.services.ai_reply_service import AIReplyService

async def main():
    async with AsyncSessionLocal() as session:
        # Run query directly to get raw results
        query = """
            SELECT 
                el.organization_id,
                o.display_name AS organization_name,
                el.customer_id,
                c.contact_name AS customer_name,
                c.contact_email AS customer_email,
                aoe.mailbox_email,
                el.thread_id,
                el.conversation_id,
                el.graph_message_id AS message_id,
                el.subject,
                el.body AS latest_email,
                el.sent_at AS received_datetime,
                settings.reply_tone,
                settings.default_cc_emails AS default_cc,
                settings.ai_writing_instructions,
                settings.email_signature,
                el.internet_message_id
            FROM email_log el
            JOIN customers c ON el.customer_id = c.id
            JOIN organizations o ON el.organization_id = o.id
            JOIN organization_ai_settings settings ON el.organization_id = settings.organization_id
            LEFT JOIN active_organizations_for_engagement aoe ON el.organization_id = aoe.organization_id
            WHERE el.direction = 'inbound'
              AND settings.ai_enabled = TRUE
            ORDER BY el.sent_at ASC
        """
        
        print("--- 1. RAW SQL RESULTS (ALL INBOUND FROM AI ORGS) ---")
        res = await session.execute(text(query))
        rows = res.fetchall()
        print("Count:", len(rows))
        for r in rows:
            print(dict(r._mapping))
            
        print("\n--- 2. RUNNING SERVICE LAYER (PENDING REPLIES) ---")
        service = AIReplyService(session)
        pending = await service.get_pending_replies()
        print("Count:", len(pending))
        for p in pending:
            print("ORM / Schema Object:")
            print(p.model_dump())
            print("Serialized JSON:")
            print(p.model_dump_json())

if __name__ == "__main__":
    asyncio.run(main())
