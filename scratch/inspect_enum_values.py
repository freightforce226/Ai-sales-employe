import asyncio
import sys
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv(r"c:\Users\golu\Desktop\freightforce.ai\backend\.env")
sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')

from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(text("""
            SELECT e.enumlabel
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid  
            JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = (
                SELECT udt_name 
                FROM information_schema.columns 
                WHERE table_name = 'email_log' AND column_name = 'delivery_status'
            );
        """))
        print("Enum values:")
        for r in res.fetchall():
            print("-", r[0])

if __name__ == "__main__":
    asyncio.run(main())
