import re
import httpx
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.schemas.signature import OrganizationSignatureSchema
from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

class EmailBrandingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_signed_url(self, file_path: str) -> str:
        """
        Generates a 10-year signed URL for private Supabase storage objects.
        """
        if not file_path:
            return ""
        supabase_sign_file_url = f"{settings.supabase_url}/storage/v1/object/sign/tenant-attachments/{file_path}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    supabase_sign_file_url,
                    json={"expiresIn": 315360000},  # 10 years
                    headers={
                        "apikey": settings.supabase_service_role_key,
                        "Authorization": f"Bearer {settings.supabase_service_role_key}",
                        "Content-Type": "application/json"
                    }
                )
                if res.status_code == 200:
                    signed_path = res.json().get("signedURL") or res.json().get("signedUrl")
                    if signed_path:
                        url_out = f"{settings.supabase_url}/storage/v1{signed_path}" if signed_path.startswith('/') else signed_path
                        return url_out
        except Exception as e:
            logger.error("Failed to generate signature banner signed URL in branding service", error=str(e))
        return ""

    async def get_signature(self, organization_id: UUID) -> OrganizationSignatureSchema:
        """
        Get organization's email signature settings. If not found, generates safe defaults.
        """
        # Query signature table
        res = await self.session.execute(
            text("""
                SELECT sender_name, designation, department, phone, website, linkedin_url, signature_html,
                       footer_image_name, footer_image_content_type, footer_image_size, footer_image_path
                FROM organization_signatures
                WHERE organization_id = :org_id
            """),
            {"org_id": organization_id}
        )
        row = res.fetchone()
        
        if not row:
            return OrganizationSignatureSchema(
                is_configured=False,
                sender_name="",
                designation="",
                department="",
                phone="",
                website="",
                linkedin_url="",
                signature_html="",
                footer_image_url="",
                updated_at=None
            )

        keys = [
            "sender_name", "designation", "department", "phone", "website", "linkedin_url", "signature_html",
            "footer_image_name", "footer_image_content_type", "footer_image_size", "footer_image_path"
        ]
        
        data = {"is_configured": True}
        for key, val in zip(keys, row[:11]):
            data[key] = val if val is not None else ""

        # Generate public signed URL
        data["footer_image_url"] = await self.generate_signed_url(data.get("footer_image_path"))
        return OrganizationSignatureSchema(**data)

    def clean_and_format_body(self, body_text: str) -> str:
        """
        Cleans the email body to remove markdown wrappers, redundant subjects, 
        excessive line breaks, unnecessary whitespaces, empty paragraph tags, and duplicate signatures.
        """
        if not body_text:
            return ""

        # Normalize line breaks
        cleaned = body_text.replace("\r\n", "\n").strip()

        # Remove markdown code block wrappers (e.g. ```html ... ```)
        cleaned = re.sub(r'^```[a-zA-Z]*\n', '', cleaned)
        cleaned = re.sub(r'\n```$', '', cleaned)
        cleaned = cleaned.replace("```html", "").replace("```json", "").replace("```", "").strip()

        # Remove redundant LLM-generated subject prefixes (case-insensitive)
        cleaned = re.sub(r'(?i)^\s*subject:\s*.*?\n+', '', cleaned)
        cleaned = re.sub(r'(?i)^\s*re:\s*.*?\n+', '', cleaned)
        cleaned = re.sub(r'(?i)^\s*fwd:\s*.*?\n+', '', cleaned)

        # Remove pre-existing signatures at the end of the text if any (prevent double signatures)
        sig_patterns = [
            r'(?i)(?:best\s+)?regards,?\s*[\r\n]+.*$',
            r'(?i)sincerely,?\s*[\r\n]+.*$',
            r'(?i)thanks\s+and\s+regards,?\s*[\r\n]+.*$',
            r'(?i)thank\s+you,?\s*[\r\n]+.*$',
            r'(?i)best\s+wishes,?\s*[\r\n]+.*$',
            r'(?i)kind\s+regards,?\s*[\r\n]+.*$',
            r'(?i)warm\s+regards,?\s*[\r\n]+.*$'
        ]
        for pattern in sig_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL).strip()

        # Remove double blank lines/paragraphs (collapse \n\n\n+ into \n\n)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        return cleaned.strip()

    def render_html_email(self, body_content: str, signature_html: str, banner_url: str = None) -> str:
        """
        Renders a responsive, Outlook and Gmail compatible HTML email using only inline styles.
        """
        logger.info("ENTER render_html_email()")
        
        body_content = body_content.strip()

        # 1. Detect if body_content is already a complete HTML document
        body_lower = body_content.lower().strip()
        is_full_html = (
            body_lower.startswith("<!doctype html") or
            body_lower.startswith("<html") or
            ("<html" in body_lower and "</html>" in body_lower)
        )

        if is_full_html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body_content, "html.parser")
            
            # Check if signature already exists
            has_existing_sig = False
            if signature_html:
                if soup.find(id="org-signature") or soup.find(class_="signature-block"):
                    has_existing_sig = True
            
            if signature_html and not has_existing_sig:
                sig_content = signature_html.strip()
                optional_banner = ""
                if banner_url:
                    optional_banner = f'<div style="margin-top:24px;"><img src="{banner_url}" alt="Banner" style="max-width:100%;height:auto;border:0;display:block;" /></div>'
                
                # Signature wrapper exactly as requested
                inject_content = f'<div style="margin-top:20px;padding-top:14px;border-top:1px solid #e5e7eb;">{sig_content}{optional_banner}</div>'
                inject_soup = BeautifulSoup(inject_content, "html.parser")
                
                body_tag = soup.find("body")
                if body_tag:
                    body_tag.append(inject_soup)
                else:
                    soup.append(inject_soup)
            
            logger.info("EXIT render_html_email() - full html processed")
            return str(soup).strip()

        # Convert plain paragraphs in body to clean HTML paragraph tags if they aren't already HTML
        formatted_body = ""
        
        if not body_content.startswith("<p>") and not body_content.startswith("<div>"):
            paragraphs = body_content.split("\n\n")
            for p in paragraphs:
                p_text = p.strip().replace("\n", "<br>")
                if p_text:
                    formatted_body += f'<p style="margin-top:0;margin-bottom:16px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6;color:#333333;">{p_text}</p>'
        else:
            # Inject inline styles into existing paragraph tags for Gmail/Outlook compatibility
            formatted_body = body_content
            formatted_body = re.sub(
                r'<p\b([^>]*)>', 
                r'<p style="margin-top:0;margin-bottom:16px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6;color:#333333;" \1>', 
                formatted_body
            )

        # Build Banner HTML using public signed CDN URL
        # Check if the signature is already in the body using BeautifulSoup
        has_existing_sig = False
        if body_content and signature_html:
            from bs4 import BeautifulSoup
            soup_body = BeautifulSoup(body_content, "html.parser")
            if soup_body.find(id="org-signature") or soup_body.find(class_="signature-block"):
                has_existing_sig = True
        
        # Apply inline style wrapper to signature
        styled_signature = signature_html.strip() if signature_html else ""
        if styled_signature and not has_existing_sig:
            if not styled_signature.startswith("<div") and not styled_signature.startswith("<p"):
                styled_signature = f'<div id="org-signature" class="signature-block" style="font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5;color:#555555;">{styled_signature.replace(chr(10), "<br>")}</div>'
            else:
                styled_signature = f'<div id="org-signature" class="signature-block">{styled_signature}</div>'
                styled_signature = re.sub(
                    r'<(div|p)\b([^>]*)>', 
                    r'<\1 style="font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5;color:#555555;" \2>', 
                    styled_signature,
                    count=1
                )
        else:
            if has_existing_sig:
                logger.info("render_html_email - DETECTED DUPLICATE SIGNATURE, OMITTING APPENDING")
            styled_signature = ""

        # Build Banner HTML using public signed CDN URL
        banner_html = ""
        if banner_url and not has_existing_sig:
            banner_html = f'<div style="margin-top:24px;"><img src="{banner_url}" alt="Banner" style="max-width:100%;height:auto;border:0;display:block;" /></div>'
            logger.info("SIGNATURE RENDER ENGINE - APPENDED BANNER TAG", banner_url=banner_url, img_tag=banner_html)

        # Full responsive envelope template
        html_template = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:AllowPNG/>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
