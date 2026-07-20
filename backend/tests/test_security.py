import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.auth import create_email_verification_token
from app.database import Base
from app.main import login_user, register_user, verify_email_address
from app.security import (
    LOGIN_MAX_ATTEMPTS,
    sanitize_display_filename,
    save_bounded_pdf_upload,
)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def _verified_user(self):
        with patch("app.main.send_verification_email"):
            register_user(
                schemas.UserCreate(
                    full_name="Security Reader",
                    email="security@example.com",
                    password="Secure-password1!",
                ),
                self.db,
            )
        user = self.db.query(models.User).filter_by(
            email="security@example.com",
        ).one()
        verify_email_address(
            schemas.EmailVerificationRequest(
                token=create_email_verification_token(user.id, user.email)
            ),
            self.db,
        )
        return user

    def test_request_models_reject_extra_fields_and_controls(self):
        with self.assertRaises(ValidationError):
            schemas.LoginRequest(
                email="reader@example.com",
                password="password",
                admin=True,
            )
        with self.assertRaises(ValidationError):
            schemas.SubjectCreate(
                name="Unsafe\x00subject",
                semester_id=1,
            )

    def test_emails_and_free_text_are_normalized(self):
        request = schemas.UserCreate(
            full_name="  Reader Name  ",
            email="  READER@EXAMPLE.COM  ",
            password="Secure-password1!",
        )
        note = schemas.StudentNoteCreate(content="  first\r\nsecond  ")

        self.assertEqual("Reader Name", request.full_name)
        self.assertEqual("reader@example.com", request.email)
        self.assertEqual("first\nsecond", note.content)

    def test_login_errors_do_not_reveal_account_existence(self):
        self._verified_user()
        attempts = (
            schemas.LoginRequest(
                email="security@example.com",
                password="Wrong-password1!",
            ),
            schemas.LoginRequest(
                email="missing@example.com",
                password="Wrong-password1!",
            ),
        )

        details = []
        for attempt in attempts:
            with self.assertRaises(HTTPException) as raised:
                login_user(attempt, self.db)
            self.assertEqual(401, raised.exception.status_code)
            details.append(raised.exception.detail)
        self.assertEqual(details[0], details[1])

    def test_login_is_locked_after_the_configured_failure_limit(self):
        self._verified_user()
        bad_login = schemas.LoginRequest(
            email="security@example.com",
            password="Wrong-password1!",
        )

        for _ in range(LOGIN_MAX_ATTEMPTS - 1):
            with self.assertRaises(HTTPException) as raised:
                login_user(bad_login, self.db)
            self.assertEqual(401, raised.exception.status_code)

        with self.assertRaises(HTTPException) as raised:
            login_user(bad_login, self.db)
        self.assertEqual(429, raised.exception.status_code)
        self.assertIn("Retry-After", raised.exception.headers)

        attempt = self.db.query(models.LoginAttempt).filter(
            models.LoginAttempt.locked_until.is_not(None),
        ).one()
        self.assertNotIn("security@example.com", attempt.fingerprint)
        self.assertEqual(64, len(attempt.fingerprint))

    def test_upload_filenames_cannot_escape_the_storage_directory(self):
        for filename in ("../secret.pdf", "..\\secret.pdf", "folder/secret.pdf"):
            with self.subTest(filename=filename):
                with self.assertRaises(HTTPException):
                    sanitize_display_filename(filename, ".pdf")

    def test_pdf_upload_checks_signature_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid_path = str(Path(directory) / "invalid.pdf")
            with self.assertRaises(HTTPException) as raised:
                save_bounded_pdf_upload(
                    SimpleNamespace(file=io.BytesIO(b"not a pdf")),
                    invalid_path,
                    max_bytes=1024,
                )
            self.assertEqual(400, raised.exception.status_code)
            self.assertFalse(Path(invalid_path).exists())

            oversized_path = str(Path(directory) / "oversized.pdf")
            with self.assertRaises(HTTPException) as raised:
                save_bounded_pdf_upload(
                    SimpleNamespace(file=io.BytesIO(b"%PDF-" + b"x" * 100)),
                    oversized_path,
                    max_bytes=20,
                )
            self.assertEqual(413, raised.exception.status_code)
            self.assertFalse(Path(oversized_path).exists())


if __name__ == "__main__":
    unittest.main()
