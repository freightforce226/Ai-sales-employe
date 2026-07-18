import asyncio
from sqlalchemy import text
import sys
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        try:
            # Let's see what columns supabase_tokens has
            res = await session.execute(text("SELECT * FROM supabase_tokens LIMIT 1"))
            print("Columns:", res.keys())
        except Exception as e:
            print("Error query supabase_tokens:", str(e))

asyncio.run(main())
