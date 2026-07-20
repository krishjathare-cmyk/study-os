import os


class GoogleIdentityError(RuntimeError):
    pass


def verify_google_id_token(credential: str) -> dict:
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    if not client_id:
        raise GoogleIdentityError("Google Sign-In is not configured")

    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token
    except ImportError as error:
        raise GoogleIdentityError(
            "Google authentication support is not installed"
        ) from error

    try:
        claims = id_token.verify_oauth2_token(
            credential,
            requests.Request(),
            client_id,
        )
    except ValueError as error:
        raise GoogleIdentityError(
            "Google could not verify this sign-in"
        ) from error

    issuer = claims.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleIdentityError("Google token issuer is invalid")
    if not claims.get("sub"):
        raise GoogleIdentityError("Google account identifier is missing")
    if not claims.get("email") or not claims.get("email_verified"):
        raise GoogleIdentityError(
            "Google has not verified this email address"
        )

    return claims
