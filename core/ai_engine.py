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
    return f"""You are {settings.AGENT_NAME}, a warm, energetic, and persuasive AI sales assistant representing TWO powerful health and wellness brands: Vital Health Global AND Ignty.

═══════════════════════════════════════════════
🔥 IGNTY — PRELAUNCH (FREE SIGNUP BEFORE JULY 4TH) — LEAD WITH THIS
═══════════════════════════════════════════════
IGNTY is a brand-new health and wellness company launching July 4th — the "Freedom Run."
RIGHT NOW it is FREE to sign up as a brand partner. After July 4th, it becomes a paid opportunity.
This is the #1 urgency play — every call should mention Ignty prelaunch.

IGNTY PRODUCTS:
• Ignyt Metabolic Booster — Energy and metabolism support. Natural formula designed to fire up your body's fat-burning and energy systems.
• BMore — A complete daily execution framework combining focus tools, movement, gratitude practice, breathwork, and brainwave audio. Not just a supplement — a daily success system.

IGNTY INCOME OPPORTUNITY:
• 50% INSTANT PAYOUT on every customer sale — one of the highest payouts in the industry
• $10K BMore Guarantee (with qualifications)
• Free to join NOW — positions fill before launch day

IGNTY SIGNUP URL: https://www.ignyt750.com/healme
TAGLINE: "Everything stacked in your favor"

IGNTY PITCH ANGLES:
→ "Right now you can secure your spot completely free — that changes on July 4th"
→ "This is a once-in-a-year prelaunch window — most people pay to get in after launch"
→ "50% payout means if you just refer 2 people, you've already made money"
→ "The Ignyt Metabolic Booster is designed to fire up your energy AND metabolism at the same time"

═══════════════════════════════════════════════
VITAL HEALTH GLOBAL — IMMEDIATE PURCHASE PRODUCTS
═══════════════════════════════════════════════
COMPANY: {settings.COMPANY_NAME}
SHOP URL: {settings.SHOP_URL}

── AWAKEN FAMILY (energy, focus, performance) ──
• V-NRGY ($55) — Natural energy booster. Sustained energy without crashes. Perfect for busy professionals and gym-goers.
• V-NITRO ($70) — Nitric oxide & circulation support. Boosts performance, endurance, blood flow.
• V-NEUROKAFE ($70) — Nootropic coffee blend. Focus, mental clarity, brain performance in every cup.
• V-LOVKAFE ($70) — Premium wellness coffee. Energy + mood + vitality in one drink.

── DETOX FAMILY (cleansing, gut health) ──
• V-TEDETOX ($18) — Gentle detox tea. Best entry-level product — easy first purchase.
• V-ORGANEX ($55) — Deep organ cleanse. Liver, kidneys, and gut detox.

── NOURISH FAMILY (daily nutrition) ──
• VITALPRO ($84) — Complete meal replacement protein. Weight management + busy lifestyles.
• V-OMEGA 3 ($84) — Premium fish oil. Heart, brain, joints, inflammation.
• V-DAILY ($100) — Comprehensive daily multivitamin. Full-spectrum nutrients.
• V-GLUTATION PLUS ($100) — Glutathione + antioxidants. Anti-aging, immune boost, skin brightening.
• V-GLUTATION ($90) — Glutathione antioxidant. Free radicals, immunity, skin health.
• V-FORTYFLORA ($55) — Advanced probiotic. Gut health, digestion, immunity.
• VITALAGE COLLAGEN ($90) — Marine collagen. Skin, hair, nails, joints. Best-seller for anti-aging.

── RESTORE FAMILY (recovery, balance) ──
• V-ITAREN ($55) — Natural recovery support.
• V-ITALAY ($55) — Relaxation and sleep support.
• V-ITADOL ($55) — Natural pain and discomfort support.
• V-ASCULAX ($55) — Cardiovascular and circulation health.
• S-BALANCE ($55) — Hormonal balance and wellness.

── KIDS COLLECTION ──
• SMARTBIOTICS KIDS — Probiotic for children's gut and immunity.
• D-FENZ KIDS — Immune defense for kids.
• GENIUS SHAKE KIDS — Nutritious shake for growing children.

── SPECIALTY ──
• Vital Health Scanner ($149, normally $300) — Biometric wellness device. Great upsell.
• V-HARMONY — Hormonal harmony support.
• V-PRIME — Premium vitality and performance formula.

PRODUCT MATCHING GUIDE:
• Low energy / fatigue → Ignyt Metabolic Booster (Ignty), V-NRGY, V-NEUROKAFE
• Weight management → Ignyt Metabolic Booster, VITALPRO, V-TEDETOX
• Anti-aging / skin → VITALAGE COLLAGEN, V-GLUTATION PLUS
• Daily health → V-DAILY, V-OMEGA 3, VITALPRO
• Athletes / active → V-NRGY, V-NITRO, VITALPRO
• Detox / cleanse → V-TEDETOX ($18 entry point), V-ORGANEX
• Brain / focus → BMore (Ignty), V-NEUROKAFE, V-DAILY
• Joint / pain → V-OMEGA 3, VITALAGE COLLAGEN, V-ITADOL
• Income opportunity → Ignty prelaunch (FREE until July 4th), VHG affiliate program
• Gut health → V-FORTYFLORA, V-TEDETOX
• Kids → SMARTBIOTICS KIDS, D-FENZ KIDS, GENIUS SHAKE KIDS
• Sleep → V-ITALAY, BMore (breathwork + sleep tools)

SALES STRATEGY:
1. IGNTY FIRST — open with the free prelaunch opportunity. "Before I tell you about our products, there's a free window closing July 4th you need to know about."
2. HOOK FAST — grab attention in the first 10 seconds with a bold benefit
3. MATCH THE PRODUCT — recommend a specific product by name from either brand
4. PRICE ANCHOR — VHG starts at $18 (V-TEDETOX). Ignty signup is FREE right now.
5. DUAL URGENCY — Ignty prelaunch closes July 4th + limited-time VHG offers
6. INCOME ANGLE — Ignty pays 50% instantly. VHG also has affiliate income. Most people can earn back their investment in the first week.
7. DRIVE TO BOTH URLS — Ignty: https://www.ignyt750.com/healme | VHG: {settings.SHOP_URL}
8. FOLLOW UP — the system will follow up automatically; set that expectation

LEGAL: Always say "supports," "promotes," "helps" — never "treats," "cures," or "prevents disease."
TONE: Warm, excited, confident, and genuinely passionate about both brands
NEVER: Make medical diagnoses, use fear tactics, or make claims you cannot back up"""


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

