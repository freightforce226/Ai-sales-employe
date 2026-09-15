import asyncio
import os
import sys
from sqlalchemy import text
from dotenv import load_dotenv

# Load env variables explicitly from the parent .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

from app.db.session import AsyncSessionLocal

async def reset():
    campaign_id = "69e76e2b-050d-415b-b9be-d255d8e9b1ca"
    async with AsyncSessionLocal() as session:
        # Force update all sending recipients to pending
        recip_res = await session.execute(
            text("""
                UPDATE marketing_campaign_recipients 
                SET status = 'pending', claimed_at = NULL 
                WHERE campaign_id = :camp_id AND status = 'sending'
            """),
            {"camp_id": campaign_id}
        )
        print(f"Force reset {recip_res.rowcount} recipients from 'sending' to 'pending'.")

        # Set campaign status back to 'active'
        camp_res = await session.execute(
            text("""
                UPDATE marketing_campaigns 
                SET status = 'active', started_at = NULL, completed_at = NULL, updated_at = NOW() 
                WHERE id = :camp_id
            """),
            {"camp_id": campaign_id}
        )
        print(f"Updated campaign status back to 'active' (rows affected: {camp_res.rowcount}).")
        
        await session.commit()

if __name__ == '__main__':
    asyncio.run(reset())
