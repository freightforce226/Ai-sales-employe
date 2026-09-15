"""
Phase 2A - Bounce / DSN Detection Service
==========================================
Detects inbound DSN (Delivery Status Notification) emails from MAILER-DAEMON
or Postmaster, parses them, and records the bounce result back into email_log.

Constraints:
- Does NOT alter delivery_status (stays 'sent').
- Does NOT suppress customers or stop campaigns.
- Matches strictly by Message-ID / References from the original outbound email.
- Never updates an email_log row based on recipient email address alone.
"""

import re
import email as email_lib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.schemas.inbound_message import InboundMessage

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Senders that are well-known DSN/bounce originators
_BOUNCE_SENDER_PATTERNS = re.compile(
    r"(mailer-daemon|postmaster|mail-daemon|noreply|delivery-notification"
    r"|bounce|bounced|daemon@|mdaemon|mailerdaemon)",
    re.IGNORECASE,
)

# Subject patterns that strongly indicate a delivery failure notification
_BOUNCE_SUBJECT_PATTERNS = [
    "delivery status notification",
    "delivery failure",
    "mail delivery failed",
    "mail delivery failure",
    "undeliverable",
    "returned mail",
    "failed delivery",
    "nondelivery report",
    "non-delivery",
    "message not delivered",
    "delivery notification",
    "could not be delivered",
    "failure notice",
    "delivery problem",
    "retry timeout exceeded",
    "bounce",
]

# SMTP status codes that indicate hard vs. soft bounce
# 5xx = permanent (hard), 4xx = transient (soft)
_HARD_BOUNCE_CODES = re.compile(r"\b5\d{2}\b")
_SOFT_BOUNCE_CODES = re.compile(r"\b4\d{2}\b")

# RFC 3464 DSN header fields
_FINAL_RECIPIENT_RE = re.compile(
    r"Final-Recipient\s*:\s*(?:rfc822\s*;\s*)?(.+)", re.IGNORECASE
)
_STATUS_RE = re.compile(r"Status\s*:\s*(\d+\.\d+\.\d+)", re.IGNORECASE)
_DIAGNOSTIC_RE = re.compile(r"Diagnostic-Code\s*:\s*(.+)", re.IGNORECASE)
_ORIGINAL_MSG_ID_RE = re.compile(
    r"Original-Message-ID\s*:\s*(.+)", re.IGNORECASE
)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


