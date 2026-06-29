from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Safely add new columns to existing tables without dropping data."""
    new_columns = [
        ("users",     "from_email",         "VARCHAR(200)"),
        ("users",     "from_name",          "VARCHAR(200)"),
        ("users",     "elevenlabs_api_key", "VARCHAR(300)"),
        ("users",     "yelp_api_key",       "VARCHAR(300)"),
        ("users",     "reset_token",        "VARCHAR(100)"),
        ("users",     "reset_token_expires","TIMESTAMP"),
        ("users",     "referral_code",      "VARCHAR(20)"),
        ("users",     "referred_by",        "VARCHAR(20)"),
        ("campaigns", "company_brand",      "VARCHAR(200)"),
        ("campaigns", "shop_url_override",  "VARCHAR(500)"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in new_columns:
            try:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    )
                )
                conn.commit()
            except Exception:
                conn.rollback()  # column already exists — skip
