"""JWT authentication + password hashing + current_user dependency."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session
from database import get_db
from config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT tokens ────────────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str, plan: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "plan": plan, "exp": expire},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=7)
    return jwt.encode(
        {"sub": str(user_id), "type": "refresh", "exp": expire},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


# ── Dependencies ──────────────────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """FastAPI dependency — returns the authenticated User or raises 401."""
    from models import User
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exc
    return user


def get_active_user(user=Depends(get_current_user)):
    """Like get_current_user but also checks subscription is active."""
    if not user.is_active():
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription expired or inactive. Please upgrade your plan.",
        )
    return user


def check_lead_limit(user=Depends(get_active_user), db: Session = Depends(get_db)):
    """Raises 403 if user has hit their plan's lead limit."""
    from models import Lead
    limit = user.leads_limit()
    if limit == -1:
        return user
    count = db.query(Lead).filter(Lead.user_id == user.id).count()
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Lead limit ({limit}) reached on the {user.plan} plan. Upgrade to add more leads.",
        )
    return user


def check_call_limit(user=Depends(get_active_user), db: Session = Depends(get_db)):
    """Raises 403 if user has hit their monthly call limit."""
    from models import Interaction
    from datetime import date
    limit = user.calls_limit()
    if limit == -1:
        return user
    month_start = date.today().replace(day=1)
    from models import Lead as _Lead
    count = db.query(Interaction).join(Interaction.lead).filter(
        _Lead.user_id == user.id,
        Interaction.type == "call",
        Interaction.created_at >= str(month_start),
    ).count()
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Monthly call limit ({limit}) reached on the {user.plan} plan. Upgrade for more calls.",
        )
    return user