class BounceDetectionService:
    """
    Singleton-style service (one instance per sync call) that inspects an
    inbound InboundMessage, decides if it is a bounce/DSN, attempts to match
    it to the original outbound email_log row, and records the bounce result.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ──────────────────────────────────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────────────────────────────────

    async def process(self, msg: InboundMessage) -> dict:
        """
        Attempt to detect and record a bounce for *msg*.

        Returns a dict::

            {
                "is_bounce": bool,
                "bounce_type": "hard_bounce" | "soft_bounce" | None,
                "matched_email_log_id": UUID | None,
                "bounce_reason": str | None,
            }
        """
        result = {
            "is_bounce": False,
            "bounce_type": None,
            "matched_email_log_id": None,
            "bounce_reason": None,
        }

        # Step 1 – Quick sender / subject heuristic
        if not self._looks_like_bounce(msg):
            return result

        result["is_bounce"] = True
        logger.info(
            "Potential bounce DSN detected",
            subject=msg.subject,
            from_email=msg.from_email,
        )

        # Step 2 – Parse the DSN for details
        parsed = self._parse_dsn(msg)
        bounce_type = parsed.get("bounce_type")  # 'hard_bounce' or 'soft_bounce'
        result["bounce_type"] = bounce_type
        result["bounce_reason"] = parsed.get("bounce_reason")

        if not bounce_type:
            # We can't classify – log but don't update DB
            logger.info(
                "Bounce detected but could not classify as hard/soft; skipping DB update",
                subject=msg.subject,
            )
            return result

        # Step 3 – Match to original outbound email_log by Message-ID
        original_id = await self._match_original_email_log(msg, parsed)
        if not original_id:
            logger.info(
                "Bounce detected but no matching outbound email_log found by Message-ID",
                subject=msg.subject,
                in_reply_to=msg.in_reply_to,
                references=msg.references,
                parsed_original_msg_id=parsed.get("original_message_id"),
            )
            return result

        result["matched_email_log_id"] = original_id

        # Step 4 – Record bounce in DB (only bounce_status + bounce_reason)
        await self._record_bounce(
            email_log_id=original_id,
            bounce_type=bounce_type,
            bounce_reason=parsed.get("bounce_reason"),
        )

        # Step 5 – Record email suppression for hard bounces (Phase 2B)
        if bounce_type == "hard_bounce":
            await self._record_email_suppression(
                email_log_id=original_id,
                bounce_reason=parsed.get("bounce_reason"),
            )

        logger.info(
            "Bounce recorded in email_log",
            email_log_id=str(original_id),
            bounce_type=bounce_type,
            bounce_reason=parsed.get("bounce_reason"),
        )

        return result


    # ──────────────────────────────────────────────────────────────────────────
    # Step 1 – Heuristic detection
    # ──────────────────────────────────────────────────────────────────────────

    def _looks_like_bounce(self, msg: InboundMessage) -> bool:
        from_email = (msg.from_email or "").lower()
        subject = (msg.subject or "").lower()

        # Sender heuristic
        if _BOUNCE_SENDER_PATTERNS.search(from_email):
            return True

        # Subject heuristic
        if any(pat in subject for pat in _BOUNCE_SUBJECT_PATTERNS):
            return True

        return False

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2 – DSN parsing
    # ──────────────────────────────────────────────────────────────────────────

    def _parse_dsn(self, msg: InboundMessage) -> dict:
        """
        Parse the DSN body / headers to extract:
        - original_message_id (the Message-ID we originally sent)
        - bounce_type (hard_bounce / soft_bounce)
        - bounce_reason (human-readable diagnostic)
        """
        parsed = {
            "original_message_id": None,
            "bounce_type": None,
            "bounce_reason": None,
            "final_recipient": None,
            "status_code": None,
        }

        # Combine all text available for scanning
        text_blob = "\n".join(
            filter(None, [msg.subject, msg.html_body, msg.in_reply_to, msg.references])
        )

        # ── Original-Message-ID (RFC 3464)
        parsed["original_message_id"] = self._extract_original_message_id(
            msg, text_blob
        )

        # ── Final-Recipient
        m = _FINAL_RECIPIENT_RE.search(text_blob)
        if m:
            parsed["final_recipient"] = m.group(1).strip()

        # ── DSN Status Code (e.g. 5.1.1)
        m = _STATUS_RE.search(text_blob)
        if m:
            parsed["status_code"] = m.group(1).strip()

        # ── Diagnostic-Code
        m = _DIAGNOSTIC_RE.search(text_blob)
        if m:
            parsed["bounce_reason"] = m.group(1).strip()[:500]

        # ── Fallback: collect first 500 chars of body as reason
        if not parsed["bounce_reason"] and msg.html_body:
            # Strip HTML tags for a readable reason
            plain = re.sub(r"<[^>]+>", " ", msg.html_body)
            plain = re.sub(r"\s+", " ", plain).strip()
            parsed["bounce_reason"] = plain[:500]

        # ── Bounce type classification
        parsed["bounce_type"] = self._classify_bounce(text_blob, parsed.get("status_code"))

        return parsed

    def _extract_original_message_id(self, msg: InboundMessage, text_blob: str) -> Optional[str]:
        """
        Attempt to find the Message-ID of the original outbound email.
        Priority:
          1. in_reply_to header (most reliable for DSNs)
          2. References header (first or last entry)
          3. Original-Message-ID DSN header parsed from body
          4. X-Failed-Recipients / X-Spam-Status (Exim/cPanel specific)
        """
        # 1. in_reply_to
        if msg.in_reply_to:
            candidate = msg.in_reply_to.strip()
            if candidate.startswith("<") or "@" in candidate:
                return candidate

        # 2. References – try each entry
        if msg.references:
            refs = msg.references.split()
            # Prefer last (most recent outbound)
            for ref in reversed(refs):
                ref = ref.strip()
                if ref.startswith("<") or "@" in ref:
                    return ref

        # 3. RFC 3464 Original-Message-ID in body
        m = _ORIGINAL_MSG_ID_RE.search(text_blob)
        if m:
            return m.group(1).strip()

        # 4. Scan body for any <...@...> that looks like a Message-ID
        ids_in_body = re.findall(r"<[^@<>\s]+@[^@<>\s]+>", text_blob)
        if ids_in_body:
            return ids_in_body[0]

        return None

    def _classify_bounce(self, text_blob: str, status_code: Optional[str]) -> Optional[str]:
        """
        Classify as 'hard_bounce' (5xx / permanent) or 'soft_bounce' (4xx / transient).
        """
        # Use DSN status code first (most reliable)
        if status_code:
            major = status_code.split(".")[0]
            if major == "5":
                return "hard_bounce"
            if major == "4":
                return "soft_bounce"

        # Fall back to scanning text for raw SMTP codes
        if _HARD_BOUNCE_CODES.search(text_blob):
            return "hard_bounce"
        if _SOFT_BOUNCE_CODES.search(text_blob):
            return "soft_bounce"

        # If no SMTP codes found but subject/sender indicates bounce, default to hard
        # (conservative: we'd rather mark unknown bounces as hard so they're visible)
        return "hard_bounce"

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3 – Match to original outbound email_log
    # ──────────────────────────────────────────────────────────────────────────

    async def _match_original_email_log(
        self, msg: InboundMessage, parsed: dict
    ) -> Optional[object]:
        """
        Attempt to match to an outbound email_log row using Message-ID(s).
        Returns the email_log.id (UUID) if found, else None.

        IMPORTANT: never matches on recipient email address alone.
        """
        candidates: list[str] = []

        if parsed.get("original_message_id"):
            candidates.append(parsed["original_message_id"])

        if msg.in_reply_to and msg.in_reply_to not in candidates:
            candidates.append(msg.in_reply_to.strip())

        if msg.references:
            for ref in msg.references.split():
                ref = ref.strip()
                if ref and ref not in candidates:
                    candidates.append(ref)

        if not candidates:
            return None

        # Query: find outbound email_log by internet_message_id
        for candidate_id in candidates:
            # Exact match on internet_message_id
            res = await self.db.execute(
                text("""
                    SELECT id FROM email_log
                    WHERE internet_message_id = :msg_id
                      AND direction = 'outbound'
                    LIMIT 1
                """),
                {"msg_id": candidate_id},
            )
            row = res.fetchone()
            if row:
                logger.info(
                    "Bounce matched outbound email by internet_message_id",
                    message_id=candidate_id,
                    email_log_id=str(row[0]),
                )
                return row[0]

            # Fallback: graph_message_id (in case IMAP populates provider_message_id)
            res = await self.db.execute(
                text("""
                    SELECT id FROM email_log
                    WHERE graph_message_id = :msg_id
                      AND direction = 'outbound'
                    LIMIT 1
                """),
                {"msg_id": candidate_id},
            )
            row = res.fetchone()
            if row:
                logger.info(
                    "Bounce matched outbound email by graph_message_id",
                    message_id=candidate_id,
                    email_log_id=str(row[0]),
                )
                return row[0]

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4 – Record bounce in DB
    # ──────────────────────────────────────────────────────────────────────────

    async def _record_bounce(
        self,
        email_log_id: object,
        bounce_type: str,
        bounce_reason: Optional[str],
    ) -> None:
        """
        Updates email_log.bounce_status and email_log.bounce_reason.
        NEVER modifies delivery_status.

        bounce_type must be one of: 'hard_bounce', 'soft_bounce', 'complaint'
        (these are the valid enum values from bounce_status_type).
        """
        # Only update if not already marked (idempotent)
        await self.db.execute(
            text("""
                UPDATE email_log
                SET bounce_status   = CAST(:bounce_type AS bounce_status_type),
                    bounce_reason   = :bounce_reason,
                    bounced_at      = NOW()
                WHERE id = :email_log_id
                  AND (bounce_status IS NULL OR CAST(bounce_status AS text) = 'none')
            """),
            {
                "bounce_type": bounce_type,
                "bounce_reason": bounce_reason,
                "email_log_id": email_log_id,
            },
        )
        await self.db.commit()

    async def _record_email_suppression(
        self,
        email_log_id: object,
        bounce_reason: Optional[str],
    ) -> None:
        """
        Inserts recipient email address into email_suppressions table (Phase 2B).
        Strictly associated with (organization_id, lower(email_address)).
        Idempotent ON CONFLICT DO NOTHING.
        """
        # Fetch organization_id and recipient email via customer_id → customers.contact_email
        # NOTE: email_log has no direct recipient_email column; the address lives on the customer.
        res = await self.db.execute(
            text("""
                SELECT el.organization_id, c.contact_email
                FROM email_log el
                JOIN customers c ON c.id = el.customer_id
                WHERE el.id = :email_log_id
            """),
            {"email_log_id": email_log_id},
        )
        row = res.fetchone()
        if not row or not row[0] or not row[1]:
            logger.warning("Cannot record suppression: email_log organization_id or recipient_email missing", email_log_id=str(email_log_id))
            return

        org_id, recipient_email = row[0], row[1].strip()

        await self.db.execute(
            text("""
                INSERT INTO email_suppressions (
                    organization_id,
                    email_address,
                    reason,
                    bounce_reason,
                    suppressed_at,
                    created_at
                )
                VALUES (
                    :org_id,
                    :email_address,
                    'hard_bounce',
                    :bounce_reason,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (organization_id, email_address) DO NOTHING
            """),
            {
                "org_id": org_id,
                "email_address": recipient_email,
                "bounce_reason": bounce_reason,
            },
        )
        await self.db.commit()
        logger.info(
            "Hard bounce suppression recorded for email address",
            org_id=str(org_id),
            email_address=recipient_email,
        )

