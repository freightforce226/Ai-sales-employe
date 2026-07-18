import asyncio
from sqlalchemy import text
import sys
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Check email_templates structure and content
        res = await session.execute(text("SELECT * FROM email_templates LIMIT 5"))
        print("--- EMAIL TEMPLATES ---")
        print("Keys:", res.keys())
        for r in res.fetchall():
            print(dict(zip(res.keys(), r)))
            
        res = await session.execute(text("SELECT * FROM campaigns LIMIT 5"))
        print("--- CAMPAIGNS ---")
        print("Keys:", res.keys())
        for r in res.fetchall():
            print(dict(zip(res.keys(), r)))

asyncio.run(main())