def generate_cold_call_script(lead: dict, product_focus: str = None, shop_url: str = None, user=None) -> dict:
    """
    Generate a full personalized cold call script for a lead.
    Returns: opening, discovery_questions, value_prop, objection_handlers,
             call_to_action, voicemail_script
    """
    effective_url = shop_url or (user.shop_url if user and user.shop_url else None) or settings.SHOP_URL
    company = (user.company_name if user and user.company_name else None) or settings.COMPANY_NAME
    agent = (user.agent_name if user and user.agent_name else None) or settings.AGENT_NAME

    prompt = f"""Generate a HIGH-ENERGY, CONVERSATIONAL cold call script. This will be spoken by an AI voice — every word must sound natural when heard out loud.

LEAD DETAILS:
- Name: {lead.get('name', 'there')}
- Company: {lead.get('company', 'not specified')}
- Health Interest: {lead.get('health_interest', 'general wellness')}
- Pain Points: {lead.get('pain_points', 'unknown')}
- Product Focus: {product_focus or 'health and energy solutions'}

COMPANY: {company}
AGENT NAME: {agent}
WEBSITE: {effective_url}

CRITICAL SCRIPT RULES — follow every single one:

OPENING (this is what gets spoken first — make or break):
- Start with "Hey [NAME]!" — warm, upbeat, like you know them
- NEVER say "I hope I'm not catching you at a bad time" — it's an instant hangup
- NEVER say "do you have 60 seconds" — just deliver the value immediately
- Drop a SPECIFIC benefit in the first sentence: energy, metabolism, weight, income
- Name a SPECIFIC product if possible based on their health interest
- Tell them you will TEXT THE LINK right now — creates a reason to say yes
- End with ONE easy yes/no question: "Does that sound like something worth 2 minutes?"
- Speak like a REAL PERSON, not a telemarketer — contractions, natural rhythm
- Keep it under 25 seconds when spoken aloud

VOICEMAIL (spoken if they don't answer):
- MUST include the website URL spoken letter by letter if unusual, or naturally if simple
- Create curiosity they cannot ignore — hint at the benefit without giving it all away
- Include: "Check us out at {effective_url}"
- Under 20 seconds
- End with your name and company

Return a JSON object with these exact fields:
{{
  "opening": "The spoken opening — warm, specific, benefit-first. Mention the product and that you'll text the link. End with one yes/no question. No press-1/press-2 instructions. Sound like a real person.",
  "discovery_questions": ["question 1", "question 2", "question 3"],
  "value_proposition": "Exciting 2-3 sentence pitch focused on transformation and results",
  "objection_handlers": {{
    "too expensive": "reframe around daily cost + mention entry-level option",
    "not interested": "create curiosity — hint at what they might be missing",
    "already have a supplier": "acknowledge + offer what their current supplier doesn't have",
    "send me info": "yes AND lock in a quick follow-up call",
    "call back later": "lock in a specific time right now"
  }},
  "call_to_action": "Send them to {effective_url} — mention it feels like browsing not buying",
  "voicemail_script": "20-second voicemail that hints at the benefit and includes the website {effective_url}"
}}"""

    try:
        text = _call_claude([{"role": "user", "content": prompt}], max_tokens=1500, user=user)
        return _extract_json(text)
    except Exception:
        name = lead.get('name', 'there')
        interest = lead.get('health_interest', 'energy and wellness')
        return {
            "opening": f"Hey {name}! It's {agent} from {company}. Real quick — there's a free wellness opportunity that closes July 4th and I think you need to hear about it before it's gone. It takes 30 seconds and there's literally no cost to get in right now. Does that sound worth hearing?",
            "discovery_questions": [
                "If you could fix one thing about your energy or health right now, what would it be?",
                "Have you tried supplements before — what worked or didn't work for you?",
                "Are you open to something that not only helps your health but could also earn you extra income?"
            ],
            "value_proposition": f"What we offer at {company} isn't just another supplement — it's a complete system for better energy, faster metabolism, and a sharper mind. Real people are seeing real results, and the income opportunity on top of that is what makes this different from everything else out there.",
            "objection_handlers": {
                "too expensive": "I hear you — and honestly our entry-level product starts at under twenty dollars. That's less than a coffee a day. The question is whether feeling great every single day is worth that.",
                "not interested": "That's totally fair! But can I ask — is energy or weight something you've been struggling with? Because the people who say that usually haven't seen what we actually have. Two minutes at our website — that's all I'm asking.",
                "already have a supplier": "Respect that! Most of our best customers said the same thing. What we have fills gaps that most suppliers don't touch — especially on the energy and metabolism side. Worth a two-minute look.",
                "send me info": "Done — I'm texting you the link right now. And let's lock in a quick five-minute call so I can answer any questions personally. Does Tuesday or Thursday work better for you?",
                "call back later": "Absolutely — I respect your time. Quick question though — does tomorrow morning or afternoon work better for you? I want to make sure I actually reach you."
            },
            "call_to_action": f"Just go to {effective_url} — it feels like browsing, not buying. Take two minutes, see what catches your eye, and I'll personally follow up to make sure you get the best deal available.",
            "voicemail_script": f"Hey {name}, it's {agent} from {company}. I was calling because we just launched something for energy and metabolism that I genuinely think would change things for you. Check us out at {effective_url} — takes two minutes. I'll follow up soon. Have an amazing day!",
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
  "body": "Full email body. Use \\n for line breaks. Sign off as {settings.AGENT_NAME} from {settings.COMPANY_NAME}. Include one clear call-to-action pointing them to {settings.SHOP_URL} to learn more. Do NOT ask them to reply to the email. Mention that we will follow up with them soon."
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
                f"Visit our website to explore everything we have available:\n{settings.SHOP_URL}\n\n"
                f"We'll be following up with you soon. Stay tuned!\n\n"
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
    company_name = campaign.get('company_brand') or (user.company_name if user else None) or settings.COMPANY_NAME
    agent_name = (user.agent_name if user else None) or settings.AGENT_NAME
    shop_url = campaign.get('shop_url_override') or (user.shop_url if user else None) or settings.SHOP_URL

    prompt = f"""Create complete sales templates for this campaign. Use the exact company name and URL below — do NOT substitute them with any other brand.

Company/Brand: {company_name}
Agent Name: {agent_name}
Shop/Product URL: {shop_url}
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
        focus = campaign.get('product_focus', 'natural health products')
        audience = campaign.get('target_audience', 'health-conscious individuals')
        return {
            "call_script_template": f"Hi [LEAD_NAME], this is {agent_name} from {company_name}. I'm reaching out because we help {audience} with {focus}. Do you have 60 seconds to hear how we can help you? Visit {shop_url} to learn more.",
            "sms_template": f"Hi [NAME], {agent_name} from {company_name} here! We have amazing {focus} that could help you. Reply YES to learn more or STOP to unsubscribe.",
            "email_subject": f"Discover {focus} — {company_name}",
            "email_body": f"Hi [NAME],\n\nI hope this finds you well! I'm reaching out from {company_name} because we specialize in {focus} for {audience}.\n\nI'd love to share how our products can support your health goals.\n\nVisit us at {shop_url}\n\nTo your health,\n{agent_name}\n{company_name}",
            "followup_sequence": [
                {"day": 1, "type": "call", "notes": "Initial cold call"},
                {"day": 3, "type": "sms", "notes": "Check-in SMS"},
                {"day": 7, "type": "email", "notes": "Value-add email"},
                {"day": 14, "type": "call", "notes": "Second call attempt"},
                {"day": 21, "type": "email", "notes": "Special offer"},
                {"day": 30, "type": "sms", "notes": "Final check-in"},
            ],
        }
