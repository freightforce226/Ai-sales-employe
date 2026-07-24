import asyncio
import sys
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Fetch the inbound email
        res = await session.execute(text("""
            SELECT id, organization_id, customer_id, subject, thread_id, in_reply_to, "references", sent_at, internet_message_id
            FROM email_log
            WHERE direction = 'inbound' AND subject = 'Re: Following Up - Hitachi'
            LIMIT 1
        """))
        ib = res.fetchone()
        if not ib:
            print("Hitachi inbound email not found!")
            return
            
        ib_id, org_id, cust_id, ib_subject, ib_thread, ib_irt, ib_ref, ib_sent_at, ib_internet_id = ib
        print(f"Inbound:")
        print(f"  ID: {ib_id}")
        print(f"  Subject: {ib_subject}")
        print(f"  Sent At: {ib_sent_at}")
        
        # Fetch all outbound emails for this customer
        res_out = await session.execute(text("""
            SELECT id, subject, sent_at, thread_id, internet_message_id
            FROM email_log
            WHERE direction = 'outbound' AND customer_id = :cust_id
        """), {"cust_id": cust_id})
        outbounds = res_out.fetchall()
        print(f"\nOutbounds for Hitachi Customer:")
        for o in outbounds:
            o_id, o_subject, o_sent_at, o_thread, o_msg_id = o
            print(f"  - ID: {o_id}")
            print(f"    Subject: {o_subject}")
            print(f"    Sent At: {o_sent_at}")
            print(f"    Thread ID: {o_thread}")
            print(f"    Msg ID: {o_msg_id}")
            
            # Evaluate individual predicates:
            p_time = o_sent_at < ib_sent_at
            p_thread = (o_thread == ib_thread and o_thread is not None)
            p_irt = (o_msg_id == ib_irt and o_msg_id is not None)
            p_ref = (ib_ref is not None and o_msg_id is not None and o_msg_id in ib_ref)
            
            import re
            def norm(s):
                if not s: return ""
                return re.sub(r'^(re|fwd|reply|aw|ref):\s*', '', s, flags=re.IGNORECASE).strip().lower()
            p_sub = (norm(o_subject) == norm(ib_subject) and o_subject is not None and ib_subject is not None)
            
            print(f"    Predicates: Time={p_time}, Thread={p_thread}, IRT={p_irt}, Ref={p_ref}, Sub={p_sub}")
            
        # Run NOT EXISTS check (are there any outbound emails sent AFTER this inbound email?)
        res_after = await session.execute(text("""
            SELECT id, subject, sent_at FROM email_log
            WHERE direction = 'outbound' AND customer_id = :cust_id AND sent_at > :sent_at
        """), {"cust_id": cust_id, "sent_at": ib_sent_at})
        after_rows = res_after.fetchall()
        print(f"\nOutbound Emails sent AFTER Inbound (Excluding condition):")
        for r in after_rows:
            print(f"  - ID: {r[0]} | Subject: {r[1]} | Sent At: {r[2]}")

if __name__ == "__main__":
    asyncio.run(main())
