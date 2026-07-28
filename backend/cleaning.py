"""Data validation + cleaning: whitespace, email, phone, company, job title,
seniority classification, and safe handling of missing values.

Every normalize_* function is intentionally small and pure so it can be
unit tested in isolation (see tests/test_cleaning.py).
"""
import re
from typing import List, Optional, Tuple

import pandas as pd

REQUIRED_COLUMNS = [
    "name",
    "email",
    "phone",
    "company",
    "job_title",
    "industry",
    "employee_count",
    "source",
    "last_activity_days",
]

# Public / free email domains used for email-quality scoring later.
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Longest-suffix-first so "private limited" matches before "limited".
_COMPANY_SUFFIXES = [
    "private limited",
    "pvt ltd",
    "pvt. ltd.",
    "limited",
    "ltd",
    "llc",
    "inc",
]

_JOB_TITLE_MAP = {
    "cto": "Chief Technology Officer",
    "ceo": "Chief Executive Officer",
    "cfo": "Chief Financial Officer",
    "coo": "Chief Operating Officer",
    "cmo": "Chief Marketing Officer",
    "cio": "Chief Information Officer",
    "vp engineering": "Vice President of Engineering",
    "vp sales": "Vice President of Sales",
    "vp marketing": "Vice President of Marketing",
    "vp product": "Vice President of Product",
    "mgr": "Manager",
    "sr mgr": "Senior Manager",
    "dir": "Director",
}

_WORD_REPLACEMENTS = {
    "vp": "Vice President of",
    "svp": "Senior Vice President of",
    "mgr": "Manager",
    "sr": "Senior",
    "dir": "Director",
}


def clean_text(value) -> Optional[str]:
    """Trim whitespace and collapse internal double-spaces. None/NaN safe."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def safe_int(value) -> Optional[int]:
    """Convert to int if possible, otherwise None (never raises)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def normalize_email(email) -> Optional[str]:
    """Lowercase + trim. Returns None if missing or not a valid email shape."""
    text = clean_text(email)
    if not text:
        return None
    text = text.lower()
    if not _EMAIL_RE.match(text):
        return None
    return text


def is_corporate_email(email: Optional[str]) -> bool:
    """True if the email domain is not a well-known public/free provider."""
    if not email or "@" not in email:
        return False
    domain = email.split("@", 1)[1]
    return domain not in PUBLIC_EMAIL_DOMAINS


def normalize_phone(phone) -> Optional[str]:
    """Strip everything but digits, dropping a leading country-code '1' so
    that '+1 (555) 123-4567' and '555-123-4567' normalize the same way."""
    text = clean_text(phone)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_company(company) -> Optional[str]:
    """Lowercase, strip punctuation, and remove common legal suffixes.

    Examples:
        "ACME Private Limited" -> "acme"
        "Acme Pvt. Ltd."       -> "acme"
    """
    text = clean_text(company)
    if not text:
        return None
    text = text.lower()
    text = text.replace(".", "").replace(",", "")
    text = re.sub(r"\s+", " ", text).strip()

    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            pattern = r"\s*\b" + re.escape(suffix) + r"\b\.?\s*$"
            new_text = re.sub(pattern, "", text).strip()
            if new_text != text:
                text = new_text
                changed = True

    return text or None


def normalize_job_title(job_title) -> Optional[str]:
    """Expand common abbreviations into full job titles."""
    text = clean_text(job_title)
    if not text:
        return None

    lower = text.lower().replace(".", "").strip()
    lower = re.sub(r"\s+", " ", lower)

    if lower in _JOB_TITLE_MAP:
        return _JOB_TITLE_MAP[lower]

    tokens = lower.split(" ")
    replaced_tokens = []
    any_replacement = False
    for token in tokens:
        stripped = token.strip(",")
        if stripped in _WORD_REPLACEMENTS:
            replaced_tokens.append(_WORD_REPLACEMENTS[stripped])
            any_replacement = True
        else:
            replaced_tokens.append(stripped.capitalize())

    if any_replacement:
        rebuilt = " ".join(replaced_tokens)
        return re.sub(r"\s+", " ", rebuilt).strip()

    return text.title()


def derive_seniority(normalized_job_title: Optional[str]) -> str:
    """Classify a normalized job title into a seniority bucket."""
    if not normalized_job_title:
        return "Student or Unknown"

    title = normalized_job_title.lower()

    if "student" in title or "intern" in title or "unknown" in title:
        return "Student or Unknown"
    if "chief" in title or "founder" in title or "owner" in title:
        return "C-Level"
    if "vice president" in title:
        return "Vice President"
    if "director" in title or "head of" in title:
        return "Director"
    if "manager" in title or "lead" in title:
        return "Manager"

    individual_contributor_keywords = [
        "engineer",
        "developer",
        "analyst",
        "specialist",
        "representative",
        "associate",
        "consultant",
        "designer",
        "executive",
        "accountant",
        "coordinator",
        "administrator",
        "scientist",
    ]
    if any(keyword in title for keyword in individual_contributor_keywords):
        return "Individual Contributor"

    return "Student or Unknown"


def validate_columns(df: pd.DataFrame) -> List[str]:
    """Return a list of human-readable errors for missing required columns."""
    errors = []
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        errors.append(f"Missing required column(s): {', '.join(missing)}")
    return errors


def clean_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Validate + clean an uploaded leads DataFrame.

    Returns (cleaned_df, validation_errors). Rows with no name, email, or
    phone at all are dropped (nothing to identify the lead by) and recorded
    as a validation error; every other missing field is simply set to None
    and scored/weighted accordingly downstream.
    """
    errors = validate_columns(df)
    if errors:
        return pd.DataFrame(), errors

    cleaned_rows = []
    for idx, row in df.iterrows():
        name = clean_text(row.get("name"))
        email = normalize_email(row.get("email"))
        phone = normalize_phone(row.get("phone"))

        if not name and not email and not phone:
            errors.append(
                f"Row {idx + 2}: missing name, email, and phone - skipped"
            )
            continue

        company = clean_text(row.get("company"))
        job_title = clean_text(row.get("job_title"))
        normalized_company = normalize_company(company)
        normalized_job_title = normalize_job_title(job_title)

        cleaned_rows.append(
            {
                "name": name,
                "email": email,
                "phone": phone,
                "company": company,
                "job_title": job_title,
                "industry": clean_text(row.get("industry")),
                "employee_count": safe_int(row.get("employee_count")),
                "source": clean_text(row.get("source")),
                "last_activity_days": safe_int(row.get("last_activity_days")),
                "normalized_company": normalized_company,
                "normalized_job_title": normalized_job_title,
                "seniority": derive_seniority(normalized_job_title),
            }
        )

    cleaned_df = pd.DataFrame(cleaned_rows)

    # pandas silently upcasts an int column containing any None to float64
    # (e.g. 1450 -> 1450.0), and re-infers that same float64 dtype even on
    # plain-list/apply reassignment. An explicit object-dtype Series is the
    # only way to keep these as real Python int/None so downstream score
    # reasons and JSON output stay clean.
    if not cleaned_df.empty:
        for col in ("employee_count", "last_activity_days"):
            cleaned_df[col] = pd.Series(
                [int(v) if pd.notna(v) else None for v in cleaned_df[col]],
                index=cleaned_df.index,
                dtype=object,
            )

    return cleaned_df, errors
