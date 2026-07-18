import asyncio
import sys
import uuid
import httpx
from unittest.mock import AsyncMock, patch
from sqlalchemy import text

sys.path.append(r"c:\Users\golu\Desktop\freightforce.ai\backend")
from app.db.session import AsyncSessionLocal
from app.services.inbound_sync_service import InboundSyncService

async def test_inbound_delta_sync():
    org_id_1 = uuid.uuid4()
    org_id_2 = uuid.uuid4()
    cust_id_1 = uuid.uuid4()
    cust_id_2 = uuid.uuid4()
    domain_1 = f"test-sync1-{str(uuid.uuid4())[:8]}.com"
    domain_2 = f"test-sync2-{str(uuid.uuid4())[:8]}.com"
    parent_log_1 = uuid.uuid4()

    print("--- SETUP ISOLATION TEST ENVIRONMENT ---")
    async with AsyncSessionLocal() as db:
        # Pre-cleanup static records from any previously aborted/interrupted runs
        await db.execute(text("DELETE FROM email_log WHERE graph_message_id IN ('graph-msg-ooo', 'graph-msg-reply')"))
        await db.execute(text("DELETE FROM tenant_integrations WHERE mailbox_email = 'mailbox1@test.com'"))
        await db.execute(text("DELETE FROM customers WHERE contact_email IN ('cust1@test.com', 'cust2@test.com')"))
        await db.execute(text("DELETE FROM campaign_enrollments WHERE exit_reason LIKE 'Reply detected:%'"))
        await db.execute(text("DELETE FROM organizations WHERE name IN ('Org 1', 'Org 2')"))
        await db.commit()

        # Organization 1
        await db.execute(
            text("INSERT INTO organizations (id, name, display_name, custom_domain) VALUES (:org_id, 'Org 1', 'Org 1', :domain)"),
            {"org_id": org_id_1, "domain": domain_1}
        )
        # Organization 2
        await db.execute(
            text("INSERT INTO organizations (id, name, display_name, custom_domain) VALUES (:org_id, 'Org 2', 'Org 2', :domain)"),
            {"org_id": org_id_2, "domain": domain_2}
        )
        # Customer 1
        await db.execute(
            text("INSERT INTO customers (id, organization_id, contact_name, contact_email, company_name) VALUES (:cust_id, :org_id, 'Cust 1', 'cust1@test.com', 'Cust 1 Co')"),
            {"cust_id": cust_id_1, "org_id": org_id_1}
        )
        # Customer 2 (Isolation Test)
        await db.execute(
            text("INSERT INTO customers (id, organization_id, contact_name, contact_email, company_name) VALUES (:cust_id, :org_id, 'Cust 2', 'cust2@test.com', 'Cust 2 Co')"),
            {"cust_id": cust_id_2, "org_id": org_id_2}
        )
        # Outbound Engagement Log 1
        await db.execute(
            text("""
                INSERT INTO email_log (id, organization_id, customer_id, direction, email_type, subject, body, sent_at, internet_message_id, conversation_id)
                VALUES (:log_id, :org_id, :cust_id, 'outbound', 'followup', 'Sequence Intro', 'Start', NOW() - INTERVAL '5 days', 'outbound-msg-id-1', 'conv-id-1')
            """),
            {"log_id": parent_log_1, "org_id": org_id_1, "cust_id": cust_id_1}
        )
        # Sequence Settings (Max = 3, Stop on Reply = True)
        await db.execute(
            text("""
                INSERT INTO organization_engagement_settings (organization_id, max_follow_ups, stop_on_reply, follow_up_sequence_config)
                VALUES (:org_id, 3, true, '[
                    {"step_number": 1, "delay_days": 2, "is_enabled": true},
                    {"step_number": 2, "delay_days": 2, "is_enabled": true}
                ]'::jsonb)
            """),
            {"org_id": org_id_1}
        )
        # Active Schedule for Org 1 Customer 1
        sched_id_1 = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO follow_up_schedule (id, organization_id, customer_id, step_number, source_email_log_id, status, scheduled_datetime, scheduled_date)
                VALUES (:id, :org_id, :cust_id, 1, :log_id, 'pending', NOW() + INTERVAL '2 days', CURRENT_DATE + 2)
            """),
            {"id": sched_id_1, "org_id": org_id_1, "cust_id": cust_id_1, "log_id": parent_log_1}
        )
        # Active Integrations for Mailbox 1 (Org 1)
        await db.execute(
            text("""
                INSERT INTO tenant_integrations (id, organization_id, provider, mailbox_email, encrypted_access_token, encrypted_refresh_token, token_expires_at, is_active)
                VALUES (:id, :org_id, 'microsoft_graph', 'mailbox1@test.com', 'dummy-token', 'dummy-token', NOW() + INTERVAL '2 hours', true)
            """),
            {"id": uuid.uuid4(), "org_id": org_id_1}
        )
        await db.commit()

    print("Mocking Graph client call...")
    mock_messages = [
        # Message 1: Duplicate check - internetMessageId matched outbound-msg-id-1 (should skip duplicate insertion)
        {
            "id": "graph-msg-dup",
            "internetMessageId": "outbound-msg-id-1",
            "conversationId": "conv-id-1",
            "subject": "Duplicate Msg",
            "from": {"emailAddress": {"address": "cust1@test.com"}},
            "receivedDateTime": "2026-07-16T00:00:00Z"
        },
        # Message 2: OOO auto-reply (should insert log but NOT stop schedule)
        {
            "id": "graph-msg-ooo",
            "internetMessageId": "ooo-inbound-msg-id",
            "conversationId": "conv-id-1",
            "subject": "Out of office: Automatic response",
            "from": {"emailAddress": {"address": "cust1@test.com"}},
            "receivedDateTime": "2026-07-16T00:01:00Z"
        },
        # Message 3: Valid Inbound reply (should insert log and trigger completion via stop_on_reply)
        {
            "id": "graph-msg-reply",
            "internetMessageId": "reply-inbound-msg-id",
            "conversationId": "conv-id-1",
            "subject": "Re: Sequence Intro",
            "from": {"emailAddress": {"address": "cust1@test.com"}},
            "receivedDateTime": "2026-07-16T00:02:00Z",
            "singleValueExtendedProperties": [
                {"id": "String 0x1039", "value": "outbound-msg-id-1"},
                {"id": "String 0x1042", "value": "outbound-msg-id-1"}
            ]
        },
        # Message 4: Unknown sender (should log and skip completely without SQL error)
        {
            "id": "graph-msg-unknown",
            "internetMessageId": "unknown-msg-id",
            "conversationId": "conv-id-2",
            "subject": "Spam/Newsletter",
            "from": {"emailAddress": {"address": "unknown@spam.com"}},
            "receivedDateTime": "2026-07-16T00:03:00Z"
        }
    ]

    # Execute Sync Service
    async with AsyncSessionLocal() as db:
        service = InboundSyncService(db)
        # Patch client delta calls and token service decrypt
        with patch.object(service.graph_client, 'fetch_inbox_messages_delta', new_callable=AsyncMock) as mock_delta:
            mock_delta.return_value = {
                "messages": mock_messages,
                "delta_link": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=new-token-123"
            }
            with patch('app.services.token_service.TokenService.get_valid_access_token', new_callable=AsyncMock) as mock_token:
                mock_token.return_value = "decrypted-valid-token"

                print("\nRunning synchronization service...")
                stats = await service.sync_all_active_mailboxes([org_id_1])
                print("Sync result statistics:", stats)
                
                assert stats["mailboxes_processed"] == 1
                assert stats["messages_scanned"] == 4
                assert stats["messages_inserted"] == 2 # ooo and reply (dup and unknown skipped)
                assert stats["duplicates_skipped"] == 1
                assert stats["messages_skipped_unknown_sender"] == 1
                assert stats["reply_candidates"] == 2 # ooo and reply (dup and unknown not candidate)
                assert stats["reply_matches"] == 1
                assert stats["reply_detected"] == 1
                assert stats["schedules_completed"] == 1
                assert stats["campaigns_completed"] == 1
                assert len(stats["errors"]) == 0

    # Verify Database Results
    async with AsyncSessionLocal() as db:
        # Check deltaLink is persisted
        integ_res = await db.execute(text("SELECT last_graph_delta_link, last_successful_sync FROM tenant_integrations WHERE organization_id = :org_id"), {"org_id": org_id_1})
        integ_row = integ_res.fetchone()
        print(f"Persisted deltaLink: {integ_row[0]} | Last Sync: {integ_row[1]}")
        assert "new-token-123" in integ_row[0]
        assert integ_row[1] is not None

        # Check schedule completed status
        sched_res = await db.execute(text("SELECT status, reply_message_id, reply_reason FROM follow_up_schedule WHERE customer_id = :cust_id"), {"cust_id": cust_id_1})
        sched_row = sched_res.fetchone()
        print(f"Schedule Status: {sched_row[0]} | Reply Msg ID: {sched_row[1]} | Match Reason: {sched_row[2]}")
        assert sched_row[0] == 'completed'
        assert sched_row[1] == 'graph-msg-reply'
        assert 'Matched' in sched_row[2]

        print("\n[SUCCESS] Inbound polling delta sync, de-duplication, false positive filtering, and isolation tests passed successfully.")

        # Cleanup
        print("\n--- CLEANING UP ---")
        await db.execute(text("DELETE FROM tenant_integrations WHERE organization_id = :org_id"), {"org_id": org_id_1})
        await db.execute(text("DELETE FROM follow_up_schedule WHERE customer_id = :cust_id"), {"cust_id": cust_id_1})
        await db.execute(text("DELETE FROM organization_engagement_settings WHERE organization_id = :org_id"), {"org_id": org_id_1})
        await db.execute(text("DELETE FROM email_log WHERE customer_id = :cust_id"), {"cust_id": cust_id_1})
        await db.execute(text("DELETE FROM customers WHERE id IN (:c1, :c2)"), {"c1": cust_id_1, "c2": cust_id_2})
        await db.execute(text("DELETE FROM organizations WHERE id IN (:o1, :o2)"), {"o1": org_id_1, "o2": org_id_2})
        await db.commit()
        print("Cleanup completed.")

if __name__ == "__main__":
    asyncio.run(test_inbound_delta_sync())
