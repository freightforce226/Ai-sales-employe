import asyncio
import sys
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Check all outbound emails in email_log
        res = await session.execute(text("""
            SELECT id, customer_id, subject, direction, sent_at, thread_id, internet_message_id
            FROM email_log
            WHERE direction = 'outbound'
            ORDER BY sent_at DESC
        """))
        rows = res.fetchall()
        print(f"Total Outbound Emails in DB: {len(rows)}")
        for r in rows:
            print(f"  - ID: {r[0]} | Customer: {r[1]} | Subject: {r[2]} | Thread: {r[5]} | MsgID: {r[6]}")

if __name__ == "__main__":
    asyncio.run(main())
