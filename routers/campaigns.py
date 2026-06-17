"""Campaign management — scoped to current user."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import Campaign, Lead
from schemas import CampaignCreate, CampaignOut
from core.auth import get_active_user
from core.ai_engine import generate_campaign_templates

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=List[CampaignOut])
def list_campaigns(current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    return db.query(Campaign).filter(Campaign.user_id == current_user.id).order_by(Campaign.created_at.desc()).all()


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(data: CampaignCreate, auto_generate: bool = True, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    campaign = Campaign(**data.model_dump(), user_id=current_user.id)
    db.add(campaign)
    db.flush()
    if auto_generate:
        templates = generate_campaign_templates(data.model_dump(), user=current_user)
        campaign.call_script_template = templates.get("call_script_template", "")
        campaign.sms_template = templates.get("sms_template", "")
        campaign.email_template = json.dumps({"subject": templates.get("email_subject", ""), "body": templates.get("email_body", "")})
        if templates.get("followup_sequence"):
            campaign.followup_sequence = json.dumps(templates["followup_sequence"])
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    return c


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    db.delete(c)
    db.commit()


@router.get("/{campaign_id}/stats")
def campaign_stats(campaign_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    leads = db.query(Lead).filter(Lead.campaign_id == campaign_id, Lead.user_id == current_user.id).all()
    stats = {}
    for lead in leads:
        stats[lead.status] = stats.get(lead.status, 0) + 1
    return {"campaign_id": campaign_id, "total_leads": len(leads), "by_status": stats, "conversion_rate": round(stats.get("won", 0) / max(len(leads), 1) * 100, 1)}


@router.post("/{campaign_id}/regenerate-templates")
def regenerate_templates(campaign_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    templates = generate_campaign_templates({"name": c.name, "product_focus": c.product_focus, "target_audience": c.target_audience, "goal": c.goal}, user=current_user)
    c.call_script_template = templates.get("call_script_template", "")
    c.sms_template = templates.get("sms_template", "")
    c.email_template = json.dumps({"subject": templates.get("email_subject", ""), "body": templates.get("email_body", "")})
    if templates.get("followup_sequence"):
        c.followup_sequence = json.dumps(templates["followup_sequence"])
    db.commit()
    return {"message": "Templates regenerated", "templates": templates}
