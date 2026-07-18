import asyncio
import sys
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import text

sys.path.append(r"c:\Users\golu\Desktop\freightforce.ai\backend")
from app.db.session import AsyncSessionLocal
from app.api.routes.follow_ups import check_and_register_reply

async def setup_test_data(db):
    # Create test organization, customer, and schedule
    org_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    parent_log_id = uuid.uuid4()
    sched_id = uuid.uuid4()

    # Insert Organization
    domain = f"{str(uuid.uuid4())[:8]}.com"
    await db.execute(
        text("INSERT INTO organizations (id, name, display_name, custom_domain) VALUES (:org_id, 'Test Org', 'Test Org', :domain)"),
        {"org_id": org_id, "domain": domain}
    )
    # Insert Customer
    await db.execute(
        text("INSERT INTO customers (id, organization_id, contact_name, contact_email, company_name) VALUES (:cust_id, :org_id, 'Test Customer', 'customer@test.com', 'Cust Co')"),
        {"cust_id": cust_id, "org_id": org_id}
    )
    # Insert Parent outbound email
    await db.execute(
        text("""
            INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, thread_id, internet_message_id)
            VALUES (:log_id, :org_id, :cust_id, 'outbound', 'followup', 'First Followup', 'Outbound body', :sent_at, 'thread_123', 'msg_outbound_123')
        """),
        {"log_id": parent_log_id, "org_id": org_id, "cust_id": cust_id, "sent_at": datetime.now(timezone.utc) - timedelta(hours=2)}
    )
    # Insert Schedule
    await db.execute(
        text("""
            INSERT INTO follow_up_schedule (id, organization_id, customer_id, step_number, source_email_log_id, status, scheduled_datetime, scheduled_date)
            VALUES (:sched_id, :org_id, :cust_id, 2, :log_id, 'pending', NOW(), CURRENT_DATE)
        """),
        {"sched_id": sched_id, "org_id": org_id, "cust_id": cust_id, "log_id": parent_log_id}
    )
    await db.commit()
    return org_id, cust_id, parent_log_id, sched_id


async def test_reply_cases():
    async with AsyncSessionLocal() as db:
        print("\n--- SETTING UP TEST DATA ---")
        org_id, cust_id, parent_log_id, sched_id = await setup_test_data(db)
        print(f"Created Org: {org_id}\nCust: {cust_id}\nOutbound Log: {parent_log_id}\nSched ID: {sched_id}")

        # Case 1: Normal Thread Reply
        print("\n--- CASE 1: Normal Thread Reply ---")
        inbound_log_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, thread_id, in_reply_to)
                VALUES (:log_id, :org_id, :cust_id, 'inbound', 'followup', 'Re: First Followup', 'This is a normal reply', :sent_at, 'thread_123', 'msg_outbound_123')
            """),
            {"log_id": inbound_log_id, "org_id": org_id, "cust_id": cust_id, "sent_at": datetime.now(timezone.utc) - timedelta(hours=1)}
        )
        await db.commit()

        res1 = await check_and_register_reply(db, cust_id, org_id, parent_log_id, sched_id, "customer@test.com")
        assert res1["reply_detected"] is True
        assert "Thread Match" in res1["reply_reason"]
        print("[SUCCESS] Thread Match reply detected correctly.")

        # Clean reply columns for next test
        await db.execute(
            text("UPDATE follow_up_schedule SET reply_detected_at = NULL, reply_message_id = NULL, reply_thread_id = NULL, reply_subject = NULL, reply_from = NULL, reply_reason = NULL WHERE id = :sched_id"),
            {"sched_id": sched_id}
        )
        # Delete Case 1 inbound email
        await db.execute(text("DELETE FROM email_log WHERE id = :log_id"), {"log_id": inbound_log_id})
        await db.commit()

        # Case 2: Out of Office (OOO) Filter
        print("\n--- CASE 2: OOO / Auto-Reply Filter ---")
        inbound_log_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, thread_id, in_reply_to)
                VALUES (:log_id, :org_id, :cust_id, 'inbound', 'followup', 'Automatic Reply: Out of office', 'I am currently away.', :sent_at, 'thread_123', 'msg_outbound_123')
            """),
            {"log_id": inbound_log_id, "org_id": org_id, "cust_id": cust_id, "sent_at": datetime.now(timezone.utc) - timedelta(hours=1)}
        )
        await db.commit()

        res2 = await check_and_register_reply(db, cust_id, org_id, parent_log_id, sched_id, "customer@test.com")
        assert res2["reply_detected"] is False
        print("[SUCCESS] OOO email ignored correctly.")

        # Clean OOO email
        await db.execute(text("DELETE FROM email_log WHERE id = :log_id"), {"log_id": inbound_log_id})
        await db.commit()

        # Case 3: Bounce Notification Filter
        print("\n--- CASE 3: Bounce / Delivery Failure Notification Filter ---")
        inbound_log_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, thread_id, bounce_status)
                VALUES (:log_id, :org_id, :cust_id, 'inbound', 'followup', 'Undeliverable: First Followup', 'Mailbox full', :sent_at, 'thread_123', 'hard_bounce')
            """),
            {"log_id": inbound_log_id, "org_id": org_id, "cust_id": cust_id, "sent_at": datetime.now(timezone.utc) - timedelta(hours=1)}
        )
        await db.commit()

        res3 = await check_and_register_reply(db, cust_id, org_id, parent_log_id, sched_id, "customer@test.com")
        assert res3["reply_detected"] is False
        print("[SUCCESS] Bounce email ignored correctly.")

        # Clean bounce email
        await db.execute(text("DELETE FROM email_log WHERE id = :log_id"), {"log_id": inbound_log_id})
        await db.commit()

        # Case 4: Timestamp Fallback Matching
        print("\n--- CASE 4: Timestamp Fallback Match ---")
        inbound_log_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at)
                VALUES (:log_id, :org_id, :cust_id, 'inbound', 'followup', 'New thread reply', 'Answering here', :sent_at)
            """),
            {"log_id": inbound_log_id, "org_id": org_id, "cust_id": cust_id, "sent_at": datetime.now(timezone.utc) - timedelta(hours=1)}
        )
        await db.commit()

        res4 = await check_and_register_reply(db, cust_id, org_id, parent_log_id, sched_id, "customer@test.com")
        assert res4["reply_detected"] is True
        assert res4["reply_reason"] == "Timestamp Fallback"
        print("[SUCCESS] Fallback timestamp reply detected correctly.")

        # Cleanup all test database records
        print("\n--- CLEANING UP DATABASE ---")
        await db.execute(text("DELETE FROM follow_up_schedule WHERE id = :sched_id"), {"sched_id": sched_id})
        await db.execute(text("DELETE FROM email_log WHERE customer_id = :cust_id"), {"cust_id": cust_id})
        await db.execute(text("DELETE FROM customers WHERE id = :cust_id"), {"cust_id": cust_id})
        await db.execute(text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org_id})
        await db.commit()
        print("[SUCCESS] All test records cleaned up.")

if __name__ == "__main__":
    asyncio.run(test_reply_cases())
