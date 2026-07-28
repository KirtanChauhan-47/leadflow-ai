"""LeadFlow AI - FastAPI backend.

Endpoints:
    GET  /health
    POST /upload
    GET  /leads
    GET  /leads/{lead_id}
    POST /leads/{lead_id}/generate-ai-summary
    GET  /dashboard
"""
import io
import json
from contextlib import asynccontextmanager
from typing import Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import ai_service
from backend.cleaning import clean_dataframe
from backend.database import get_db, init_db
from backend.duplicate_detection import detect_duplicates
from backend.models import AIResult, Lead
from backend.schemas import AIBriefOut, DashboardSummary, LeadOut, UploadSummary
from backend.scoring import score_lead

MANUAL_RESEARCH_MINUTES_PER_LEAD = 5
AI_SUMMARY_MINUTES_SAVED_PER_HIGH_PRIORITY_LEAD = 3


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LeadFlow AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _lead_to_out(lead: Lead) -> LeadOut:
    return LeadOut(
        id=lead.id,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        company=lead.company,
        job_title=lead.job_title,
        industry=lead.industry,
        employee_count=lead.employee_count,
        source=lead.source,
        last_activity_days=lead.last_activity_days,
        normalized_company=lead.normalized_company,
        normalized_job_title=lead.normalized_job_title,
        seniority=lead.seniority,
        is_duplicate=bool(lead.is_duplicate),
        duplicate_group=lead.duplicate_group,
        duplicate_reason=lead.duplicate_reason,
        score=lead.score,
        priority=lead.priority,
        score_breakdown=json.loads(lead.score_breakdown) if lead.score_breakdown else None,
        positive_reasons=json.loads(lead.positive_reasons) if lead.positive_reasons else None,
        negative_reasons=json.loads(lead.negative_reasons) if lead.negative_reasons else None,
        created_at=lead.created_at,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadSummary)
