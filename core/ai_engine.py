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
    return f"""You are {settings.AGENT_NAME}, a warm, energetic, and persuasive AI sales assistant for {settings.COMPANY_NAME}.

COMPANY: {settings.COMPANY_NAME}
SHOP URL: {settings.SHOP_URL}
MISSION: Helping people discover premium natural health products that transform their energy, wellness, and vitality.

PRODUCT CATALOGUE (always recommend from this list):

── AWAKEN FAMILY (energy, focus, performance) ──
• V-NRGY ($55) — Natural energy booster. Sustained energy without crashes or jitters. Perfect for busy professionals, gym-goers, and anyone fighting fatigue.
• V-NITRO ($70) — Nitric oxide & circulation support. Boosts performance, endurance, and blood flow. Great for athletes and active people.
• V-NEUROKAFE ($70) — Nootropic coffee blend. Focus, mental clarity, and brain performance in every cup. Replace your morning coffee with this.
• V-LOVKAFE ($70) — Premium wellness coffee blend. Energy + mood + vitality in one delicious drink.

── DETOX FAMILY (cleansing, gut health) ──
• V-TEDETOX ($18) — Gentle detox tea. Daily cleansing, bloat relief, and gut support. Best entry-level product — great for first-time buyers.
• V-ORGANEX ($55) — Deep organ cleanse. Supports liver, kidneys, and gut detox. Ideal for anyone who wants a full-body reset.

── NOURISH FAMILY (daily nutrition, foundational health) ──
• VITALPRO ($84) — Complete meal replacement protein. Full nutrition in one shake — great for weight management and busy lifestyles.
• V-OMEGA 3 ($84) — Premium fish oil. Supports heart, brain, joints, and inflammation. Essential daily supplement.
• V-DAILY ($100) — Comprehensive daily multivitamin. Full-spectrum nutrients for overall health. The foundation of any wellness routine.
• V-GLUTATION PLUS ($100) — Glutathione + antioxidants. Anti-aging, immune boost, and skin brightening. Very popular with women.
• V-GLUTATION ($90) — Glutathione antioxidant. Fights free radicals, supports immunity and skin health.
• V-FORTYFLORA ($55) — Advanced probiotic blend. Gut health, digestion, and immunity from the inside out.
• VITALAGE COLLAGEN ($90) — Marine collagen peptides. Skin, hair, nails, and joint health. Best-seller for anti-aging.

── RESTORE FAMILY (recovery, pain, balance) ──
• V-ITAREN ($55) — Natural recovery and restoration support.
• V-ITALAY ($55) — Relaxation and sleep support blend.
• V-ITADOL ($55) — Natural pain and discomfort support.
• V-ASCULAX ($55) — Cardiovascular and circulation health.
• S-BALANCE ($55) — Hormonal balance and wellness support.

── KIDS COLLECTION ──
• SMARTBIOTICS KIDS — Probiotic support for children's gut and immunity.
• D-FENZ KIDS — Immune defense formula for kids.
• GENIUS SHAKE KIDS — Nutritious shake for growing children.

── SPECIALTY ──
• Vital Health Scanner ($149, normally $300) — Biometric wellness device. Scans and tracks key health metrics. Great upsell for serious health buyers.
• V-HARMONY — Hormonal harmony and balance support.
• V-PRIME — Premium vitality and performance formula.

PRODUCT MATCHING GUIDE (match to prospect's need):
• Low energy / fatigue → V-NRGY, V-NITRO, V-NEUROKAFE
• Weight management → VITALPRO, V-TEDETOX, V-ORGANEX
• Anti-aging / skin / beauty → VITALAGE COLLAGEN, V-GLUTATION PLUS
• Daily health / nutrition → V-DAILY, V-OMEGA 3, VITALPRO
• Athletes / active lifestyle → V-NRGY, V-NITRO, VITALPRO
• Detox / cleanse → V-TEDETOX ($18 — easy entry point!), V-ORGANEX
• Brain / focus → V-NEUROKAFE, V-DAILY
• Joint / pain → V-OMEGA 3, VITALAGE COLLAGEN, V-ITADOL
• Gut health → V-FORTYFLORA, V-TEDETOX
• Kids health → SMARTBIOTICS KIDS, D-FENZ KIDS, GENIUS SHAKE KIDS
• Sleep / relaxation → V-ITALAY

SALES STRATEGY:
1. HOOK FAST — grab attention in the first 10 seconds with a bold benefit or question
2. MATCH THE PRODUCT — always recommend a specific product by name based on what they say
3. MENTION THE PRICE — our products start at just $18 (V-TEDETOX). Make price feel accessible.
4. CREATE URGENCY — limited-time offers, bundles, and the affiliate income opportunity
5. AFFILIATE ANGLE — mention that customers can also EARN income by sharing products. This is a big hook.
6. DRIVE TO THE WEBSITE — always close with "visit {settings.SHOP_URL} to see everything"
7. FOLLOW UP — the system will follow up automatically; set that expectation

LEGAL: Always say "supports," "promotes," "helps" — never "treats," "cures," or "prevents disease."
TONE: Warm, excited, confident, and genuinely passionate about the products
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

def generate_cold_call_script(lead: dict, product_focus: str = None, user=None) -> dict:
    """
    Generate a full personalized cold call script for a lead.
    Returns: opening, discovery_questions, value_prop, objection_handlers,
             call_to_action, voicemail_script
    """
    prompt = f"""Generate a HIGH-ENERGY, PERSUASIVE cold call script for this lead. The goal is to create IMMEDIATE EXCITEMENT and URGENCY so they want to take action RIGHT NOW.

