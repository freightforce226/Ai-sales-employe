import asyncio
from uuid import UUID
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db_session
from sqlalchemy import text

async def run_audit():
    # 1. Fetch a valid customer ID
    async for db in get_db_session():
        res = await db.execute(text("SELECT id, organization_id FROM customers WHERE deleted_at IS NULL LIMIT 1"))
        row = res.fetchone()
        if not row:
            print("No customers found to test.")
            return
        
        customer_id, org_id = row
        print(f"Auditing customer_id={customer_id} from org_id={org_id}")

        # Get a user associated with this organization
        u_res = await db.execute(text("SELECT email FROM users WHERE organization_id = :org_id LIMIT 1"), {"org_id": org_id})
        u_row = u_res.fetchone()
        if not u_row:
            print("No user found for organization.")
            return
        user_email = u_row[0]

        # Use TestClient with mock/headers
        client = TestClient(app)
        # Mock auth: we can pass a test token or call the route directly in-process
        from app.services.customer_journey_service import CustomerJourneyService
        service = CustomerJourneyService(db, org_id)
        
        import time
        start_t = time.perf_counter()
        resp = await service.get_journey(customer_id)
        elapsed = (time.perf_counter() - start_t) * 1000

        print(f"API Execution Time: {elapsed:.2f} ms")
        print(f"Total events found: {len(resp.timeline)}")
        
        # Verify chronological sorting
        timestamps = [e.timestamp for e in resp.timeline]
        sorted_timestamps = sorted(timestamps)
        assert timestamps == sorted_timestamps, "Timestamps are not chronologically sorted!"
        print("SUCCESS: Events are strictly chronologically sorted.")

        # Print events DTO preview
        for event in resp.timeline[:5]:
            print(f"- [{event.timestamp}] Module: {event.module} | Event: {event.event_type} | Title: {event.title}")
            
if __name__ == "__main__":
    asyncio.run(run_audit())
