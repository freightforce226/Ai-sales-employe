import hashlib
import json
import uuid
import re
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.llm_service import LLMService
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_FILTER_FIELDS = {
    'company_name', 'contact_name', 'contact_email', 'phone', 
    'designation', 'industry', 'country', 'city', 'state', 
    'shipment_mode', 'trade_direction', 'customer_type', 
    'trade_region', 'goods_description'
}

def clean_spelling(text_str: str) -> str:
    if not text_str:
        return ""
    replacements = {
        r"(?i)\bhongcong\b": "Hong Kong",
        r"(?i)\bshippment\b": "shipment",
        r"(?i)\bshippments\b": "shipments",
        r"(?i)\bspetemeber\b": "September",
        r"(?i)\bspetember\b": "September",
        r"(?i)\bseptemeber\b": "September",
    }
    cleaned = text_str
    for pattern, rep in replacements.items():
        cleaned = re.sub(pattern, rep, cleaned)
    return cleaned

def normalize_business_phrase(phrase: str) -> str:
    if not phrase:
        return ""
    phrase_clean = clean_spelling(phrase).strip()
    phrase_clean = re.sub(r"(?i)\bocean sales up\b", "ocean freight capacity", phrase_clean)
    phrase_clean = re.sub(r"(?i)\bair shippment\b", "air cargo shipping", phrase_clean)
    phrase_clean = re.sub(r"(?i)\bair shipment\b", "air cargo shipping", phrase_clean)
    phrase_clean = re.sub(r"(?i)\bclaim it fast\b", "secure space", phrase_clean)
    return phrase_clean

def strip_signature(text_str: str) -> str:
    if not text_str:
        return ""
    patterns = [
        r"(?i)<p>(?:best\s+)?regards,?\s*.*?</p>",
        r"(?i)<p>sincerely,?\s*.*?</p>",
        r"(?i)<p>thanks,?\s*.*?</p>",
        r"(?i)<p>freightforce\s+cargo\s+team.*?</p>",
        r"(?i)(?:best\s+)?regards,?\s*.*$",
        r"(?i)sincerely,?\s*.*$",
        r"(?i)thanks,?\s*.*$",
        r"(?i)freightforce\s+cargo\s+team.*$",
        r"(?i)kind\s+regards,?\s*.*$"
    ]
    cleaned = text_str
    for pat in patterns:
        cleaned = re.split(pat, cleaned)[0].strip()
    return cleaned

