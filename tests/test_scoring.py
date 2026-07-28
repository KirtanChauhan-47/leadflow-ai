"""Tests for backend.scoring and AI provider error mapping (backend.main)."""
import pytest
from fastapi.testclient import TestClient

from backend import ai_service
from backend.database import Base, engine
from backend.main import app
from backend.scoring import priority_from_score, score_lead

Base.metadata.create_all(bind=engine)
client = TestClient(app)


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------
def test_score_calculation_strong_lead():
    lead = {
        "seniority": "C-Level",
        "employee_count": 5000,
        "industry": "SaaS",
        "last_activity_days": 2,
        "email": "ceo@bigcorp.com",
    }
    result = score_lead(lead)
    assert result["score_breakdown"] == {
        "seniority_points": 30,
        "company_size_points": 25,
        "industry_points": 20,
        "recency_points": 15,
        "email_quality_points": 10,
    }
    assert result["score"] == 100
    assert result["priority"] == "High"
    assert len(result["positive_reasons"]) == 5
    assert result["negative_reasons"] == []


def test_score_calculation_weak_lead():
    lead = {
        "seniority": "Student or Unknown",
        "employee_count": 5,
        "industry": "Manufacturing",
        "last_activity_days": 400,
        "email": None,
    }
    result = score_lead(lead)
    assert result["score_breakdown"] == {
        "seniority_points": 0,
        "company_size_points": 2,
        "industry_points": 5,
        "recency_points": 0,
        "email_quality_points": 0,
    }
    assert result["score"] == 7
    assert result["priority"] == "Low"


def test_score_calculation_public_email_scores_lower_than_corporate():
    base = {
        "seniority": "Manager",
        "employee_count": 150,
        "industry": "FinTech",
        "last_activity_days": 20,
    }
    corporate = score_lead({**base, "email": "person@fintechco.com"})
    public = score_lead({**base, "email": "person@gmail.com"})
    assert corporate["score_breakdown"]["email_quality_points"] == 10
    assert public["score_breakdown"]["email_quality_points"] == 3
    assert corporate["score"] > public["score"]


def test_score_calculation_missing_email_scores_zero():
    lead = {
        "seniority": "Manager", "employee_count": 150,
        "industry": "FinTech", "last_activity_days": 20, "email": None,
    }
    result = score_lead(lead)
    assert result["score_breakdown"]["email_quality_points"] == 0


# ---------------------------------------------------------------------------
# Priority assignment boundaries
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "score, expected_priority",
    [
        (100, "High"),
        (75, "High"),
        (74, "Medium"),
        (45, "Medium"),
        (44, "Low"),
        (0, "Low"),
    ],
)
def test_priority_from_score_boundaries(score, expected_priority):
    assert priority_from_score(score) == expected_priority


# ---------------------------------------------------------------------------
# Provider error mapping (429 / 504 / 503 / 500)
# ---------------------------------------------------------------------------
def _seed_one_lead():
    csv_content = (
        "name,email,phone,company,job_title,industry,employee_count,source,last_activity_days\n"
        "Test Lead,test.lead@acme.com,555-000-1111,Acme Inc,CTO,SaaS,500,Website,3\n"
    )
    files = {"file": ("leads.csv", csv_content, "text/csv")}
    resp = client.post("/upload", files=files)
    assert resp.status_code == 200
    leads = client.get("/leads").json()
    return leads[0]["id"]


def test_ai_summary_maps_rate_limit_to_http_429(monkeypatch):
    lead_id = _seed_one_lead()

    def _raise_rate_limit(lead):
        raise ai_service.AIRateLimitError("Groq API rate limit exceeded")

    monkeypatch.setattr(ai_service, "generate_ai_brief", _raise_rate_limit)
    resp = client.post(f"/leads/{lead_id}/generate-ai-summary")
    assert resp.status_code == 429


def test_ai_summary_maps_timeout_to_http_504(monkeypatch):
    lead_id = _seed_one_lead()

    def _raise_timeout(lead):
        raise ai_service.AITimeoutError("Timed out")

    monkeypatch.setattr(ai_service, "generate_ai_brief", _raise_timeout)
    resp = client.post(f"/leads/{lead_id}/generate-ai-summary")
    assert resp.status_code == 504


def test_ai_summary_maps_provider_unavailable_to_http_503(monkeypatch):
    lead_id = _seed_one_lead()

    def _raise_unavailable(lead):
        raise ai_service.AIProviderUnavailableError("Unavailable")

    monkeypatch.setattr(ai_service, "generate_ai_brief", _raise_unavailable)
    resp = client.post(f"/leads/{lead_id}/generate-ai-summary")
    assert resp.status_code == 503


def test_ai_summary_maps_unexpected_error_to_http_500(monkeypatch):
    lead_id = _seed_one_lead()

    def _raise_unexpected(lead):
        raise ai_service.AIUnexpectedError("Boom")

    monkeypatch.setattr(ai_service, "generate_ai_brief", _raise_unexpected)
    resp = client.post(f"/leads/{lead_id}/generate-ai-summary")
    assert resp.status_code == 500


def test_ai_summary_uses_mock_when_no_api_key_configured():
    lead_id = _seed_one_lead()
    resp = client.post(f"/leads/{lead_id}/generate-ai-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_mock"] is True
    assert "Human review is required" in body["disclaimer"]
    assert len(body["discovery_questions"]) == 3
