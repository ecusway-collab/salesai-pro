"""SalesAI Pro — Multi-tenant SaaS entry point."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config import settings
from database import init_db
from core.scheduler import start_scheduler, stop_scheduler
from routers import leads, campaigns, calls, webhooks, scraper
from routers import auth, billing, schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SalesAI Pro...")
    init_db()
    start_scheduler()
    logger.info("Ready. Open http://localhost:8000")
    yield
    stop_scheduler()


app = FastAPI(
    title="SalesAI Pro",
    description="AI-powered sales automation SaaS for natural health products",
    version="2.0.0",
    lifespan=lifespan,
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(leads.router)
app.include_router(campaigns.router)
app.include_router(calls.router)
app.include_router(webhooks.router)
app.include_router(scraper.router)
app.include_router(schedule.router)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def landing():
    return FileResponse("static/landing.html")


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse("static/login.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse("static/index.html")


@app.get("/reset-password", include_in_schema=False)
def reset_password_page():
    return FileResponse("static/reset-password.html")


@app.get("/privacy", include_in_schema=False)
def privacy_page():
    return FileResponse("static/privacy.html")


@app.get("/terms", include_in_schema=False)
def terms_page():
    return FileResponse("static/terms.html")


@app.get("/refund", include_in_schema=False)
def refund_page():
    return FileResponse("static/refund.html")


@app.get("/billing/success", include_in_schema=False)
def billing_success():
    return FileResponse("static/index.html")


@app.get("/pricing", include_in_schema=False)
def pricing():
    return FileResponse("static/landing.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "SalesAI Pro", "version": "2.0.0"}


@app.get("/unsubscribe/{lead_id}", include_in_schema=False)
def unsubscribe(lead_id: int):
    from database import SessionLocal
    from models import Lead
    from fastapi.responses import HTMLResponse
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.do_not_contact = True
            lead.status = "lost"
            db.commit()
            name = lead.name
        else:
            name = "there"
    finally:
        db.close()
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Unsubscribed</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-light d-flex align-items-center justify-content-center" style="min-height:100vh">
    <div class="text-center p-5">
    <h2 class="text-success">&#10003; Unsubscribed</h2>
    <p class="text-muted">Hi {name}, you have been removed from our mailing list.<br>
    You will no longer receive emails or calls from {settings.COMPANY_NAME}.</p>
    <a href="/" class="btn btn-outline-secondary mt-3">Go to Homepage</a>
    </div></body></html>""")
