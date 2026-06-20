"""
AI Engine — uses Claude to generate scripts, follow-ups, objection responses,
lead scoring, and interaction analysis for natural health product sales.
"""
import json
import logging
import anthropic
from config import settings

logger = logging.getLogger(__name__)


def _get_client(user=None):
    """Return an Anthropic client using the user's key, falling back to platform key."""
    key = (user.anthropic_api_key if user and user.anthropic_api_key
           else settings.ANTHROPIC_API_KEY)
    return anthropic.Anthropic(api_key=key)

def _get_system_prompt() -> str:
    """Build the AI system prompt dynamically from current settings."""
    return f"""You are {settings.AGENT_NAME}, a warm and professional AI sales assistant for {settings.COMPANY_NAME}.

COMPANY: {settings.COMPANY_NAME}
SHOP URL: {settings.SHOP_URL}
MISSION: Helping businesses and individuals discover powerful health and wealth solutions.

YOUR ROLE:
You represent {settings.COMPANY_NAME} on outbound sales calls, SMS, and emails.
Your job is to identify prospect needs, build rapport, and guide them toward solutions that genuinely help them.

YOUR SALES APPROACH:
1. EMPATHY FIRST — ask about their goals and challenges before pitching anything
2. MATCH precisely — recommend solutions that best fit their specific situation
3. EDUCATE, don't pressure — explain benefits clearly and honestly
4. MENTION VALUE — savings, business opportunities, and referral programs where relevant
5. BUILD TRUST — be honest, professional, and respectful at all times
6. FOLLOW UP CONSISTENTLY — most sales happen on the 5th-7th contact

TARGET CUSTOMERS:
• Business owners, entrepreneurs, and professionals
• Health-conscious individuals and wellness seekers
• People looking for supplemental income or business opportunities
• Fitness centers, gyms, wellness centers, health food stores
• Coaches, trainers, and health practitioners

TONE: Warm, confident, professional, energetic, and genuinely helpful
NEVER: Make medical diagnoses, guarantee outcomes, use pressure tactics, or make claims you cannot back up
ALWAYS: Respect the prospect's time and decision — a "no" today can become a "yes" later with great follow-up"""


def _call_claude(messages: list, max_tokens: int = 1000, user=None) -> str:
    """Make a Claude API call with prompt caching on the system prompt."""
    try:
        client = _get_client(user)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": _get_system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise


def _extract_json(text: str) -> dict:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    # Try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip markdown fences
    for fence in ["```json", "```"]:
        if fence in text:
            text = text.split(fence)[1].split("```")[0].strip()
            try:
                return json.loads(text)
            except Exception:
                pass
    # Try to find JSON object in text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except Exception:
            pass
    return {"raw": text}


# ── Script Generation ─────────────────────────────────────────────────────────

def generate_cold_call_script(lead: dict, product_focus: str = None, user=None) -> dict:
    """
    Generate a full personalized cold call script for a lead.
    Returns: opening, discovery_questions, value_prop, objection_handlers,
             call_to_action, voicemail_script
    """
    prompt = f"""Generate a personalized cold call script for this lead.

LEAD DETAILS:
- Name: {lead.get('name', 'there')}
- Company: {lead.get('company', 'not specified')}
- Health Interest: {lead.get('health_interest', 'general wellness')}
- Pain Points: {lead.get('pain_points', 'unknown')}
- Notes: {lead.get('notes', 'none')}
- Product Focus: {product_focus or 'general natural health products'}

Return a JSON object with these exact fields:
{{
  "opening": "The first 20-30 seconds — introduce yourself warmly, state reason for call, create curiosity",
  "discovery_questions": ["question 1", "question 2", "question 3", "question 4"],
  "value_proposition": "2-3 sentences on how our products solve their health needs",
  "objection_handlers": {{
    "too expensive": "response...",
    "not interested": "response...",
    "already have a supplier": "response...",
    "send me info": "response...",
    "call back later": "response..."
  }},
  "call_to_action": "Specific next step to propose (schedule follow-up call, send samples, book consultation)",
  "voicemail_script": "Max 25-second voicemail if they don't answer"
}}"""

    try:
        text = _call_claude([{"role": "user", "content": prompt}], max_tokens=1500, user=user)
        return _extract_json(text)
    except Exception:
        name = lead.get('name', 'there')
        return {
            "opening": f"Hi {name}, my name is {settings.AGENT_NAME} calling from {settings.COMPANY_NAME}. I'm reaching out because we help businesses and individuals discover powerful health and wealth solutions. Do you have just 60 seconds?",
            "discovery_questions": ["What's your biggest challenge right now?", "Have you explored health or wellness products before?", "What does your ideal outcome look like?"],
            "value_proposition": f"{settings.COMPANY_NAME} offers premium solutions backed by results. We have products and opportunities that fit every lifestyle and goal.",
            "objection_handlers": {"too expensive": "I understand — we also have starter options and opportunities to earn while you explore.", "not interested": "No problem at all! Can I send you some information to review at your own pace?"},
            "call_to_action": "I'd love to send you more information. What's the best email for you?",
            "voicemail_script": f"Hi {name}, this is {settings.AGENT_NAME} from {settings.COMPANY_NAME}. I'm calling to share some exciting solutions that may be a great fit for you. Please call me back or visit {settings.SHOP_URL}. Have a great day!",
        }


