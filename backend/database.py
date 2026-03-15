import os
from urllib.parse import urlparse, urlunparse, quote_plus, parse_qsl, urlencode

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use DATABASE_URL in production (e.g. PostgreSQL); default to local SQLite
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./wordle.db")

# Render and some hosts set DATABASE_URL with postgres://; SQLAlchemy 1.4+ wants postgresql://
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)


def _ensure_postgres_ssl(url: str) -> str:
    """Ensure postgres URLs have sslmode=require and connect_timeout for Supabase/Neon and similar cloud DBs."""
    if not url.startswith("postgresql://"):
        return url
    parsed = urlparse(url)
    query = parsed.query
    params = parse_qsl(query) if query else []
    # Avoid duplicate keys; build dict then back to list for urlencode
    param_dict = dict(params)
    param_dict.setdefault("sslmode", "require")
    param_dict.setdefault("connect_timeout", "15")  # Fail fast on Render instead of hanging
    parsed = parsed._replace(query=urlencode(sorted(param_dict.items())))
    return urlunparse(parsed)


def _fix_postgres_url_with_special_chars_in_password(url: str) -> str:
    """
    If the password in a postgres URL contains '@', URL parsers treat it as the user@host
    separator and break (e.g. host becomes "468726@db.xxx.supabase.co"). Re-parse and
    rebuild the URL with the password properly quoted so the host is correct.
    """
    if not url.startswith("postgresql://"):
        return url
    parsed = urlparse(url)
    netloc = parsed.netloc
    if "@" not in netloc or netloc.count("@") < 2:
        return url
    # netloc is like "user:pass@word@db.host.com:5432" -> we want host:port = last segment
    parts = netloc.split("@")
    host_port = parts[-1]
    user_pass = "@".join(parts[:-1])
    if ":" not in user_pass:
        return url
    user, password = user_pass.split(":", 1)
    encoded_password = quote_plus(password)
    new_netloc = f"{user}:{encoded_password}@{host_port}"
    parsed = parsed._replace(netloc=new_netloc)
    return urlunparse(parsed)


SQLALCHEMY_DATABASE_URL = _fix_postgres_url_with_special_chars_in_password(SQLALCHEMY_DATABASE_URL)
SQLALCHEMY_DATABASE_URL = _ensure_postgres_ssl(SQLALCHEMY_DATABASE_URL)

_connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
