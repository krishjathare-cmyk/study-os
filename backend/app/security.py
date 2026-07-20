import hashlib
import hmac
import ipaddress
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app import models


GENERIC_LOGIN_MESSAGE = "Unable to sign in with those credentials"
GENERIC_GOOGLE_AUTH_MESSAGE = "Unable to sign in with Google"
GENERIC_REGISTRATION_MESSAGE = (
    "If the address can be registered, check your email for a verification link."
)

_EMAIL_LOCAL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_{}|~-]+$")
_DOMAIN_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_SAFE_DISPLAY_FILENAME_RE = re.compile(r"[^A-Za-z0-9._()\- ]+")
_AUDIO_EXTENSIONS = {".webm", ".ogg", ".wav", ".mp3", ".m4a", ".mp4", ".mpeg"}


def normalize_free_text(
    value: str,
    *,
    field_name: str,
    min_length: int = 0,
    max_length: int,
    multiline: bool = False,
) -> str:
    """Normalize free-form Unicode and reject unsafe control characters."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")

    normalized = unicodedata.normalize("NFC", value)
    if multiline:
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    for character in normalized:
        if multiline and character in {"\n", "\t"}:
            continue
        if unicodedata.category(character).startswith("C"):
            raise ValueError(f"{field_name} contains unsupported control characters")

    normalized = normalized.strip()
    if len(normalized) < min_length:
        raise ValueError(f"{field_name} must contain at least {min_length} character(s)")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must contain at most {max_length} characters")
    return normalized


def normalize_email_address(value: str) -> str:
    email = normalize_free_text(
        value,
        field_name="Email",
        min_length=3,
        max_length=254,
    ).lower()
    if email.count("@") != 1:
        raise ValueError("Enter a valid email address")

    local_part, domain = email.rsplit("@", 1)
    if (
        not local_part
        or len(local_part) > 64
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or not _EMAIL_LOCAL_RE.fullmatch(local_part)
    ):
        raise ValueError("Enter a valid email address")

    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("Enter a valid email address") from error

    labels = ascii_domain.split(".")
    if (
        len(ascii_domain) > 253
        or len(labels) < 2
        or any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels)
        or labels[-1].isdigit()
    ):
        raise ValueError("Enter a valid email address")
    return f"{local_part}@{ascii_domain}"


def sanitize_display_filename(filename: str | None, expected_extension: str) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Choose a {expected_extension.upper()} file to upload",
        )

    normalized = unicodedata.normalize("NFC", filename).strip()
    # A supplied path is never accepted, even though storage uses a random name.
    if (
        Path(normalized).name != normalized
        or "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded filename is invalid",
        )

    extension = expected_extension.lower()
    if not normalized.lower().endswith(extension):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {extension.upper()} files are allowed",
        )

    stem = normalized[: -len(extension)]
    safe_stem = _SAFE_DISPLAY_FILENAME_RE.sub("_", stem)
    safe_stem = re.sub(r"\s+", " ", safe_stem).strip(" ._")
    if not safe_stem:
        safe_stem = "document"
    return f"{safe_stem[:180]}{extension}"


def sanitize_audio_filename(filename: str | None, fallback: str) -> str:
    candidate = filename or fallback
    normalized = unicodedata.normalize("NFC", candidate).strip()
    if (
        Path(normalized).name != normalized
        or "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded audio filename is invalid",
        )
    extension = Path(normalized).suffix.lower()
    if extension not in _AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported audio format",
        )
    safe_stem = _SAFE_DISPLAY_FILENAME_RE.sub("_", Path(normalized).stem)
    safe_stem = safe_stem.strip(" ._") or "lecture-audio"
    return f"{safe_stem[:180]}{extension}"


def save_bounded_pdf_upload(
    upload: UploadFile,
    destination: str,
    *,
    max_bytes: int,
) -> None:
    """Save a PDF using a byte limit and a signature check."""
    first_chunk = b""
    written = 0
    try:
        with open(destination, "xb") as output:
            while chunk := upload.file.read(1024 * 1024):
                if not first_chunk:
                    first_chunk = chunk
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="The PDF exceeds the configured upload limit",
                    )
                output.write(chunk)
    except Exception:
        try:
            os.remove(destination)
        except OSError:
            pass
        raise
    finally:
        upload.file.close()

    if written == 0 or not first_chunk.lstrip().startswith(b"%PDF-"):
        try:
            os.remove(destination)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid PDF",
        )


def enforce_bounded_audio_upload(upload: UploadFile, *, max_bytes: int) -> None:
    """Reject oversized audio before the transcription provider reads it."""
    stream = upload.file
    current_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current_position)
    if size <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The audio chunk is empty",
        )
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The audio chunk exceeds the configured upload limit",
        )


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _positive_environment_integer(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(1, value)


LOGIN_MAX_ATTEMPTS = _positive_environment_integer("LOGIN_MAX_ATTEMPTS", 5)
LOGIN_CLIENT_MAX_ATTEMPTS = _positive_environment_integer(
    "LOGIN_CLIENT_MAX_ATTEMPTS",
    25,
)
LOGIN_ATTEMPT_WINDOW_SECONDS = _positive_environment_integer(
    "LOGIN_ATTEMPT_WINDOW_SECONDS",
    15 * 60,
)
LOGIN_LOCKOUT_SECONDS = _positive_environment_integer(
    "LOGIN_LOCKOUT_SECONDS",
    15 * 60,
)


def request_client_address(request: Request | None) -> str:
    if request is None or request.client is None:
        return "direct"
    address = request.client.host
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        return "unknown"


def login_attempt_fingerprint(
    email: str,
    client_address: str,
    secret: str,
    *,
    scope: str,
) -> str:
    # Separate account and client buckets stop both distributed account attacks
    # and high-volume attacks that rotate email addresses.
    if scope == "account":
        material_text = f"account\0{email}"
    elif scope == "client":
        material_text = f"client\0{client_address}"
    else:
        raise ValueError("Unknown login-attempt scope")
    # A keyed digest prevents account emails being recoverable from this table.
    material = material_text.encode("utf-8")
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


def check_login_allowed(
    db: Session,
    fingerprint: str,
    *,
    now: datetime | None = None,
) -> int | None:
    current_time = now or datetime.now(timezone.utc)
    attempt = db.get(models.LoginAttempt, fingerprint)
    if attempt is None:
        return None

    locked_until = _aware(attempt.locked_until)
    if locked_until is not None and locked_until > current_time:
        return max(1, int((locked_until - current_time).total_seconds()))

    window_started_at = _aware(attempt.window_started_at)
    if (
        window_started_at is None
        or (current_time - window_started_at).total_seconds()
        >= LOGIN_ATTEMPT_WINDOW_SECONDS
    ):
        db.delete(attempt)
        db.commit()
    return None


def record_login_failure(
    db: Session,
    fingerprint: str,
    *,
    now: datetime | None = None,
    max_attempts: int = LOGIN_MAX_ATTEMPTS,
) -> int | None:
    current_time = now or datetime.now(timezone.utc)
    attempt = db.get(models.LoginAttempt, fingerprint)
    window_started_at = _aware(attempt.window_started_at) if attempt else None
    if (
        attempt is None
        or window_started_at is None
        or (current_time - window_started_at).total_seconds()
        >= LOGIN_ATTEMPT_WINDOW_SECONDS
    ):
        if attempt is None:
            attempt = models.LoginAttempt(
                fingerprint=fingerprint,
                failed_attempts=0,
                window_started_at=current_time,
            )
            db.add(attempt)
        else:
            attempt.failed_attempts = 0
            attempt.window_started_at = current_time
            attempt.locked_until = None

    attempt.failed_attempts += 1
    retry_after = None
    if attempt.failed_attempts >= max(1, max_attempts):
        attempt.locked_until = current_time + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)
        retry_after = LOGIN_LOCKOUT_SECONDS
    db.commit()
    return retry_after


def clear_login_failures(db: Session, fingerprint: str) -> None:
    attempt = db.get(models.LoginAttempt, fingerprint)
    if attempt is not None:
        db.delete(attempt)
        db.commit()
