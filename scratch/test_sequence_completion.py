import asyncio
import sys
import uuid
import httpx
from sqlalchemy import text

sys.path.append(r"c:\Users\golu\Desktop\freightforce.ai\backend")
from app.db.session import AsyncSessionLocal

async def test_full_sequence():
    org_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    camp_id = uuid.uuid4()
    domain = f"test-seq-{str(uuid.uuid4())[:8]}.com"
    parent_log_id = uuid.uuid4()
    sched_id_1 = uuid.uuid4()

    print("--- SETUP TEST ENVIRONMENT ---")
    async with AsyncSessionLocal() as db:
        # Organization
        await db.execute(
            text("INSERT INTO organizations (id, name, display_name, custom_domain) VALUES (:org_id, 'Sequence Org', 'Sequence Org', :domain)"),
            {"org_id": org_id, "domain": domain}
        )
        # Customer
        await db.execute(
            text("INSERT INTO customers (id, organization_id, contact_name, contact_email, company_name) VALUES (:cust_id, :org_id, 'Seq Customer', 'seq@test.com', 'Seq Co')"),
            {"cust_id": cust_id, "org_id": org_id}
        )
        # Sequence Settings (Max Follow Ups = 3)
        await db.execute(
            text("""
                INSERT INTO organization_engagement_settings (organization_id, max_follow_ups, stop_on_reply, follow_up_sequence_config)
                VALUES (:org_id, 3, true, '[
                    {"step_number": 1, "delay_days": 2, "is_enabled": true},
                    {"step_number": 2, "delay_days": 2, "is_enabled": true},
                    {"step_number": 3, "delay_days": 2, "is_enabled": true}
                ]'::jsonb)
            """),
            {"org_id": org_id}
        )
        # Campaign
        await db.execute(
            text("INSERT INTO campaigns (id, organization_id, name) VALUES (:camp_id, :org_id, 'Test Sequence Campaign')"),
            {"camp_id": camp_id, "org_id": org_id}
        )
        # Campaign Enrollment
        await db.execute(
            text("""
                INSERT INTO campaign_enrollments (id, organization_id, campaign_id, customer_id, current_step, enrollment_status)
                VALUES (:enroll_id, :org_id, :camp_id, :cust_id, 1, 'active')
            """),
            {"enroll_id": uuid.uuid4(), "org_id": org_id, "camp_id": camp_id, "cust_id": cust_id}
        )
        # Outbound Engagement Log (parent of the sequence)
        await db.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at)
                VALUES (:log_id, :org_id, :cust_id, 'outbound', 'followup', 'Engage Email', 'Start', NOW() - INTERVAL '6 days')
            """),
            {"log_id": parent_log_id, "org_id": org_id, "cust_id": cust_id}
        )

        # Enqueue Step 1
        await db.execute(
            text("""
                INSERT INTO follow_up_schedule (id, organization_id, customer_id, step_number, source_email_log_id, status, scheduled_datetime, scheduled_date, campaign_id)
                VALUES (:id, :org_id, :cust_id, 1, :log_id, 'pending', NOW() + INTERVAL '2 days', CURRENT_DATE + 2, :camp_id)
            """),
            {"id": sched_id_1, "org_id": org_id, "cust_id": cust_id, "log_id": parent_log_id, "camp_id": camp_id}
        )
        await db.commit()
    
    print(f"Initialized Step 1 Schedule: {sched_id_1}")

    # Let's perform complete sequence execution using the complete endpoint
    async with httpx.AsyncClient(timeout=30.0) as client:
        # --- COMPLETE STEP 1 ---
        print("\n--- COMPLETING STEP 1 ---")
        r1 = await client.post(
            "http://localhost:8000/api/v1/followups/schedule/complete",
            json={"schedule_id": str(sched_id_1), "message_id": "msg_step_1"}
        )
        print("Response:", r1.status_code, r1.json())
        assert r1.status_code == 200
        res_data1 = r1.json()
        assert res_data1["success"] is True
        assert res_data1["next_step_created"] is True
        assert res_data1["sequence_completed"] is False

    # Get Step 2 ID in a separate session
    async with AsyncSessionLocal() as db:
        step_2_res = await db.execute(
            text("SELECT id, status, step_number FROM follow_up_schedule WHERE customer_id = :cust_id AND step_number = 2"),
            {"cust_id": cust_id}
        )
        step_2_row = step_2_res.fetchone()
        assert step_2_row is not None
        sched_id_2 = step_2_row[0]
        print(f"Step 2 enqueued successfully: {sched_id_2}")

    # Call Step 2 Complete
    async with httpx.AsyncClient(timeout=30.0) as client:
        # --- COMPLETE STEP 2 ---
        print("\n--- COMPLETING STEP 2 ---")
        r2 = await client.post(
            "http://localhost:8000/api/v1/followups/schedule/complete",
            json={"schedule_id": str(sched_id_2), "message_id": "msg_step_2"}
        )
        print("Response:", r2.status_code, r2.json())
        assert r2.status_code == 200
        res_data2 = r2.json()
        assert res_data2["success"] is True
        assert res_data2["next_step_created"] is True
        assert res_data2["sequence_completed"] is False

    # Get Step 3 ID and verify count in a separate session
    async with AsyncSessionLocal() as db:
        step_3_res = await db.execute(
            text("SELECT id, status, step_number FROM follow_up_schedule WHERE customer_id = :cust_id AND step_number = 3"),
            {"cust_id": cust_id}
        )
        step_3_row = step_3_res.fetchone()
        assert step_3_row is not None
        sched_id_3 = step_3_row[0]
        print(f"Step 3 enqueued successfully: {sched_id_3}")

        # Count rows before Step 3 completion
        cnt_res_before = await db.execute(
            text("SELECT COUNT(*) FROM follow_up_schedule WHERE customer_id = :cust_id"),
            {"cust_id": cust_id}
        )
        count_before = cnt_res_before.scalar()
        print(f"Total schedule rows before completing Step 3: {count_before}")

    # Call Step 3 Complete
    async with httpx.AsyncClient(timeout=30.0) as client:
        # --- COMPLETE STEP 3 (MAX FOLLOW UPS) ---
        print("\n--- COMPLETING STEP 3 ---")
        r3 = await client.post(
            "http://localhost:8000/api/v1/followups/schedule/complete",
            json={"schedule_id": str(sched_id_3), "message_id": "msg_step_3"}
        )
        print("Response:", r3.status_code, r3.json())
        assert r3.status_code == 200
        res_data3 = r3.json()
        assert res_data3["success"] is True
        assert res_data3["next_step_created"] is False
        assert res_data3["sequence_completed"] is True

    # Verification and Cleanup in a final session
    async with AsyncSessionLocal() as db:
        # Count rows after Step 3 completion (must be identical)
        cnt_res_after = await db.execute(
            text("SELECT COUNT(*) FROM follow_up_schedule WHERE customer_id = :cust_id"),
            {"cust_id": cust_id}
        )
        count_after = cnt_res_after.scalar()
        print(f"Total schedule rows after completing Step 3: {count_after}")
        assert count_before == count_after, f"Expected count to remain {count_before}, but got {count_after}"

        # Verify enrollment status is 'completed'
        enroll_res = await db.execute(
            text("SELECT enrollment_status, exit_reason FROM campaign_enrollments WHERE customer_id = :cust_id AND campaign_id = :camp_id"),
            {"cust_id": cust_id, "camp_id": camp_id}
        )
        enroll_row = enroll_res.fetchone()
        print(f"Campaign Enrollment Status: {enroll_row[0]} | Exit Reason: {enroll_row[1]}")
        assert enroll_row[0] == 'completed'
        assert 'Completed all' in enroll_row[1]

        print("\n[SUCCESS] Sequence completed correctly at Step 3. No new schedules created. Enrollment completed.")

        # Cleanup
        print("\n--- CLEANING UP ---")
        await db.execute(text("DELETE FROM follow_up_schedule WHERE customer_id = :cust_id"), {"cust_id": cust_id})
        await db.execute(text("DELETE FROM campaign_enrollments WHERE customer_id = :cust_id"), {"cust_id": cust_id})
        await db.execute(text("DELETE FROM email_log WHERE customer_id = :cust_id"), {"cust_id": cust_id})
        await db.execute(text("DELETE FROM campaigns WHERE id = :camp_id"), {"camp_id": camp_id})
        await db.execute(text("DELETE FROM customers WHERE id = :cust_id"), {"cust_id": cust_id})
        await db.execute(text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org_id})
        await db.commit()
        print("Cleanup completed.")

if __name__ == "__main__":
    asyncio.run(test_full_sequence())
