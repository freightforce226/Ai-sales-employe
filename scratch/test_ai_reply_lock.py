import asyncio
import sys
import requests
from uuid import uuid4
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal

async def test_flow():
    org_id = "d519ac7f-9c38-46c6-a981-0426cf6e561b"
    customer_id = "c58a9ee7-efd6-43a6-96f8-d3551fa2d974"
    thread_id = f"thread-lock-{uuid4().hex[:6]}"
    msg_id = f"msg-lock-{uuid4().hex[:6]}"
    
    async with AsyncSessionLocal() as session:
        # Clean up existing if any
        await session.execute(text("DELETE FROM email_log WHERE thread_id = :thread"), {"thread": thread_id})
        await session.commit()
        
        # Insert inbound pending email
        await session.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, graph_message_id, thread_id, delivery_status)
                VALUES (:id, :org_id, :cust_id, 'inbound', 'followup', 'Test Subject', 'Body', NOW(), :msg_id, :thread_id, 'delivered')
            """),
            {"id": uuid4(), "org_id": org_id, "cust_id": customer_id, "msg_id": msg_id, "thread_id": thread_id}
        )
        await session.commit()
        print("Setup: Injected inbound pending email.")
        
    try:
        url_lock = "http://localhost:8000/api/v1/ai-reply/lock"
        headers = {
            "X-API-Key": "freightforce-dev-123",
            "Content-Type": "application/json"
        }
        
        # 2. Try locking a non-existent reply/thread
        payload_nonexistent = {
            "thread_id": f"nonexistent-{uuid4().hex[:6]}",
            "organization_id": org_id
        }
        print("Testing lock acquisition for non-existent thread...")
        res_nonexistent = requests.post(url_lock, headers=headers, json=payload_nonexistent)
        print("Status Code:", res_nonexistent.status_code)
        res_nonexistent_data = res_nonexistent.json()
        assert res_nonexistent_data["success"] is False
        assert res_nonexistent_data["reason"] == "reply_not_found"
        
        # 3. Try locking the reply
        payload = {
            "thread_id": thread_id,
            "organization_id": org_id
        }
        print("Testing lock acquisition (First try)...")
        res1 = requests.post(url_lock, headers=headers, json=payload)
        print("Status Code:", res1.status_code)
        print("Response Body:", res1.json())
        
        res1_data = res1.json()
        assert res1_data["success"] is True
        assert res1_data["status"] == "processing"
        assert res1_data["reply_id"] is not None
        assert res1_data["organization_id"] == org_id
        assert res1_data["customer_id"] == customer_id
        assert res1_data["thread_id"] == thread_id
        assert res1_data["message_id"] == msg_id
        assert res1_data["customer_reply_text"] == "Body"
        
        # 3. Try locking it again (should fail)
        print("Testing lock acquisition (Second try, should fail)...")
        res2 = requests.post(url_lock, headers=headers, json=payload)
        print("Status Code:", res2.status_code)
        print("Response Body:", res2.json())
        
        res2_data = res2.json()
        assert res2_data["success"] is False
        assert res2_data["reason"] == "already_processing"
        
        print("Verification: Lock flow executed exactly as expected!")
        
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM email_log WHERE thread_id = :thread"), {"thread": thread_id})
            await session.commit()
            print("Cleanup: Removed test email.")

if __name__ == "__main__":
    asyncio.run(test_flow())
