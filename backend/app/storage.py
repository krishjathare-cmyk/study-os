import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=BACKEND_DIR / ".env")


def _configured_directory(environment_name: str, default: Path) -> Path:
    configured_value = (os.getenv(environment_name) or "").strip()
    directory = Path(configured_value).expanduser() if configured_value else default
    if not directory.is_absolute():
        directory = BACKEND_DIR / directory
    return directory.resolve()


# Point APP_DATA_DIR at a persistent volume (for example, /data in Railway).
# The more specific variables remain available when a deployment needs to split
# uploads and model storage across different volumes.
DATA_DIR = _configured_directory("APP_DATA_DIR", BACKEND_DIR)
UPLOAD_DIR = _configured_directory("UPLOAD_DIR", DATA_DIR / "uploads")
WHISPER_MODEL_DIR = _configured_directory(
    "LOCAL_TRANSCRIPTION_CACHE_DIR",
    DATA_DIR / "whisper-models",
)

for directory in (DATA_DIR, UPLOAD_DIR, WHISPER_MODEL_DIR):
    directory.mkdir(parents=True, exist_ok=True)
