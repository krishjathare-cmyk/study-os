import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.auth import create_email_verification_token
from app.database import Base
from app.main import (
    authenticate_with_google,
    login_user,
    register_user,
    verify_email_address,
)


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def _register(self, email="reader@example.com"):
        with patch("app.main.send_verification_email"):
            return register_user(
                schemas.UserCreate(
                    full_name="Reader",
                    email=email,
                    password="Secure-password1!",
                    account_type="student",
                ),
                self.db,
            )

    def test_registration_rejects_each_missing_password_requirement(self):
        weak_passwords = (
            "Short1!",
            "NOLOWERCASE1!",
            "nouppercase1!",
            "NoNumber!",
            "NoSpecial1",
        )

        for password in weak_passwords:
            with self.subTest(password=password):
                with self.assertRaises(ValidationError):
                    schemas.UserCreate(
                        full_name="Reader",
                        email="reader@example.com",
                        password=password,
                    )

    def test_password_login_requires_verified_email(self):
        user = self._register()

        with self.assertRaises(HTTPException) as raised:
            login_user(
                schemas.LoginRequest(
                    email=user.email,
                    password="Secure-password1!",
                ),
                self.db,
            )
        self.assertEqual(403, raised.exception.status_code)

        session = verify_email_address(
            schemas.EmailVerificationRequest(
                token=create_email_verification_token(user.id, user.email)
            ),
            self.db,
        )
        self.assertTrue(session["user"].email_verified)
        self.assertTrue(session["access_token"])

    def test_google_token_creates_verified_professional_account(self):
        claims = {
            "sub": "google-user-123",
            "email": "professional@gmail.com",
            "email_verified": True,
            "name": "Google Professional",
            "iss": "https://accounts.google.com",
        }
        with patch("app.main.verify_google_id_token", return_value=claims):
            session = authenticate_with_google(
                schemas.GoogleAuthRequest(
                    credential="credential-value-long-enough",
                    account_type="professional",
                    create_account=True,
                ),
                self.db,
            )

        user = session["user"]
        self.assertEqual("google", user.auth_provider)
        self.assertTrue(user.email_verified)
        self.assertEqual("professional", user.account_type)
        self.assertEqual("google-user-123", user.google_subject)
        self.assertEqual(
            "Professional library",
            self.db.query(models.Semester).filter_by(user_id=user.id).one().name,
        )

    def test_google_sign_in_links_an_existing_email_account(self):
        user = self._register(email="linked@gmail.com")
        claims = {
            "sub": "google-linked-456",
            "email": user.email,
            "email_verified": True,
            "name": "Linked User",
            "iss": "accounts.google.com",
        }

        with patch("app.main.verify_google_id_token", return_value=claims):
            session = authenticate_with_google(
                schemas.GoogleAuthRequest(
                    credential="credential-value-long-enough",
                    create_account=False,
                ),
                self.db,
            )

        self.assertEqual(user.id, session["user"].id)
        self.assertTrue(session["user"].email_verified)
        self.assertEqual("google", session["user"].auth_provider)
        self.assertEqual("google-linked-456", session["user"].google_subject)

        with self.assertRaises(HTTPException) as raised:
            login_user(
                schemas.LoginRequest(
                    email=user.email,
                    password="Secure-password1!",
                ),
                self.db,
            )
        self.assertEqual(401, raised.exception.status_code)

    def test_google_links_verified_gmail_password_account(self):
        user = self._register(email="verified@gmail.com")
        verify_email_address(
            schemas.EmailVerificationRequest(
                token=create_email_verification_token(user.id, user.email)
            ),
            self.db,
        )
        claims = {
            "sub": "different-google-identity",
            "email": user.email,
            "email_verified": True,
            "name": "Verified User",
            "iss": "https://accounts.google.com",
        }

        with patch("app.main.verify_google_id_token", return_value=claims):
            session = authenticate_with_google(
                schemas.GoogleAuthRequest(
                    credential="credential-value-long-enough",
                    create_account=False,
                ),
                self.db,
            )

        self.assertEqual(user.id, session["user"].id)
        self.assertEqual("different-google-identity", session["user"].google_subject)
        password_session = login_user(
            schemas.LoginRequest(
                email=user.email,
                password="Secure-password1!",
            ),
            self.db,
        )
        self.assertEqual(user.id, password_session["user"].id)

    def test_google_does_not_silently_link_third_party_email(self):
        user = self._register(email="verified@example.com")
        verify_email_address(
            schemas.EmailVerificationRequest(
                token=create_email_verification_token(user.id, user.email)
            ),
            self.db,
        )
        claims = {
            "sub": "third-party-google-identity",
            "email": user.email,
            "email_verified": True,
            "name": "Verified User",
            "iss": "https://accounts.google.com",
        }

        with (
            patch("app.main.verify_google_id_token", return_value=claims),
            self.assertRaises(HTTPException) as raised,
        ):
            authenticate_with_google(
                schemas.GoogleAuthRequest(
                    credential="credential-value-long-enough",
                    create_account=False,
                ),
                self.db,
            )

        self.assertEqual(409, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