def generate_sms_message(lead: dict, interaction_history: list, followup_number: int, user=None) -> str:
    """Generate a personalized SMS follow-up (max 160 characters)."""
    history = "\n".join(
        [f"- {i.get('type','?')} ({i.get('date','?')}): {i.get('outcome','?')}"
         for i in interaction_history[-3:]]
    ) or "No prior contact"

    prompt = f"""Write a follow-up SMS for {lead.get('name', 'this lead')}.

Follow-up #: {followup_number}
Health interest: {lead.get('health_interest', 'general wellness')}
Pain points: {lead.get('pain_points', 'not specified')}
Recent interactions:
{history}

Rules:
- MAXIMUM 160 characters (SMS limit)
- Warm and personal, not robotic
- Include a soft call-to-action
- Sign as "{settings.AGENT_NAME} | {settings.COMPANY_NAME}"
- No links unless user has a specific product URL

Return ONLY the SMS text, nothing else."""

    try:
        return _call_claude([{"role": "user", "content": prompt}], max_tokens=200, user=user).strip()
    except Exception:
        name = lead.get('name', 'there')
        return (
            f"Hi {name}, this is {settings.AGENT_NAME} from {settings.COMPANY_NAME}! "
            f"Just checking in on you. "
            f"Visit {settings.SHOP_URL} to explore what we offer. "
            f"Reply STOP to unsubscribe."
        )[:160]


def generate_email(lead: dict, interaction_history: list, email_type: str = "first_followup", user=None) -> dict:
    """
    Generate a personalized follow-up email.
    email_type: first_followup | value_add | special_offer | last_attempt | re_engagement
    """
    type_descriptions = {
        "first_followup": "first follow-up after initial call — recap conversation, next step",
        "value_add": "value-add email with a free health tip or resource (no hard sell)",
        "special_offer": "limited-time offer or bundle discount",
        "last_attempt": "final check-in before closing this lead (respectful, no pressure)",
        "re_engagement": "re-engagement after 30+ days of no contact",
    }

    history = "\n".join(
        [f"- {i.get('type','?')} ({i.get('date','?')}): {i.get('outcome','?')}"
         for i in interaction_history[-5:]]
    ) or "No prior contact"

    prompt = f"""Write a {type_descriptions.get(email_type, email_type)} for {lead.get('name', 'this lead')}.

Lead info:
- Company: {lead.get('company', 'not specified')}
- Health interest: {lead.get('health_interest', 'general wellness')}
- Pain points: {lead.get('pain_points', 'not specified')}
Recent interactions:
{history}

Return JSON:
{{
  "subject": "Compelling subject line (not spammy, max 60 chars)",
  "preview_text": "Email preview/preheader text (max 90 chars)",
  "body": "Full email body. Use \\n for line breaks. Sign off as {settings.AGENT_NAME} from {settings.COMPANY_NAME}. Include one clear call-to-action."
}}"""

    try:
        text = _call_claude([{"role": "user", "content": prompt}], max_tokens=800, user=user)
        return _extract_json(text)
    except Exception:
        name = lead.get('name', 'there')
        return {
            "subject": f"Following up — {settings.COMPANY_NAME}",
            "preview_text": f"A quick note from {settings.AGENT_NAME} at {settings.COMPANY_NAME}",
            "body": (
                f"Hi {name},\n\n"
                f"Thank you for your time! I wanted to follow up and share more about how {settings.COMPANY_NAME} can help you.\n\n"
                f"We offer solutions designed to support your goals — whether that's health, wellness, or building a better lifestyle.\n\n"
                f"Visit us at {settings.SHOP_URL} to explore what we have available.\n\n"
                f"Feel free to reply to this email with any questions — I'm happy to help.\n\n"
                f"Best,\n{settings.AGENT_NAME}\n{settings.COMPANY_NAME}"
            ),
        }


# ── Analysis & Intelligence ───────────────────────────────────────────────────

def analyze_interaction(interaction_type: str, content: str, lead_name: str, user=None) -> dict:
    """
    Analyze a call transcript or message to extract insights and recommend next action.
    Returns: sentiment, interest_level, pain_points, objections, next_action, summary
    """
    prompt = f"""Analyze this {interaction_type} with {lead_name} about natural health products:

CONTENT:
{content}

Return JSON:
{{
  "sentiment": "positive | neutral | negative",
  "interest_level": 1-10,
  "pain_points_discovered": ["pain point 1", "..."],
  "objections_raised": ["objection 1", "..."],
  "health_interests_mentioned": ["product/topic 1", "..."],
  "next_action": "call | sms | email | close_won | close_lost | do_not_contact",
  "next_action_timing": "immediately | in 2 days | in 1 week | in 2 weeks | in 1 month",
  "new_status": "new | contacted | interested | qualified | proposal | won | lost",
  "summary": "2-sentence summary of what happened and what matters"
}}"""

    text = _call_claude([{"role": "user", "content": prompt}], max_tokens=600)
    return _extract_json(text)


