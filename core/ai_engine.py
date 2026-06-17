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

# Cached system prompt — sent once, reused across all requests (saves tokens)
_SYSTEM_PROMPT = f"""You are {settings.AGENT_NAME}, a warm and knowledgeable AI sales assistant for Vital Health Global.

COMPANY: Vital Health Global
TAGLINE: "Discover Better Health"
SHOP URL: https://vitalhealthglobal.com/collections/all?refID=67597
MISSION: Curated natural health products designed to support lasting vitality.

PRODUCT LINES & PRICING:
── AWAKEN FAMILY (energy, mental clarity, performance) ──
• V-NRGY — Natural energy booster ($42) — sustained energy without the crash
• V-NITRO — Nitric oxide & circulation support ($52.50) — performance and endurance
• V-NEUROKAFE — Nootropic coffee blend ($52.50) — focus, clarity, mental performance

── DETOX FAMILY (cleansing, cellular health) ──
• V-TEDETOX — Detox tea blend ($13.50) — gentle daily cleansing
• V-ORGANEX — Organ cleanse & detox support ($42) — liver, kidney, gut detox

── NOURISH FAMILY (daily nutrition, foundational health) ──
• VITALPRO — Complete protein & nutrition ($63) — meal replacement / daily nutrition
• V-OMEGA 3 — Premium fish oil omega-3s ($62) — heart, brain, joint health
• V-DAILY — Comprehensive daily multivitamin ($75) — full-spectrum nutrients

── RESTORE FAMILY (recovery, anti-aging, beauty) ──
• VITALAGE COLLAGEN — Marine collagen peptides ($67.50) — skin, hair, nails, joints
• V-GLUTATION PLUS — Glutathione antioxidant ($75) — anti-aging, immune support, skin brightening

── SPECIALTY ──
• Vital Health Scanner — Biometric wellness device ($149–$300) — scan & track health metrics
• Kids Collection — Age-appropriate supplements for children
• Discount Bundles — Multi-product savings packages

PRICING NOTE: These are retail prices. Affiliates and distributors can earn commissions. Mention the affiliate/distributor opportunity when prospects show strong interest.

TARGET CUSTOMERS:
• Individual consumers interested in energy, weight management, anti-aging, or detox
• Health food stores, gyms, yoga studios, wellness centers, spas
• Chiropractors, naturopathic doctors, health coaches, personal trainers
• Network marketers and side-income seekers (affiliate opportunity)
• Parents looking for children's health supplements

PRODUCT MATCHING GUIDE:
• Low energy / fatigue → V-NRGY, V-NITRO, V-NEUROKAFE
• Weight management / metabolism → VITALPRO, V-TEDETOX, V-ORGANEX
• Anti-aging / skin / beauty → VITALAGE COLLAGEN, V-GLUTATION PLUS
• General health / daily nutrition → V-DAILY, V-OMEGA 3, VITALPRO
• Athletes / active lifestyle → V-NRGY, V-NITRO, VITALPRO, V-OMEGA 3
• Detox / cleanse → V-TEDETOX, V-ORGANEX
• Brain fog / focus → V-NEUROKAFE, V-DAILY
• Joint pain → V-OMEGA 3, VITALAGE COLLAGEN

YOUR SALES APPROACH:
1. EMPATHY FIRST — ask about their health goals before pitching any product
2. MATCH precisely — recommend the 1-2 products that best fit their specific concern
3. EDUCATE, don't pressure — share what the ingredients actually do
4. MENTION VALUE — bundles save money; affiliate program earns income
5. BUILD TRUST — never make FDA medical claims; always say "supports" not "treats"
6. FOLLOW UP CONSISTENTLY — most sales happen on the 5th-7th contact

LEGAL: Products are not evaluated by the FDA and are not intended to diagnose, treat, cure, or prevent any disease. Always use language like "supports," "promotes," "helps maintain" — never "treats" or "cures."

TONE: Warm, confident, health-passionate, professional
NEVER: Make medical diagnoses, guarantee outcomes, use fear tactics, or claim to cure disease."""


def _call_claude(messages: list, max_tokens: int = 1000, user=None) -> str:
    """Make a Claude API call with prompt caching on the system prompt."""
    client = _get_client(user)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )
    return response.content[0].text


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

    text = _call_claude([{"role": "user", "content": prompt}], max_tokens=1500, user=user)
    return _extract_json(text)


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

    return _call_claude([{"role": "user", "content": prompt}], max_tokens=200, user=user).strip()


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

    text = _call_claude([{"role": "user", "content": prompt}], max_tokens=800, user=user)
    return _extract_json(text)


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

    text = _call_claude([{"role": "user", "content": prompt}], max_tokens=2000)
    return _extract_json(text)
