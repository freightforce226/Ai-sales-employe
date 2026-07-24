import asyncio
import sys
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from fastapi.testclient import TestClient
from app.main import app

def main():
    client = TestClient(app)
    
    # 1. First get a pending reply to get valid IDs
    res_pending = client.get(
        "/api/v1/ai-reply/pending",
        headers={"X-API-Key": "freightforce-dev-123"}
    )
    print("Pending Status:", res_pending.status_code)
    pending_items = res_pending.json()
    if not pending_items or not isinstance(pending_items, list):
        print("No pending items found to test generate-draft")
        return
        
    item = pending_items[0]
    print(f"Testing generate-draft for customer {item['customer_id']} on thread {item['thread_id']}")
    
    # 2. Call generate-draft with API Key in header
    payload = {
        "organization_id": item["organization_id"],
        "customer_id": item["customer_id"],
        "thread_id": item["thread_id"],
        "latest_customer_email": item["customer_reply_text"]
    }
    
    res_draft = client.post(
        "/api/v1/ai-reply/generate-draft",
        headers={"X-API-Key": "freightforce-dev-123"},
        json=payload
    )
    
    print("Generate Draft Status Code:", res_draft.status_code)
    print("Generate Draft Response:", res_draft.json())

if __name__ == "__main__":
    main()
