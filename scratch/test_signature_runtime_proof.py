import asyncio
import sys

sys.path.insert(0, r'c:\Users\golu\Desktop\freightforce.ai\backend')
from app.db.session import AsyncSessionLocal
from app.services.email_service import EmailService
from app.schemas.email import EmailRequest

def count_substring(text: str, sub: str) -> int:
    if not text:
        return 0
    return text.lower().count(sub.lower())

async def run_proof():
    print("="*80)
    print("RUNNING RUNTIME PROOF: SIGNATURE LIFE CYCLE TRACE")
    print("="*80)

    # 1. Construct EmailRequest for threaded reply
    request = EmailRequest(
        organization_id="d519ac7f-9c38-46c6-a981-0426cf6e561b",
        customer_email="dev@freightforce.ai",
        subject="Re: Following Up - Hitachi",
        html_body="<p>This is a threaded reply test audit message.</p>",
        parent_message_id="AQMkADAwATNiZmYAZS1hZjRiLTVjMDItMDACLTAwCgBGAAADvPkW3AHC8Eul5yg1iSsQogcA1Woe4kkRVkCJrHuz0FRo8wAAAgEMAAAA1Woe4kkRVkCJrHuz0FRo8wAAAEAJKPQAAAA=",
        attachments=[]
    )

    async with AsyncSessionLocal() as session:
        # Resolve signature settings for verification
        from app.services.email_branding_service import EmailBrandingService
        branding = EmailBrandingService(session)
        sig_config = await branding.get_signature(request.organization_id)
        org_sig = sig_config.signature_html if sig_config else ""
        print(f"Configured Org Signature: {repr(org_sig)}")

        # 2. Trigger send_tenant_email
        email_service = EmailService(session)
        
        # Intercept and log stages by executing client steps manually with detailed counts
        access_token = await email_service.token_service.get_valid_access_token(request.organization_id)
        
        # Stage A: Rendered by EmailBrandingService
        cleaned_body = branding.clean_and_format_body(request.html_body)
        version_a_html = branding.render_html_email(
            body_content=cleaned_body,
            signature_html=org_sig
        )
        version_a_plain = branding.render_plain_email(version_a_html)
        
        print("\n[Stage A: EmailBrandingService Output]")
        print(f"HTML Length: {len(version_a_html)} | Plain Length: {len(version_a_plain)}")
        sig_count_a = count_substring(version_a_html, "gourav sharma")
        sep_count_a = count_substring(version_a_html, "--")
        print(f"Signature count: {sig_count_a} | Separator count: {sep_count_a}")

        # Stage B: Immediately after createReply()
        print("\nExecuting createReply()...")
        draft_id = await email_service.graph_client.create_reply_draft(access_token, request.parent_message_id)
        post_create_html = await email_service.graph_client.get_message_html(access_token, draft_id)
        
        print("\n[Stage B: Immediately after createReply() (Before PATCH)]")
        print(f"HTML Length: {len(post_create_html)}")
        sig_count_b = count_substring(post_create_html, "gourav sharma")
        sep_count_b = count_substring(post_create_html, "--")
        print(f"Signature count: {sig_count_b} | Separator count: {sep_count_b}")
        print("Note: If signature count > 0 here, Outlook automatically inherited/injected mailbox signature.")

        # Stage C: Immediately after PATCH
        print("\nExecuting PATCH...")
        await email_service.graph_client.update_message_draft(
            access_token=access_token,
            draft_id=draft_id,
            html_content=version_a_html
        )
        post_patch_html = await email_service.graph_client.get_message_html(access_token, draft_id)
        
        print("\n[Stage C: Immediately after PATCH]")
        print(f"HTML Length: {len(post_patch_html)}")
        sig_count_c = count_substring(post_patch_html, "gourav sharma")
        sep_count_c = count_substring(post_patch_html, "--")
        print(f"Signature count: {sig_count_c} | Separator count: {sep_count_c}")

        # Stage D: Immediately before send
        print("\n[Stage D: Immediately before send]")
        pre_send_html = await email_service.graph_client.get_message_html(access_token, draft_id)
        sig_count_d = count_substring(pre_send_html, "gourav sharma")
        sep_count_d = count_substring(pre_send_html, "--")
        print(f"Signature count: {sig_count_d} | Separator count: {sep_count_d}")

        # Clean up draft to avoid sending spam emails during audit
        await email_service.graph_client.delete_draft(access_token, draft_id)
        print("\nCleanup: Deleted audit draft successfully.")

        # Print Side-by-Side Analysis Table
        print("\n" + "="*80)
        print("RUNTIME TRACE AUDIT TABLE")
        print("="*80)
        headers = ["Stage", "Signature Count", "Separator Count", "HTML Length", "Status"]
        print(f"{headers[0]:<35} | {headers[1]:<15} | {headers[2]:<17} | {headers[3]:<12} | {headers[4]}")
        print("-" * 92)
        
        # Row 1: EmailBrandingService Output
        status_a = "PASS" if sig_count_a == 1 else "FAIL"
        print(f"{'EmailBrandingService Output':<35} | {sig_count_a:<15} | {sep_count_a:<17} | {len(version_a_html):<12} | {status_a}")

        # Row 2: Post-createReply Draft
        # If Microsoft Graph returned a draft that already had a signature, we document it.
        status_b = "PASS" if sig_count_b == 0 else "PASS (Mailbox Injected)"
        print(f"{'Post-createReply Draft':<35} | {sig_count_b:<15} | {sep_count_b:<17} | {len(post_create_html):<12} | {status_b}")

        # Row 3: Post-PATCH Draft
        status_c = "PASS" if sig_count_c == 1 else "FAIL (Duplication Detected)"
        print(f"{'Post-PATCH Draft':<35} | {sig_count_c:<15} | {sep_count_c:<17} | {len(post_patch_html):<12} | {status_c}")

        # Row 4: Pre-send Draft
        status_d = "PASS" if sig_count_d == 1 else "FAIL"
        print(f"{'Pre-send Draft':<35} | {sig_count_d:<15} | {sep_count_d:<17} | {len(pre_send_html):<12} | {status_d}")
        print("="*80)

if __name__ == "__main__":
    asyncio.run(run_proof())
