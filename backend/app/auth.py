import os
import secrets
import warnings
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models
from app.database import get_db


def _jwt_secret() -> str:
    configured_secret = (os.getenv("JWT_SECRET") or "").strip()
    if configured_secret:
        return configured_secret

    if (os.getenv("APP_ENV") or "development").strip().lower() in {
        "production",
        "prod",
    }:
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
EMAIL_VERIFICATION_EXPIRE_HOURS = max(
    1,
    int(os.getenv("EMAIL_VERIFICATION_EXPIRE_HOURS", "24")),
)

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_email_verification_token(user_id: int, email: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=EMAIL_VERIFICATION_EXPIRE_HOURS
    )
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": email.strip().lower(),
            "purpose": "email_verification",
            "exp": expires_at,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_email_verification_token(token: str) -> tuple[int, str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user = db.query(models.User).filter(
        models.User.id == int(user_id)
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address before continuing",
        )

    return user
