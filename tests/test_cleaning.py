"""Tests for backend.cleaning and backend.duplicate_detection."""
import pandas as pd
import pytest

from backend.cleaning import (
    clean_dataframe,
    derive_seniority,
    normalize_company,
    normalize_email,
    normalize_job_title,
    normalize_phone,
)
from backend.duplicate_detection import detect_duplicates


# ---------------------------------------------------------------------------
# Company normalization
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ACME Private Limited", "acme"),
        ("Acme Pvt. Ltd.", "acme"),
        ("Acme Ltd", "acme"),
        ("Acme Limited", "acme"),
        ("Acme LLC", "acme"),
        ("Acme Inc", "acme"),
        ("  Acme   Inc.  ", "acme"),
    ],
)
def test_normalize_company_removes_suffixes(raw, expected):
    assert normalize_company(raw) == expected


def test_normalize_company_handles_missing_value():
    assert normalize_company(None) is None
    assert normalize_company("") is None


# ---------------------------------------------------------------------------
# Email normalization
# ---------------------------------------------------------------------------
def test_normalize_email_lowercases_and_trims():
    assert normalize_email("  John.Doe@Example.COM ") == "john.doe@example.com"


def test_normalize_email_invalid_returns_none():
    assert normalize_email("not-an-email") is None
    assert normalize_email(None) is None
    assert normalize_email("") is None


# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------
def test_normalize_phone_strips_formatting():
    assert normalize_phone("+1 (555) 123-4567") == "5551234567"
    assert normalize_phone("555-123-4567") == "5551234567"
    assert normalize_phone(None) is None
    assert normalize_phone("") is None


# ---------------------------------------------------------------------------
# Job title normalization
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("CTO", "Chief Technology Officer"),
        ("CEO", "Chief Executive Officer"),
        ("VP Engineering", "Vice President of Engineering"),
        ("Mgr", "Manager"),
    ],
)
def test_normalize_job_title_expands_abbreviations(raw, expected):
    assert normalize_job_title(raw) == expected


# ---------------------------------------------------------------------------
# Seniority classification
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "normalized_title, expected_seniority",
    [
        ("Chief Technology Officer", "C-Level"),
        ("Chief Executive Officer", "C-Level"),
        ("Vice President of Engineering", "Vice President"),
        ("Director of Sales", "Director"),
        ("Manager", "Manager"),
        ("Software Engineer", "Individual Contributor"),
        ("Student", "Student or Unknown"),
        (None, "Student or Unknown"),
    ],
)
def test_derive_seniority_categories(normalized_title, expected_seniority):
    assert derive_seniority(normalized_title) == expected_seniority


# ---------------------------------------------------------------------------
# Missing value handling
# ---------------------------------------------------------------------------
def test_clean_dataframe_drops_fully_empty_rows_and_reports_error():
    df = pd.DataFrame(
        [
            {
                "name": "", "email": "", "phone": "", "company": "Acme Inc",
                "job_title": "Engineer", "industry": "SaaS",
                "employee_count": 50, "source": "Website", "last_activity_days": 5,
            },
            {
                "name": "Jane Doe", "email": "jane@acme.com", "phone": "",
                "company": "Acme Inc", "job_title": "CTO", "industry": "SaaS",
                "employee_count": 50, "source": "Website", "last_activity_days": 5,
            },
        ]
    )
    cleaned, errors = clean_dataframe(df)
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["name"] == "Jane Doe"
    assert any("skipped" in e for e in errors)


def test_clean_dataframe_missing_column_reports_error():
    df = pd.DataFrame([{"name": "Jane Doe"}])
    cleaned, errors = clean_dataframe(df)
    assert cleaned.empty
    assert any("Missing required column" in e for e in errors)


def test_clean_dataframe_fills_missing_optional_fields_safely():
    df = pd.DataFrame(
        [
            {
                "name": "Jane Doe", "email": "jane@acme.com", "phone": "555-000-1111",
                "company": "Acme Inc", "job_title": "CTO", "industry": "",
                "employee_count": "", "source": "", "last_activity_days": "",
            }
        ]
    )
    cleaned, errors = clean_dataframe(df)
    assert len(cleaned) == 1
    row = cleaned.iloc[0]
    assert row["industry"] is None
    assert row["employee_count"] is None
    assert row["last_activity_days"] is None


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------
def _cleaned(rows):
    df = pd.DataFrame(rows)
    cleaned, _ = clean_dataframe(df)
    return cleaned


def test_duplicate_email_detection():
    rows = [
        {
            "name": "Sara Kim", "email": "sara.kim@acme.com", "phone": "555-201-3344",
            "company": "Acme Inc", "job_title": "VP Engineering", "industry": "SaaS",
            "employee_count": 500, "source": "LinkedIn", "last_activity_days": 3,
        },
        {
            "name": "sara kim", "email": "Sara.Kim@Acme.com", "phone": "555-999-0000",
            "company": "Acme LLC", "job_title": "VP Product", "industry": "SaaS",
            "employee_count": 500, "source": "Referral", "last_activity_days": 40,
        },
        {
            "name": "Unrelated Person", "email": "someone.else@other.com", "phone": "555-111-2222",
            "company": "Other Co", "job_title": "Manager", "industry": "Retail",
            "employee_count": 40, "source": "Website", "last_activity_days": 10,
        },
    ]
    result = detect_duplicates(_cleaned(rows))
    assert result.loc[0, "is_duplicate"] is True or result.loc[0, "is_duplicate"] == True  # noqa: E712
    assert result.loc[1, "is_duplicate"] == True  # noqa: E712
    assert result.loc[0, "duplicate_group"] == result.loc[1, "duplicate_group"]
    assert "email" in result.loc[0, "duplicate_reason"].lower()
    assert result.loc[2, "is_duplicate"] == False  # noqa: E712


def test_duplicate_phone_detection():
    rows = [
        {
            "name": "Marcus Johnson", "email": "marcus@shopcartly.com", "phone": "+1 (415) 555-0199",
            "company": "ShopCartly Inc", "job_title": "Director", "industry": "E-commerce",
            "employee_count": 300, "source": "Website", "last_activity_days": 5,
        },
        {
            "name": "M. Johnson", "email": "mjohnson@gmail.com", "phone": "415-555-0199",
            "company": "ShopCartly Ltd", "job_title": "Director of Sales", "industry": "E-commerce",
            "employee_count": 300, "source": "Cold Call", "last_activity_days": 65,
        },
    ]
    result = detect_duplicates(_cleaned(rows))
    assert result.loc[0, "is_duplicate"] == True  # noqa: E712
    assert result.loc[1, "is_duplicate"] == True  # noqa: E712
    assert "phone" in result.loc[0, "duplicate_reason"].lower()


def test_no_false_positive_for_distinct_leads():
    rows = [
        {
            "name": "Alice One", "email": "alice@companya.com", "phone": "555-100-2000",
            "company": "Company A", "job_title": "Engineer", "industry": "SaaS",
            "employee_count": 100, "source": "Website", "last_activity_days": 5,
        },
        {
            "name": "Bob Two", "email": "bob@companyb.com", "phone": "555-200-3000",
            "company": "Company B", "job_title": "Analyst", "industry": "Retail",
            "employee_count": 200, "source": "Website", "last_activity_days": 10,
        },
    ]
    result = detect_duplicates(_cleaned(rows))
    assert result["is_duplicate"].sum() == 0
