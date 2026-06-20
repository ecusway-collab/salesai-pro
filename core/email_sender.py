"""SendGrid email — send personalized follow-up emails to leads."""
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, ReplyTo
from config import settings

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    lead_id: int = None,
    from_email_override: str = None,
    from_name_override: str = None,
    sendgrid_key_override: str = None,
) -> dict:
    """Send a plain-text / light-HTML email via SendGrid."""
    api_key = sendgrid_key_override or settings.SENDGRID_API_KEY
    if not api_key:
        logger.warning("SendGrid API key not configured — email skipped")
        return {"success": False, "error": "SendGrid not configured"}

    sender_email = from_email_override or settings.FROM_EMAIL
    sender_name = from_name_override or settings.FROM_NAME
    reply_to = settings.REPLY_TO_EMAIL or sender_email
    contact_line = f"\n\nTo reply, email us at: {reply_to}" if reply_to != sender_email else ""

    unsubscribe_url = f"{settings.BASE_URL}/unsubscribe/{lead_id}" if lead_id else f"{settings.BASE_URL}/unsubscribe/0"
    unsubscribe_line = f"\n\n---\nTo unsubscribe from future emails, click here: {unsubscribe_url}"
    full_body = body + contact_line + unsubscribe_line

    html_body = full_body.replace("\n", "<br>")
    html_body += f'<br><br><hr><small><a href="{unsubscribe_url}" style="color:#999">Unsubscribe</a></small>'

    message = Mail(
        from_email=Email(sender_email, sender_name),
        to_emails=To(to_email, to_name),
        subject=subject,
    )
    message.reply_to = ReplyTo(reply_to, sender_name)
    message.content = [
        Content("text/plain", full_body),
        Content("text/html", f"<html><body>{html_body}</body></html>"),
    ]

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        logger.info(f"Email sent to {to_email}: status={response.status_code}")
        return {"success": True, "status_code": response.status_code}
    except Exception as e:
        logger.error(f"Email failed to {to_email}: {e}")
        return {"success": False, "error": str(e)}


def send_bulk_email(leads: list, subject_template: str, body_template: str) -> list:
    """
    Send emails to a list of leads.
    Templates support {name} and {company} placeholders.
    """
    results = []
    for lead in leads:
        subject = subject_template.replace("{name}", lead.get("name", "there"))
        body = (
            body_template
            .replace("{name}", lead.get("name", "there"))
            .replace("{company}", lead.get("company", "your company"))
        )
        result = send_email(lead["email"], lead["name"], subject, body)
        result["lead_id"] = lead.get("id")
        results.append(result)
    return results
