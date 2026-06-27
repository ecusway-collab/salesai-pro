from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# ── Plan limits ───────────────────────────────────────────────────────────────
PLAN_LIMITS = {
    "starter": {"leads": 100,  "calls_per_month": 50},
    "pro":     {"leads": 500,  "calls_per_month": 250},
    "agency":  {"leads": -1,   "calls_per_month": -1},   # -1 = unlimited
}

PLAN_PRICES = {
    "starter": 49,
    "pro":     99,
    "agency":  199,
}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)

    # Subscription
    plan = Column(String(20), default="starter")        # starter | pro | agency
    status = Column(String(20), default="trialing")     # trialing | active | cancelled | past_due
    trial_ends_at = Column(DateTime)
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))

    # User's own API credentials (they bring their own)
    twilio_account_sid = Column(String(100))
    twilio_auth_token = Column(String(200))
    twilio_phone_number = Column(String(30))
    anthropic_api_key = Column(String(300))
    sendgrid_api_key = Column(String(300))
    google_maps_api_key = Column(String(300))

    # Branding / customization
    company_name = Column(String(200), default="My Company")
    agent_name = Column(String(100), default="Alex")
    shop_url = Column(String(500))
    from_email = Column(String(200))
    from_name = Column(String(200))
    elevenlabs_api_key = Column(String(300))
    yelp_api_key = Column(String(300))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    leads = relationship("Lead", back_populates="user", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")

    def is_active(self) -> bool:
        from datetime import datetime
        if self.status in ("active",):
            return True
        if self.status == "trialing" and self.trial_ends_at:
            return datetime.utcnow() < self.trial_ends_at
        return False

    def leads_limit(self) -> int:
        return PLAN_LIMITS.get(self.plan, PLAN_LIMITS["starter"])["leads"]

    def calls_limit(self) -> int:
        return PLAN_LIMITS.get(self.plan, PLAN_LIMITS["starter"])["calls_per_month"]


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(30))
    email = Column(String(200))
    company = Column(String(200))
    address = Column(String(500))
    source = Column(String(100), default="manual")
    status = Column(String(50), default="new")
    score = Column(Float, default=0.0)
    health_interest = Column(String(500))
    pain_points = Column(Text)
    notes = Column(Text)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    do_not_contact = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="leads")
    interactions = relationship("Interaction", back_populates="lead", cascade="all, delete-orphan")
    follow_ups = relationship("FollowUp", back_populates="lead", cascade="all, delete-orphan")
    campaign = relationship("Campaign", back_populates="leads")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    company_brand = Column(String(200), nullable=True)    # e.g. "Ignyt" — overrides user's company name for this campaign
    shop_url_override = Column(String(500), nullable=True) # e.g. "https://ignyt.biz/healme"
    product_focus = Column(String(500))
    target_audience = Column(String(500))
    goal = Column(String(500))
    status = Column(String(50), default="active")
    call_script_template = Column(Text)
    sms_template = Column(Text)
    email_template = Column(Text)
    followup_sequence = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="campaigns")
    leads = relationship("Lead", back_populates="campaign")


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    type = Column(String(20))
    direction = Column(String(10), default="outbound")
    content = Column(Text)
    outcome = Column(String(100))
    duration_seconds = Column(Integer)
    call_sid = Column(String(100))
    recording_url = Column(String(500))
    ai_analysis = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    lead = relationship("Lead", back_populates="interactions")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    type = Column(String(20))
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending")
    message = Column(Text)
    executed_at = Column(DateTime)
    error_message = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())

    lead = relationship("Lead", back_populates="follow_ups")


class ScraperJob(Base):
    __tablename__ = "scraper_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    source = Column(String(50))
    query = Column(String(200))
    location = Column(String(200))
    status = Column(String(30), default="running")
    leads_found = Column(Integer, default=0)
    leads_imported = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)
