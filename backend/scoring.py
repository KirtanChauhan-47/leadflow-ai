"""Deterministic, explainable 0-100 lead scoring.

Every point awarded (or withheld) is traceable to one plain-English reason,
so the score never needs a black box to justify itself.
"""
from typing import Optional

from backend.cleaning import is_corporate_email

TARGET_INDUSTRIES = {
    "saas",
    "cloud",
    "fintech",
    "healthcare technology",
    "e-commerce",
    "artificial intelligence",
}

SENIORITY_POINTS = {
    "C-Level": 30,
    "Vice President": 25,
    "Director": 20,
    "Manager": 12,
    "Individual Contributor": 6,
    "Student or Unknown": 0,
}

HIGH_THRESHOLD = 75
MEDIUM_THRESHOLD = 45


def _score_seniority(seniority: Optional[str]) -> tuple:
    seniority = seniority or "Student or Unknown"
    points = SENIORITY_POINTS.get(seniority, 0)
    if points >= 20:
        return points, f"Senior job title ({seniority}, +{points})", None
    if points > 0:
        return points, None, f"Limited seniority ({seniority}, +{points})"
    return points, None, f"No confirmed seniority ({seniority}, +0)"


def _score_company_size(employee_count: Optional[int]) -> tuple:
    if employee_count is None:
        return 2, None, "Company size unknown (+2)"
    if employee_count >= 1000:
        return 25, f"Large company ({employee_count} employees, +25)", None
    if employee_count >= 500:
        return 20, f"Large-mid company ({employee_count} employees, +20)", None
    if employee_count >= 100:
        return 15, f"Mid-size company ({employee_count} employees, +15)", None
    if employee_count >= 20:
        return 8, None, f"Small company ({employee_count} employees, +8)"
    return 2, None, f"Very small company ({employee_count} employees, +2)"


def _score_industry(industry: Optional[str]) -> tuple:
    normalized = (industry or "").strip().lower()
    if normalized in TARGET_INDUSTRIES:
        return 20, f"Target industry ({industry}, +20)", None
    label = industry or "unknown"
    return 5, None, f"Non-target industry ({label}, +5)"


def _score_recency(last_activity_days: Optional[int]) -> tuple:
    if last_activity_days is None:
        return 0, None, "No recorded activity (+0)"
    if last_activity_days <= 7:
        return 15, f"Active in last 7 days ({last_activity_days}d, +15)", None
    if last_activity_days <= 30:
        return 10, f"Active in last 30 days ({last_activity_days}d, +10)", None
    if last_activity_days <= 90:
        return 5, None, f"Active in last 90 days ({last_activity_days}d, +5)"
    return 0, None, f"Stale activity ({last_activity_days}d ago, +0)"


def _score_email(email: Optional[str]) -> tuple:
    if not email:
        return 0, None, "No valid email on file (+0)"
    if is_corporate_email(email):
        return 10, "Corporate email address (+10)", None
    return 3, None, "Public/free email address (+3)"


def priority_from_score(score: int) -> str:
    if score >= HIGH_THRESHOLD:
        return "High"
    if score >= MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"


def score_lead(lead: dict) -> dict:
    """Score a single cleaned lead dict.

    Expects keys: seniority, employee_count, industry, last_activity_days,
    email. Returns score, priority, score_breakdown, positive_reasons,
    negative_reasons.
    """
    seniority_points, sp_pos, sp_neg = _score_seniority(lead.get("seniority"))
    size_points, sz_pos, sz_neg = _score_company_size(lead.get("employee_count"))
    industry_points, ind_pos, ind_neg = _score_industry(lead.get("industry"))
    recency_points, rec_pos, rec_neg = _score_recency(lead.get("last_activity_days"))
    email_points, em_pos, em_neg = _score_email(lead.get("email"))

    total = seniority_points + size_points + industry_points + recency_points + email_points

    positive_reasons = [r for r in [sp_pos, sz_pos, ind_pos, rec_pos, em_pos] if r]
    negative_reasons = [r for r in [sp_neg, sz_neg, ind_neg, rec_neg, em_neg] if r]

    return {
        "score": total,
        "priority": priority_from_score(total),
        "score_breakdown": {
            "seniority_points": seniority_points,
            "company_size_points": size_points,
            "industry_points": industry_points,
            "recency_points": recency_points,
            "email_quality_points": email_points,
        },
        "positive_reasons": positive_reasons,
        "negative_reasons": negative_reasons,
    }
