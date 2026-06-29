"""Schedule router — view, create, and cancel scheduled follow-ups."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db
from models import FollowUp, Lead
from core.auth import get_active_user

router = APIRouter(prefix="/schedule", tags=["schedule"])


class ManualScheduleRequest(BaseModel):
    lead_id: int
    type: str          # "call" | "sms" | "email"
    scheduled_at: str  # ISO datetime string e.g. "2026-06-30T10:00"
    message: Optional[str] = None


@router.get("/upcoming")
def upcoming(
    days: int = 14,
    current_user=Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """All pending follow-ups for this user in the next N days, newest first."""
    cutoff = datetime.now() + timedelta(days=days)
    rows = (
        db.query(FollowUp, Lead)
        .join(Lead, Lead.id == FollowUp.lead_id)
        .filter(
            Lead.user_id == current_user.id,
            FollowUp.status == "pending",
            FollowUp.scheduled_at <= cutoff,
        )
        .order_by(FollowUp.scheduled_at.asc())
        .all()
    )
    return [
        {
            "id": fu.id,
            "lead_id": lead.id,
            "lead_name": lead.name,
            "lead_phone": lead.phone,
            "lead_email": lead.email,
            "type": fu.type,
            "scheduled_at": fu.scheduled_at.isoformat() if fu.scheduled_at else None,
            "message": fu.message,
            "status": fu.status,
        }
        for fu, lead in rows
    ]


@router.get("/history")
def history(
    limit: int = 50,
    current_user=Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """Recently executed or failed follow-ups."""
    rows = (
        db.query(FollowUp, Lead)
        .join(Lead, Lead.id == FollowUp.lead_id)
        .filter(
            Lead.user_id == current_user.id,
            FollowUp.status.in_(["sent", "failed", "cancelled"]),
        )
        .order_by(FollowUp.executed_at.desc().nullslast(), FollowUp.scheduled_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": fu.id,
            "lead_id": lead.id,
            "lead_name": lead.name,
            "type": fu.type,
            "scheduled_at": fu.scheduled_at.isoformat() if fu.scheduled_at else None,
            "executed_at": fu.executed_at.isoformat() if fu.executed_at else None,
            "status": fu.status,
            "error_message": fu.error_message,
        }
        for fu, lead in rows
    ]


@router.post("/manual", status_code=201)
def schedule_manual(
    data: ManualScheduleRequest,
    current_user=Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """Manually schedule a call, SMS, or email for a specific lead."""
    if data.type not in ("call", "sms", "email"):
        raise HTTPException(400, "type must be call, sms, or email")

    lead = db.query(Lead).filter(Lead.id == data.lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")

    try:
        scheduled_dt = datetime.fromisoformat(data.scheduled_at)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use ISO format e.g. 2026-06-30T10:00")

    if scheduled_dt < datetime.now():
        raise HTTPException(400, "Scheduled time must be in the future")

    fu = FollowUp(
        lead_id=lead.id,
        type=data.type,
        scheduled_at=scheduled_dt,
        status="pending",
        message=data.message or f"Manually scheduled {data.type}",
    )
    db.add(fu)
    db.commit()
    db.refresh(fu)

    return {
        "id": fu.id,
        "lead_id": lead.id,
        "lead_name": lead.name,
        "type": fu.type,
        "scheduled_at": fu.scheduled_at.isoformat(),
        "status": fu.status,
    }


@router.delete("/{followup_id}", status_code=200)
def cancel_followup(
    followup_id: int,
    current_user=Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """Cancel a pending scheduled follow-up."""
    fu = (
        db.query(FollowUp)
        .join(Lead, Lead.id == FollowUp.lead_id)
        .filter(FollowUp.id == followup_id, Lead.user_id == current_user.id)
        .first()
    )
    if not fu:
        raise HTTPException(404, "Scheduled item not found")
    if fu.status != "pending":
        raise HTTPException(400, f"Cannot cancel a {fu.status} item")
    fu.status = "cancelled"
    fu.executed_at = datetime.now()
    db.commit()
    return {"cancelled": followup_id}
