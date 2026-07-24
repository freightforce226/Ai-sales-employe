import asyncio
import sys
from uuid import UUID
from dotenv import load_dotenv
from sqlalchemy import text

# Load environment variables
load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal
from app.services.ai_reply_service import AIReplyService
from app.schemas.ai_reply import AIReplySettingsUpdate

async def main():
    org_id = UUID("d519ac7f-9c38-46c6-a981-0426cf6e561b")
    customer_id = UUID("c58a9ee7-efd6-43a6-96f8-d3551fa2d974")
    thread_id = "test-thread-12345"
    
    async with AsyncSessionLocal() as session:
        service = AIReplyService(session)
        
        # 1. Fetch default settings
        print("--- 1. FETCHING DEFAULT AI REPLY SETTINGS ---")
        settings = await service.get_settings(org_id)
        print("AI Enabled:", settings.ai_enabled)
        print("Company Name:", settings.company_name)
        print("Reply Tone:", settings.reply_tone)
        print("Writing Instructions:", settings.ai_writing_instructions)
        print("Signature:", settings.email_signature)
        print("Default CC:", settings.default_cc_emails)
        
        # 2. Update settings
        print("\n--- 2. UPDATING AI REPLY SETTINGS ---")
        update_dto = AIReplySettingsUpdate(
            ai_enabled=True,
            company_name="FreightForce Global Logistics",
            reply_tone="helpful and warm",
            ai_writing_instructions="Keep replies under 100 words. Always mention that shipment routes are being optimized.",
            email_signature="Best Regards, AI Sales Agent",
            default_cc_emails=["supervisor@freightforce.ai", "ops@freightforce.ai"]
        )
        updated_settings = await service.update_settings(org_id, update_dto)
        print("AI Enabled (Updated):", updated_settings.ai_enabled)
        print("Company Name (Updated):", updated_settings.company_name)
        print("Reply Tone (Updated):", updated_settings.reply_tone)
        print("Writing Instructions (Updated):", updated_settings.ai_writing_instructions)
        print("Signature (Updated):", updated_settings.email_signature)
        print("Default CC (Updated):", updated_settings.default_cc_emails)

        # 3. Create dummy email log for thread context
        print("\n--- 3. CREATING DUMMY EMAIL THREAD LOGS ---")
        await session.execute(text("DELETE FROM email_log WHERE thread_id = :thread_id"), {"thread_id": thread_id})
        await session.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, graph_message_id, thread_id)
                VALUES 
                  (gen_random_uuid(), :org_id, :cust_id, 'outbound', 'engagement'::email_type, 'Quote Inquiry', '<p>Hello, we can ship your containers next week. What are the dimensions?</p>', NOW() - INTERVAL '1 hour', 'msg-1', :thread_id),
                  (gen_random_uuid(), :org_id, :cust_id, 'inbound', 'engagement'::email_type, 'Quote Inquiry', '<p>Hi! The dimensions are 20ft standard containers. Can you optimize the route?</p>', NOW() - INTERVAL '30 minutes', 'msg-2', :thread_id)
            """),
            {"org_id": org_id, "cust_id": customer_id, "thread_id": thread_id}
        )
        await session.commit()
        
        # 4. Generate draft reply
        print("\n--- 4. GENERATING AI REPLY DRAFT ---")
        latest_email = "<p>Please send the finalized draft quickly.</p>"
        res = await service.generate_reply_draft(org_id, customer_id, thread_id, latest_email)
        
        print("Generated Subject:", res.subject)
        print("Generated Body:\n", res.reply_body)
        print("Suggested CC Emails:", res.suggested_cc_emails)
        print("Generation Time:", res.generation_time)
        print("Provider:", res.provider)
        print("Model:", res.model)

        # Cleanup
        await session.execute(text("DELETE FROM email_log WHERE thread_id = :thread_id"), {"thread_id": thread_id})
        await session.commit()
        print("\n--- Cleanup successful. Integration test complete! ---")

if __name__ == "__main__":
    asyncio.run(main())
