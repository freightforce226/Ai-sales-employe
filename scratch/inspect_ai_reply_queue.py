import asyncio
import sys
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Get columns of ai_reply_queue
        res = await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'ai_reply_queue';
        """))
        print("Columns in ai_reply_queue:")
        for r in res.fetchall():
            print(f"  {r[0]} ({r[1]})")
            
        # Get some sample data
        res_data = await session.execute(text("SELECT * FROM ai_reply_queue LIMIT 5;"))
        print("\nSample data from ai_reply_queue:")
        print(res_data.fetchall())

if __name__ == "__main__":
    asyncio.run(main())
