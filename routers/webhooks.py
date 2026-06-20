"""
Twilio webhooks — handles voice call events, AMD (answering machine detection),
call status callbacks, SMS status callbacks, and incoming SMS replies.
"""
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Lead, Interaction
from core.voice_caller import build_call_twiml, build_call_twiml_elevenlabs, build_voicemail_twiml, build_response_twiml
from core.ai_engine import analyze_interaction, generate_cold_call_script, handle_objection
from core.sms_sender import send_sms

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
        opening = script.get("opening", f"Hi {name}, this is {_agent_name()} calling from {_company_name()}. I hope I'm not catching you at a bad time? We help people discover powerful health and wellness solutions. Do you have just 60 seconds?")

        gather_url = f"{_base_url()}/webhooks/voice/gather?lead_id={lead_id}"
        from config import settings as _s
        if _s.ELEVENLABS_API_KEY:
            audio_url = f"{_base_url()}/webhooks/audio/lead/{lead_id}.mp3"
            twiml = build_call_twiml_elevenlabs(opening, gather_url, audio_url)
        else:
            twiml = build_call_twiml(opening, gather_url)
        return xml_response(twiml)
    except Exception as e:
        logger.error(f"voice_answer error for lead {lead_id}: {e}")
        from twilio.twiml.voice_response import VoiceResponse
        r = VoiceResponse()
        from config import settings as _cfg
        r.say(f"Hi, this is {_agent_name()} from {_company_name()}. Please visit {_cfg.SHOP_URL} to learn more about our products. Have a wonderful day!", voice="Google.en-US-Neural2-F")
        r.hangup()
        return xml_response(str(r))


