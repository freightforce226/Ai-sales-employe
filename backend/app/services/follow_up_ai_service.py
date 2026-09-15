"""
===========================================================

File:
follow_up_ai_service.py

Purpose:
Orchestrates Follow-Up AI Prompt Construction, 24-Hour Step-Wise DB Caching,
Deterministic Personalization, and LLM Invocation with Fallback.

===========================================================
"""

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.llm_service import LLMService
from app.core.logging import get_logger

logger = get_logger(__name__)

PROMPT_VERSION = "followup_v3"

INVALID_NAMES = {"null", "undefined", "unknown", "test", "team", "sir", "madam", "valued customer", "customer", "there"}
INVALID_COMPANIES = {"null", "undefined", "unknown", "test", "your company", "company", "client"}


def resolve_deterministic_greeting(contact_name: Optional[str], company_name: Optional[str]) -> str:
    """
    Deterministically computes recipient greeting with ZERO LLM token consumption.
    1. Valid First Name -> "Hi Rahul,"
    2. Valid Company Name -> "Hello SharmaTech team,"
    3. Fallback -> "Hello Sir,"
    """
    if contact_name:
        clean_name = re.sub(r'[^\w\s-]', '', str(contact_name)).strip()
        # Reject purely numeric names, postal codes, phone numbers, or customer IDs (e.g. "99271")
        if not clean_name.isdigit() and not re.match(r'^\d+$', clean_name):
            parts = clean_name.split()
            if parts:
                first_name = parts[0].capitalize()
                # Ensure first_name contains at least one alphabetic character and is not numeric
                if (
                    first_name.lower() not in INVALID_NAMES 
                    and len(first_name) > 1 
                    and not first_name.isdigit()
                    and any(c.isalpha() for c in first_name)
                ):
                    return f"Hi {first_name},"

    if company_name:
        clean_company = str(company_name).strip()
        if (
            clean_company.lower() not in INVALID_COMPANIES 
            and len(clean_company) > 1 
            and not clean_company.isdigit()
            and any(c.isalpha() for c in clean_company)
        ):
            return f"Hello {clean_company} team,"

    return "Hello,"


def sanitize_commercial_context(body_text: str) -> str:
    """
    Strips recipient PII, greetings, and dynamic footers while preserving 
    commercially meaningful context (origin/destination, freight mode, rates, services).
    """
    text = body_text or ""
    # Strip HTML
    text = re.sub(r'<[^>]+>', ' ', text)
    # Strip greetings (Hi Rahul, Dear Rohan, Hello SharmaTech)
    text = re.sub(r'^(?:hi|hello|dear|greetings)\s+[\w\s,-]+[!\.,]?', '', text, flags=re.IGNORECASE)
    # Strip email addresses and phone numbers
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text)
    text = re.sub(r'\+?\d[\d\s-]{7,}\d', '', text)
    # Normalize whitespace & lowercase
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def compute_normalized_cache_key(
    organization_id: str,
    step_number: int,
    previous_subject: str,
    previous_body: str,
    customer_company: Optional[str] = None,
    industry: Optional[str] = None,
    goods_description: Optional[str] = None,
    shipment_mode: Optional[str] = None,
    prompt_version: str = PROMPT_VERSION
) -> Tuple[str, Dict[str, Any]]:
    """
    Computes a deterministic SHA-256 cache key based on commercial generation context and verified customer parameters.
    """
    sanitized_body = sanitize_commercial_context(previous_body)
    body_hash = hashlib.sha256(sanitized_body.encode("utf-8")).hexdigest()
    normalized_subj = (previous_subject or '').strip().lower()
    norm_company = (customer_company or '').strip().lower()
    norm_industry = (industry or '').strip().lower()
    norm_goods = (goods_description or '').strip().lower()
    norm_mode = (shipment_mode or '').strip().lower()

    context_payload = {
        "org_id": str(organization_id),
        "step": int(step_number),
        "prompt_version": prompt_version,
        "normalized_subject": normalized_subj,
        "body_hash": body_hash,
        "customer_company": norm_company,
        "industry": norm_industry,
        "goods_description": norm_goods,
        "shipment_mode": norm_mode
    }

    serialized = json.dumps(context_payload, sort_keys=True)
    cache_key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return cache_key, context_payload


