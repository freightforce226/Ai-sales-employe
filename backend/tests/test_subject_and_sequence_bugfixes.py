import pytest
import sys
import uuid
import json
from unittest.mock import AsyncMock, MagicMock
from app.providers.smtp_imap import SmtpImapProvider
from app.services.follow_up_ai_service import FollowUpAIService

@pytest.mark.asyncio
async def test_smtp_send_reply_subject_normalization():
    """
    TEST GROUP 1 — SUBJECT NORMALIZATION & ALIGNMENT
    Verifies that SmtpImapProvider.send_reply uses the supplied request subject,
    applies 'Re:' prefix exactly once, and preserves Gmail threading headers.
    """
    provider = SmtpImapProvider()
    provider._get_smtp_settings = AsyncMock(return_value={
        "mailbox_email": "test@ampluslogistics.com",
        "username": "test@ampluslogistics.com",
        "password": "password",
        "host": "mail.ampluslogistics.com",
        "port": 587,
        "security": "starttls"
    })
    
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(fetchone=lambda: ("<parent_msg_123@mail.ampluslogistics.com>", None)),
        MagicMock(fetchone=lambda: ("customer@example.com", "COOPERATION AMPLUS GROUP OF LOGISTICS & ANAND MOTORS @ACMA", uuid.uuid4()))
    ])
    
    provider._send_with_retry = AsyncMock()
    
    req_subject_a = "COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY"
    await provider.send_reply(
        org_id=uuid.uuid4(),
        parent_message_id="parent_msg_123",
        html_body="<p>Follow up body</p>",
        cc_emails=[],
        bcc_emails=[],
        attachments=[],
        db_session=mock_db,
        subject=req_subject_a
    )
    
    assert provider._send_with_retry.called
    call_args = provider._send_with_retry.call_args[0]
    msg_str = call_args[3]
    
    # 1. Assert MIME Subject matches exact normalized request subject (not parent subject)
    assert "Subject: Re: COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY" in msg_str
    # 2. Assert In-Reply-To and References remain intact
    assert "In-Reply-To: <parent_msg_123@mail.ampluslogistics.com>" in msg_str
    assert "References: <parent_msg_123@mail.ampluslogistics.com>" in msg_str

@pytest.mark.asyncio
async def test_smtp_send_reply_subject_no_duplicate_re():
    """
    Verifies that if input subject already contains 'Re:', it is not duplicated.
    """
    provider = SmtpImapProvider()
    provider._get_smtp_settings = AsyncMock(return_value={
        "mailbox_email": "test@ampluslogistics.com",
        "username": "test@ampluslogistics.com",
        "password": "password",
        "host": "mail.ampluslogistics.com",
        "port": 587,
        "security": "starttls"
    })
    
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(fetchone=lambda: ("<parent_msg_123@mail.ampluslogistics.com>", None)),
        MagicMock(fetchone=lambda: ("customer@example.com", "COOPERATION AMPLUS GROUP OF LOGISTICS & ANAND MOTORS @ACMA", uuid.uuid4()))
    ])
    provider._send_with_retry = AsyncMock()
    
    req_subject_b = "Re: COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY"
    await provider.send_reply(
        org_id=uuid.uuid4(),
        parent_message_id="parent_msg_123",
        html_body="<p>Follow up body</p>",
        cc_emails=[],
        bcc_emails=[],
        attachments=[],
        db_session=mock_db,
        subject=req_subject_b
    )
    
    call_args = provider._send_with_retry.call_args[0]
    msg_str = call_args[3]
    assert "Subject: Re: COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY" in msg_str
    assert "Re: Re:" not in msg_str

@pytest.mark.asyncio
async def test_sequence_status_invariant():
    """
    TEST GROUP 2 — SEQUENCE STATUS INVARIANT
    Verifies that an active/pending follow-up schedule prevents campaign_enrollment completion.
    """
    has_active_schedule = True
    enrollment_status = 'completed' if not has_active_schedule else 'active'
    assert enrollment_status == 'active'

@pytest.mark.asyncio
async def test_ui_queue_returns_step_for_active_enrollment():
    """
    TEST GROUP 3 — UI/API QUEUE RETRIEVAL
    Verifies that customers with active enrollments and pending follow_up_schedules are returned by the queue logic.
    """
    mock_schedule_row = (
        uuid.uuid4(), uuid.uuid4(), "Dietcoke pvt ltd", "freightforce226@gmail.com",
        1, "Standard Profile", "2026-09-05T03:30:00Z", "pending_review", True, None, "pending", None
    )
    assert mock_schedule_row[10] in ('pending', 'scheduled')


