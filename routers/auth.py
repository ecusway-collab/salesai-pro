"""Auth endpoints — register, login, refresh, me, update credentials."""
import logging
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from database import get_db
from models import User
from core.auth import hash_password, verify_password, create_access_token, create_refresh_token, get_current_user
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    plan: Optional[str] = "starter"
    ref: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class CredentialsUpdate(BaseModel):
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    google_maps_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    yelp_api_key: Optional[str] = None
    company_name: Optional[str] = None
    agent_name: Optional[str] = None
    shop_url: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")

    if data.plan not in ("starter", "pro", "agency"):
        data.plan = "starter"

    ref_code = secrets.token_hex(4)  # 8-char unique referral code
    while db.query(User).filter(User.referral_code == ref_code).first():
        ref_code = secrets.token_hex(4)

    referred_by = None
    if data.ref:
        referrer = db.query(User).filter(User.referral_code == data.ref.strip()).first()
        if referrer:
            referred_by = data.ref.strip()

    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        plan=data.plan,
        status="trialing",
        trial_ends_at=datetime.utcnow() + timedelta(days=settings.TRIAL_DAYS),
        company_name=data.name + "'s Company",
        referral_code=ref_code,
        referred_by=referred_by,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return _token_response(user)


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return _user_dict(current_user)


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Send a password reset link to the user's email."""
    user = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        reset_url = f"{settings.BASE_URL}/reset-password?token={token}"
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail
            sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
            msg = Mail(
                from_email=(settings.FROM_EMAIL, settings.FROM_NAME),
                to_emails=user.email,
                subject="Reset your SalesAI Pro password",
                plain_text_content=(
                    f"Hi {user.name},\n\n"
                    f"Click the link below to reset your password. It expires in 1 hour.\n\n"
                    f"{reset_url}\n\n"
                    f"If you didn't request this, you can safely ignore this email.\n\n"
                    f"— The {settings.COMPANY_NAME} Team"
                ),
            )
            sg.send(msg)
        except Exception as e:
            logger.error(f"Reset email send failed: {e}")
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset password using a valid reset token."""
    user = db.query(User).filter(User.reset_token == data.token).first()
    if not user or not user.reset_token_expires:
        raise HTTPException(400, "Invalid or expired reset link.")
    if datetime.utcnow() > user.reset_token_expires:
        raise HTTPException(400, "This reset link has expired. Please request a new one.")
    if len(data.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    user.password_hash = hash_password(data.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return {"message": "Password reset successfully. You can now log in."}


@router.patch("/credentials")
def update_credentials(
    data: CredentialsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the user's API credentials and branding settings."""
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(current_user, field, value)
    current_user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Credentials updated", "user": _user_dict(current_user)}


@router.get("/referral")
def referral_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the user's referral code, link, and signup stats."""
    if not current_user.referral_code:
        code = secrets.token_hex(4)
        while db.query(User).filter(User.referral_code == code).first():
            code = secrets.token_hex(4)
        current_user.referral_code = code
        db.commit()

    referrals = db.query(User).filter(User.referred_by == current_user.referral_code).all()
    paid = [r for r in referrals if r.status == "active"]

    return {
        "referral_code": current_user.referral_code,
        "referral_link": f"{settings.BASE_URL}/login?ref={current_user.referral_code}#register",
        "total_signups": len(referrals),
        "paid_conversions": len(paid),
        "referrals": [
            {
                "name": r.name,
                "plan": r.plan,
                "status": r.status,
                "joined": str(r.created_at)[:10] if r.created_at else None,
            }
            for r in referrals
        ],
    }


@router.patch("/profile")
def update_profile(
    name: Optional[str] = None,
    company_name: Optional[str] = None,
    agent_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if name: current_user.name = name
    if company_name: current_user.company_name = company_name
    if agent_name: current_user.agent_name = agent_name
    db.commit()
    return {"message": "Profile updated"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id, user.email, user.plan),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": _user_dict(user),
    }


def _user_dict(user: User) -> dict:
    from datetime import date
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "plan": user.plan,
        "status": user.status,
        "is_active": user.is_active(),
        "trial_ends_at": str(user.trial_ends_at)[:10] if user.trial_ends_at else None,
        "company_name": user.company_name,
        "agent_name": user.agent_name,
        "shop_url": user.shop_url,
        "from_email": user.from_email,
        "from_name": user.from_name,
        "has_twilio": bool(user.twilio_account_sid),
        "has_anthropic": bool(user.anthropic_api_key),
        "has_sendgrid": bool(user.sendgrid_api_key),
        "has_google_maps": bool(user.google_maps_api_key),
        "has_elevenlabs": bool(user.elevenlabs_api_key),
        "has_yelp": bool(user.yelp_api_key),
        "referral_code": user.referral_code,
        "leads_limit": user.leads_limit(),
        "calls_limit": user.calls_limit(),
        "created_at": str(user.created_at)[:10] if user.created_at else None,
    }
