import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.auth import _jwt_secret
from app.llm_provider import _get_local_transcription_model
from app.storage import WHISPER_MODEL_DIR


class DeploymentConfigTests(unittest.TestCase):
    def tearDown(self):
        _get_local_transcription_model.cache_clear()

    def test_jwt_secret_comes_from_environment(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET": "configured-secret"},
        ):
            self.assertEqual("configured-secret", _jwt_secret())

    def test_production_requires_jwt_secret(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET": ""},
        ):
            with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                _jwt_secret()

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
