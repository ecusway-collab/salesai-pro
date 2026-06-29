from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "EXAVITQu4vr4xnSDxMaL"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    SENDGRID_API_KEY: str = ""
    FROM_EMAIL: str = "noreply@getfreeproducts.net"
    FROM_NAME: str = "Vital Health Global"
    REPLY_TO_EMAIL: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    YELP_API_KEY: str = ""
    BASE_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///./healthsales.db"
    COMPANY_NAME: str = "Vital Health Global"
    AGENT_NAME: str = "Alex"
    SHOP_URL: str = "http://primitivesolution.net"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_PRICE_STARTER: str = ""
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_AGENCY: str = ""

    # Auth
    JWT_SECRET: str = "change-this-jwt-secret-now"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    TRIAL_DAYS: int = 14

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
