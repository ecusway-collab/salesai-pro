"""
Twilio webhooks — handles voice call events, AMD (answering machine detection),
call status callbacks, SMS status callbacks, and incoming SMS replies.
"""
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Lead, Interaction
from core.voice_caller import build_call_twiml, build_voicemail_twiml, build_response_twiml
from core.ai_engine import analyze_interaction, generate_cold_call_script, handle_objection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def xml_response(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


@router.post("/voice/answer")
async def voice_answer(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """
    Called by Twilio when a lead picks up the phone.
    Returns TwiML with the AI-generated opening script.
    """
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        name = lead.name if lead else "there"

        lead_dict = {
            "name": name,
            "company": lead.company if lead else "",
            "health_interest": lead.health_interest if lead else "",
            "pain_points": lead.pain_points if lead else "",
            "notes": lead.notes if lead else "",
        }
        script = generate_cold_call_script(lead_dict)
        opening = script.get("opening", f"Hi {name}, this is {_agent_name()} calling from Vital Health Global. I hope I'm not catching you at a bad time? We help people discover natural health solutions for energy, wellness and vitality. Do you have just 60 seconds?")

        gather_url = f"{_base_url()}/webhooks/voice/gather?lead_id={lead_id}"
        twiml = build_call_twiml(opening, gather_url)
        return xml_response(twiml)
    except Exception as e:
        logger.error(f"voice_answer error for lead {lead_id}: {e}")
        from twilio.twiml.voice_response import VoiceResponse
        r = VoiceResponse()
        r.say(f"Hi, this is Alex from Vital Health Global. We offer premium natural health products that can help with energy, wellness and vitality. Please visit getfreeproducts.net to learn more. Have a wonderful day!", voice="Polly.Joanna")
        r.hangup()
        return xml_response(str(r))


@router.post("/voice/gather")
async def voice_gather(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """
    Called when lead responds (keypress or speech).
    AI decides how to respond.
    """
    form = await request.form()
    speech = form.get("SpeechResult", "").strip()
    digits = form.get("Digits", "").strip()

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    response_text = ""

    if digits == "2" or any(phrase in speech.lower() for phrase in [
        "not interested", "remove", "don't call", "stop calling", "take me off"
    ]):
        if lead:
            lead.do_not_contact = True
            lead.status = "lost"
            lead.updated_at = datetime.now()
            db.commit()
        response_text = "Absolutely, I'll remove you from our list right away. I'm sorry to have bothered you. Have a wonderful day and take care!"
        twiml = build_response_twiml(response_text)
        return xml_response(twiml)

    if digits == "1" or any(phrase in speech.lower() for phrase in [
        "tell me more", "interested", "yes", "sure", "go ahead"
    ]):
        if lead:
            lead.status = "interested"
            lead.updated_at = datetime.now()
            db.commit()
        response_text = (
            f"Wonderful! We specialize in natural health supplements and wellness programs "
            f"that help people like you feel their absolute best. "
            f"Can I ask — what's your biggest health concern right now? Whether it's energy, "
            f"sleep, weight, or just overall wellness, we likely have something perfect for you."
        )
        gather_url = f"{_base_url()}/webhooks/voice/gather2?lead_id={lead_id}"
        twiml = build_response_twiml(response_text, gather_url)
        return xml_response(twiml)

    # Handle speech objection with AI
    if speech and lead:
        lead_context = {
            "health_interest": lead.health_interest or "general wellness",
            "pain_points": lead.pain_points or "",
        }
        response_text = handle_objection(speech, lead_context)

        # Log the speech input
        interaction = Interaction(
            lead_id=lead.id, type="call", direction="inbound",
            content=speech, outcome="speech_response",
        )
        db.add(interaction)
        db.commit()
    else:
        response_text = (
            "No problem at all! I'd love to send you some information about our natural health products. "
            "What's the best way to reach you — text or email?"
        )

    gather_url = f"{_base_url()}/webhooks/voice/gather2?lead_id={lead_id}"
    twiml = build_response_twiml(response_text, gather_url)
    return xml_response(twiml)


@router.post("/voice/gather2")
async def voice_gather2(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """Secondary gather — wrap up the call."""
    form = await request.form()
    speech = form.get("SpeechResult", "").strip()

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead and speech:
        # Log and update pain points if we learned something
        interaction = Interaction(
            lead_id=lead.id, type="call", direction="inbound",
            content=speech, outcome="discovery",
        )
        db.add(interaction)
        if not lead.pain_points:
            lead.pain_points = speech[:500]
        db.commit()

    closing = (
        "That's really helpful to know. I'll follow up with some personalized information "
        "that I think will genuinely help you. "
        "Thank you so much for your time today, and I hope you have a fantastic, healthy day!"
    )
    twiml = build_response_twiml(closing)
    return xml_response(twiml)


@router.post("/voice/amd")
async def voice_amd(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """
    Answering Machine Detection callback.
    If machine detected, leave a voicemail TwiML.
    """
    form = await request.form()
    amd_status = form.get("AnsweredBy", "")
    call_sid = form.get("CallSid", "")

    logger.info(f"AMD for lead {lead_id}: {amd_status}")

    if amd_status in ("machine_start", "machine_end_beep", "machine_end_silence"):
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead_dict = {
                "name": lead.name, "company": lead.company or "",
                "health_interest": lead.health_interest or "",
                "pain_points": lead.pain_points or "", "notes": lead.notes or "",
            }
            script = generate_cold_call_script(lead_dict)
            voicemail = script.get(
                "voicemail_script",
                f"Hi {lead.name}, this is {_agent_name()} from NaturalWell Health Solutions. "
                f"I'm reaching out because we have some natural wellness products that many "
                f"people in your area are loving. I'd love to chat — please call us back at your convenience. Have a healthy day!"
            )
            # Update the live call with voicemail TwiML via Twilio API
            from core.voice_caller import get_client
            try:
                get_client().calls(call_sid).update(
                    twiml=build_voicemail_twiml(voicemail)
                )
            except Exception as e:
                logger.error(f"AMD voicemail update failed: {e}")

            interaction = Interaction(
                lead_id=lead.id, type="call", direction="outbound",
                content=voicemail, outcome="voicemail",
            )
            db.add(interaction)
            db.commit()

    return Response(status_code=204)


@router.post("/voice/status")
async def voice_status(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """Call status callback — update interaction record with final status."""
    form = await request.form()
    call_status = form.get("CallStatus", "")
    call_sid = form.get("CallSid", "")
    duration = form.get("CallDuration", 0)

    interaction = (
        db.query(Interaction)
        .filter(Interaction.lead_id == lead_id, Interaction.call_sid == call_sid)
        .first()
    )
    if not interaction:
        interaction = (
            db.query(Interaction)
            .filter(Interaction.lead_id == lead_id, Interaction.type == "call")
            .order_by(Interaction.created_at.desc())
            .first()
        )

    if interaction:
        interaction.outcome = call_status
        interaction.duration_seconds = int(duration) if duration else None
        db.commit()

    logger.info(f"Call {call_sid} for lead {lead_id}: {call_status} ({duration}s)")
    return Response(status_code=204)


@router.post("/voice/recording")
async def voice_recording(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """Store recording URL on the most recent call interaction."""
    form = await request.form()
    recording_url = form.get("RecordingUrl", "")
    call_sid = form.get("CallSid", "")

    if recording_url:
        interaction = (
            db.query(Interaction)
            .filter(Interaction.lead_id == lead_id, Interaction.type == "call")
            .order_by(Interaction.created_at.desc())
            .first()
        )
        if interaction:
            interaction.recording_url = recording_url + ".mp3"
            db.commit()

    return Response(status_code=204)


@router.post("/sms/incoming")
async def sms_incoming(request: Request, db: Session = Depends(get_db)):
    """Handle inbound SMS replies from leads."""
    form = await request.form()
    from_number = form.get("From", "")
    body = form.get("Body", "").strip()

    lead = db.query(Lead).filter(Lead.phone == from_number).first()
    if lead:
        interaction = Interaction(
            lead_id=lead.id, type="sms", direction="inbound", content=body,
        )
        db.add(interaction)

        # Auto-analyse and update lead
        if any(word in body.lower() for word in ["stop", "unsubscribe", "remove", "opt out"]):
            lead.do_not_contact = True
            lead.status = "lost"
            interaction.outcome = "opted_out"
        elif any(word in body.lower() for word in ["yes", "interested", "tell me", "more info", "sure"]):
            lead.status = "interested"
            interaction.outcome = "positive_reply"
        else:
            interaction.outcome = "reply"

        lead.updated_at = datetime.now()
        db.commit()

    # Auto-reply with TwiML SMS
    from twilio.twiml.messaging_response import MessagingResponse
    resp = MessagingResponse()
    if lead and lead.do_not_contact:
        resp.message("You've been removed from our list. We're sorry to see you go! Stay healthy. 🌿")
    else:
        resp.message(
            f"Thanks for your reply! {_agent_name()} from NaturalWell will get back to you shortly. "
            f"Reply STOP to unsubscribe."
        )

    return Response(content=str(resp), media_type="application/xml")


@router.post("/sms/status")
async def sms_status(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """SMS delivery status callback."""
    form = await request.form()
    message_status = form.get("MessageStatus", "")
    logger.info(f"SMS status for lead {lead_id}: {message_status}")
    return Response(status_code=204)


def _base_url() -> str:
    from config import settings
    return settings.BASE_URL


def _agent_name() -> str:
    from config import settings
    return settings.AGENT_NAME
