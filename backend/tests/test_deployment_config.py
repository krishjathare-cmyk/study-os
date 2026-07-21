import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.auth import _jwt_secret
from app.config import validate_runtime_config
from app.llm_provider import _get_local_transcription_model
from app.storage import WHISPER_MODEL_DIR


class DeploymentConfigTests(unittest.TestCase):
    def tearDown(self):
        _get_local_transcription_model.cache_clear()

    def test_jwt_secret_comes_from_environment(self):
        secret = "configured-production-secret-at-least-32-bytes"
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET": secret},
        ):
            self.assertEqual(secret, _jwt_secret())

    def test_production_requires_jwt_secret(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET": ""},
        ):
            with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                _jwt_secret()

    def test_production_rejects_weak_jwt_secret(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET": "too-short"},
        ):
            with self.assertRaisesRegex(RuntimeError, "at least 32 bytes"):
                _jwt_secret()

    def test_production_rejects_localhost_and_missing_services(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "DATABASE_URL": "sqlite:///local.db",
                "FRONTEND_URL": "http://localhost:5173",
                "FRONTEND_ORIGINS": "http://localhost:5173",
                "EMAIL_DELIVERY_MODE": "console",
                "GOOGLE_CLIENT_ID": "",
                "STRIPE_SECRET_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
                validate_runtime_config()

    def test_complete_production_configuration_is_accepted(self):
        configured = {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:password@db/study",
            "FRONTEND_URL": "https://study.example.com",
            "FRONTEND_ORIGINS": "https://study.example.com",
            "EMAIL_DELIVERY_MODE": "smtp",
            "JWT_SECRET": "a-unique-production-secret-that-is-long-enough",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "smtp-user",
            "SMTP_PASSWORD": "smtp-password",
            "SMTP_FROM_EMAIL": "no-reply@example.com",
            "GOOGLE_CLIENT_ID": "google-client-id",
            "STRIPE_SECRET_KEY": "stripe-secret",
            "STRIPE_WEBHOOK_SECRET": "stripe-webhook-secret",
            "STRIPE_PRICE_STUDENT_PRO": "price_student",
            "STRIPE_PRICE_PROFESSIONAL": "price_professional",
        }
        with patch.dict(os.environ, configured, clear=True):
            validate_runtime_config()

    def test_whisper_downloads_into_persistent_model_directory(self):
        whisper_model = Mock(return_value=object())
        fake_module = SimpleNamespace(WhisperModel=whisper_model)

        with (
            patch.dict(sys.modules, {"faster_whisper": fake_module}),
            patch.dict(
                os.environ,
                {
                    "LOCAL_TRANSCRIPTION_MODEL": "small",
                    "LOCAL_TRANSCRIPTION_DEVICE": "cpu",
                    "LOCAL_TRANSCRIPTION_COMPUTE_TYPE": "int8",
                },
            ),
        ):
            _get_local_transcription_model.cache_clear()
            _get_local_transcription_model()

        whisper_model.assert_called_once_with(
            "small",
            device="cpu",
            compute_type="int8",
            download_root=str(WHISPER_MODEL_DIR),
        )


if __name__ == "__main__":
    unittest.main()