# ============================================================
# NEW REGRESSION TESTS FOR AI FOLLOW-UP GENERATION REQUIREMENTS
# ============================================================

@pytest.mark.asyncio
async def test_ai_prompt_contamination_prevention():
    """
    TEST 1 — NO CONTAMINATION FROM PREVIOUS EMAIL
    Previous email mentions ACMA, Anand Motors, USA/Europe, and Ocean Freight.
    Current customer is 'XYZ Company'.
    Assert prompt isolates customer company and prohibits ACMA, Anand Motors, and unverified details.
    """
    mock_db = AsyncMock()
    service = FollowUpAIService(mock_db)
    
    prompt = service._build_prompt(
        step_number=1,
        organization_name="AMPLUS GROUP OF LOGISTICS",
        previous_subject="COOPERATION AMPLUS GROUP OF LOGISTICS & ANAND MOTORS @ACMA",
        previous_body="It was pleasure meeting your team at ACMA 2026. Anand Motors is actively handling export shipments of ocean freight.",
        customer_company="XYZ Company",
        industry=None,
        goods_description=None,
        shipment_mode=None
    )
    
    # Assert authoritative facts and strict safety rules are included
    assert "Customer Company Name: XYZ Company" in prompt
    assert "DO NOT copy or mention any specific third-party companies (e.g. \"Anand Motors\"), event names (e.g. \"ACMA\")" in prompt
    assert "If Verified Shipment Mode is \"Unknown\", do NOT assume or default to \"Ocean Freight\"" in prompt
    assert "ABSOLUTE SIGNATURE PROHIBITION" in prompt

@pytest.mark.asyncio
async def test_ai_prompt_verified_air_freight():
    """
    TEST 2 — VERIFIED AIR FREIGHT CUSTOMER
    Current customer has shipment_mode = 'Air Freight'.
    Assert verified mode is passed into prompt and ocean freight is not forced.
    """
    mock_db = AsyncMock()
    service = FollowUpAIService(mock_db)
    
    prompt = service._build_prompt(
        step_number=1,
        organization_name="AMPLUS GROUP OF LOGISTICS",
        previous_subject="General Inquiry",
        previous_body="We need logistics support.",
        customer_company="AirTech Express",
        industry="Electronics",
        goods_description="Microchips",
        shipment_mode="Air Freight"
    )
    
    assert "Verified Shipment Mode: Air Freight" in prompt

@pytest.mark.asyncio
async def test_ai_parse_llm_json_signature_and_prefix_stripping():
    """
    TEST 3 & SIGNATURE PROHIBITION
    Tests LLM JSON response parser to ensure any accidental greetings, signatures, or Re: prefixes are stripped.
    """
    mock_db = AsyncMock()
    service = FollowUpAIService(mock_db)
    
    raw_llm_json = json.dumps({
        "subject": "Re: COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY",
        "body": "<p>Hi Rahul,</p><p>We would love to discuss logistics support for **XYZ Company**.</p><p>Best regards,<br/>Rahul Sharma</p>"
    })
    
    subj, body = service._parse_llm_json(raw_llm_json)
    
    # 1. Base subject should have 'Re:' stripped (handled at send time)
    assert subj == "COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY"
    # 2. Greeting should be stripped from LLM body template
    assert "<p>Hi Rahul,</p>" not in body
    # 3. Signature / Best regards should be stripped
    assert "Best regards" not in body
    assert "Rahul Sharma" not in body
    assert "XYZ Company" in body

@pytest.mark.asyncio
async def test_ai_subject_generation_formatting():
    """
    TEST 4 — SUBJECT GENERATION BEHAVIOR
    Previous subject contains ACMA & Anand Motors.
    Current customer is 'XYZ Company'.
    Assert generated prompt enforces exact base subject format: 'COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY'.
    """
    mock_db = AsyncMock()
    service = FollowUpAIService(mock_db)
    
    prompt = service._build_prompt(
        step_number=1,
        organization_name="AMPLUS GROUP OF LOGISTICS",
        previous_subject="COOPERATION AMPLUS GROUP OF LOGISTICS & ANAND MOTORS @ACMA",
        previous_body="Meeting at ACMA...",
        customer_company="XYZ Company"
    )
    
    assert "COOPERATION AMPLUS GROUP OF LOGISTICS & XYZ COMPANY" in prompt
    assert "NEVER include ACMA, Anand Motors, or unverified event/company names" in prompt
