import asyncio
import sys
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Run query directly to get raw results
        query = """
            SELECT 
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
                settings.email_signature,
                el.internet_message_id
            FROM email_log el
            JOIN customers c ON el.customer_id = c.id
            JOIN organizations o ON el.organization_id = o.id
            JOIN organization_ai_settings settings ON el.organization_id = settings.organization_id
            LEFT JOIN active_organizations_for_engagement aoe ON el.organization_id = aoe.organization_id
            WHERE el.direction = 'inbound'
              AND settings.ai_enabled = TRUE
              AND EXISTS (
                  SELECT 1 FROM email_log el_prev
                  WHERE el_prev.direction = 'outbound'
                    AND el_prev.customer_id = el.customer_id
                    AND el_prev.organization_id = el.organization_id
                    AND el_prev.sent_at < el.sent_at
                    AND (
                        (el_prev.thread_id = el.thread_id AND el_prev.thread_id IS NOT NULL AND el.thread_id IS NOT NULL)
                        OR (el_prev.internet_message_id = el.in_reply_to AND el_prev.internet_message_id IS NOT NULL)
                        OR (el.references LIKE '%' || el_prev.internet_message_id || '%' AND el_prev.internet_message_id IS NOT NULL AND el.references IS NOT NULL)
                        OR (
                            LOWER(REGEXP_REPLACE(el.subject, '^(re|fwd|reply|aw|ref):\s*', '', 'i')) = LOWER(REGEXP_REPLACE(el_prev.subject, '^(re|fwd|reply|aw|ref):\s*', '', 'i'))
                            AND el.subject IS NOT NULL AND el_prev.subject IS NOT NULL
                        )
                    )
              )
              AND NOT EXISTS (
                  SELECT 1 FROM email_log el_out 
                  WHERE el_out.direction = 'outbound' 
                    AND el_out.customer_id = el.customer_id
                    AND el_out.organization_id = el.organization_id
                    AND el_out.sent_at > el.sent_at
                    AND (
                        (el_out.thread_id = el.thread_id AND el_out.thread_id IS NOT NULL AND el.thread_id IS NOT NULL)
                        OR (el_out.in_reply_to = el.internet_message_id AND el_out.in_reply_to IS NOT NULL)
                        OR (el_out.references LIKE '%' || el.internet_message_id || '%' AND el.internet_message_id IS NOT NULL AND el_out.references IS NOT NULL)
                        OR (
                            LOWER(REGEXP_REPLACE(el_out.subject, '^(re|fwd|reply|aw|ref):\s*', '', 'i')) = LOWER(REGEXP_REPLACE(el.subject, '^(re|fwd|reply|aw|ref):\s*', '', 'i'))
                            AND el_out.subject IS NOT NULL AND el.subject IS NOT NULL
                        )
                    )
              )
            ORDER BY el.sent_at ASC
        """
        
        print("--- RUNNING PENDING REPLIES QUERY ---")
        res = await session.execute(text(query))
        rows = res.fetchall()
        print("Count:", len(rows))
        for r in rows:
            print(dict(r._mapping))

if __name__ == "__main__":
    asyncio.run(main())
