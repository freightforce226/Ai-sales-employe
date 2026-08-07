import re
from typing import List
from pydantic import BaseModel

class ClassificationResult(BaseModel):
    is_inquiry: bool
    score: int
    matched_keywords: List[str]
    matched_rules: List[str]

class InquiryClassifier:
    # Target scoring threshold
    THRESHOLD = 3

    # Strong inquiry keywords (+3 score)
    INQUIRY_KEYWORDS = [
        "pricing", "price", "quotation", "quote", "freight", "shipment", "shipping",
        "container", "cargo", "import", "export", "transport", "logistics", "customs",
        "warehouse", "warehousing", "door delivery", "air freight", "ocean freight",
        "sea freight", "booking", "schedule", "pickup", "delivery", "rate", "rfq",
        "insurance", "dangerous goods", "dg cargo", "tracking", "invoice", "payment",
        "documentation", "rail", "ftl", "ltl", "courier"
    ]

    # Negative/Exclusion subject and body overrides (-100 score)
    EXCLUSIONS = [
        "out of office", "automatic reply", "automatic response", "auto reply", "autoresponse",
        "vacation", "read receipt", "delivery status notification", "delivery failure",
        "undelivered mail", "undeliverable", "returned mail", "mail delivery failure", "bounce",
        "spam reports", "spam notification"
    ]

    # Standard email greetings (+1 score)
    GREETINGS = [
        r"\bhi\b", r"\bhello\b", r"\bhey\b", r"\bdir\b", r"\b dear\b"
    ]

    @classmethod
    def classify(cls, subject: str, plain_text_body: str, html_body: str) -> ClassificationResult:
        score = 0
        matched_keywords = []
        matched_rules = []

        # Combine subject and body text for holistic evaluation
        subj_lower = (subject or "").lower()
        body_lower = (plain_text_body or "").lower()
        html_lower = (html_body or "").lower()
        combined_text = f"{subj_lower} {body_lower} {html_lower}"

        # 1. Evaluate Negative Exclusions (-100)
        for exclusion in cls.EXCLUSIONS:
            if exclusion in combined_text:
                score -= 100
                matched_rules.append(f"exclusion_{exclusion.replace(' ', '_')}")

        # 2. Evaluate Inquiry Keywords (+3)
        for kw in cls.INQUIRY_KEYWORDS:
            pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            if pattern.search(combined_text):
                score += 3
                matched_keywords.append(kw)
                matched_rules.append("inquiry_keyword")

        # 3. Question Mark Rule (+1)
        if "?" in combined_text:
            score += 1
            matched_rules.append("question_mark")

        # 4. Greeting Rule (+1)
        for greeting_pattern in cls.GREETINGS:
            if re.search(greeting_pattern, combined_text, re.IGNORECASE):
                score += 1
                matched_rules.append("greeting")
                break

        # Decision threshold evaluation
        is_inquiry = score >= cls.THRESHOLD

        return ClassificationResult(
            is_inquiry=is_inquiry,
            score=score,
            matched_keywords=matched_keywords,
            matched_rules=matched_rules
        )
