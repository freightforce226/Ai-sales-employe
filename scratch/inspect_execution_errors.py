import asyncio
from sqlalchemy import text
import sys
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        r = await session.execute(text("SELECT id, status, trigger_type, error_message FROM engagement_executions ORDER BY started_at DESC LIMIT 5"))
        rows = r.fetchall()
        print("Latest executions:")
        for row in rows:
            print(f"ID: {row[0]}, Status: {row[1]}, Trigger: {row[2]}, Error: {row[3]}")
            
asyncio.run(main())
