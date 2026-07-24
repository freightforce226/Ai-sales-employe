import asyncio
import json
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.schemas.ai_reply import AIReplyPendingResponse

async def inspect():
    async with AsyncSessionLocal() as session:
        query = """
            SELECT 
                el.id AS reply_id,
                el.organization_id,
                o.display_name AS organization_name,
                el.customer_id,
                c.contact_name AS customer_name,
                c.contact_email AS customer_email,
                aoe.mailbox_email,
                el.thread_id,
                el.conversation_id,
                el.graph_message_id AS message_id,
                el.subject,
                el.body AS latest_email,
                el.sent_at AS received_datetime,
                settings.reply_tone,
                settings.default_cc_emails AS default_cc,
                settings.ai_writing_instructions,
                COALESCE(sig.signature_html, settings.email_signature) AS email_signature,
                el.internet_message_id
            FROM email_log el
            JOIN customers c ON el.customer_id = c.id
            JOIN organizations o ON el.organization_id = o.id
            JOIN organization_ai_settings settings ON el.organization_id = settings.organization_id
            LEFT JOIN organization_signatures sig ON el.organization_id = sig.organization_id
            LEFT JOIN active_organizations_for_engagement aoe ON el.organization_id = aoe.organization_id
            WHERE el.direction = 'inbound'
              AND el.delivery_status = 'delivered'
              AND settings.ai_enabled = TRUE
        """
        res = await session.execute(text(query))
        rows = res.fetchall()
        print(f"Total pending rows found in actual DB: {len(rows)}")
        for i, r in enumerate(rows):
            print(f"\n--- Row {i+1} ---")
            print("Raw Row:", r)
            try:
                reply_id, org_id, org_name, cust_id, cust_name, cust_email, mailbox_email, thread_id, conv_id, msg_id, subject, latest_email, received_dt, reply_tone, default_cc, instructions, signature, internet_msg_id = r
                cc_emails = []
                if default_cc:
                    if isinstance(default_cc, str):
                        cc_emails = json.loads(default_cc)
                    else:
                        cc_emails = default_cc
                model_obj = AIReplyPendingResponse(
                    reply_id=reply_id,
                    organization_id=org_id,
                    organization_name=org_name,
                    customer_id=cust_id,
                    customer_name=cust_name,
                    customer_email=cust_email,
                    mailbox_email=mailbox_email,
                    thread_id=thread_id,
                    conversation_id=conv_id,
                    message_id=msg_id,
                    internet_message_id=internet_msg_id,
                    subject=subject,
                    latest_email_html=latest_email or "",
                    customer_reply_text=latest_email or "",
                    received_datetime=received_dt,
                    reply_tone=reply_tone,
                    default_cc=[str(e) for e in cc_emails],
                    ai_writing_instructions=instructions,
                    email_signature=signature
                )
                print("Pydantic Parse: SUCCESS")
                print("Dumped Dict:", model_obj.model_dump())
            except Exception as e:
                print("Pydantic Parse: FAILED")
                print("Error:", e)

if __name__ == "__main__":
    asyncio.run(inspect())
