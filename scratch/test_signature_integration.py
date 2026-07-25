import asyncio
import sys
import requests
import json

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal
from app.services.email_branding_service import EmailBrandingService
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
        "Automation Engineer", "Phone", "Mobile", "Email", "--"
    ]

    # --- Scenario A: No Organization Signature Configured ---
    print("\n--- Scenario A: Testing API output with EMPTY organization signature ---")
    await update_db_signature("")
    
    res_a = requests.post(url, headers=headers, json=payload)
    assert res_a.status_code == 200
    body_a = res_a.json().get("reply_body", "")
    print("Response reply_body:\n", body_a)
    
    # Word count assertion
    word_count_a = len(body_a.split())
    print(f"Word count for Scenario A: {word_count_a}")
    assert word_count_a <= 60, f"Word count exceeds 60 words: {word_count_a}"
    
    # Greeting strategy assertion (starts with Hi)
    assert body_a.strip().startswith("Hi"), "Greeting strategy failed: Reply does not start with Hi"

    failed_a = False
    for term in forbidden:
        if term.lower() in body_a.lower():
            print(f"FAIL: reply_body contains signature element: '{term}'")
            failed_a = True
        else:
            print(f"PASS: '{term}' not found.")
            
    assert not failed_a, "Scenario A failed: Signature elements leaked into signature-free draft!"

    # --- Scenario B: With Organization Signature Configured ---
    test_signature = "Best regards,\nGourav Sharma\nAutomation Engineer\nPhone: 8209427429"
    print("\n--- Scenario B: Testing API output with CONFIGURED organization signature ---")
    await update_db_signature(test_signature)

    res_b = requests.post(url, headers=headers, json=payload)
    assert res_b.status_code == 200
    body_b = res_b.json().get("reply_body", "")
    print("Response reply_body:\n", body_b)

    # Word count assertion
    word_count_b = len(body_b.split())
    print(f"Word count for Scenario B: {word_count_b}")
    assert word_count_b <= 60, f"Word count exceeds 60 words: {word_count_b}"
    
    assert body_b.strip().startswith("Hi"), "Greeting strategy failed: Reply does not start with Hi"

    # In Scenario B, the API output itself must STILL be signature-free
    failed_b = False
    for term in forbidden:
        if term.lower() in body_b.lower():
            print(f"FAIL: API reply_body contains signature element under Scenario B: '{term}'")
            failed_b = True
        else:
            print(f"PASS: '{term}' not found.")
            
    assert not failed_b, "Scenario B failed: Signature elements leaked into API output reply_body!"

    # --- Scenario C: Verify Final HTML & Plain Text Send Mail compilation ---
    print("\n--- Scenario C: Testing outbound builder (EmailBrandingService) signature compilation ---")
    async with AsyncSessionLocal() as session:
        branding = EmailBrandingService(session)
        cleaned_body = branding.clean_and_format_body(body_b)
        
        final_html = branding.render_html_email(
            body_content=cleaned_body,
            signature_html="Best regards,<br>Gourav Sharma<br>Automation Engineer<br>Phone: 8209427429",
            banner_url=None
        )
        final_plain = branding.render_plain_email(final_html)
        
        # Verify exactly one signature block exists in HTML
        print("\nChecking HTML output...")
        assert "gourav sharma" in final_html.lower(), "Signature missing from final HTML!"
        assert final_html.lower().count("gourav sharma") == 1, "Duplicate signature block in HTML!"
        print("PASS: Exactly one signature block found in HTML.")

        # Verify exactly one signature block exists in Plain Text
        print("\nChecking Plain Text output...")
        assert "gourav sharma" in final_plain.lower(), "Signature missing from final Plain Text!"
        assert final_plain.lower().count("gourav sharma") == 1, "Duplicate signature block in Plain Text!"
        print("PASS: Exactly one signature block found in Plain Text.")
        
    print("\nResult: ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_integration_test())