class FollowUpAIService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMService()

    async def generate_followup_email(
        self,
        organization_id: UUID,
        customer_id: UUID,
        step_number: int,
        customer_name: Optional[str] = None,
        customer_company: Optional[str] = None,
        organization_name: Optional[str] = None,
        previous_subject: Optional[str] = None,
        previous_body: Optional[str] = None,
        email_thread: Optional[list] = None,
        industry: Optional[str] = None,
        goods_description: Optional[str] = None,
        shipment_mode: Optional[str] = None,
        trade_region: Optional[str] = None,
        trade_direction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Orchestrates AI Generation with 24-Hour DB Caching & Deterministic Personalization.
        """
        start_time = time.perf_counter()
        org_id_str = str(organization_id)
        
        # 1. Compute Cache Key (Includes customer company and verified commercial attributes to isolate cache entries)
        cache_key, norm_payload = compute_normalized_cache_key(
            organization_id=org_id_str,
            step_number=step_number,
            previous_subject=previous_subject or "",
            previous_body=previous_body or "",
            customer_company=customer_company,
            industry=industry,
            goods_description=goods_description,
            shipment_mode=shipment_mode
        )

        # 2. Check DB Cache (Strict 24-Hour TTL: expires_at > NOW())
        cache_res = await self.db.execute(
            text("""
                SELECT generated_subject, generated_body_template, model_used
                FROM follow_up_ai_cache
                WHERE organization_id = :org_id
                  AND step_number = :step_num
                  AND cache_key = :c_key
                  AND expires_at > NOW()
                LIMIT 1
            """),
            {"org_id": organization_id, "step_num": step_number, "c_key": cache_key}
        )
        cache_row = cache_res.fetchone()

        if cache_row:
            cached_subj, cached_body_template, model_used = cache_row
            
            # Increment hit count atomically
            await self.db.execute(
                text("""
                    UPDATE follow_up_ai_cache
                    SET hit_count = hit_count + 1
                    WHERE organization_id = :org_id AND step_number = :step_num AND cache_key = :c_key
                """),
                {"org_id": organization_id, "step_num": step_number, "c_key": cache_key}
            )
            await self.db.commit()

            # Apply Deterministic Greeting
            greeting = resolve_deterministic_greeting(customer_name, customer_company)
            final_body = f"<p>{greeting}</p>{cached_body_template}"
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "FOLLOWUP_AI_CACHE_HIT",
                organization_id=org_id_str,
                step_number=step_number,
                cache_key=cache_key,
                duration_ms=elapsed_ms
            )

            return {
                "success": True,
                "subject": cached_subj,
                "body": final_body,
                "llm_called": False,
                "tokens_consumed": 0,
                "cache_hit": True,
                "step_number": step_number,
                "model_used": model_used,
                "generation_time_ms": elapsed_ms
            }

        # 3. Cache MISS -> Acquire Advisory Lock on (org_id + cache_key) for Concurrency Safety
        lock_id = int(hashlib.sha256(f"{org_id_str}:{cache_key}".encode()).hexdigest()[:15], 16) % (2**63 - 1)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

        # Re-check Cache (Double-Checked Locking pattern)
        recheck_res = await self.db.execute(
            text("""
                SELECT generated_subject, generated_body_template, model_used
                FROM follow_up_ai_cache
                WHERE organization_id = :org_id
                  AND step_number = :step_num
                  AND cache_key = :c_key
                  AND expires_at > NOW()
                LIMIT 1
            """),
            {"org_id": organization_id, "step_num": step_number, "c_key": cache_key}
        )
        recheck_row = recheck_res.fetchone()
        if recheck_row:
            cached_subj, cached_body_template, model_used = recheck_row
            greeting = resolve_deterministic_greeting(customer_name, customer_company)
            final_body = f"<p>{greeting}</p>{cached_body_template}"
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "success": True,
                "subject": cached_subj,
                "body": final_body,
                "llm_called": False,
                "tokens_consumed": 0,
                "cache_hit": True,
                "step_number": step_number,
                "model_used": model_used,
                "generation_time_ms": elapsed_ms
            }

        # 4. Construct Backend Prompt with Explicit Fact Categorization
        prompt = self._build_prompt(
            step_number=step_number,
            organization_name=organization_name or "our logistics team",
            previous_subject=previous_subject or "N/A",
            previous_body=previous_body or "N/A",
            customer_company=customer_company,
            industry=industry,
            goods_description=goods_description,
            shipment_mode=shipment_mode,
            trade_region=trade_region,
            trade_direction=trade_direction
        )

        # 5. Invoke LLM via LLMService (with configured Gemini model & fallback chain)
        raw_output = await self.llm.generate_text(
            prompt=prompt,
            org_id=org_id_str,
            raise_on_error=True
        )

        # Parse output JSON
        subj, body_template = self._parse_llm_json(raw_output)

        # 6. Store in DB Cache with 24-Hour Expiry
        model_used = self.llm.model_name or "gemini-2.5-flash"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24)

        await self.db.execute(
            text("""
                INSERT INTO follow_up_ai_cache 
                (organization_id, step_number, cache_key, generated_subject, generated_body_template, prompt_version, model_used, tokens_consumed, hit_count, created_at, expires_at)
                VALUES (:org_id, :step_num, :c_key, :subj, :body_tpl, :p_ver, :model, :tokens, 1, :now, :exp)
                ON CONFLICT (organization_id, step_number, cache_key)
                DO UPDATE SET
                    generated_subject = EXCLUDED.generated_subject,
                    generated_body_template = EXCLUDED.generated_body_template,
                    model_used = EXCLUDED.model_used,
                    created_at = EXCLUDED.created_at,
                    expires_at = EXCLUDED.expires_at,
                    hit_count = follow_up_ai_cache.hit_count + 1
            """),
            {
                "org_id": organization_id,
                "step_num": step_number,
                "c_key": cache_key,
                "subj": subj,
                "body_tpl": body_template,
                "p_ver": PROMPT_VERSION,
                "model": model_used,
                "tokens": 450,  # Estimated tokens for fresh generation
                "now": now,
                "exp": expires_at
            }
        )
        await self.db.commit()

        # Apply Personalization
        greeting = resolve_deterministic_greeting(customer_name, customer_company)
        final_body = f"<p>{greeting}</p>{body_template}"
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "FOLLOWUP_AI_GENERATION_SUCCESS",
            organization_id=org_id_str,
            step_number=step_number,
            cache_key=cache_key,
            model_used=model_used,
            duration_ms=elapsed_ms
        )

        return {
            "success": True,
            "subject": subj,
            "body": final_body,
            "llm_called": True,
            "tokens_consumed": 450,
            "cache_hit": False,
            "step_number": step_number,
            "model_used": model_used,
            "generation_time_ms": elapsed_ms
        }

    def _build_prompt(
        self,
        step_number: int,
        organization_name: str,
        previous_subject: str,
        previous_body: str,
        customer_company: Optional[str] = None,
        industry: Optional[str] = None,
        goods_description: Optional[str] = None,
        shipment_mode: Optional[str] = None,
        trade_region: Optional[str] = None,
        trade_direction: Optional[str] = None
    ) -> str:
        """
        Constructs the backend prompt anchored strictly to verified context.
        Enforces strict Fact Hierarchy: Verified CRM Facts > Previous Email Context.
        """
        step_objectives = {
            1: "Step 1: Re-open conversation naturally. Reference the original offer and clarify value. Low-pressure CTA.",
            2: "Step 2: Introduce a fresh commercial angle (routing, rate options, transit reliability) related to the original offer. ZERO Step 1 repetition.",
            3: "Step 3: Professional soft closing. Leave door open for future requirements with zero pressure or desperation."
        }
        step_obj = step_objectives.get(step_number, f"Step {step_number}: Continue conversation with fresh commercial value.")

        # Clean verified customer attributes
        clean_company = str(customer_company).strip() if customer_company and str(customer_company).strip().lower() not in ["null", "none", "unknown", ""] else "Current Customer"
        clean_industry = str(industry).strip() if industry and str(industry).strip().lower() not in ["null", "none", "unknown", ""] else "Unknown"
        clean_goods = str(goods_description).strip() if goods_description and str(goods_description).strip().lower() not in ["null", "none", "unknown", ""] else "Unknown"
        clean_mode = str(shipment_mode).strip() if shipment_mode and str(shipment_mode).strip().lower() not in ["null", "none", "unknown", ""] else "Unknown"
        clean_region = str(trade_region).strip() if trade_region and str(trade_region).strip().lower() not in ["null", "none", "unknown", ""] else "Unknown"
        clean_direction = str(trade_direction).strip() if trade_direction and str(trade_direction).strip().lower() not in ["null", "none", "unknown", ""] else "Unknown"

        return f"""
You are an experienced freight-forwarding sales executive representing {organization_name}.

ROLE & OBJECTIVE:
- Write a professional, short, attractive one-to-one sales follow-up email.
- {step_obj}

VERIFIED CURRENT CUSTOMER FACTS (AUTHORITATIVE TRUTH):
- Customer Company Name: {clean_company}
- Industry: {clean_industry}
- Goods / Commodity: {clean_goods}
- Verified Shipment Mode: {clean_mode}
- Trade Region: {clean_region}
- Trade Direction: {clean_direction}

PREVIOUS EMAIL CONTEXT (FOR TONE/COMMUNICATION STYLE ONLY — NOT VERIFIED CUSTOMER FACTS):
Subject: {previous_subject}
Body: {previous_body}

STRICT SAFETY & CONTAMINATION PREVENTION RULES:
1. FACT ISOLATION:
   - Previous email content is ONLY for tone and general offer context.
   - DO NOT copy or mention any specific third-party companies (e.g. "Anand Motors"), event names (e.g. "ACMA"), specific unverified countries, ports, or trade lanes from the previous email text.
   - Use the Current Customer Company Name ({clean_company}) as the lead company name.

2. SERVICE MODE ACCURACY:
   - If Verified Shipment Mode is "Unknown", do NOT assume or default to "Ocean Freight". Use general logistics terms like "freight services", "logistics requirements", or "export/import moves".
   - Only mention "Air Freight" or "Ocean Freight" if it is explicitly listed in Verified Shipment Mode above.

3. SUBJECT LINE GENERATION RULES:
   - Generate a short, attractive, professional base subject line.
   - Preferred format: "COOPERATION {organization_name.upper()} & {clean_company.upper()}" or "Commercial collaboration - {organization_name} & {clean_company}".
   - NEVER include ACMA, Anand Motors, or unverified event/company names in the subject.
   - NEVER hardcode "Ocean Freight" in the subject unless verified in Shipment Mode.
   - DO NOT prefix the subject with "Re:" (the sending system handles thread prefixes automatically).

4. COPYWRITING REQUIREMENTS & LENGTH:
   - Keep the body concise (50 to 90 words, 2 short paragraphs max).
   - Use light bold formatting on key value propositions or company name (e.g. **{clean_company}** or **{organization_name}**). Do not overuse bolding.
   - Write body content ONLY. Do NOT generate greetings (e.g. "Hi Name") as greetings are appended deterministically.
   - Forbidden words: "hope this email finds you well", "just following up", "checking in", "gentle reminder", "touch base", "optimize", "leverage", "seamless", "synergy".

5. ABSOLUTE SIGNATURE PROHIBITION:
   - DO NOT include ANY email closing or signature (e.g., "Best regards", "Kind regards", "Thanks", "Sincerely", or sender name).
   - The backend automatically appends the user's signature after the body.

OUTPUT FORMAT:
Return strictly valid JSON only:
{{
  "subject": "COOPERATION {organization_name.upper()} & {clean_company.upper()}",
  "body": "<p>First short paragraph introducing value for **{clean_company}**.</p><p>Brief, low-pressure question asking for a short call or rate check.</p>"
}}
"""


    def _parse_llm_json(self, raw_text: str) -> Tuple[str, str]:
        """
        Extracts subject and body from LLM output JSON securely.
        Post-processes body to remove greetings and signatures.
        """
        try:
            # Strip markdown codeblocks if present
            cleaned = re.sub(r'```json\s*', '', raw_text)
            cleaned = re.sub(r'```\s*$', '', cleaned).strip()
            data = json.loads(cleaned)
            subj = data.get("subject", "").strip()
            body = data.get("body", "").strip()

            # Clean subject: strip any LLM generated "Re:" or "Fwd:" prefixes (handled automatically at send time)
            subj = re.sub(r'^(?:(re|fwd|reply):\s*)+', '', subj, flags=re.IGNORECASE).strip()

            # Remove any greeting Gemini might have generated accidentally
            body = re.sub(r'^<p>\s*(Hi|Hello|Dear|Greetings)[^,<]*[,!]?\s*</p>', '', body, flags=re.IGNORECASE).strip()

            # Strip any trailing email signature / closing (e.g. Best regards, Sincerely, Thanks, Regards)
            sig_patterns = [
                r'(?i)<p>\s*(?:best\s+regards|kind\s+regards|warm\s+regards|regards|thanks|sincerely|thank\s+you)[^<]*</p>.*$',
                r'(?i)(?:<p>|<br\s*/?>|\n)\s*(?:best\s+regards|kind\s+regards|warm\s+regards|regards|thanks|sincerely|thank\s+you)[,\s]*.*$'
            ]
            for pat in sig_patterns:
                body = re.sub(pat, '', body, flags=re.DOTALL).strip()

            if not subj or not body:
                raise ValueError("LLM returned empty subject or body.")

            return subj, body
        except Exception as e:
            logger.error("Failed to parse LLM JSON response", raw_output=raw_text, error=str(e))
            return "Commercial collaboration & freight options", "<p>Following up on our previous conversation regarding freight rates and routing options. Let us know whenever you have an upcoming movement to review.</p>"
