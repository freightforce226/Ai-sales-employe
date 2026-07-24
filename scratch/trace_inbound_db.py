import asyncio
import sys
from uuid import UUID
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal
from app.services.ai_reply_service import AIReplyService

async def main():
    async with AsyncSessionLocal() as session:
        # Check last inserted inbound email
        res = await session.execute(text("""
            SELECT id, organization_id, customer_id, subject, conversation_id, thread_id, direction, sent_at
            FROM email_log
            WHERE direction = 'inbound'
            ORDER BY sent_at DESC
            LIMIT 1
        """))
        inbound = res.fetchone()
        if not inbound:
            print("No inbound emails found in database.")
            return
            
        ib_id, org_id, cust_id, subject, conv_id, thread_id, direction, sent_at = inbound
        print(f"Latest Inbound Email Log:")
        print(f"  ID: {ib_id}")
        print(f"  Org ID: {org_id}")
        print(f"  Cust ID: {cust_id}")
        print(f"  Subject: {subject}")
        print(f"  Thread ID: {thread_id}")
        print(f"  Sent At: {sent_at}")
        
        # Check Organization AI Settings
        ai_res = await session.execute(text("""
            SELECT ai_enabled FROM organization_ai_settings WHERE organization_id = :org_id
        """), {"org_id": org_id})
        ai_row = ai_res.fetchone()
        ai_enabled = ai_row[0] if ai_row else None
        print(f"Organization AI Enabled: {ai_enabled}")
        
        # Check if there is a matching outbound email in the thread
        out_res = await session.execute(text("""
            SELECT id, sent_at, direction FROM email_log
            WHERE thread_id = :thread_id AND direction = 'outbound'
        """), {"thread_id": thread_id})
        outbound_rows = out_res.fetchall()
        print(f"Outbound Emails on Thread {thread_id}:")
        for r in outbound_rows:
            print(f"  - Outbound ID: {r[0]} | Sent At: {r[1]}")
            
        # Check if there is any outbound email sent AFTER the inbound email
        out_after_res = await session.execute(text("""
            SELECT id, sent_at FROM email_log
            WHERE thread_id = :thread_id AND direction = 'outbound' AND sent_at > :sent_at
        """), {"thread_id": thread_id, "sent_at": sent_at})
        out_after_rows = out_after_res.fetchall()
        print(f"Outbound Emails Sent AFTER Inbound:")
        for r in out_after_rows:
            print(f"  - ID: {r[0]} | Sent At: {r[1]}")
            
        # Run pending query
        service = AIReplyService(session)
        pending = await service.get_pending_replies()
        print(f"Total Pending Replies in Queue: {len(pending)}")
        matched_pending = [p for p in pending if str(p.message_id) == str(ib_id) or p.thread_id == thread_id]
        print(f"Did the latest inbound match pending queue? {'Yes' if matched_pending else 'No'}")

if __name__ == "__main__":
    asyncio.run(main())