def score_lead(lead: dict, interactions: list, user=None) -> dict:
    """
    Score a lead 0-100 and assign a tier (hot/warm/cold).
    Returns: score, tier, buying_probability, recommended_product, reasoning
    """
    interactions_text = "\n".join([
        f"- {i.get('type','?')} ({i.get('created_at','?')}): outcome={i.get('outcome','?')} | {str(i.get('ai_analysis',''))[:120]}"
        for i in interactions
    ]) or "No interactions yet"

    prompt = f"""Score this natural health products lead:

LEAD:
Name: {lead.get('name')}
Health Interest: {lead.get('health_interest', 'unknown')}
Pain Points: {lead.get('pain_points', 'unknown')}
Current Status: {lead.get('status', 'new')}

INTERACTION HISTORY:
{interactions_text}

Return JSON:
{{
  "score": 0-100,
  "tier": "hot | warm | cold",
  "buying_probability": 0-100,
  "recommended_product": "best product match for this specific lead",
  "reasoning": "1-2 sentence explanation",
  "urgency": "high | medium | low"
}}"""

    text = _call_claude([{"role": "user", "content": prompt}], max_tokens=400)
    return _extract_json(text)


def handle_objection(objection: str, lead_context: dict) -> str:
    """Return a warm, empathetic response to a specific sales objection."""
    prompt = f"""A prospect just said: "{objection}"

Their context:
- Health interest: {lead_context.get('health_interest', 'general wellness')}
- Pain points: {lead_context.get('pain_points', 'not specified')}

Write a 2-3 sentence response that:
1. Validates their concern (no arguing)
2. Gently reframes toward their health goals
3. Proposes a low-commitment next step

Speak directly to them (no quotes, no labels). Just the response text."""

    return _call_claude([{"role": "user", "content": prompt}], max_tokens=300).strip()


def generate_campaign_templates(campaign: dict, user=None) -> dict:
    """Generate all templates for a new campaign at once."""
    prompt = f"""Create complete sales templates for this natural health campaign:

Campaign: {campaign.get('name')}
Product Focus: {campaign.get('product_focus', 'general wellness products')}
Target Audience: {campaign.get('target_audience', 'health-conscious individuals')}
Goal: {campaign.get('goal', 'generate sales')}

Return JSON:
{{
  "call_script_template": "Full cold call script template with [LEAD_NAME] placeholders",
  "sms_template": "SMS template (max 160 chars, use [NAME] placeholder)",
  "email_subject": "Email subject line template",
  "email_body": "Full email body template with [NAME] and [COMPANY] placeholders",
  "followup_sequence": [
    {{"day": 1, "type": "call", "notes": "Initial cold call"}},
    {{"day": 3, "type": "sms", "notes": "Check-in SMS if no answer"}},
    {{"day": 7, "type": "email", "notes": "Value-add email"}},
    {{"day": 14, "type": "call", "notes": "Second call attempt"}},
    {{"day": 21, "type": "email", "notes": "Special offer"}},
    {{"day": 30, "type": "sms", "notes": "Final check-in"}}
  ]
}}"""

    try:
        text = _call_claude([{"role": "user", "content": prompt}], max_tokens=2000, user=user)
        return _extract_json(text)
    except Exception:
        name = campaign.get('name', 'Campaign')
        focus = campaign.get('product_focus', 'natural health products')
        audience = campaign.get('target_audience', 'health-conscious individuals')
        return {
            "call_script_template": f"Hi [LEAD_NAME], this is {settings.AGENT_NAME} from {settings.COMPANY_NAME}. I'm reaching out because we help {audience} with {focus}. Do you have 60 seconds to hear how we can help you? Visit {settings.SHOP_URL} to learn more.",
            "sms_template": f"Hi [NAME], {settings.AGENT_NAME} from {settings.COMPANY_NAME} here! We have amazing {focus} that could help you. Reply YES to learn more or STOP to unsubscribe.",
            "email_subject": f"Discover {focus} — {settings.COMPANY_NAME}",
            "email_body": f"Hi [NAME],\n\nI hope this finds you well! I'm reaching out from {settings.COMPANY_NAME} because we specialize in {focus} for {audience}.\n\nI'd love to share how our products can support your health goals.\n\nVisit us at {settings.SHOP_URL}\n\nTo your health,\n{settings.AGENT_NAME}\n{settings.COMPANY_NAME}",
            "followup_sequence": [
                {"day": 1, "type": "call", "notes": "Initial cold call"},
                {"day": 3, "type": "sms", "notes": "Check-in SMS"},
                {"day": 7, "type": "email", "notes": "Value-add email"},
                {"day": 14, "type": "call", "notes": "Second call attempt"},
                {"day": 21, "type": "email", "notes": "Special offer"},
                {"day": 30, "type": "sms", "notes": "Final check-in"},
            ],
        }
