import asyncio
import sys
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal
from app.services.inbound_sync_service import InboundSyncService

async def main():
    org_id = UUID("d519ac7f-9c38-46c6-a981-0426cf6e561b")
    customer_id = UUID("c58a9ee7-efd6-43a6-96f8-d3551fa2d974")
    
    # Test message and thread identifiers
    outbound_msg_id = f"<outbound-{uuid4().hex[:6]}@freightforce.ai>"
    thread_id = f"thread-{uuid4().hex[:6]}"
    
    async with AsyncSessionLocal() as session:
        sync_service = InboundSyncService(session)
        
        print("--- 1. INSERTING OUTBOUND REFERENCE EMAIL ---")
        # Clean up any potential leftovers
        await session.execute(text("DELETE FROM email_log WHERE thread_id = :thread"), {"thread": thread_id})
        await session.commit()
        
        await session.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, graph_message_id, thread_id, internet_message_id)
                VALUES (gen_random_uuid(), :org_id, :cust_id, 'outbound', 'engagement'::email_type, 'Rate Request Inquiry', 'Hello', NOW() - INTERVAL '1 hour', 'graph-msg-1', :thread, :internet_id)
            """),
            {"org_id": org_id, "cust_id": customer_id, "thread": thread_id, "internet_id": outbound_msg_id}
        )
        await session.commit()
        
        print("--- 2. TESTING IN-REPLY-TO MATCHING ---")
        res_irt = await sync_service._run_reply_detection(
            org_id=org_id,
            customer_id=customer_id,
            from_email="gouravshamraa@outlook.com",
            subject="Re: Rate Request Inquiry",
            conversation_id=thread_id,
            internet_message_id=f"<inbound-irt-{uuid4().hex[:6]}@mail.com>",
            in_reply_to=outbound_msg_id,
            references=outbound_msg_id,
            received_at=datetime.now(timezone.utc),
            graph_message_id="graph-msg-irt"
        )
        print("IRT Match Result (Expected True):", res_irt["matched"])
        assert res_irt["matched"] is True, "IRT matching failed!"

        print("--- 3. TESTING CONVERSATION ID MATCHING ---")
        res_conv = await sync_service._run_reply_detection(
            org_id=org_id,
            customer_id=customer_id,
            from_email="gouravshamraa@outlook.com",
            subject="Re: Rate Request Inquiry",
            conversation_id=thread_id,
            internet_message_id=f"<inbound-conv-{uuid4().hex[:6]}@mail.com>",
            in_reply_to=None,
            references=None,
            received_at=datetime.now(timezone.utc),
            graph_message_id="graph-msg-conv"
        )
        print("Conversation ID Match Result (Expected True):", res_conv["matched"])
        assert res_conv["matched"] is True, "Conversation ID matching failed!"

        print("--- 4. TESTING SUBJECT NORMALIZATION MATCHING (FALLBACK) ---")
        res_sub = await sync_service._run_reply_detection(
            org_id=org_id,
            customer_id=customer_id,
            from_email="gouravshamraa@outlook.com",
            subject="Re: Rate Request Inquiry",
            conversation_id="completely-unrelated-thread",
            internet_message_id=f"<inbound-sub-{uuid4().hex[:6]}@mail.com>",
            in_reply_to=None,
            references=None,
            received_at=datetime.now(timezone.utc),
            graph_message_id="graph-msg-sub"
        )
        print("Subject Normalization Match Result (Expected True):", res_sub["matched"])
        assert res_sub["matched"] is True, "Subject normalization matching failed!"

        print("--- 5. TESTING UNMATCHED EMAIL ---")
        res_unmatched = await sync_service._run_reply_detection(
            org_id=org_id,
            customer_id=customer_id,
            from_email="gouravshamraa@outlook.com",
            subject="New Warehousing Options",
            conversation_id="completely-unrelated-thread-2",
            internet_message_id=f"<inbound-unmatch-{uuid4().hex[:6]}@mail.com>",
            in_reply_to=None,
            references=None,
            received_at=datetime.now(timezone.utc),
            graph_message_id="graph-msg-unmatch"
        )
        print("Unmatched Match Result (Expected False):", res_unmatched["matched"])
        assert res_unmatched["matched"] is False, "Unmatched matching failed!"
        
        print("\nSUCCESS: All thread-centric reply detection test cases passed!")

        # Clean up
        await session.execute(text("DELETE FROM email_log WHERE thread_id = :thread"), {"thread": thread_id})
        await session.commit()
        print("Cleanup completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
