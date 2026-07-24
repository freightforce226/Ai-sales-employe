import asyncio
import json
import re
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

def clean_subject(subj):
    if not subj:
        return ""
    # Strip common reply prefixes case-insensitively
    return re.sub(r'^(re|fwd|reply|aw|ref):\s*', '', subj, flags=re.IGNORECASE).strip().lower()

async def run_diagnostics():
    async with AsyncSessionLocal() as session:
        # 1. Fetch all inbound email logs with 'delivered' status
        inbound_res = await session.execute(
            text("""
                SELECT id, direction, delivery_status, customer_id, organization_id, thread_id, graph_message_id, sent_at, subject, in_reply_to, "references", internet_message_id
                FROM email_log
                WHERE direction = 'inbound' AND delivery_status = 'delivered'
                ORDER BY sent_at DESC
            """)
        )
        inbound_emails = inbound_res.fetchall()
        
        print(f"DIAGNOSTIC REPORT: {len(inbound_emails)} Inbound Pending Emails Found\n")
        
        for idx, el in enumerate(inbound_emails):
            el_id, direction, delivery_status, customer_id, org_id, thread_id, msg_id, sent_at, subject, in_reply_to, refs, internet_msg_id = el
            print("=" * 80)
            print(f"Inbound Email {idx + 1}: {el_id}")
            print(f"  Subject:          {subject}")
            print(f"  Sent At:          {sent_at}")
            print(f"  Thread ID:        {thread_id}")
            print(f"  Message ID:       {msg_id}")
            print(f"  Customer ID:      {customer_id}")
            print(f"  Organization ID:  {org_id}")
            print(f"  Delivery Status:  {delivery_status}")
            print("-" * 80)
            
            # Check Organization AI Enabled Settings
            settings_res = await session.execute(
                text("SELECT ai_enabled FROM organization_ai_settings WHERE organization_id = :org_id"),
                {"org_id": org_id}
            )
            settings_row = settings_res.fetchone()
            ai_enabled = settings_row[0] if settings_row else False
            
            # Check individual filters
            print("Evaluation filters:")
            print(f"  {'[PASS]' if direction == 'inbound' else '[FAIL]'} direction='inbound'")
            print(f"  {'[PASS]' if delivery_status == 'delivered' else '[FAIL]'} delivery_status='delivered'")
            print(f"  {'[PASS]' if ai_enabled else '[FAIL]'} settings.ai_enabled = TRUE (Org AI settings: {'Enabled' if ai_enabled else 'Disabled'})")
            
            # Evaluate EXISTS(previous outbound)
            # Find all outbound emails for this customer
            outbound_res = await session.execute(
                text("""
                    SELECT id, customer_id, organization_id, thread_id, sent_at, subject, internet_message_id
                    FROM email_log
                    WHERE direction = 'outbound' AND customer_id = :cust_id AND organization_id = :org_id
                    ORDER BY sent_at ASC
                """),
                {"cust_id": customer_id, "org_id": org_id}
            )
            outbounds = outbound_res.fetchall()
            
            existed_previous = False
            reasons_fail = []
            
            if not outbounds:
                reasons_fail.append("No outbound emails exist in the database for this customer.")
            else:
                for out in outbounds:
                    out_id, out_cust_id, out_org_id, out_thread_id, out_sent_at, out_subject, out_internet_msg_id = out
                    match_thread = (out_thread_id == thread_id) if (out_thread_id and thread_id) else False
                    match_in_reply = (out_internet_msg_id == in_reply_to) if (out_internet_msg_id and in_reply_to) else False
                    match_refs = (refs and out_internet_msg_id in refs) if (refs and out_internet_msg_id) else False
                    
                    clean_subj_in = clean_subject(subject)
                    clean_subj_out = clean_subject(out_subject)
                    match_subject = (clean_subj_in == clean_subj_out) if (clean_subj_in and clean_subj_out) else False
                    
                    ordered_time = out_sent_at < sent_at
                    
                    correlated = match_thread or match_in_reply or match_refs or match_subject
                    
                    if correlated and ordered_time:
                        existed_previous = True
                        print(f"  [PASS] Correlation matches with Outbound ID: {out_id}")
                        print(f"    - Subject: {out_subject}")
                        print(f"    - Sent At: {out_sent_at}")
                        print(f"    - Match criteria: thread={match_thread}, in_reply={match_in_reply}, refs={match_refs}, subject={match_subject}")
                    else:
                        fail_details = []
                        if not ordered_time:
                            fail_details.append(f"sent_at ordering fails (Outbound {out_sent_at} is not before Inbound {sent_at})")
                        if not correlated:
                            fail_details.append("no correlation matches (thread, in_reply_to, references, or subject)")
                        reasons_fail.append(f"Outbound {out_id} ('{out_subject}'): " + ", ".join(fail_details))
            
            print(f"  {'[PASS]' if existed_previous else '[FAIL]'} EXISTS(previous outbound)")
            if not existed_previous:
                print("    Why failed:")
                for r_fail in reasons_fail:
                    print(f"      - {r_fail}")
                    
            # Evaluate NOT EXISTS(subsequent outbound)
            subsequent_res = await session.execute(
                text("""
                    SELECT id, customer_id, organization_id, thread_id, sent_at, subject, in_reply_to, "references"
                    FROM email_log
                    WHERE direction = 'outbound' AND customer_id = :cust_id AND organization_id = :org_id AND sent_at > :sent_at
                """),
                {"cust_id": customer_id, "org_id": org_id, "sent_at": sent_at}
            )
            subsequents = subsequent_res.fetchall()
            
            no_subsequent = True
            subsequent_reasons = []
            for sub in subsequents:
                sub_id, sub_cust_id, sub_org_id, sub_thread_id, sub_sent_at, sub_subject, sub_in_reply, sub_refs = sub
                match_thread = (sub_thread_id == thread_id) if (sub_thread_id and thread_id) else False
                match_in_reply = (sub_in_reply == internet_msg_id) if (sub_in_reply and internet_msg_id) else False
                match_refs = (sub_refs and internet_msg_id in sub_refs) if (sub_refs and internet_msg_id) else False
                
                clean_subj_in = clean_subject(subject)
                clean_subj_sub = clean_subject(sub_subject)
                match_subject = (clean_subj_in == clean_subj_sub) if (clean_subj_in and clean_subj_sub) else False
                
                correlated = match_thread or match_in_reply or match_refs or match_subject
                if correlated:
                    no_subsequent = False
                    subsequent_reasons.append(f"Outbound {sub_id} ('{sub_subject}') sent at {sub_sent_at} is correlated (thread={match_thread}, in_reply={match_in_reply}, refs={match_refs}, subject={match_subject})")
            
            print(f"  {'[PASS]' if no_subsequent else '[FAIL]'} NOT EXISTS(subsequent outbound)")
            if not no_subsequent:
                print("    Why failed:")
                for s_fail in subsequent_reasons:
                    print(f"      - {s_fail}")
            
            print("\nCandidate outbound rows considered:")
            for out in outbounds:
                print(f"  Outbound ID: {out[0]}")
                print(f"    customer_id: {out[1]}")
                print(f"    thread_id:   {out[3]}")
                print(f"    sent_at:     {out[4]}")
                print(f"    subject:     {out[5]}")
            print("\n")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
