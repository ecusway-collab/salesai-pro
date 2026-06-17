"""Twilio voice call management — outbound calls, TwiML generation, webhooks."""
import logging
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Say
from config import settings

logger = logging.getLogger(__name__)

_twilio = None


def get_client(user=None) -> Client:
    if user and user.twilio_account_sid and user.twilio_auth_token:
        return Client(user.twilio_account_sid, user.twilio_auth_token)
    global _twilio
    if _twilio is None:
        _twilio = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _twilio


def _phone_number(user=None) -> str:
    if user and user.twilio_phone_number:
        return user.twilio_phone_number
    return settings.TWILIO_PHONE_NUMBER


def make_outbound_call(lead_phone: str, lead_id: int, user=None) -> dict:
    """
    Initiate an outbound call to a lead.
    Twilio will hit /webhooks/voice/answer when the call connects.
    """
    try:
        call = get_client(user).calls.create(
            to=lead_phone,
            from_=_phone_number(user),
            url=f"{settings.BASE_URL}/webhooks/voice/answer?lead_id={lead_id}",
            status_callback=f"{settings.BASE_URL}/webhooks/voice/status?lead_id={lead_id}",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
            record=True,
            recording_status_callback=f"{settings.BASE_URL}/webhooks/voice/recording?lead_id={lead_id}",
            recording_status_callback_method="POST",
            machine_detection="Enable",              # detect answering machines
            async_amd=True,
            async_amd_status_callback=f"{settings.BASE_URL}/webhooks/voice/amd?lead_id={lead_id}",
        )
        logger.info(f"Call initiated to lead {lead_id}: SID={call.sid}")
        return {"success": True, "call_sid": call.sid, "status": call.status}
    except Exception as e:
        logger.error(f"Call failed for lead {lead_id}: {e}")
        return {"success": False, "error": str(e)}


def build_call_twiml(opening: str, gather_action_url: str) -> str:
    """
    Build TwiML for the opening of a cold call.
    Uses Polly.Joanna for natural-sounding AI voice.
    Lead can press 1 (interested), 2 (not interested), or speak freely.
    """
    response = VoiceResponse()

    gather = Gather(
        input="speech dtmf",
        action=gather_action_url,
        method="POST",
        speech_timeout="3",
        timeout=8,
        num_digits=1,
    )
    gather.say(opening, voice="Polly.Joanna", language="en-US")
    gather.say(
        "Press 1 to learn more, press 2 to be removed from our list, "
        "or just speak your response.",
        voice="Polly.Joanna",
    )
    response.append(gather)

    # If no input captured, leave a brief message and hang up
    response.say(
        "I didn't catch that — no problem at all! I'll follow up another time. "
        "Have a wonderful and healthy day!",
        voice="Polly.Joanna",
    )
    response.hangup()
    return str(response)


def build_voicemail_twiml(voicemail_script: str) -> str:
    """TwiML for leaving a voicemail on an answering machine."""
    response = VoiceResponse()
    response.say(voicemail_script, voice="Polly.Joanna", language="en-US")
    response.hangup()
    return str(response)


def build_response_twiml(message: str, gather_url: str = None) -> str:
    """TwiML for responding mid-call with optional follow-up gather."""
    response = VoiceResponse()
    if gather_url:
        gather = Gather(
            input="speech dtmf",
            action=gather_url,
            method="POST",
            speech_timeout="3",
            timeout=8,
        )
        gather.say(message, voice="Polly.Joanna")
        response.append(gather)
    else:
        response.say(message, voice="Polly.Joanna")
        response.hangup()
    return str(response)


def get_call_recording(call_sid: str) -> dict:
    """Fetch recording details for a completed call."""
    try:
        recordings = get_client().recordings.list(call_sid=call_sid, limit=1)
        if recordings:
            rec = recordings[0]
            return {
                "recording_sid": rec.sid,
                "duration": rec.duration,
                "url": f"https://api.twilio.com{rec.uri.replace('.json', '.mp3')}",
            }
        return {}
    except Exception as e:
        logger.error(f"Failed to fetch recording for {call_sid}: {e}")
        return {}


def get_call_details(call_sid: str) -> dict:
    """Fetch status and duration of a call by SID."""
    try:
        call = get_client().calls(call_sid).fetch()
        return {
            "status": call.status,
            "duration": call.duration,
            "start_time": str(call.start_time),
            "end_time": str(call.end_time),
        }
    except Exception as e:
        return {"error": str(e)}