async def upload_leads(file: UploadFile, db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    raw_bytes = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

    total_rows_received = len(df)

    cleaned_df, validation_errors = clean_dataframe(df)
    if cleaned_df.empty and any("Missing required column" in e for e in validation_errors):
        raise HTTPException(status_code=400, detail="; ".join(validation_errors))

    cleaned_df = detect_duplicates(cleaned_df)

    # Each upload replaces the previous dataset to keep the demo simple and
    # avoid cross-upload duplicate/score confusion.
    db.query(AIResult).delete()
    db.query(Lead).delete()
    db.commit()

    high = medium = low = 0
    for _, row in cleaned_df.iterrows():
        row_dict = row.to_dict()
        score_result = score_lead(row_dict)

        if score_result["priority"] == "High":
            high += 1
        elif score_result["priority"] == "Medium":
            medium += 1
        else:
            low += 1

        lead = Lead(
            name=row_dict.get("name"),
            email=row_dict.get("email"),
            phone=row_dict.get("phone"),
            company=row_dict.get("company"),
            job_title=row_dict.get("job_title"),
            industry=row_dict.get("industry"),
            employee_count=row_dict.get("employee_count"),
            source=row_dict.get("source"),
            last_activity_days=row_dict.get("last_activity_days"),
            normalized_company=row_dict.get("normalized_company"),
            normalized_job_title=row_dict.get("normalized_job_title"),
            seniority=row_dict.get("seniority"),
            is_duplicate=bool(row_dict.get("is_duplicate")),
            duplicate_group=row_dict.get("duplicate_group"),
            duplicate_reason=row_dict.get("duplicate_reason"),
            score=score_result["score"],
            priority=score_result["priority"],
            score_breakdown=json.dumps(score_result["score_breakdown"]),
            positive_reasons=json.dumps(score_result["positive_reasons"]),
            negative_reasons=json.dumps(score_result["negative_reasons"]),
        )
        db.add(lead)

    db.commit()

    duplicate_count = int(cleaned_df["is_duplicate"].sum()) if not cleaned_df.empty else 0

    return UploadSummary(
        total_rows_received=total_rows_received,
        rows_stored=len(cleaned_df),
        rows_rejected=total_rows_received - len(cleaned_df),
        validation_errors=validation_errors,
        duplicate_count=duplicate_count,
        high_priority_count=high,
        medium_priority_count=medium,
        low_priority_count=low,
    )


@app.get("/leads", response_model=list[LeadOut])
def list_leads(
    priority: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Lead)
    if priority:
        query = query.filter(Lead.priority == priority)
    if source:
        query = query.filter(Lead.source == source)
    leads = query.order_by(Lead.score.desc()).all()
    return [_lead_to_out(lead) for lead in leads]


@app.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _lead_to_out(lead)


@app.post("/leads/{lead_id}/generate-ai-summary", response_model=AIBriefOut)
def generate_ai_summary(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead_dict = {
        "name": lead.name,
        "job_title": lead.job_title,
        "seniority": lead.seniority,
        "company": lead.company,
        "industry": lead.industry,
        "employee_count": lead.employee_count,
        "source": lead.source,
        "last_activity_days": lead.last_activity_days,
        "email": lead.email,
        "score": lead.score,
        "priority": lead.priority,
        "positive_reasons": json.loads(lead.positive_reasons) if lead.positive_reasons else [],
        "negative_reasons": json.loads(lead.negative_reasons) if lead.negative_reasons else [],
    }

    try:
        brief = ai_service.generate_ai_brief(lead_dict)
    except ai_service.AIRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except ai_service.AITimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except ai_service.AIProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ai_service.AIUnexpectedError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    ai_result = AIResult(
        lead_id=lead.id,
        lead_summary=brief["lead_summary"],
        why_this_lead_matters=brief["why_this_lead_matters"],
        suggested_outreach_angle=brief["suggested_outreach_angle"],
        discovery_questions=json.dumps(brief["discovery_questions"]),
    )
    db.add(ai_result)
    db.commit()

    return AIBriefOut(
        lead_id=lead.id,
        lead_summary=brief["lead_summary"],
        why_this_lead_matters=brief["why_this_lead_matters"],
        suggested_outreach_angle=brief["suggested_outreach_angle"],
        discovery_questions=brief["discovery_questions"],
        disclaimer=brief["disclaimer"],
        is_mock=brief["is_mock"],
    )


@app.get("/dashboard", response_model=DashboardSummary)
def dashboard(db: Session = Depends(get_db)):
    total_leads = db.query(func.count(Lead.id)).scalar() or 0
    duplicate_count = db.query(func.count(Lead.id)).filter(Lead.is_duplicate.is_(True)).scalar() or 0
    high_priority_count = db.query(func.count(Lead.id)).filter(Lead.priority == "High").scalar() or 0
    medium_priority_count = db.query(func.count(Lead.id)).filter(Lead.priority == "Medium").scalar() or 0
    low_priority_count = db.query(func.count(Lead.id)).filter(Lead.priority == "Low").scalar() or 0
    average_score = db.query(func.avg(Lead.score)).scalar() or 0.0

    estimated_time_saved_minutes = (
        high_priority_count * AI_SUMMARY_MINUTES_SAVED_PER_HIGH_PRIORITY_LEAD
    )

    return DashboardSummary(
        total_leads=total_leads,
        duplicate_count=duplicate_count,
        high_priority_count=high_priority_count,
        medium_priority_count=medium_priority_count,
        low_priority_count=low_priority_count,
        average_score=round(float(average_score), 1),
        estimated_time_saved_minutes=estimated_time_saved_minutes,
        estimated_time_saved_note=(
            f"Estimate assumes manual research takes "
            f"{MANUAL_RESEARCH_MINUTES_PER_LEAD} minutes per lead and an AI "
            f"summary saves {AI_SUMMARY_MINUTES_SAVED_PER_HIGH_PRIORITY_LEAD} "
            f"minutes for each high-priority lead "
            f"({high_priority_count} high-priority leads currently)."
        ),
    )
