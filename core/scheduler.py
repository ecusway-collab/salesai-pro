"""
Follow-up scheduler using APScheduler.
Automatically executes pending follow-ups (calls, SMS, emails) at their scheduled time.
Also handles post-call analysis and lead scoring after each interaction.
"""
import json
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from config import settings

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None

DEFAULT_SEQUENCE = [
    {"day": 0,  "type": "call",  "notes": "Initial cold call"},
    {"day": 2,  "type": "sms",   "notes": "Follow-up SMS if no answer"},
    {"day": 5,  "type": "email", "notes": "Value-add email"},
    {"day": 10, "type": "call",  "notes": "Second call attempt"},
    {"day": 16, "type": "sms",   "notes": "Check-in SMS"},
    {"day": 22, "type": "email", "notes": "Special offer email"},
    {"day": 30, "type": "call",  "notes": "Final call attempt"},
]


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        executors = {"default": ThreadPoolExecutor(5)}
        _scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults={
                "coalesce": True,        # merge missed runs into one
                "max_instances": 3,
                "misfire_grace_time": 300,  # ignore misfires older than 5 min
            },
        )
    return _scheduler


def start_scheduler():
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        # Main tick: check and execute pending follow-ups every minute
        sched.add_job(
            _execute_pending_followups,
            trigger="interval",
            minutes=1,
            id="followup_tick",
            replace_existing=True,
            name="Execute Pending Follow-ups",
        )
        logger.info("Scheduler started")


def stop_scheduler():
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("Scheduler stopped")


def schedule_followup_sequence(lead_id: int, campaign_sequence: list = None):
    """
    Schedule the full follow-up sequence for a newly added lead.
    Uses campaign sequence if provided, otherwise uses DEFAULT_SEQUENCE.
    """
    from database import SessionLocal
    from models import FollowUp, Lead
    from core.ai_engine import generate_sms_message, generate_email

    sequence = campaign_sequence or DEFAULT_SEQUENCE
    db = SessionLocal()

    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return

        now = datetime.now()
        for step in sequence:
            scheduled_at = now + timedelta(days=step["day"])
            # Skip if already scheduled for this type at this time
            existing = db.query(FollowUp).filter(
                FollowUp.lead_id == lead_id,
                FollowUp.type == step["type"],
                FollowUp.status == "pending",
            ).first()
            if existing:
                continue

            fu = FollowUp(
                lead_id=lead_id,
                type=step["type"],
                scheduled_at=scheduled_at,
                status="pending",
                message=step.get("notes", ""),
            )
            db.add(fu)

        db.commit()
        logger.info(f"Scheduled {len(sequence)}-step follow-up sequence for lead {lead_id}")
    except Exception as e:
        logger.error(f"Failed to schedule follow-up for lead {lead_id}: {e}")
        db.rollback()
    finally:
        db.close()


def _execute_pending_followups():
    """Called every minute — executes all follow-ups due now or in the past."""
    from database import SessionLocal
    from models import FollowUp, Lead, Interaction
    from core.voice_caller import make_outbound_call
    from core.sms_sender import send_sms
    from core.email_sender import send_email
    from core.ai_engine import generate_sms_message, generate_email, generate_cold_call_script

    db = SessionLocal()
    now = datetime.now()

    try:
        pending = (
            db.query(FollowUp)
            .filter(FollowUp.status == "pending", FollowUp.scheduled_at <= now)
            .limit(20)
            .all()
        )

        for fu in pending:
            lead = db.query(Lead).filter(Lead.id == fu.lead_id).first()
            if not lead or lead.do_not_contact:
                fu.status = "cancelled"
                db.commit()
                continue

            try:
                _execute_single_followup(fu, lead, db)
            except Exception as e:
                logger.error(f"Follow-up {fu.id} failed: {e}")
                fu.status = "failed"
                fu.error_message = str(e)
                fu.executed_at = now
                db.commit()

    except Exception as e:
        logger.error(f"Scheduler tick error: {e}")
    finally:
        db.close()


def _execute_single_followup(fu, lead, db):
    """Execute one follow-up action."""
    from models import Interaction
    from core.voice_caller import make_outbound_call
    from core.sms_sender import send_sms
    from core.email_sender import send_email
    from core.ai_engine import (
        generate_cold_call_script, generate_sms_message,
        generate_email, score_lead
    )

    now = datetime.now()
    lead_dict = {
        "name": lead.name, "company": lead.company or "",
        "health_interest": lead.health_interest or "",
        "pain_points": lead.pain_points or "",
        "notes": lead.notes or "", "status": lead.status,
    }

    # Build interaction history for context
    history = [
        {"type": i.type, "date": str(i.created_at)[:10],
         "outcome": i.outcome or "", "ai_analysis": i.ai_analysis or ""}
        for i in lead.interactions[-5:]
    ]
    followup_number = len(lead.interactions) + 1

    outcome = None
    content = None
    result = {}

    if fu.type == "call" and lead.phone:
        script = generate_cold_call_script(lead_dict)
        result = make_outbound_call(lead.phone, lead.id)
        outcome = "call_initiated" if result.get("success") else "call_failed"
        content = json.dumps(script)

    elif fu.type == "sms" and lead.phone:
        message = generate_sms_message(lead_dict, history, followup_number)
        result = send_sms(lead.phone, message, lead.id)
        outcome = "sent" if result.get("success") else "failed"
        content = message

    elif fu.type == "email" and lead.email:
        email_data = generate_email(lead_dict, history, "first_followup")
        result = send_email(
            lead.email, lead.name,
            email_data.get("subject", "Following up on your wellness journey"),
            email_data.get("body", ""),
        )
        outcome = "sent" if result.get("success") else "failed"
        content = json.dumps(email_data)

    else:
        fu.status = "cancelled"
        fu.executed_at = now
        db.commit()
        return

    # Log the interaction
    interaction = Interaction(
        lead_id=lead.id,
        type=fu.type,
        direction="outbound",
        content=content,
        outcome=outcome,
    )
    db.add(interaction)

    # Update lead status
    if lead.status == "new":
        lead.status = "contacted"
    lead.updated_at = now

    # Update follow-up
    fu.status = "sent" if result.get("success") else "failed"
    fu.executed_at = now
    fu.error_message = result.get("error")

    db.commit()
    logger.info(f"Follow-up {fu.id} ({fu.type}) for lead {lead.id}: {outcome}")
