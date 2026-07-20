import html
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import quote


class EmailDeliveryError(RuntimeError):
    pass


def _verification_url(token: str) -> str:
    frontend_url = (
        os.getenv("FRONTEND_URL")
        or "http://localhost:5173"
    ).strip().rstrip("/")
    return f"{frontend_url}/?verify_email={quote(token, safe='')}"


def send_verification_email(email: str, full_name: str, token: str) -> None:
    verification_url = _verification_url(token)
    delivery_mode = (
        os.getenv("EMAIL_DELIVERY_MODE") or "console"
    ).strip().lower()
    app_environment = (
        os.getenv("APP_ENV") or "development"
    ).strip().lower()

    if delivery_mode == "console":
        if app_environment in {"production", "prod"}:
            raise EmailDeliveryError(
                "Production email delivery must use SMTP"
            )
        print(
            f"Email verification for {email}: {verification_url}",
            flush=True,
        )
        return

    if delivery_mode != "smtp":
        raise EmailDeliveryError(
            "EMAIL_DELIVERY_MODE must be 'console' or 'smtp'"
        )

    host = (os.getenv("SMTP_HOST") or "").strip()
    username = (os.getenv("SMTP_USERNAME") or "").strip()
    password = os.getenv("SMTP_PASSWORD") or ""
    from_email = (os.getenv("SMTP_FROM_EMAIL") or username).strip()
    from_name = (os.getenv("SMTP_FROM_NAME") or "Study OS").strip()
    if not host or not from_email:
        raise EmailDeliveryError(
            "SMTP_HOST and SMTP_FROM_EMAIL are required for SMTP delivery"
        )

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as error:
        raise EmailDeliveryError("SMTP_PORT must be a number") from error

    use_ssl = (os.getenv("SMTP_USE_SSL") or "false").lower() == "true"
    use_starttls = (os.getenv("SMTP_USE_TLS") or "true").lower() == "true"
    safe_name = html.escape((full_name or "there").strip())
    safe_url = html.escape(verification_url, quote=True)

    message = EmailMessage()
    message["Subject"] = "Verify your Study OS email"
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = email
    message.set_content(
        "Welcome to Study OS.\n\n"
        f"Verify your email by opening this link:\n{verification_url}\n\n"
        "This link expires in 24 hours. If you did not create this account, "
        "you can ignore this message."
    )
    message.add_alternative(
        "<!doctype html>"
        "<html><body style=\"font-family:Arial,sans-serif;color:#182436\">"
        f"<h2>Welcome, {safe_name}</h2>"
        "<p>Verify your email address to open your Study OS workspace.</p>"
        f"<p><a href=\"{safe_url}\" style=\"display:inline-block;"
        "padding:12px 18px;background:#254c67;color:#fff;"
        "text-decoration:none;border-radius:4px\">Verify email</a></p>"
        "<p>This link expires in 24 hours. If you did not create this "
        "account, you can ignore this message.</p>"
        "</body></html>",
        subtype="html",
    )

    try:
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as server:
            if not use_ssl and use_starttls:
                server.starttls()
            if username:
                server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError(
            "The verification email could not be delivered"
        ) from error