@router.post("/voice/gather")
async def voice_gather(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """
    Called when lead responds (keypress or speech).
    AI decides how to respond.
    """
    try:
        form = await request.form()
        speech = form.get("SpeechResult", "") or ""
        speech = speech.strip()
        digits = form.get("Digits", "") or ""
        digits = digits.strip()

        lead = db.query(Lead).filter(Lead.id == lead_id).first()

        if digits == "2" or any(phrase in speech.lower() for phrase in [
            "not interested", "remove", "don't call", "stop calling", "take me off"
        ]):
            try:
                if lead:
                    lead.do_not_contact = True
                    lead.status = "lost"
                    lead.updated_at = datetime.now()
                    db.commit()
            except Exception as db_err:
                logger.error(f"DB update error (opt-out) lead {lead_id}: {db_err}")
            response_text = "Absolutely, I'll remove you from our list right away. I'm sorry to have bothered you. Have a wonderful day and take care!"
            return xml_response(build_response_twiml(response_text))

        if digits == "1" or any(phrase in speech.lower() for phrase in [
            "tell me more", "interested", "yes", "sure", "go ahead", "okay", "ok", "sounds good"
        ]):
            try:
                if lead:
                    lead.status = "interested"
                    lead.updated_at = datetime.now()
                    db.commit()
            except Exception as db_err:
                logger.error(f"DB update error (interested) lead {lead_id}: {db_err}")

            # Fire SMS immediately with the website link
            try:
                if lead and lead.phone:
                    from config import settings as _cfg
                    sms_body = (
                        f"Hi {lead.name or 'there'}! It's {_agent_name()} from {_company_name()}. "
                        f"Here's the link I mentioned — check it out: {_cfg.SHOP_URL} "
                        f"Our team will follow up with you soon. Reply STOP to unsubscribe."
                    )
                    send_sms(lead.phone, sms_body, lead_id=lead_id)
            except Exception as sms_err:
                logger.error(f"SMS send error for lead {lead_id}: {sms_err}")

            response_text = (
                "Amazing — I just sent you a text message right now with the link to our website. "
                "Check it out when you get a chance — it only takes two minutes and I think you'll love what you see. "
                "Can I ask quickly — what's your biggest health goal right now? "
                "Energy, weight, sleep, or maybe even earning some extra income from home?"
            )
            gather_url = f"{_base_url()}/webhooks/voice/gather2?lead_id={lead_id}"
            return xml_response(build_response_twiml(response_text, gather_url))

        # Handle speech with AI
        response_text = (
            "No problem at all! We have some amazing products that could really help you. "
            "Check us out online and our team will follow up with you soon."
        )
        if speech and lead:
            try:
                lead_context = {
                    "health_interest": lead.health_interest or "general wellness",
                    "pain_points": lead.pain_points or "",
                }
                response_text = handle_objection(speech, lead_context)
                interaction = Interaction(
                    lead_id=lead.id, type="call", direction="inbound",
                    content=speech, outcome="speech_response",
                )
                db.add(interaction)
                db.commit()
            except Exception as ai_err:
                logger.error(f"AI objection handler error lead {lead_id}: {ai_err}")

        gather_url = f"{_base_url()}/webhooks/voice/gather2?lead_id={lead_id}"
        return xml_response(build_response_twiml(response_text, gather_url))

    except Exception as e:
        logger.error(f"voice_gather crash for lead {lead_id}: {e}")
        from twilio.twiml.voice_response import VoiceResponse
        r = VoiceResponse()
        r.say(
            "Thank you so much for your time! We'll be in touch soon with more information. Have a wonderful day!",
            voice="Google.en-US-Neural2-F",
        )
        r.hangup()
        return xml_response(str(r))


@router.post("/voice/gather2")
async def voice_gather2(request: Request, lead_id: int, db: Session = Depends(get_db)):
    """Secondary gather — wrap up the call."""
    try:
        form = await request.form()
        speech = form.get("SpeechResult", "") or ""
        speech = speech.strip()

        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead and speech:
            try:
                interaction = Interaction(
                    lead_id=lead.id, type="call", direction="inbound",
                    content=speech, outcome="discovery",
                )
                db.add(interaction)
                if not lead.pain_points:
                    lead.pain_points = speech[:500]
                db.commit()
            except Exception as db_err:
                logger.error(f"DB error in gather2 lead {lead_id}: {db_err}")

        closing = (
            "Perfect — that's exactly what we can help with! "
            "Check the text message I just sent you — the website link is right there. "
            "Browse through and you'll see exactly what I mean. "
            "Our team will personally follow up with you very soon to answer any questions. "
            "Thank you so much — exciting things are coming your way!"
        )
        return xml_response(build_response_twiml(closing))
    except Exception as e:
        logger.error(f"voice_gather2 crash for lead {lead_id}: {e}")
        from twilio.twiml.voice_response import VoiceResponse
        r = VoiceResponse()
        r.say("Thank you for your time! We'll follow up with you soon.", voice="Google.en-US-Neural2-F")
        r.hangup()
        return xml_response(str(r))


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
                f"Hi {lead.name}, this is {_agent_name()} from {_company_name()}. "
                f"I'm reaching out because we have some great products I think you'd love. "
                f"I'd love to chat — please call us back at your convenience. Have a great day!"
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
            f"Thanks for your reply! {_agent_name()} from {_company_name()} will get back to you shortly. "
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


@router.get("/audio/lead/{lead_id}.mp3")
async def call_audio(lead_id: int, db: Session = Depends(get_db)):
    """Generate ElevenLabs audio for the lead's call opening. Twilio plays this via <Play>."""
    from fastapi.responses import Response as FastResponse
    from core.tts import generate_audio
    import json

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    name = lead.name if lead else "there"

    interaction = (
        db.query(Interaction)
        .filter(Interaction.lead_id == lead_id, Interaction.type == "call")
        .order_by(Interaction.created_at.desc())
        .first()
    )

    text = (
        f"Hi {name}, this is {_agent_name()} calling from {_company_name()}. "
        f"We help people discover powerful health and wellness solutions. "
        f"Do you have just 60 seconds?"
    )
    if interaction and interaction.content:
        try:
            script = json.loads(interaction.content)
            text = script.get("opening", text)
        except Exception:
            pass

    try:
        audio = generate_audio(text)
    except Exception as e:
        logger.error(f"ElevenLabs TTS failed: {e}")
        audio = None

    if not audio:
        # Fall back to Polly TwiML so the call doesn't fail
        from twilio.twiml.voice_response import VoiceResponse as VR
        r = VR()
        r.say(text, voice="Google.en-US-Neural2-F", language="en-US")
        return Response(content=str(r), media_type="application/xml")

    return FastResponse(content=audio, media_type="audio/mpeg")


def _base_url() -> str:
    from config import settings
    return settings.BASE_URL


def _agent_name() -> str:
    from config import settings
    return settings.AGENT_NAME


def _company_name() -> str:
    from config import settings
    return settings.COMPANY_NAME
