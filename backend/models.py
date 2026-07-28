"""SQLAlchemy ORM models: Lead and AIResult."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)

    # Raw / lightly-cleaned input fields
    name = Column(String, nullable=True)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    company = Column(String, nullable=True)
    job_title = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    employee_count = Column(Integer, nullable=True)
    source = Column(String, nullable=True, index=True)
    last_activity_days = Column(Integer, nullable=True)

    # Derived / normalized fields
    normalized_company = Column(String, nullable=True)
    normalized_job_title = Column(String, nullable=True)
    seniority = Column(String, nullable=True)

    # Duplicate detection
    is_duplicate = Column(Boolean, default=False)
    duplicate_group = Column(String, nullable=True, index=True)
    duplicate_reason = Column(String, nullable=True)

    # Scoring
    score = Column(Integer, nullable=True)
    priority = Column(String, nullable=True, index=True)
    score_breakdown = Column(Text, nullable=True)  # JSON string
    positive_reasons = Column(Text, nullable=True)  # JSON string
    negative_reasons = Column(Text, nullable=True)  # JSON string

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ai_results = relationship(
        "AIResult", back_populates="lead", cascade="all, delete-orphan"
    )


class AIResult(Base):
    __tablename__ = "ai_results"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)

    lead_summary = Column(Text, nullable=True)
    why_this_lead_matters = Column(Text, nullable=True)
    suggested_outreach_angle = Column(Text, nullable=True)
    discovery_questions = Column(Text, nullable=True)  # JSON string (list)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    lead = relationship("Lead", back_populates="ai_results")