def generate_natural_copy(campaign_type: str, params: Dict[str, Any]) -> Tuple[str, str, str]:
    service_raw = params.get("promoted_service") or ""
    opp_raw = params.get("target_opportunity") or ""
    val_raw = params.get("validity") or ""
    
    service = clean_spelling(service_raw).strip()
    opp = clean_spelling(opp_raw).strip()
    val = clean_spelling(val_raw).strip()
    
    def normalize_text(t: str) -> str:
        t = re.sub(r"(?i)\b(?:hongcong|hong\s+kong)\s+to\s+china\b", "Hong Kong-China shipments", t)
        t = re.sub(r"(?i)\bhongcong\b", "Hong Kong", t)
        return t

    service = normalize_text(service)
    opp = normalize_text(opp)
    val = normalize_text(val)

    if campaign_type == "Sales":
        service_phrase = re.sub(r"(?i)\bocean sales up\b", "additional ocean freight capacity", service)
        service_phrase = re.sub(r"(?i)\bshipment\s+Hong\s+Kong-China\s+shipments\b", "for Hong Kong-China shipments", service_phrase)
        if not service_phrase:
            service_phrase = "ocean and air freight capacity"
            
        opp_phrase = "the upcoming peak season" if "peak season shipping" in opp.lower() else opp
        if not opp_phrase:
            opp_phrase = "upcoming shipment planning"
            
        val_phrase = ""
        if val:
            val_clean = val.lower()
            if "5-sep" in val_clean:
                val_phrase = "with support available through September 5, 2026."
            else:
                val_phrase = f"with support available through {val}."
        else:
            val_phrase = "with support available to secure space."

        if "ocean" in service_phrase.lower() or "ocean" in service_raw.lower():
            subject = "Planning ocean shipments for peak season?"
        else:
            subject = "Assisting with upcoming freight shipments"
            
        html_body = (
            f"<p>Hi {{{{contact_name}}}},</p>"
            f"<p>I wanted to reach out to see how your team is managing shipments for {opp_phrase}. "
            f"At FreightForce, we currently have {service_phrase} to help you secure space and manage your volumes, "
            f"{val_phrase}</p>"
            f"<p>Would you be open to sharing your current lane requirements or volume projections so we can see how we can assist?</p>"
        )
        plain_text = (
            f"Hi {{{{contact_name}}}},\n\n"
            f"I wanted to reach out to see how your team is managing shipments for {opp_phrase}. "
            f"At FreightForce, we currently have {service_phrase} to help you secure space and manage your volumes, "
            f"{val_phrase}\n\n"
            f"Would you be open to sharing your current lane requirements or volume projections so we can see how we can assist?"
        )
        
    elif campaign_type == "Price Drop":
        route_raw = params.get("route_service") or ""
        rate = params.get("new_rate") or "reduced rates"
        route = normalize_text(clean_spelling(route_raw).strip())
        
        subject = f"Recent rate reductions on {route.lower() or 'key routes'}"
        html_body = (
            f"<p>Hi {{{{contact_name}}}},</p>"
            f"<p>I wanted to share a quick update regarding cargo rates. We have recently introduced optimized pricing of {rate} on our {route or 'standard routes'} lanes.</p>"
            f"<p>Would you be open to checking if this drop matches any of your upcoming shipping lanes?</p>"
        )
        plain_text = (
            f"Hi {{{{contact_name}}}},\n\n"
            f"I wanted to share a quick update regarding cargo rates. We have recently introduced optimized pricing of {rate} on our {route or 'standard routes'} lanes.\n\n"
            f"Would you be open to checking if this drop matches any of your upcoming shipping lanes?"
        )
    else:
        subject = "Personalized freight forwarding solutions for your cargo"
        html_body = (
            f"<p>Hi {{{{contact_name}}}},</p>"
            f"<p>At FreightForce, we assist B2B shippers in optimizing their logistics pipelines with tailored shipping solutions.</p>"
            f"<p>If you have any current requirements, feel free to reply with your shipment details.</p>"
        )
        plain_text = (
            f"Hi {{{{contact_name}}}},\n\n"
            f"At FreightForce, we assist B2B shippers in optimizing their logistics pipelines with tailored shipping solutions.\n\n"
            f"If you have any current requirements, feel free to reply with your shipment details."
        )
        
    return subject, html_body, plain_text

class MarketingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMService()

    def _build_audience_query(self, org_id: uuid.UUID, filters: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Builds a parameterized SQL query scoped by organization_id to safely fetch matching customers.
        """
        query = """
            SELECT id, company_name, contact_name, contact_email, country, 
                   shipment_mode, trade_direction, industry, designation, goods_description, customer_type
            FROM public.customers 
            WHERE organization_id = :org_id AND deleted_at IS NULL
        """
        params = {"org_id": org_id}
        conditions = []

        for key, val in filters.items():
            if key not in ALLOWED_FILTER_FIELDS:
                continue
            if val is None or val == "":
                continue
            
            if isinstance(val, list):
                if not val:
                    continue
                placeholders = []
                for idx, item in enumerate(val):
                    param_name = f"{key}_{idx}"
                    placeholders.append(f"LOWER(TRIM(BOTH FROM :{param_name}))")
                    params[param_name] = str(item).strip().lower() if isinstance(item, str) else item
                conditions.append(f"LOWER(TRIM(BOTH FROM {key})) IN ({', '.join(placeholders)})")
            else:
                conditions.append(f"LOWER(TRIM(BOTH FROM {key})) = LOWER(TRIM(BOTH FROM :{key}))")
                params[key] = str(val).strip().lower() if isinstance(val, str) else val

        if conditions:
            query += " AND " + " AND ".join(conditions)

        return query, params

    async def get_audience_count(self, org_id: uuid.UUID, filters: Dict[str, Any]) -> int:
        """
        Gets the count of customers matching the filters.
        """
        sub_query, params = self._build_audience_query(org_id, filters)
        count_query = f"SELECT COUNT(*)::INTEGER FROM ({sub_query}) AS sub"
        res = await self.db.execute(text(count_query), params)
        return res.scalar() or 0

    async def get_audience_preview(self, org_id: uuid.UUID, filters: Dict[str, Any], limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Gets a preview list of matching customers.
        """
        sub_query, params = self._build_audience_query(org_id, filters)
        preview_query = f"{sub_query} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        res = await self.db.execute(text(preview_query), params)
        return [dict(row._mapping) for row in res.fetchall()]

    async def lock_audience(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> int:
        """
        Locks the current matching audience to marketing_campaign_recipients as a frozen snapshot.
        Utilizes transactional advisory locking to prevent concurrency races.
        """
        # Lock campaign-level operations
        await self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": f"lock_{campaign_id}"})

        # Fetch campaign status and filters
        camp_res = await self.db.execute(
            text("SELECT status, audience_filters FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
            {"id": campaign_id, "org_id": org_id}
        )
        camp = camp_res.fetchone()
        if not camp:
            raise ValueError("Campaign not found.")

        status, filters_json = camp
        if status != "draft":
            raise ValueError(f"Cannot lock audience for campaign in '{status}' status.")

        filters = filters_json if isinstance(filters_json, dict) else {}

        # Fetch all matching customer IDs
        query, params = self._build_audience_query(org_id, filters)
        id_query = f"SELECT id FROM ({query}) AS sub"
        ids_res = await self.db.execute(text(id_query), params)
        customer_ids = [row[0] for row in ids_res.fetchall()]

        if not customer_ids:
            raise ValueError("No customers match the campaign filters.")

        # Batch insert recipients, ignoring duplicates safely
        recip_inserts = []
        for cust_id in customer_ids:
            recip_inserts.append({
                "id": uuid.uuid4(),
                "org_id": org_id,
                "campaign_id": campaign_id,
                "customer_id": cust_id
            })

        if recip_inserts:
            await self.db.execute(
                text("""
                    INSERT INTO marketing_campaign_recipients (id, organization_id, campaign_id, customer_id, status, created_at)
                    VALUES (:id, :org_id, :campaign_id, :customer_id, 'pending', NOW())
                    ON CONFLICT (campaign_id, customer_id) DO NOTHING
                """),
                recip_inserts
            )
            # Update campaign status
            await self.db.execute(
                text("UPDATE marketing_campaigns SET status = 'audience_locked', updated_at = NOW() WHERE id = :id"),
                {"id": campaign_id}
            )
            await self.db.commit()

        return len(recip_inserts)

    def compute_content_key(self, org_id: uuid.UUID, campaign_type: str, filters: Dict[str, Any], user_prompt: str, prompt_version: str) -> str:
        """
        Computes a deterministic content key hash to cache AI calls.
        """
        normalized_filters = json.dumps(filters, sort_keys=True)
        raw_str = f"{org_id}:{campaign_type}:{normalized_filters}:{user_prompt.strip()}:{prompt_version}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    async def get_or_generate_content(
        self, org_id: uuid.UUID, campaign_id: uuid.UUID, user_prompt: Optional[str] = None, force_regenerate: bool = False, structured_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolves or generates campaign-level HTML/plain copy using Google Gemini.
        Applies prompt enhancement, templates personalization variables, and caches content by key.
        """
        # Fetch organization AI config
        cfg_res = await self.db.execute(
            text("SELECT system_prompt, campaign_prompt, model, temperature, prompt_version FROM marketing_ai_configs WHERE organization_id = :org_id AND is_active = TRUE"),
            {"org_id": org_id}
        )
        cfg = cfg_res.fetchone()
        if not cfg:
            # Fallback default settings
            system_prompt = "You are a professional B2B logistics cargo marketing assistant."
            campaign_prompt = "Write professional B2B email campaigns focused on freight solutions."
            model = "gemini-2.5-flash"
            temperature = 0.7
            prompt_version = "1.0"
        else:
            system_prompt, campaign_prompt, model, temperature, prompt_version = cfg

        # Fetch organization details (specifically name/display_name)
        org_res = await self.db.execute(
            text("SELECT display_name, name FROM organizations WHERE id = :org_id"),
            {"org_id": org_id}
        )
        org_row = org_res.fetchone()
        org_display_name = org_row[0] if (org_row and org_row[0]) else (org_row[1] if org_row else "FreightForce")

        # Fetch campaign details
        camp_res = await self.db.execute(
            text("SELECT campaign_type, audience_filters, status, custom_prompt FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
            {"id": campaign_id, "org_id": org_id}
        )
        camp = camp_res.fetchone()
        if not camp:
            raise ValueError("Campaign not found.")

        campaign_type, filters_json, status, campaign_custom_prompt = camp
        if campaign_custom_prompt and campaign_custom_prompt.strip().startswith("{"):
            resolved_campaign_prompt = campaign_prompt
        else:
            resolved_campaign_prompt = campaign_custom_prompt if campaign_custom_prompt else campaign_prompt
        filters = filters_json if isinstance(filters_json, dict) else {}
        
        # Build prompt instructions from structured parameters if present
        resolved_user_prompt = user_prompt or ""
        research_context_str = ""
        
        if structured_parameters:
            camp_type = campaign_type or "Custom"
            parts = []
            if camp_type == "Festival":
                parts.append(f"Festival Occasion: {structured_parameters.get('festival_occasion', '')}")
                if structured_parameters.get('message_context'):
                    parts.append(f"Special Context: {structured_parameters.get('message_context')}")
            elif camp_type == "Price Drop":
                parts.append(f"Price Drop Route/Service: {structured_parameters.get('route_service', '')}")
                if structured_parameters.get('previous_rate'):
                    parts.append(f"Previous Rate: {structured_parameters.get('previous_rate')}")
                if structured_parameters.get('new_rate'):
                    parts.append(f"New Rate: {structured_parameters.get('new_rate')}")
                if structured_parameters.get('validity'):
                    parts.append(f"Rate Validity: {structured_parameters.get('validity')}")
            elif camp_type == "Sales":
                parts.append(f"Service Promoted: {structured_parameters.get('promoted_service', '')}")
                if structured_parameters.get('target_opportunity'):
                    parts.append(f"Sales Target/Opportunity: {structured_parameters.get('target_opportunity')}")
                if structured_parameters.get('validity'):
                    parts.append(f"Offer Validity: {structured_parameters.get('validity')}")
            elif camp_type == "Promotional Services":
                region = structured_parameters.get('region', '')
                focus = structured_parameters.get('logistics_focus', '')
                parts.append(f"Campaign Category: Promotional Services")
                parts.append(f"Target Region: {region}")
                parts.append(f"Logistics/Trade Focus: {focus}")
                
                # Minimum research implementation using Google News RSS search
                if region and focus:
                    query = f"{region} {focus} shipping cargo logistics"
                    try:
                        import urllib.request
                        import xml.etree.ElementTree as ET
                        from datetime import datetime
                        import urllib.parse
                        
                        encoded_query = urllib.parse.quote(query)
                        rss_url = f"https://news.google.com/rss/search?q={encoded_query}"
                        
                        # Fetch the RSS feed
                        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
                        # Perform external HTTP call without holding a checked-out DB connection (the service has its own DB session session/engine, but we commit/rollback around the transaction. Since this is get_or_generate_content, we are running on get_db_session yielded db context. The db session itself is not actively locked on any statement during this HTTP call).
                        with urllib.request.urlopen(req, timeout=10.0) as response:
                            xml_data = response.read()
                            
                        # Parse the XML output
                        root = ET.fromstring(xml_data)
                        items = root.findall('.//item')
                        
                        articles = []
                        for i in items[:5]: # Limit to top 5 news entries
                            title_el = i.find('title')
                            link_el = i.find('link')
                            pub_el = i.find('pubDate')
                            
                            title = title_el.text if title_el is not None else ""
                            link = link_el.text if link_el is not None else ""
                            pub_date = pub_el.text if pub_el is not None else ""
                            
                            articles.append(
                                f"SOURCE TITLE: {title}\n"
                                f"SOURCE URL: {link}\n"
                                f"PUBLICATION DATE: {pub_date}\n"
                            )
                        if articles:
                            research_context_str = "\n---\n".join(articles)
                    except Exception as research_err:
                        logger.error("Factual research query failed. Falling back to non-time-sensitive logistics insight generation.", error=str(research_err))
            
            if structured_parameters.get('additional_instructions'):
                parts.append(f"Additional Instructions: {structured_parameters.get('additional_instructions')}")
                
            resolved_user_prompt = ". ".join([p for p in parts if p])

        if not resolved_user_prompt:
            resolved_user_prompt = "Write a B2B logistics cargo marketing campaign email outreach."

        # Compute deterministic content key
        content_key = self.compute_content_key(
            org_id, campaign_type or "Promotion", filters, resolved_user_prompt, prompt_version
        )

        # Check cache if not forced to regenerate
        if not force_regenerate:
            cached_res = await self.db.execute(
                text("""
                    SELECT id, version, subject, preview_text, html_body, plain_text, prompt_version, status, attachments
                    FROM marketing_campaign_contents
                    WHERE campaign_id = :campaign_id AND content_key = :content_key
                    ORDER BY version DESC LIMIT 1
                """),
                {"campaign_id": campaign_id, "content_key": content_key}
            )
            cached = cached_res.fetchone()
            if cached:
                logger.info("Found cached marketing content. Skipping AI call.", campaign_id=str(campaign_id))
                return dict(cached._mapping)

        # Enhance Prompt deterministically
        research_grounding_instruction = ""
        if campaign_type == "Promotional Services":
            if research_context_str:
                research_grounding_instruction = f"""
                FACTUAL GROUNDING GUIDELINE:
                Use only the following supplied recent research context for all claims about recent events. 
                Do not invent news, dates, companies, regulations, statistics, rates, prices, disruptions, or events.
                
                RECENT RESEARCH CONTEXT:
                {research_context_str}
                """
            else:
                research_grounding_instruction = """
                FACTUAL GROUNDING GUIDELINE:
                No verified recent news information is available. Do not claim that any recent news or event occurred. 
                Generate only a general, non-time-sensitive logistics/trade insight related to the selected region and logistics focus.
                """

        enhanced_prompt = f"""
        System Role: {system_prompt}
        Organization Guidance: {resolved_campaign_prompt}
        Campaign Category: {campaign_type}
        Targeting Filters: {json.dumps(filters)}
        User Objectives: {resolved_user_prompt}
        
        Our Company Name: {org_display_name}
        Target Company Name (Literal Placeholder): {{{{customer_company_name}}}}

        {research_grounding_instruction}

        Write a professional B2B logistics outreach email from a real B2B sales representative working for our company ({org_display_name}).
        
        Style & Tone Guidelines:
        - Concise, natural, friendly, consultative human tone (80 to 150 words).
        - Write in simple, friendly, moderate English. Avoid unnecessary business jargon or complex wording.
        - Dynamic Subject Line: Your generated subject line MUST naturally use our company name ({org_display_name}) AND the exact literal placeholder "{{{{customer_company_name}}}}".
          Example: "Special Cargo Offer for {{{{customer_company_name}}}} from {org_display_name}".
          DO NOT generate awkward constructions (e.g. "{org_display_name} X Havells" or "X + Company").
        - Must include personalization placeholder {{{{contact_name}}}} in the greeting (e.g., "Hi {{{{contact_name}}}}" or "Dear {{{{contact_name}}}}").
        - Selective HTML emphasis: You may selectively use <strong>important text</strong> and subtle professional text color for key offer details.
        - Correct spelling errors automatically.
        
        Email Structure:
        1. Personal greeting with {{{{contact_name}}}}
        2. Relevant B2B opening (why this may be relevant to them based on current campaign details or research insights)
        3. Simple natural introduction to our capabilities
        4. Clear customer business value or season/service detail (promoted service, validity, or lane context if mentioned)
        5. Simple conversational CTA/question
        
        CRITICAL RULES:
        - The email body must end naturally with the CTA/question.
        - DO NOT generate any sign-off, closing remarks, or signature blocks.
        - DO NOT include: "Best regards", "Regards", "Sincerely", "Thanks", "FreightForce Cargo Team", any sender names, or company footers.
        
        Output strictly in valid JSON format with keys: "subject", "preview_text", "html_body", "plain_text", "cta".
        Do not surround output with backticks. Return raw JSON only.
        """

        # Validator helper for campaign output validation
        def validate_campaign_response(raw_text: str) -> bool:
            try:
                cleaned = re.sub(r"^```json\s*|\s*```$", "", raw_text, flags=re.MULTILINE).strip()
                parsed = json.loads(cleaned)
                for key in ["subject", "html_body", "plain_text"]:
                    val = parsed.get(key)
                    if not val or not isinstance(val, str) or not val.strip():
                        return False
                
                subject = parsed.get("subject", "")
                html_body = parsed.get("html_body", "")
                plain_text = parsed.get("plain_text", "")
                
                # Check for dynamic customer company placeholder in subject
                if "{{customer_company_name}}" not in subject:
                    return False
                
                # Check that resolved organization name is in the subject (case-insensitive)
                if org_display_name.lower() not in subject.lower():
                    return False

                if "{{contact_name}}" not in html_body and "{{contact_name}}" not in plain_text:
                    return False
                if "{contact_name}" in html_body.replace("{{contact_name}}", ""):
                    return False
                if "{contact_name}" in plain_text.replace("{{contact_name}}", ""):
                    return False
                
                for sig in ["Best regards", "Regards", "Sincerely", "Thanks", "FreightForce Cargo Team"]:
                    if sig.lower() in html_body.lower() or sig.lower() in plain_text.lower():
                        return False
                return True
            except Exception:
                return False

        # Call LLM Service with fallback chain and validations
        try:
            generated_text = await self.llm.generate_text(
                enhanced_prompt, 
                org_id=str(org_id),
                raise_on_error=True,
                validator=validate_campaign_response
            )
            
            cleaned_json = re.sub(r"^```json\s*|\s*```$", "", generated_text, flags=re.MULTILINE).strip()
            parsed = json.loads(cleaned_json)
            subject = parsed.get("subject", "FreightForce Logistics Update")
            preview_text = parsed.get("preview_text", "")
            html_body = parsed.get("html_body", "")
            plain_text = parsed.get("plain_text", "")
            cta = parsed.get("cta", "")
        except Exception as e:
            logger.error("All AI models failed content generation", error=str(e))
            raise RuntimeError("AI content generation failed after trying the configured models. Campaign was not approved. Please try again.") from e

        # Apply strict signature stripping post-processing
        subject = clean_spelling(subject)
        preview_text = clean_spelling(preview_text)
        html_body = strip_signature(clean_spelling(html_body))
        plain_text = strip_signature(clean_spelling(plain_text))

        # Fetch current content version count
        ver_res = await self.db.execute(
            text("SELECT COALESCE(MAX(version), 0) FROM marketing_campaign_contents WHERE campaign_id = :campaign_id"),
            {"campaign_id": campaign_id}
        )
        current_version = ver_res.scalar() or 0
        new_version = current_version + 1

        content_id = uuid.uuid4()
        
        # Save new content version
        await self.db.execute(
            text("""
                INSERT INTO marketing_campaign_contents (
                    id, campaign_id, version, subject, preview_text, html_body, plain_text, 
                    prompt_version, status, content_key, attachments, created_at, updated_at
                ) VALUES (
                    :id, :campaign_id, :version, :subject, :preview_text, :html_body, :plain_text,
                    :prompt_version, 'draft', :content_key, '[]'::jsonb, NOW(), NOW()
                )
            """),
            {
                "id": content_id,
                "campaign_id": campaign_id,
                "version": new_version,
                "subject": subject,
                "preview_text": preview_text,
                "html_body": html_body,
                "plain_text": plain_text,
                "prompt_version": prompt_version,
                "content_key": content_key
            }
        )
        await self.db.commit()

        return {
            "id": content_id,
            "campaign_id": campaign_id,
            "version": new_version,
            "subject": subject,
            "preview_text": preview_text,
            "html_body": html_body,
            "plain_text": plain_text,
            "prompt_version": prompt_version,
            "status": "draft",
            "attachments": []
        }

    async def approve_content(self, org_id: uuid.UUID, campaign_id: uuid.UUID, content_id: uuid.UUID, attachments: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Marks the specified content version as approved, updating the campaign state to approved.
        """
        # Verify content exists and belongs to the campaign
        verify_res = await self.db.execute(
            text("""
                SELECT c.id FROM marketing_campaign_contents cc
                JOIN marketing_campaigns c ON c.id = cc.campaign_id
                WHERE cc.id = :content_id AND c.id = :campaign_id AND c.organization_id = :org_id
            """),
            {"content_id": content_id, "campaign_id": campaign_id, "org_id": org_id}
        )
        if not verify_res.fetchone():
            raise ValueError("Content or Campaign association not found.")

        # Update all other content versions of the campaign to draft
        await self.db.execute(
            text("UPDATE marketing_campaign_contents SET status = 'draft' WHERE campaign_id = :campaign_id"),
            {"campaign_id": campaign_id}
        )

        # Set selected version as approved & save optional attachments metadata
        if attachments is not None:
            await self.db.execute(
                text("UPDATE marketing_campaign_contents SET status = 'approved', attachments = CAST(:attachments AS jsonb) WHERE id = :content_id"),
                {"content_id": content_id, "attachments": json.dumps(attachments)}
            )
        else:
            await self.db.execute(
                text("UPDATE marketing_campaign_contents SET status = 'approved' WHERE id = :content_id"),
                {"content_id": content_id}
            )

        # Set campaign status to approved
        await self.db.execute(
            text("UPDATE marketing_campaigns SET status = 'approved' WHERE id = :campaign_id"),
            {"campaign_id": campaign_id}
        )
        await self.db.commit()

    async def activate_campaign(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> None:
        """
        Activates a campaign. Enforces only one active campaign per organization.
        """
        # Check active campaign rule constraint
        active_res = await self.db.execute(
            text("SELECT id FROM marketing_campaigns WHERE organization_id = :org_id AND status = 'active' AND id != :campaign_id"),
            {"org_id": org_id, "campaign_id": campaign_id}
        )
        if active_res.fetchone():
            raise ValueError("Another campaign is already active for this organization. You must complete or pause it first.")

        # Verify campaign is in approved state
        verify_res = await self.db.execute(
            text("SELECT status FROM marketing_campaigns WHERE id = :id AND organization_id = :org_id"),
            {"id": campaign_id, "org_id": org_id}
        )
        camp = verify_res.fetchone()
        if not camp:
            raise ValueError("Campaign not found.")
        
        status = camp[0]
        if status != "approved":
            raise ValueError(f"Cannot activate campaign in '{status}' status. It must be approved first.")

        await self.db.execute(
            text("UPDATE marketing_campaigns SET status = 'active', started_at = NOW(), updated_at = NOW() WHERE id = :id"),
            {"id": campaign_id}
        )
        await self.db.commit()
