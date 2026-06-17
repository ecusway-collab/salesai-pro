"""Auth endpoints — register, login, refresh, me, update credentials."""
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

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    plan: Optional[str] = "starter"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class CredentialsUpdate(BaseModel):
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    google_maps_api_key: Optional[str] = None
    company_name: Optional[str] = None
    agent_name: Optional[str] = None
    shop_url: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")

    if data.plan not in ("starter", "pro", "agency"):
        data.plan = "starter"

    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        plan=data.plan,
        status="trialing",
        trial_ends_at=datetime.utcnow() + timedelta(days=settings.TRIAL_DAYS),
        company_name=data.name + "'s Company",
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
        "has_twilio": bool(user.twilio_account_sid),
        "has_anthropic": bool(user.anthropic_api_key),
        "has_sendgrid": bool(user.sendgrid_api_key),
        "has_google_maps": bool(user.google_maps_api_key),
        "leads_limit": user.leads_limit(),
        "calls_limit": user.calls_limit(),
        "created_at": str(user.created_at)[:10] if user.created_at else None,
    }
