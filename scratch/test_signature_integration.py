import asyncio
import sys
import requests
import json

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def update_db_signature(signature: str):
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                UPDATE organization_ai_settings 
                SET email_signature = :signature 
                WHERE organization_id = 'd519ac7f-9c38-46c6-a981-0426cf6e561b'
            """),
            {"signature": signature or None}
        )
        await session.commit()

async def run_integration_test():
    url = "http://localhost:8000/api/v1/ai-reply/generate-draft"
    headers = {
        "X-API-Key": "freightforce-dev-123",
        "Content-Type": "application/json"
    }
    
    payload = {
        "organization_id": "d519ac7f-9c38-46c6-a981-0426cf6e561b",
        "customer_id": "c58a9ee7-efd6-43a6-96f8-d3551fa2d974",
        "thread_id": "thread_test_sig_123",
        "customer_reply_text": "Hi, I have a question about the price for Hitachi."
    }

    forbidden = [
        "Regards", "Best Regards", "Kind Regards", "Warm Regards",
        "Thanks & Regards", "Sincerely", "AI Sales Agent", 
        "Automation Engineer", "Phone:", "Mobile:", "Email:", "--"
    ]

    # --- Scenario A: No Organization Signature Configured ---
    print("\n--- Scenario A: Testing with EMPTY organization signature ---")
    await update_db_signature("")
    
    res_a = requests.post(url, headers=headers, json=payload)
    assert res_a.status_code == 200
    body_a = res_a.json().get("reply_body", "")
    print("Response reply_body (No signature):\n", body_a)
    
    failed_a = False
    for term in forbidden:
        if term.lower() in body_a.lower():
            print(f"FAIL: reply_body contains signature element under Scenario A: '{term}'")
            failed_a = True
        else:
            print(f"PASS: '{term}' not found.")
            
    assert not failed_a, "Scenario A failed: Signature elements leaked into signature-free draft!"

    # --- Scenario B: With Organization Signature Configured ---
    test_signature = "Best regards,\nGourav Sharma\nAutomation Engineer\nPhone: 8209427429"
    print("\n--- Scenario B: Testing with CONFIGURED organization signature ---")
    await update_db_signature(test_signature)

    res_b = requests.post(url, headers=headers, json=payload)
    assert res_b.status_code == 200
    body_b = res_b.json().get("reply_body", "")
    print("Response reply_body (With signature):\n", body_b)

    # 1. Assert exactly one signature block is appended (split by signature separator "--")
    parts = body_b.split("\n\n--\n")
    print(f"Split count by '--': {len(parts)}")
    assert len(parts) == 2, f"Expected exactly one signature separator '--', found {len(parts) - 1}!"
    
    llm_part = parts[0]
    signature_part = parts[1]

    # 2. Assert LLM part has no signature elements
    failed_b = False
    for term in forbidden:
        if term.lower() in llm_part.lower():
            print(f"FAIL: LLM generated portion contains signature element: '{term}'")
            failed_b = True
        else:
            print(f"PASS: '{term}' not found in LLM portion.")
            
    assert not failed_b, "Scenario B failed: Signature elements leaked into the LLM narrative body!"

    # 3. Assert signature part matches the configured signature
    assert "gourav sharma" in signature_part.lower(), "Configured signature was not appended correctly!"
    
    print("\nResult: ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_integration_test())
