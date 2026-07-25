import asyncio
import sys
import requests
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def get_test_reply_id():
    async with AsyncSessionLocal() as session:
        # Find any outbound email log record to act as test subject
        res = await session.execute(
            text("SELECT id FROM email_log WHERE direction = 'outbound' ORDER BY created_at DESC LIMIT 1")
        )
        row = res.fetchone()
        if row:
            return row[0]
        
        # If no outbound exists, create a dummy one for the integration test
        dummy_id = uuid4()
        await session.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, delivery_status, subject, body, created_at)
                VALUES (:id, 'd519ac7f-9c38-46c6-a981-0426cf6e561b', 'c58a9ee7-efd6-43a6-96f8-d3551fa2d974', 'outbound', 'delivered', 'Subject', 'Body', NOW())
            """),
            {"id": dummy_id}
        )
        await session.commit()
        return dummy_id

async def run_tests():
    reply_id = await get_test_reply_id()
    print(f"Using Test Reply ID: {reply_id}")
    
    url = "http://localhost:8000/api/v1/ai-reply/complete"
    headers = {
        "X-API-Key": "freightforce-dev-123",
        "Content-Type": "application/json"
    }

    # --- Test 1: Valid completion ---
    print("\n--- Test 1: Valid completion request ---")
    payload_valid = {
        "reply_id": str(reply_id),
        "graph_message_id": "test-message-graph-id-12345",
        "sent_at": datetime.now(timezone.utc).isoformat()
    }
    res_1 = requests.post(url, headers=headers, json=payload_valid)
    print("Status Code:", res_1.status_code)
    print("Response Body:", res_1.json())
    assert res_1.status_code == 200
    assert res_1.json()["success"] is True
    assert res_1.json()["delivery_status"] == "sent"

    # --- Test 2: Unknown reply_id ---
    print("\n--- Test 2: Unknown reply_id ---")
    payload_unknown = {
        "reply_id": str(uuid4()),
        "graph_message_id": "test-msg-unknown",
        "sent_at": datetime.now(timezone.utc).isoformat()
    }
    res_2 = requests.post(url, headers=headers, json=payload_unknown)
    print("Status Code:", res_2.status_code)
    print("Response Body:", res_2.json())
    assert res_2.status_code == 404
    assert res_2.json()["detail"] == "reply_not_found"

    # --- Test 3: Idempotent call ---
    print("\n--- Test 3: Idempotent call (already completed) ---")
    res_3 = requests.post(url, headers=headers, json=payload_valid)
    print("Status Code:", res_3.status_code)
    print("Response Body:", res_3.json())
    assert res_3.status_code == 200
    assert res_3.json()["success"] is True
    assert res_3.json()["delivery_status"] == "sent"

    # --- Test 4: Blank/whitespace graph_message_id ---
    print("\n--- Test 4: Blank/whitespace graph_message_id ---")
    payload_blank = {
        "reply_id": str(reply_id),
        "graph_message_id": "   ",
        "sent_at": datetime.now(timezone.utc).isoformat()
    }
    res_4 = requests.post(url, headers=headers, json=payload_blank)
    print("Status Code:", res_4.status_code)
    print("Response Body:", res_4.json())
    assert res_4.status_code == 422
    print("\nAll integration tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
