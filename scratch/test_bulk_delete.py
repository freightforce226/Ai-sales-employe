import asyncio
import sys
import uuid

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal
from app.repositories.customer_repository import CustomerRepository

async def test_bulk():
    async with AsyncSessionLocal() as session:
        repo = CustomerRepository(session, uuid.UUID("d519ac7f-9c38-46c6-a981-0426cf6e561b"))
        # Get some customer IDs
        from sqlalchemy import text
        res = await session.execute(text("SELECT id FROM customers LIMIT 2"))
        ids = [row[0] for row in res.fetchall()]
        print("Testing bulk delete with IDs:", ids)
        try:
            count = await repo.bulk_delete_customers(ids)
            print("Successfully deleted count:", count)
        except Exception as e:
            print("Failed with error:", type(e), e)
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_bulk())
