"""Pydantic schemas for API request/response bodies."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ScoreBreakdown(BaseModel):
    seniority_points: int
    company_size_points: int
    industry_points: int
    recency_points: int
    email_quality_points: int


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    source: Optional[str] = None
    last_activity_days: Optional[int] = None

    normalized_company: Optional[str] = None
    normalized_job_title: Optional[str] = None
    seniority: Optional[str] = None

    is_duplicate: bool = False
    duplicate_group: Optional[str] = None
    duplicate_reason: Optional[str] = None

    score: Optional[int] = None
    priority: Optional[str] = None
    score_breakdown: Optional[dict] = None
    positive_reasons: Optional[List[str]] = None
    negative_reasons: Optional[List[str]] = None

    created_at: datetime


class UploadSummary(BaseModel):
    total_rows_received: int
    rows_stored: int
    rows_rejected: int
    validation_errors: List[str]
    duplicate_count: int
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int


class DashboardSummary(BaseModel):
    total_leads: int
    duplicate_count: int
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int
    average_score: float
    estimated_time_saved_minutes: int
    estimated_time_saved_note: str


class AIBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lead_id: int
    lead_summary: str
    why_this_lead_matters: str
    suggested_outreach_angle: str
    discovery_questions: List[str]
    disclaimer: str
    is_mock: bool
