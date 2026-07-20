import os
import secrets
import warnings
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from sqlalchemy.orm import Session

from app import models
from app.database import get_db


def _jwt_secret() -> str:
    configured_secret = (os.getenv("JWT_SECRET") or "").strip()
    is_production = (os.getenv("APP_ENV") or "development").strip().lower() in {
        "production",
        "prod",
    }
    if configured_secret:
        if is_production and (
            len(configured_secret.encode("utf-8")) < 32
            or configured_secret == "replace-with-a-long-random-value"
        ):
            raise RuntimeError(
                "JWT_SECRET must be a unique value of at least 32 bytes "
                "when APP_ENV is production"
            )
        return configured_secret

    if is_production:
        raise RuntimeError(
            "JWT_SECRET must be set when APP_ENV is production"
        )

    warnings.warn(
        "JWT_SECRET is not set. Using a temporary development-only secret; "
        "sessions will be invalid after the backend restarts.",
        RuntimeWarning,
        stacklevel=2,
    )
    return secrets.token_urlsafe(48)


SECRET_KEY = _jwt_secret()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
JWT_ISSUER = (os.getenv("JWT_ISSUER") or "study-os-api").strip()
JWT_AUDIENCE = (os.getenv("JWT_AUDIENCE") or "study-os-web").strip()
EMAIL_VERIFICATION_EXPIRE_HOURS = max(
    1,
    int(os.getenv("EMAIL_VERIFICATION_EXPIRE_HOURS", "24")),
)

try:
    BCRYPT_ROUNDS = min(16, max(12, int(os.getenv("BCRYPT_ROUNDS", "12"))))
except ValueError:
    BCRYPT_ROUNDS = 12

password_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=BCRYPT_ROUNDS,
)
security = HTTPBearer(auto_error=False)
INVALID_AUTHENTICATION_MESSAGE = "Invalid or expired authentication credentials"


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be non-empty text")
    if "\x00" in password or len(password.encode("utf-8")) > 72:
        raise ValueError("Password cannot be hashed safely")
    return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if (
        not isinstance(plain_password, str)
        or not isinstance(hashed_password, str)
        or not hashed_password
        or "\x00" in plain_password
        or len(plain_password.encode("utf-8")) > 72
    ):
        return False
    try:
        return password_context.verify(plain_password, hashed_password)
    except (TypeError, ValueError, UnknownHashError):
        return False


def password_hash_needs_update(hashed_password: str) -> bool:
    try:
        return password_context.needs_update(hashed_password)
    except (TypeError, ValueError, UnknownHashError):
        return False


# Used when an email does not exist so password verification takes the same
# expensive path and does not become an account-enumeration timing signal.
DUMMY_PASSWORD_HASH = hash_password("Timing-only-password-7!")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update(
        {
            "purpose": "access",
            "iat": issued_at,
            "exp": expire,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "jti": secrets.token_urlsafe(16),
        }
    )

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_email_verification_token(user_id: int, email: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=EMAIL_VERIFICATION_EXPIRE_HOURS
    )
    issued_at = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": email.strip().lower(),
            "purpose": "email_verification",
            "iat": issued_at,
            "exp": expires_at,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "jti": secrets.token_urlsafe(16),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_email_verification_token(token: str) -> tuple[int, str]:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except ExpiredSignatureError as error:
        raise ValueError("Verification link has expired") from error
    except JWTError as error:
        raise ValueError("Verification link is invalid") from error

    if payload.get("purpose") != "email_verification":
        raise ValueError("Verification link is invalid")

    user_id = payload.get("sub")
    email = (payload.get("email") or "").strip().lower()
    if not user_id or not email:
        raise ValueError("Verification link is invalid")

    try:
        return int(user_id), email
    except (TypeError, ValueError) as error:
        raise ValueError("Verification link is invalid") from error


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
    db: Session = Depends(get_db)
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_AUTHENTICATION_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
        user_id = payload.get("sub")

        if user_id is None or payload.get("purpose") != "access":
            raise JWTError("Invalid token purpose")
        user_id = int(user_id)
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_AUTHENTICATION_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_AUTHENTICATION_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address before continuing",
        )

    return user
