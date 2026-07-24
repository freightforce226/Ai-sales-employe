import asyncio
import json
import requests
from uuid import uuid4
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def run_test():
    org_id = "d519ac7f-9c38-46c6-a981-0426cf6e561b"
    customer_id = "c58a9ee7-efd6-43a6-96f8-d3551fa2d974"
    thread_id = f"thread-pending-{uuid4().hex[:6]}"
    
    # 1. Inject outbound and inbound emails
    async with AsyncSessionLocal() as session:
        # Outbound parent email
        await session.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, graph_message_id, thread_id, delivery_status)
                VALUES (:id, :org_id, :cust_id, 'outbound', 'followup', 'Re: Test Pending', 'Parent Body', NOW() - INTERVAL '1 hour', :msg_id, :thread_id, 'sent')
            """),
            {"id": uuid4(), "org_id": org_id, "cust_id": customer_id, "msg_id": f"out-{uuid4().hex[:6]}", "thread_id": thread_id}
        )
        
        # Inbound reply email
        inbound_id = uuid4()
        await session.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, graph_message_id, thread_id, delivery_status)
                VALUES (:id, :org_id, :cust_id, 'inbound', 'followup', 'Re: Test Pending', 'Reply Body', NOW(), :msg_id, :thread_id, 'delivered')
            """),
            {"id": inbound_id, "org_id": org_id, "cust_id": customer_id, "msg_id": f"in-{uuid4().hex[:6]}", "thread_id": thread_id}
        )
        await session.commit()
        print("Setup: Injected outbound parent and inbound pending reply.")
        
    try:
        # 2. Call HTTP API
        url = "http://localhost:8000/api/v1/ai-reply/pending"
        headers = {
            "X-API-Key": "freightforce-dev-123"
        }
        res = requests.get(url, headers=headers)
        print("HTTP Status Code:", res.status_code)
        print("HTTP Response JSON:", res.json())
    finally:
        # 3. Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM email_log WHERE thread_id = :thread"), {"thread": thread_id})
            await session.commit()
            print("Cleanup: Removed test emails.")

if __name__ == "__main__":
    asyncio.run(run_test())
