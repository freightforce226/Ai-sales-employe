import asyncio
import json
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.ai_reply_service import AIReplyService
from app.schemas.ai_reply import AIReplyLockRequest

async def verify_recovery_lifecycle():
    async with AsyncSessionLocal() as session:
        # 1. Verify Schema Columns
        res = await session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'email_log' AND column_name = 'queued_at'")
        )
        col_exists = res.fetchone() is not None
        print(f"Schema Verification: Column 'queued_at' exists? {col_exists}")
        assert col_exists, "Database column queued_at does not exist!"

        # Verify Index
        res_idx = await session.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'email_log' AND indexname = 'idx_email_log_queued_recovery'")
        )
        idx_exists = res_idx.fetchone() is not None
        print(f"Schema Verification: Index 'idx_email_log_queued_recovery' exists? {idx_exists}")
        assert idx_exists, "Database index idx_email_log_queued_recovery does not exist!"

        # 2. Inject inbound email for testing
        test_id = uuid4()
        org_id = "d519ac7f-9c38-46c6-a981-0426cf6e561b"
        cust_id = "c58a9ee7-efd6-43a6-96f8-d3551fa2d974"
        thread_id = f"thread-recovery-{uuid4().hex[:6]}"
        msg_id = f"msg-recovery-{uuid4().hex[:6]}"

        await session.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, graph_message_id, thread_id, delivery_status)
                VALUES (:id, :org_id, :cust_id, 'inbound', 'followup', 'Test Recovery', 'Recovery Body', NOW(), :msg_id, :thread_id, 'delivered')
            """),
            {"id": test_id, "org_id": org_id, "cust_id": cust_id, "msg_id": msg_id, "thread_id": thread_id}
        )
        await session.commit()
        print("\nSetup: Injected inbound pending reply.")

        service = AIReplyService(session)

        # 3. Test Lock Reply
        lock_req = AIReplyLockRequest(
            reply_id=str(test_id),
            organization_id=org_id,
            thread_id=thread_id,
            message_id=msg_id
        )
        lock_res = await service.lock_reply(lock_req)
        print(f"Lock Response: {lock_res}")
        assert lock_res["success"] is True, "Failed to lock reply!"

        # Query and assert queued_at is set
        row_res = await session.execute(
            text("SELECT delivery_status, queued_at FROM email_log WHERE id = :id"),
            {"id": test_id}
        )
        status, queued_at = row_res.fetchone()
        print(f"Locked record state - status: {status}, queued_at: {queued_at}")
        assert status == 'queued', "Status not updated to queued!"
        assert queued_at is not None, "queued_at was not populated!"

        # 4. Test Failure Path Endpoint releasing
        fail_res = await service.fail_reply(lock_req)
        print(f"Fail/Unlock Response: {fail_res}")
        assert fail_res["success"] is True, "Failed to release lock on fail!"

        row_res = await session.execute(
            text("SELECT delivery_status, queued_at FROM email_log WHERE id = :id"),
            {"id": test_id}
        )
        status, queued_at = row_res.fetchone()
        print(f"Failed record state - status: {status}, queued_at: {queued_at}")
        assert status == 'delivered', "Status not reset to delivered!"
        assert queued_at is None, "queued_at was not reset to NULL!"

        # 5. Lock again and manually age the queued_at timestamp
        lock_res = await service.lock_reply(lock_req)
        assert lock_res["success"] is True

        await session.execute(
            text("UPDATE email_log SET queued_at = NOW() - INTERVAL '25 minutes' WHERE id = :id"),
            {"id": test_id}
        )
        await session.commit()
        print("\nAged the locked record's queued_at timestamp to 25 minutes ago.")

        # 6. Run recovery service
        recovered_count = await service.recover_stale_locks(timeout_minutes=15)
        print(f"Recovery Run: Recovered {recovered_count} stale locks.")
        assert recovered_count == 1, "Failed to recover stale lock!"

        # Verify record is back to delivered and queued_at is NULL
        row_res = await session.execute(
            text("SELECT delivery_status, queued_at FROM email_log WHERE id = :id"),
            {"id": test_id}
        )
        status, queued_at = row_res.fetchone()
        print(f"Post-Recovery record state - status: {status}, queued_at: {queued_at}")
        assert status == 'delivered', "Post-recovery status is not delivered!"
        assert queued_at is None, "Post-recovery queued_at is not NULL!"

        # Cleanup
        await session.execute(
            text("DELETE FROM email_log WHERE id = :id"),
            {"id": test_id}
        )
        await session.commit()
        print("Cleanup: Removed test email.")
        print("\nAll lifecycle verification checks PASSED successfully!")

if __name__ == "__main__":
    asyncio.run(verify_recovery_lifecycle())
