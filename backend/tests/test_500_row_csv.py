import pytest
import io
import csv
from app.core.normalization import validate_email_syntax

def test_mixed_500_rows_filtering():
    # Construct 500 rows CSV content in-memory
    # 450 valid, 50 invalid
    rows = [["company_name", "contact_name", "contact_email", "industry"]]
    
    for i in range(1, 451):
        rows.append([f"Company {i}", f"Contact {i}", f"user{i}@syro.com", "Logistics"])
        
    invalid_examples = [
        "infor@syro.con",
        "infor@syro.comm",
        "infor@syro.conn",
        "infor@syro..com",
        "infor@syro",
        "infor@syro.",
        "infor @syro.com",
        "infor@syro .com",
        "@syro.com",
        "infor@@syro.com"
    ]
    
    for i in range(451, 501):
        bad_email = invalid_examples[(i - 451) % len(invalid_examples)]
        rows.append([f"Bad Company {i}", f"Bad Contact {i}", bad_email, "Logistics"])

    assert len(rows) == 501 # Header + 500 data rows

    # Simulate backend start_import validation filtering
    valid_normalized_data = []
    rejected_error_log = []
    
    valid_count = 0
    invalid_count = 0
    for idx, row in enumerate(rows[1:], start=1):
        company, contact, email, industry = row
        is_valid, err = validate_email_syntax(email)
        if is_valid:
            valid_count += 1
            valid_normalized_data.append(row)
        else:
            invalid_count += 1
            row_num = valid_count + invalid_count + 1
            rejected_error_log.append({
                "row_number": row_num,
                "original_email": email,
                "error_type": "invalid_email_syntax",
                "error_message": err or "Invalid email syntax",
                "errors": [{"field": "contact_email", "reason": err or "Invalid email syntax"}]
            })

    assert len(valid_normalized_data) == 450
    assert len(rejected_error_log) == 50
    # First invalid row was index 451 in rows (450 valid + 1), so row_number should be 452 (since header is row 1)
    assert rejected_error_log[0]["row_number"] == 452

    
    # Verify no invalid emails present in normalized data
    for row in valid_normalized_data:
        assert not row[2].endswith(".con")
        assert not row[2].endswith(".comm")
        assert not row[2].endswith(".conn")
        assert ".." not in row[2]
        assert " " not in row[2]
