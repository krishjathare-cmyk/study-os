import argparse
import os
import signal
import time
from pathlib import Path

from sqlalchemy import text

from app.config import validate_runtime_config
from app.database import SessionLocal, engine
from app.pdf_jobs import claim_next_job, process_job, recover_stale_jobs


HEALTH_FILE = Path(os.getenv("WORKER_HEALTH_FILE", "/tmp/study-os-worker-heartbeat"))
POLL_SECONDS = max(0.25, float(os.getenv("WORKER_POLL_SECONDS", "2")))
STALE_SECONDS = max(60, int(os.getenv("WORKER_STALE_SECONDS", "900")))
running = True


def _stop(*_):
    global running
    running = False


def healthcheck() -> int:
    if not HEALTH_FILE.exists() or time.time() - HEALTH_FILE.stat().st_mtime > 90:
        return 1
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return 1
    return 0


def run() -> None:
    validate_runtime_config()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    with SessionLocal() as db:
        recover_stale_jobs(db, STALE_SECONDS)

    while running:
        HEALTH_FILE.touch()
        with SessionLocal() as db:
            job_id = claim_next_job(db)
        if job_id:
            with SessionLocal() as db:
                process_job(db, job_id)
        else:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    raise SystemExit(healthcheck()) if args.healthcheck else run()
