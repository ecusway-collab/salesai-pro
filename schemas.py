from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Lead ──────────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    source: Optional[str] = "manual"
    health_interest: Optional[str] = None
    pain_points: Optional[str] = None
    notes: Optional[str] = None
    campaign_id: Optional[int] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    health_interest: Optional[str] = None
    pain_points: Optional[str] = None
    notes: Optional[str] = None
    score: Optional[float] = None
    campaign_id: Optional[int] = None
    do_not_contact: Optional[bool] = None


class LeadOut(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    company: Optional[str]
    address: Optional[str]
    source: Optional[str]
    status: str
    score: float
    health_interest: Optional[str]
    pain_points: Optional[str]
    notes: Optional[str]
    campaign_id: Optional[int]
    do_not_contact: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Campaign ──────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str
    company_brand: Optional[str] = None
    shop_url_override: Optional[str] = None
    product_focus: Optional[str] = None
    target_audience: Optional[str] = None
    goal: Optional[str] = None
    followup_sequence: Optional[str] = None  # JSON string


class CampaignOut(BaseModel):
    id: int
    name: str
    company_brand: Optional[str]
    shop_url_override: Optional[str]
    product_focus: Optional[str]
    target_audience: Optional[str]
    goal: Optional[str]
    status: str
    call_script_template: Optional[str]
    sms_template: Optional[str]
    email_template: Optional[str]
    followup_sequence: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Interaction ───────────────────────────────────────────────────────────────

class InteractionOut(BaseModel):
    id: int
    lead_id: int
    type: str
    direction: str
    content: Optional[str]
    outcome: Optional[str]
    duration_seconds: Optional[int]
    recording_url: Optional[str]
    ai_analysis: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Follow-up ─────────────────────────────────────────────────────────────────

class FollowUpOut(BaseModel):
    id: int
    lead_id: int
    type: str
    scheduled_at: datetime
    status: str
    message: Optional[str]
    executed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Scraper ───────────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    source: str          # google_maps, yellow_pages
    query: str           # e.g. "health food stores"
    location: str        # e.g. "Houston, TX"
    max_results: Optional[int] = 50
    campaign_id: Optional[int] = None


class ScraperJobOut(BaseModel):
    id: int
    source: str
    query: str
    location: str
    status: str
    leads_found: int
    leads_imported: int
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_leads: int
    new_leads: int
    contacted: int
    interested: int
    qualified: int
    won: int
    lost: int
    calls_today: int
    sms_today: int
    emails_today: int
    pending_followups: int
    conversion_rate: float
