import asyncio
import sys
from uuid import UUID, uuid4
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal
from app.services.email_service import EmailService
from app.schemas.email import EmailRequest

async def main():
    org_id = UUID("d519ac7f-9c38-46c6-a981-0426cf6e561b")
    customer_email = "gouravshamraa@outlook.com"
    subject = f"Test Outbound Metadata Retrieval - Refactor Audit {uuid4().hex[:6]}"
    
    print(f"--- SENDING TEST EMAIL: {subject} ---")
    
    async with AsyncSessionLocal() as session:
        # Resolve customer details to ensure validity
        cust_res = await session.execute(
            text("SELECT contact_email FROM customers WHERE contact_email = :email AND organization_id = :org_id"),
            {"email": customer_email, "org_id": org_id}
        )
        if not cust_res.fetchone():
            print("Test customer not found in DB.")
            return

        email_service = EmailService(session)
        
        request = EmailRequest(
            organization_id=org_id,
            customer_email=customer_email,
            subject=subject,
            html_body="<p>This is a test email to verify outbound metadata retrieval from Sent Items folder.</p>",
            attachments=[]
        )
        
        # Send outbound email (this calls Microsoft Graph and performs the Sent Items polling)
        try:
            response = await email_service.send_email(request)
            print("Send Email Response success status:", response.success)
        except Exception as e:
            print("Failed to send email:", str(e))
            return
            
        # Verify the newly inserted email_log row
        print("--- VERIFYING INSERTED email_log ROW ---")
        log_res = await session.execute(text("""
            SELECT graph_message_id, conversation_id, thread_id, internet_message_id, created_at
            FROM email_log
            WHERE subject = :subject
            LIMIT 1
        """), {"subject": subject})
        row = log_res.fetchone()
        
        if row:
            print("Outbound Email Log Row Found:")
            print(f"  graph_message_id: {row[0]}")
            print(f"  conversation_id: {row[1]}")
            print(f"  thread_id: {row[2]}")
            print(f"  internet_message_id: {row[3]}")
            print(f"  created_at: {row[4]}")
            
            if row[1] and row[3] and row[0] != "ACCEPTED":
                print("\nCONFIRMATION: Sent Items polling successfully retrieved and updated metadata in the outbound log!")
            else:
                print("\nWARNING: Metadata is still missing or has default values!")
        else:
            print("Error: No email log row found matching this subject.")

if __name__ == "__main__":
    asyncio.run(main())