</head>
<body style="margin:0;padding:0;width:100% !important;background-color:#ffffff;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;background-color:#ffffff;">
    <tr>
      <td align="left" style="padding:20px;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;max-width:600px;">
          <tr>
            <td style="font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6;color:#333333;">
              <div style="margin-bottom:24px;">
                {formatted_body}
              </div>
              <div style="border-top:1px solid #eeeeee;padding-top:16px;margin-top:24px;">
                {styled_signature}
                {banner_html}
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
        # Compress and remove excessive whitespace/blank paragraphs
        html_template = re.sub(r'[\r\n\t]+', ' ', html_template)
        html_template = re.sub(r'\s{2,}', ' ', html_template)
        html_template = html_template.replace("<p></p>", "").replace("<p style=\"margin-top:0;margin-bottom:16px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6;color:#333333;\"></p>", "")
        logger.info("EXIT render_html_email()")
        return html_template.strip()

    def render_plain_email(self, html_content: str) -> str:
        """
        Renders a clean plain text email from the final rendered HTML content dynamically.
        """
        # Convert break tags to line breaks
        text_content = re.sub(r'<br\s*/?>', '\n', html_content)
        # Convert paragraph blocks to double line breaks
        text_content = re.sub(r'</p>', '\n\n', text_content)
        text_content = re.sub(r'</div>', '\n', text_content)
        # Strip all HTML tags
        text_content = re.sub(r'<[^>]+>', '', text_content)
        
        # Replace entities
        text_content = text_content.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        
        # Normalize double space/newlines
        text_content = re.sub(r'\n{3,}', '\n\n', text_content)
        
        return text_content.strip()
