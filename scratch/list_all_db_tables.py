import asyncio
from sqlalchemy import text
import sys
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """))
        print("Database Tables:")
        for r in res.fetchall():
            print("-", r[0])

asyncio.run(main())
