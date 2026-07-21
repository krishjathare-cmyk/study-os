import os
from dataclasses import dataclass
from datetime import datetime, time, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


PDF_UPLOAD = "pdf_upload"
AI_MESSAGE = "ai_message"
NOTE_GENERATION = "note_generation"
CONTENT_GENERATION = "content_generation"
PRACTICE_GENERATION = "practice_generation"
TRANSCRIPT_SECOND = "transcript_second"


@dataclass(frozen=True)
class PlanLimits:
    pdfs_total: int
    ai_messages_daily: int
    note_generations_daily: int
    content_generations_daily: int
    practice_generations_daily: int
    transcript_seconds_daily: int


DEFAULT_LIMITS = {
    "free": PlanLimits(
        pdfs_total=3,
        ai_messages_daily=30,
        note_generations_daily=10,
        content_generations_daily=25,
        practice_generations_daily=20,
        transcript_seconds_daily=30 * 60,
    ),
    "student": PlanLimits(
        pdfs_total=3,
        ai_messages_daily=30,
        note_generations_daily=10,
        content_generations_daily=25,
        practice_generations_daily=20,
        transcript_seconds_daily=30 * 60,
    ),
    "student_pro": PlanLimits(
        pdfs_total=50,
        ai_messages_daily=300,
        note_generations_daily=100,
        content_generations_daily=300,
        practice_generations_daily=200,
        transcript_seconds_daily=300 * 60,
    ),
    "professional": PlanLimits(
        pdfs_total=100,
        ai_messages_daily=500,
        note_generations_daily=150,
        content_generations_daily=300,
        practice_generations_daily=0,
        transcript_seconds_daily=300 * 60,
    ),
}


ENV_LIMITS = {
    "pdfs_total": "LIMIT_PDFS_TOTAL",
    "ai_messages_daily": "LIMIT_AI_MESSAGES_DAILY",
    "note_generations_daily": "LIMIT_NOTE_GENERATIONS_DAILY",
    "content_generations_daily": "LIMIT_CONTENT_GENERATIONS_DAILY",
    "practice_generations_daily": "LIMIT_PRACTICE_GENERATIONS_DAILY",
    "transcript_seconds_daily": "LIMIT_TRANSCRIPT_MINUTES_DAILY",
}


def plan_name_for_user(user: models.User) -> str:
    return (user.account_type or "free").strip().lower()


def limits_for_user(user: models.User) -> PlanLimits:
    plan_name = plan_name_for_user(user)
    limits = DEFAULT_LIMITS.get(plan_name, DEFAULT_LIMITS["free"])
    overrides = {}
    for field_name, env_name in ENV_LIMITS.items():
        raw_value = (
            os.getenv(f"{env_name}_{plan_name.upper()}")
            or os.getenv(env_name)
            or ""
        ).strip()
        if not raw_value:
            continue
        try:
            value = int(raw_value)
        except ValueError:
            continue
        if field_name == "transcript_seconds_daily":
            value *= 60
        overrides[field_name] = max(0, value)
    return PlanLimits(**{**limits.__dict__, **overrides})


def daily_window_start() -> datetime:
    return datetime.combine(
        datetime.now(timezone.utc).date(),
        time.min,
        tzinfo=timezone.utc,
    )


def daily_usage(db: Session, user_id: int, event_type: str) -> int:
    used = db.query(func.coalesce(func.sum(models.UsageEvent.amount), 0)).filter(
        models.UsageEvent.user_id == user_id,
        models.UsageEvent.event_type == event_type,
        models.UsageEvent.created_at >= daily_window_start(),
    ).scalar()
    return int(used or 0)


def total_pdf_count(db: Session, user_id: int) -> int:
    document_count = db.query(func.count(models.Document.id)).join(models.Subject).join(
        models.Semester
    ).filter(models.Semester.user_id == user_id).scalar()
    assignment_count = db.query(func.count(models.AssignmentDocument.id)).join(
        models.Subject
    ).join(models.Semester).filter(models.Semester.user_id == user_id).scalar()
    return int(document_count or 0) + int(assignment_count or 0)


def _raise_limit(limit_name: str, limit: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"{limit_name} limit reached for your current plan.",
        headers={"X-Plan-Limit": str(limit)},
    )


def require_pdf_capacity(db: Session, user: models.User, amount: int = 1) -> None:
    limit = limits_for_user(user).pdfs_total
    if limit <= 0 or total_pdf_count(db, user.id) + amount > limit:
        _raise_limit("PDF upload", limit)


def require_daily_capacity(
    db: Session,
    user: models.User,
    event_type: str,
    amount: int = 1,
) -> None:
    limits = limits_for_user(user)
    limit_by_event = {
        AI_MESSAGE: limits.ai_messages_daily,
        NOTE_GENERATION: limits.note_generations_daily,
        CONTENT_GENERATION: limits.content_generations_daily,
        PRACTICE_GENERATION: limits.practice_generations_daily,
        TRANSCRIPT_SECOND: limits.transcript_seconds_daily,
    }
    limit = limit_by_event[event_type]
    if limit <= 0 or daily_usage(db, user.id, event_type) + amount > limit:
        _raise_limit(event_type.replace("_", " ").title(), limit)


def record_usage(
    db: Session,
    user: models.User,
    event_type: str,
    amount: int = 1,
) -> None:
    db.add(
        models.UsageEvent(
            user_id=user.id,
            event_type=event_type,
            amount=max(1, int(amount)),
        )
    )


def usage_summary(db: Session, user: models.User) -> dict:
    limits = limits_for_user(user)
    used = {
        "pdfs_total": total_pdf_count(db, user.id),
        "ai_messages_daily": daily_usage(db, user.id, AI_MESSAGE),
        "note_generations_daily": daily_usage(db, user.id, NOTE_GENERATION),
        "content_generations_daily": daily_usage(db, user.id, CONTENT_GENERATION),
        "practice_generations_daily": daily_usage(db, user.id, PRACTICE_GENERATION),
        "transcript_seconds_daily": daily_usage(db, user.id, TRANSCRIPT_SECOND),
    }
    limit_values = {
        "pdfs_total": limits.pdfs_total,
        "ai_messages_daily": limits.ai_messages_daily,
        "note_generations_daily": limits.note_generations_daily,
        "content_generations_daily": limits.content_generations_daily,
        "practice_generations_daily": limits.practice_generations_daily,
        "transcript_seconds_daily": limits.transcript_seconds_daily,
    }
    remaining = {
        key: max(0, limit_values[key] - used[key])
        for key in limit_values
    }
    return {
        "plan": plan_name_for_user(user),
        "used": used,
        "limits": limit_values,
        "remaining": remaining,
    }