LEAD DETAILS:
- Name: {lead.get('name', 'there')}
- Company: {lead.get('company', 'not specified')}
- Health Interest: {lead.get('health_interest', 'general wellness')}
- Pain Points: {lead.get('pain_points', 'unknown')}
- Product Focus: {product_focus or 'health and wealth solutions'}

SCRIPT RULES:
1. OPENING: Start with their name, create INSTANT CURIOSITY with a bold statement or surprising fact. Do NOT just say "I'm calling to share products." Make them think "wait, what?" — hook them in the first 5 seconds.
2. URGENCY: Include a time-sensitive reason to act NOW (limited spots, special offer this week, product just launched, etc.)
3. SOCIAL PROOF: Mention that others like them are already getting results
4. BENEFIT-FIRST: Lead with what they GAIN, not what the product IS
5. EASY YES: The call-to-action must be low-commitment and easy to say yes to (visit the website, get a free info pack, quick 2-minute callback)
6. VOICEMAIL: Must be irresistible — they should WANT to call back or visit the site

Return a JSON object with these exact fields:
{{
  "opening": "20-30 second hook — bold, energetic, curiosity-driven. Use their name. End with an engaging question.",
  "discovery_questions": ["question 1", "question 2", "question 3"],
  "value_proposition": "Exciting 2-3 sentence pitch focused on transformation and results, not features",
  "objection_handlers": {{
    "too expensive": "reframe as investment + mention easy entry point",
    "not interested": "create curiosity — what if they're missing out on something huge?",
    "already have a supplier": "acknowledge + offer something they don't currently have",
    "send me info": "yes AND get a commitment for a quick follow-up call",
    "call back later": "lock in a specific time right now"
  }},
  "call_to_action": "Low-commitment next step — visit the website, get a free info pack, or book a 5-minute callback",
  "voicemail_script": "Irresistible 20-second voicemail — hint at something exciting they're missing, include the website URL"
}}"""

    try:
        text = _call_claude([{"role": "user", "content": prompt}], max_tokens=1500, user=user)
        return _extract_json(text)
    except Exception:
        name = lead.get('name', 'there')
        return {
            "opening": f"Hey {name}! This is {settings.AGENT_NAME} from {settings.COMPANY_NAME} — and I'll be honest, I only have about 60 seconds but I think what I have to share could genuinely change things for you. People in your area are already seeing incredible results with what we offer, and I didn't want you to miss out. Can I take just one minute?",
            "discovery_questions": ["What's the one health or wellness goal you haven't been able to crack yet?", "If you could change one thing about how you feel every day, what would it be?", "Have you ever explored products that actually give you more energy and help you earn at the same time?"],
            "value_proposition": f"Here's the exciting part — {settings.COMPANY_NAME} isn't just about feeling better, it's about building a lifestyle. Our clients are getting real results fast, and many are even turning it into extra income. This isn't something you want to sleep on.",
            "objection_handlers": {
                "too expensive": "I completely get that — and that's exactly why we have a starter option that costs less than a cup of coffee a day. The real question is, can you afford NOT to feel your best?",
                "not interested": "Fair enough! But can I ask — what if I told you that people who said the same thing are now our biggest success stories? Just take 30 seconds to check out the website and decide for yourself.",
                "already have a supplier": "That's great — but what if what we have fills a gap your current supplier doesn't? Most of our clients said the same thing before they tried us.",
                "send me info": "Absolutely — and I'll send it right now. But let's also lock in a quick 5-minute call this week so I can answer your questions personally. What day works better for you, Tuesday or Thursday?",
                "call back later": "Of course! I respect your time. Let's make it official — does tomorrow morning or afternoon work better for you?"
            },
            "call_to_action": f"Here's what I want you to do right now — just visit {settings.SHOP_URL} and take a look. Takes 2 minutes. And I'll personally follow up with you to make sure you get the best deal available.",
            "voicemail_script": f"Hey {name}, it's {settings.AGENT_NAME} from {settings.COMPANY_NAME}. I was going to share something pretty exciting with you — something people in your area are already taking advantage of. I don't want you to miss the window on this. Check us out at {settings.SHOP_URL} — and I'll follow up soon. Talk soon!",
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
