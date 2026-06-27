"""Lead scraper — scoped to current user. Dashboard stats also here."""
from datetime import datetime, date
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import Lead, ScraperJob, Interaction, FollowUp
from schemas import ScrapeRequest, ScraperJobOut
from core.auth import get_active_user, check_lead_limit
from scraper.google_maps import scrape_google_maps, SUGGESTED_QUERIES
from scraper.yellow_pages import scrape_yellow_pages
from core.scheduler import schedule_followup_sequence

router = APIRouter(prefix="/scraper", tags=["scraper"])


@router.get("/suggested-queries")
def get_suggested_queries():
    return {"queries": SUGGESTED_QUERIES}


@router.post("/start", status_code=202)
def start_scrape(
    data: ScrapeRequest,
    background: BackgroundTasks,
    current_user=Depends(check_lead_limit),
    db: Session = Depends(get_db),
):
    job = ScraperJob(source=data.source, query=data.query, location=data.location, status="running", user_id=current_user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(_run_scrape_job, job_id=job.id, user_id=current_user.id, source=data.source, query=data.query, location=data.location, max_results=data.max_results, campaign_id=data.campaign_id)
    return {"job_id": job.id, "message": "Scrape started in background"}


@router.get("/jobs", response_model=List[ScraperJobOut])
def list_jobs(current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    return db.query(ScraperJob).filter(ScraperJob.user_id == current_user.id).order_by(ScraperJob.created_at.desc()).limit(50).all()


@router.get("/jobs/{job_id}", response_model=ScraperJobOut)
def get_job(job_id: int, current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    job = db.query(ScraperJob).filter(ScraperJob.id == job_id, ScraperJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/dashboard-stats")
def dashboard_stats(current_user=Depends(get_active_user), db: Session = Depends(get_db)):
    today = date.today()
    total = db.query(Lead).filter(Lead.user_id == current_user.id).count()
    by_status = {}
    for lead in db.query(Lead).filter(Lead.user_id == current_user.id).all():
        by_status[lead.status] = by_status.get(lead.status, 0) + 1

    calls_today = db.query(Interaction).join(Lead).filter(
        Lead.user_id == current_user.id, Interaction.type == "call",
        Interaction.created_at >= str(today)).count()
    sms_today = db.query(Interaction).join(Lead).filter(
        Lead.user_id == current_user.id, Interaction.type == "sms",
        Interaction.created_at >= str(today)).count()
    emails_today = db.query(Interaction).join(Lead).filter(
        Lead.user_id == current_user.id, Interaction.type == "email",
        Interaction.created_at >= str(today)).count()
    pending_followups = db.query(FollowUp).join(Lead).filter(
        Lead.user_id == current_user.id, FollowUp.status == "pending").count()

    won = by_status.get("won", 0)
    return {
        "total_leads": total,
        "leads_limit": current_user.leads_limit(),
        "by_status": by_status,
        "calls_today": calls_today,
        "sms_today": sms_today,
        "emails_today": emails_today,
        "pending_followups": pending_followups,
        "conversion_rate": round(won / max(total, 1) * 100, 1),
        "plan": current_user.plan,
        "status": current_user.status,
    }


def _score_lead(ld: dict) -> float:
    score = 0
    if ld.get("phone"):          score += 25
    if ld.get("email"):          score += 20
    if ld.get("address"):        score += 15
    if ld.get("health_interest"): score += 15
    if ld.get("company"):        score += 10
    if ld.get("notes") and "Website:" in ld.get("notes", "") and "N/A" not in ld.get("notes", ""):
        score += 10
    source_bonus = {"google_maps": 5, "yellow_pages": 3}.get(ld.get("source", ""), 0)
    return min(float(score + source_bonus), 100.0)


def _run_scrape_job(job_id: int, user_id: int, source: str, query: str, location: str, max_results: int, campaign_id):
    from database import SessionLocal
    from models import User
    db = SessionLocal()
    try:
        try:
            raw_leads = scrape_google_maps(query, location, max_results) if source == "google_maps" else scrape_yellow_pages(query, location, max_results)
        except RuntimeError as api_err:
            if "GOOGLE_API_DISABLED" in str(api_err):
                job = db.query(ScraperJob).filter(ScraperJob.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.leads_found = 0
                    job.leads_imported = 0
                    job.error_message = (
                        "Google Maps API not enabled on your project. "
                        "Go to console.cloud.google.com → APIs & Services → Enable APIs → "
                        "search 'Places API (New)' → Enable it. Then re-run the search."
                    )
                    job.completed_at = datetime.now()
                    db.commit()
                db.close()
                return
            raise
        job = db.query(ScraperJob).filter(ScraperJob.id == job_id).first()

        # Only count leads that have a phone number — no point importing ones you can't call
        callable_leads = [ld for ld in raw_leads if ld.get("phone")]
        job.leads_found = len(callable_leads)

        # Check how many slots remain on this user's plan
        user = db.query(User).filter(User.id == user_id).first()
        plan_limit = user.leads_limit() if user else -1

        imported = 0
        limit_hit = False
        for ld in callable_leads:
            # Stop importing if plan limit is reached
            if plan_limit != -1:
                current_count = db.query(Lead).filter(Lead.user_id == user_id).count()
                if current_count >= plan_limit:
                    limit_hit = True
                    break

            # Skip duplicates (match by phone first, then company name)
            existing = db.query(Lead).filter(Lead.phone == ld["phone"], Lead.user_id == user_id).first()
            if not existing and ld.get("company"):
                existing = db.query(Lead).filter(Lead.company == ld["company"], Lead.user_id == user_id).first()
            if existing:
                continue

            lead = Lead(**{k: v for k, v in ld.items() if hasattr(Lead, k) and k != "id"}, user_id=user_id, campaign_id=campaign_id, score=_score_lead(ld))
            db.add(lead)
            db.flush()
            schedule_followup_sequence(lead.id)
            imported += 1

        job.leads_imported = imported
        job.status = "completed"
        if limit_hit:
            job.error_message = f"Plan limit reached — upgrade for more leads"
        job.completed_at = datetime.now()
        db.commit()
    except Exception as e:
        db = SessionLocal()
        job = db.query(ScraperJob).filter(ScraperJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now()
            db.commit()
        db.close()
