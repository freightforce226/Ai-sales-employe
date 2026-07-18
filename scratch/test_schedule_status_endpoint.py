import asyncio
import sys
import uuid
import httpx
from sqlalchemy import text

sys.path.append(r"c:\Users\golu\Desktop\freightforce.ai\backend")
from app.db.session import AsyncSessionLocal

async def run_endpoint_test():
    async with AsyncSessionLocal() as db:
        # Create a test schedule item
        org_id = uuid.uuid4()
        cust_id = uuid.uuid4()
        sched_id = uuid.uuid4()

        # Insert Organization
        domain = f"{str(uuid.uuid4())[:8]}.com"
        await db.execute(
            text("INSERT INTO organizations (id, name, display_name, custom_domain) VALUES (:org_id, 'Test Org Status', 'Test Org Status', :domain)"),
            {"org_id": org_id, "domain": domain}
        )
        # Insert Customer
        await db.execute(
            text("INSERT INTO customers (id, organization_id, contact_name, contact_email, company_name) VALUES (:cust_id, :org_id, 'Status Customer', 'status@test.com', 'Status Co')"),
            {"cust_id": cust_id, "org_id": org_id}
        )
        # Insert Schedule
        await db.execute(
            text("""
                INSERT INTO follow_up_schedule (id, organization_id, customer_id, step_number, status, scheduled_datetime, scheduled_date)
                VALUES (:sched_id, :org_id, :cust_id, 3, 'pending', NOW(), CURRENT_DATE)
            """),
            {"sched_id": sched_id, "org_id": org_id, "cust_id": cust_id}
        )
        await db.commit()

        print(f"Created Schedule ID: {sched_id} for Status test.")

        # Call FastAPI app endpoint
        async with httpx.AsyncClient() as client:
            # 1. Test 404 for non-existent schedule
            fake_id = str(uuid.uuid4())
            r1 = await client.post("http://localhost:8000/api/v1/followups/schedule/status", json={"schedule_id": fake_id})
            print("Fake Schedule ID Response:", r1.status_code, r1.text)
            assert r1.status_code == 404

            # 2. Test valid status retrieval
            r2 = await client.post("http://localhost:8000/api/v1/followups/schedule/status", json={"schedule_id": str(sched_id)})
            print("Valid Schedule ID Response:", r2.status_code, r2.json())
            assert r2.status_code == 200
            data = r2.json()
            assert data["success"] is True
            assert data["schedule"]["id"] == str(sched_id)
            assert data["schedule"]["status"] == "pending"
            assert data["schedule"]["step_number"] == 3

        # Clean up
        await db.execute(text("DELETE FROM follow_up_schedule WHERE id = :sched_id"), {"sched_id": sched_id})
        await db.execute(text("DELETE FROM customers WHERE id = :cust_id"), {"cust_id": cust_id})
        await db.execute(text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org_id})
        await db.commit()
        print("Cleaned up database.")

if __name__ == "__main__":
    asyncio.run(run_endpoint_test())
