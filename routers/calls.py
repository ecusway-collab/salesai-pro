"""Call center — trigger calls, view history, send SMS/email manually."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import Lead, Interaction, FollowUp, User
from core.voice_caller import make_outbound_call
from core.sms_sender import send_sms
from core.email_sender import send_email
from core.ai_engine import (
    generate_cold_call_script, generate_sms_message,
    generate_email, handle_objection
)

router = APIRouter(prefix="/calls", tags=["calls"])


@router.post("/dial/{lead_id}")
def dial_lead(lead_id: int, product_focus: Optional[str] = None, db: Session = Depends(get_db)):
    """Initiate an AI-powered outbound call to a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead.do_not_contact:
        raise HTTPException(400, "Lead is marked Do Not Contact")
    if not lead.phone:
        raise HTTPException(400, "Lead has no phone number")

    # Generate personalized script
    lead_dict = {
        "name": lead.name, "company": lead.company or "",
        "health_interest": lead.health_interest or "",
        "pain_points": lead.pain_points or "", "notes": lead.notes or "",
    }
    script = generate_cold_call_script(lead_dict, product_focus)

    # Store script in DB for Twilio webhook to retrieve
    interaction = Interaction(
        lead_id=lead.id,
        type="call",
        direction="outbound",
        content=json.dumps(script) if isinstance(script, dict) else str(script),
        outcome="initiating",
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)

    result = make_outbound_call(lead.phone, lead.id)

    if result.get("success"):
        interaction.call_sid = result["call_sid"]
        interaction.outcome = "call_initiated"
        if lead.status == "new":
            lead.status = "contacted"
        lead.updated_at = datetime.now()
        db.commit()
        return {"message": "Call initiated", "call_sid": result["call_sid"], "script": script}
    else:
        interaction.outcome = "call_failed"
        db.commit()
        raise HTTPException(500, f"Call failed: {result.get('error')}")


@router.post("/sms/{lead_id}")
def send_sms_to_lead(lead_id: int, message: Optional[str] = None, db: Session = Depends(get_db)):
    """Send an AI-generated (or custom) SMS to a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead.do_not_contact:
        raise HTTPException(400, "Lead is marked Do Not Contact")
    if not lead.phone:
        raise HTTPException(400, "Lead has no phone number")

    if not message:
        history = [
            {"type": i.type, "date": str(i.created_at)[:10], "outcome": i.outcome or ""}
            for i in lead.interactions[-3:]
        ]
        lead_dict = {
            "name": lead.name, "health_interest": lead.health_interest or "",
            "pain_points": lead.pain_points or "",
        }
        message = generate_sms_message(lead_dict, history, len(lead.interactions) + 1)

    result = send_sms(lead.phone, message, lead.id)

    interaction = Interaction(
        lead_id=lead.id,
        type="sms",
        direction="outbound",
        content=message,
        outcome="sent" if result.get("success") else "failed",
    )
    db.add(interaction)
    if lead.status == "new":
        lead.status = "contacted"
    db.commit()

    if not result.get("success"):
        raise HTTPException(500, f"SMS failed: {result.get('error')}")
    return {"message": "SMS sent", "content": message}


@router.post("/email/{lead_id}")
def send_email_to_lead(
    lead_id: int,
    email_type: str = "first_followup",
    db: Session = Depends(get_db),
):
    """Send an AI-generated follow-up email to a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead.do_not_contact:
        raise HTTPException(400, "Lead is marked Do Not Contact")
    if not lead.email:
        raise HTTPException(400, "Lead has no email address")

    history = [
        {"type": i.type, "date": str(i.created_at)[:10], "outcome": i.outcome or ""}
        for i in lead.interactions[-5:]
    ]
    lead_dict = {
        "name": lead.name, "company": lead.company or "",
        "health_interest": lead.health_interest or "",
        "pain_points": lead.pain_points or "",
    }
    email_data = generate_email(lead_dict, history, email_type)

    user = db.query(User).filter(User.id == lead.user_id).first() if lead.user_id else None
    result = send_email(
        lead.email, lead.name,
        email_data.get("subject", "Checking in on your wellness journey"),
        email_data.get("body", ""),
        lead_id=lead.id,
        from_email_override=user.from_email if user and user.from_email else None,
        from_name_override=user.from_name if user and user.from_name else None,
        sendgrid_key_override=user.sendgrid_api_key if user and user.sendgrid_api_key else None,
    )

    interaction = Interaction(
        lead_id=lead.id,
        type="email",
        direction="outbound",
        content=str(email_data),
        outcome="sent" if result.get("success") else "failed",
    )
    db.add(interaction)
    if lead.status == "new":
        lead.status = "contacted"
    db.commit()

    if not result.get("success"):
        raise HTTPException(500, f"Email failed: {result.get('error')}")
    return {"message": "Email sent", "email": email_data}


@router.get("/preview-script/{lead_id}")
def preview_script(lead_id: int, db: Session = Depends(get_db)):
    """Generate and return the AI call script for a lead without making a call."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead_dict = {
        "name": lead.name, "company": lead.company or "",
        "health_interest": lead.health_interest or "",
        "pain_points": lead.pain_points or "", "notes": lead.notes or "",
    }
    script = generate_cold_call_script(lead_dict)
    return {"lead_id": lead_id, "lead_name": lead.name, "script": script}


@router.post("/objection-response")
def get_objection_response(objection: str, lead_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Get an AI-generated response to a sales objection in real time."""
    lead_context = {}
    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead_context = {
                "health_interest": lead.health_interest or "",
                "pain_points": lead.pain_points or "",
            }
    response = handle_objection(objection, lead_context)
    return {"objection": objection, "response": response}
