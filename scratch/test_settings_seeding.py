import asyncio
import sys

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def test_seeding():
    async with AsyncSessionLocal() as session:
        # Verify columns exist on organizations
        print("Checking organizations table schema...")
        res_org = await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'organizations' AND column_name IN ('phone_number', 'website', 'timezone', 'country')
        """))
        print("Organization columns:")
        for r in res_org.fetchall():
            print(f"  {r[0]}: {r[1]}")

        # Verify organization_settings table
        print("\nChecking organization_settings table schema...")
        res_set = await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'organization_settings'
        """))
        print("Settings columns count:", len(res_set.fetchall()))

        # Verify seeded rows
        print("\nChecking seeded settings rows...")
        res_rows = await session.execute(text("SELECT COUNT(*) FROM organization_settings"))
        print("Seeded rows count:", res_rows.scalar())

if __name__ == "__main__":
    asyncio.run(test_seeding())
