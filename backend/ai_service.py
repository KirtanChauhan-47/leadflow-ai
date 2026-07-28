"""AI lead-brief generation via the Groq API, with a mock fallback.

Design goals:
  - If GROQ_API_KEY is not set, the whole project still works end to end
    using a deterministic mock response built only from the lead's own data.
  - The AI is instructed to use ONLY the supplied lead fields. It must not
    invent company news, funding, revenue, or tech stack.
  - Provider errors are surfaced with distinct exception types so the API
    layer can map them to the correct HTTP status instead of a blanket 500.
"""
import json
import os
from typing import List, Optional

import requests

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.1-8b-instant"
REQUEST_TIMEOUT_SECONDS = 20

DISCLAIMER = (
    "AI-generated recommendation based only on uploaded lead data. "
    "Human review is required."
)


class AIServiceError(Exception):
    """Base class for AI service errors."""


class AIRateLimitError(AIServiceError):
    """Groq returned HTTP 429 (rate limited)."""


class AITimeoutError(AIServiceError):
    """The request to Groq timed out."""


class AIProviderUnavailableError(AIServiceError):
    """Groq is unreachable or returned a server error (502/503)."""


class AIUnexpectedError(AIServiceError):
    """Any other unexpected failure (bad response shape, unknown status, ...)."""


def _get_api_key() -> Optional[str]:
    key = os.getenv("GROQ_API_KEY", "").strip()
    return key or None


def _build_prompt(lead: dict) -> str:
    fields = {
        "name": lead.get("name") or "Unknown",
        "job_title": lead.get("job_title") or "Unknown",
        "seniority": lead.get("seniority") or "Unknown",
        "company": lead.get("company") or "Unknown",
        "industry": lead.get("industry") or "Unknown",
        "employee_count": lead.get("employee_count"),
        "source": lead.get("source") or "Unknown",
        "last_activity_days": lead.get("last_activity_days"),
        "score": lead.get("score"),
        "priority": lead.get("priority"),
        "positive_reasons": lead.get("positive_reasons") or [],
        "negative_reasons": lead.get("negative_reasons") or [],
    }

    return (
        "You are a sales development assistant. Using ONLY the lead data "
        "below (a JSON object), produce a lead brief. Do not invent facts "
        "that are not present in the data - no company news, no funding "
        "rounds, no revenue figures, no technology stack guesses, and no "
        "real-world facts about the company beyond what is given.\n\n"
        f"LEAD DATA:\n{json.dumps(fields, indent=2)}\n\n"
        "Respond with ONLY a JSON object with exactly these keys:\n"
        '  "lead_summary": a 2-3 sentence factual summary of who this lead is,\n'
        '  "why_this_lead_matters": 1-2 sentences grounded in the score '
        "reasons and role/industry provided,\n"
        '  "suggested_outreach_angle": one practical outreach angle based on '
        "the role and industry given,\n"
        '  "discovery_questions": a list of exactly 3 short discovery '
        "questions a rep could ask this lead.\n"
        "Return raw JSON only, no markdown fences, no extra commentary."
    )


def _call_groq(prompt: str, api_key: str, model: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            GROQ_CHAT_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout as exc:
        raise AITimeoutError("Timed out waiting for Groq API") from exc
    except requests.exceptions.ConnectionError as exc:
        raise AIProviderUnavailableError("Could not reach Groq API") from exc
    except requests.exceptions.RequestException as exc:
        raise AIUnexpectedError(f"Unexpected request failure: {exc}") from exc

    if response.status_code == 429:
        raise AIRateLimitError("Groq API rate limit exceeded")
    if response.status_code in (502, 503):
        raise AIProviderUnavailableError(
            f"Groq API unavailable (status {response.status_code})"
        )
    if response.status_code != 200:
        raise AIUnexpectedError(
            f"Groq API returned unexpected status {response.status_code}: "
            f"{response.text[:300]}"
        )

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, ValueError) as exc:
        raise AIUnexpectedError(f"Could not parse Groq response: {exc}") from exc

    return parsed


def _mock_brief(lead: dict) -> dict:
    """Deterministic offline stand-in, built only from the lead's own data."""
    name = lead.get("name") or "This contact"
    job_title = lead.get("job_title") or "an unspecified role"
    company = lead.get("company") or "their company"
    industry = lead.get("industry") or "an unspecified industry"
    employee_count = lead.get("employee_count")
    last_activity_days = lead.get("last_activity_days")
    priority = lead.get("priority") or "Unscored"

    size_phrase = (
        f"~{employee_count} employees" if employee_count is not None else "an unknown company size"
    )
    activity_phrase = (
        f"last activity was {last_activity_days} day(s) ago"
        if last_activity_days is not None
        else "no recorded recent activity"
    )

    lead_summary = (
        f"{name} works as {job_title} at {company}, a company in the "
        f"{industry} space with {size_phrase}. Based on uploaded data, "
        f"{activity_phrase}."
    )

    reasons = lead.get("positive_reasons") or []
    if reasons:
        why_matters = (
            f"This lead is rated {priority} priority because: "
            + "; ".join(reasons) + "."
        )
    else:
        why_matters = (
            f"This lead is rated {priority} priority based on the uploaded "
            f"role, company size, industry, and activity data."
        )

    outreach_angle = (
        f"Reach out to {name} with a message tailored to the priorities of "
        f"a {job_title} in {industry}, referencing their role at {company}."
    )

    discovery_questions = [
        f"What are the top priorities for your team at {company} this quarter?",
        f"How is your team at {company} currently handling this problem area today?",
        "What would need to be true for this to become a priority in the next 90 days?",
    ]

    return {
        "lead_summary": lead_summary,
        "why_this_lead_matters": why_matters,
        "suggested_outreach_angle": outreach_angle,
        "discovery_questions": discovery_questions,
    }


def generate_ai_brief(lead: dict) -> dict:
    """Generate a structured AI lead brief.

    Returns a dict with lead_summary, why_this_lead_matters,
    suggested_outreach_angle, discovery_questions (list[str]), disclaimer,
    and is_mock. Raises AIRateLimitError / AITimeoutError /
    AIProviderUnavailableError / AIUnexpectedError on provider failures.
    """
    api_key = _get_api_key()

    if not api_key:
        result = _mock_brief(lead)
        is_mock = True
    else:
        model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
        prompt = _build_prompt(lead)
        result = _call_groq(prompt, api_key, model)
        is_mock = False

    questions = result.get("discovery_questions") or []
    if not isinstance(questions, list):
        questions = [str(questions)]
    questions = [str(q) for q in questions][:3]
    while len(questions) < 3:
        questions.append("What else should we know to prioritize this lead?")

    return {
        "lead_summary": str(result.get("lead_summary", "")),
        "why_this_lead_matters": str(result.get("why_this_lead_matters", "")),
        "suggested_outreach_angle": str(result.get("suggested_outreach_angle", "")),
        "discovery_questions": questions,
        "disclaimer": DISCLAIMER,
        "is_mock": is_mock,
    }
