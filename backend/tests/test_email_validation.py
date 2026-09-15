import pytest
from app.core.normalization import normalize_email, validate_email_syntax

def test_validate_email_syntax_valid():
    valid_cases = [
        "info@syro.com",
        "INFO@SYRO.COM",
        "john.doe@company.co.in"
    ]
    for email in valid_cases:
        norm = normalize_email(email)
        is_valid, err = validate_email_syntax(norm)
        assert is_valid is True, f"Failed valid test case: {email}, err: {err}"
        assert err is None

def test_validate_email_syntax_invalid():
    invalid_cases = [
        ("infor@syro", "Invalid email syntax"),
        ("infor@syro.", "Email contains trailing dot"),
        ("infor@syro.con", "suspicious top-level domain (.con)"),
        ("infor@syro.comm", "suspicious top-level domain (.comm)"),
        ("infor@syro.conn", "suspicious top-level domain (.conn)"),
        ("infor@syro..com", "double dots"),
        ("infor @syro.com", "whitespace"),
        ("infor@syro .com", "whitespace"),
        ("@syro.com", "Invalid email syntax"),
        ("infor@@syro.com", "Invalid email syntax")
    ]
    for email, expected_err_part in invalid_cases:
        is_valid, err = validate_email_syntax(email)
        assert is_valid is False, f"Failed invalid test case (should be invalid): {email}"
        assert err is not None
        assert expected_err_part.lower() in err.lower() or "invalid email syntax" in err.lower(), f"Unexpected error msg: {err}"
