"""Twilio SMS — send outbound SMS messages to leads."""
import logging
from twilio.rest import Client
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


def send_sms(to_phone: str, message: str, lead_id: int = None, user=None) -> dict:
    """Send an SMS to a lead. Returns success status and Twilio message SID."""
    # Enforce 160-char limit (split into two messages if needed)
    if len(message) > 320:
        message = message[:317] + "..."

    try:
        from_number = (user.twilio_phone_number if user and user.twilio_phone_number else settings.TWILIO_PHONE_NUMBER)
        msg = get_client(user).messages.create(
            to=to_phone,
            from_=from_number,
            body=message,
            status_callback=f"{settings.BASE_URL}/webhooks/sms/status?lead_id={lead_id}" if lead_id else None,
        )
        logger.info(f"SMS sent to {to_phone} (lead {lead_id}): SID={msg.sid}")
        return {"success": True, "message_sid": msg.sid, "status": msg.status}
    except Exception as e:
        logger.error(f"SMS failed to {to_phone}: {e}")
        return {"success": False, "error": str(e)}


def send_bulk_sms(leads: list, message_template: str) -> list:
    """
    Send SMS to a list of leads.
    leads: list of dicts with keys: phone, name, id
    message_template: string with {name} placeholder
    """
    results = []
    for lead in leads:
        message = message_template.replace("{name}", lead.get("name", "there"))
        result = send_sms(lead["phone"], message, lead.get("id"))
        result["lead_id"] = lead.get("id")
        results.append(result)
    return results
