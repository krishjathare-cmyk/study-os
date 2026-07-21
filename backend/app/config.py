import os
from urllib.parse import urlparse


PRODUCTION_NAMES = {"production", "prod"}


def is_production() -> bool:
    return (os.getenv("APP_ENV") or "development").strip().lower() in PRODUCTION_NAMES


def env_flag(name: str, default: bool = False) -> bool:
    value = (os.getenv(name) or str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate_runtime_config() -> None:
    """Reject unsafe or incomplete public-deployment configuration."""
    if not is_production():
        return

    errors: list[str] = []
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    frontend_url = (os.getenv("FRONTEND_URL") or "").strip().rstrip("/")
    origins = [
        value.strip().rstrip("/")
        for value in (os.getenv("FRONTEND_ORIGINS") or "").split(",")
        if value.strip()
    ]

    if not database_url or database_url.startswith("sqlite"):
        errors.append("DATABASE_URL must point to PostgreSQL")
    if not _https_url(frontend_url) or "localhost" in frontend_url:
        errors.append("FRONTEND_URL must be the public HTTPS URL")
    if not origins or any(
        not _https_url(origin) or "localhost" in origin for origin in origins
    ):
        errors.append("FRONTEND_ORIGINS must contain only public HTTPS origins")
    if (os.getenv("EMAIL_DELIVERY_MODE") or "").strip().lower() != "smtp":
        errors.append("EMAIL_DELIVERY_MODE must be smtp")
    for name in (
        "JWT_SECRET",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
        "GOOGLE_CLIENT_ID",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_STUDENT_PRO",
        "STRIPE_PRICE_PROFESSIONAL",
    ):
        if not (os.getenv(name) or "").strip():
            errors.append(f"{name} is required")

    if errors:
        raise RuntimeError(
            "Unsafe production configuration:\n- " + "\n- ".join(errors)
        )


if __name__ == "__main__":
    validate_runtime_config()
    print("Runtime configuration is valid.")
