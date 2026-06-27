"""Lead management — CRUD, CSV import, scoring. All scoped to current user."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Lead, Interaction, FollowUp
from schemas import LeadCreate, LeadUpdate, LeadOut, InteractionOut, FollowUpOut
from core.auth import get_active_user, check_lead_limit
from core.ai_engine import score_lead, generate_cold_call_script
from core.scheduler import schedule_followup_sequence
from scraper.csv_importer import import_csv

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=List[LeadOut])
def list_leads(
    status: Optional[str] = None,
    campaign_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(get_active_user),
    db: Session = Depends(get_db),
):
    q = db.query(Lead).filter(Lead.user_id == current_user.id)
    if status:
        q = q.filter(Lead.status == status)
    if campaign_id:
        q = q.filter(Lead.campaign_id == campaign_id)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (Lead.name.ilike(like)) | (Lead.company.ilike(like)) |
            (Lead.phone.ilike(like)) | (Lead.email.ilike(like))
        )
    return q.order_by(Lead.score.desc(), Lead.created_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=LeadOut, status_code=201)
def create_lead(
    data: LeadCreate,
    auto_schedule: bool = True,
    current_user=Depends(check_lead_limit),
    db: Session = Depends(get_db),
):
    lead = Lead(**data.model_dump(), user_id=current_user.id)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    if auto_schedule:
        schedule_followup_sequence(lead.id)
    return lead


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int, data: LeadUpdate,
    current_user=Depends(get_active_user), db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(lead, field, value)
    lead.updated_at = datetime.now()
    db.commit()
    db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=204)
def delete_lead(lead_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    db.delete(lead)
    db.commit()


@router.delete("", status_code=200)
def delete_all_leads(current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    """Delete every lead belonging to the current user."""
    deleted = db.query(Lead).filter(Lead.user_id == current_user.id).delete()
    db.commit()
    return {"deleted": deleted}


@router.get("/{lead_id}/interactions", response_model=List[InteractionOut])
def get_interactions(lead_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return db.query(Interaction).filter(Interaction.lead_id == lead_id).order_by(Interaction.created_at.desc()).all()


@router.get("/{lead_id}/followups", response_model=List[FollowUpOut])
def get_followups(lead_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return db.query(FollowUp).filter(FollowUp.lead_id == lead_id).order_by(FollowUp.scheduled_at.asc()).all()


@router.post("/{lead_id}/score")
def rescore_lead(lead_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    interactions = [{"type": i.type, "created_at": str(i.created_at), "outcome": i.outcome, "ai_analysis": i.ai_analysis} for i in lead.interactions]
    result = score_lead({"name": lead.name, "health_interest": lead.health_interest, "pain_points": lead.pain_points, "status": lead.status}, interactions, user=current_user)
    lead.score = result.get("score", lead.score)
    lead.updated_at = datetime.now()
    db.commit()
    return result


@router.post("/{lead_id}/generate-script")
def generate_script(lead_id: int, product_focus: Optional[str] = None, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return generate_cold_call_script({"name": lead.name, "company": lead.company, "health_interest": lead.health_interest, "pain_points": lead.pain_points, "notes": lead.notes}, product_focus, user=current_user)


@router.post("/import/csv", status_code=201)
async def import_leads_csv(
    file: UploadFile = File(...),
    campaign_id: Optional[int] = None,
    auto_schedule: bool = True,
    current_user=Depends(check_lead_limit),
    db: Session = Depends(get_db),
):
    content = await file.read()
    leads_data, errors = import_csv(content, campaign_id)
    imported = []
    for ld in leads_data:
        existing = None
        if ld.get("phone"):
            existing = db.query(Lead).filter(Lead.phone == ld["phone"], Lead.user_id == current_user.id).first()
        if not existing and ld.get("email"):
            existing = db.query(Lead).filter(Lead.email == ld["email"], Lead.user_id == current_user.id).first()
        if existing:
            continue
        lead = Lead(**{k: v for k, v in ld.items() if hasattr(Lead, k)}, user_id=current_user.id)
        db.add(lead)
        db.flush()
        imported.append(lead.id)
    db.commit()
    if auto_schedule:
        for lead_id in imported:
            schedule_followup_sequence(lead_id)
    return {"imported": len(imported), "errors": errors, "lead_ids": imported}
