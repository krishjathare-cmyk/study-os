import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from app.llm_provider import (
    LLMProviderError,
    edit_structured_notes,
    generate_lecture_notes,
    generate_strict_answer,
    reset_request_llm_provider,
    set_request_llm_provider,
    transcribe_lecture_audio,
)
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.vecor_store import (
    VectorStoreError,
    delete_assignment_chunks,
    delete_document_chunks,
    index_assignment_chunks,
    index_chunks,
    retrieve_chunks,
)
from app.retrieval_utils import calculate_relevance_score
from app import models, schemas
from app.auth import (
    DUMMY_PASSWORD_HASH,
    SECRET_KEY,
    create_access_token,
    create_email_verification_token,
    decode_email_verification_token,
    get_current_user,
    hash_password,
    password_hash_needs_update,
    verify_password,
)
from app.database import Base, engine, get_db
from app.email_service import EmailDeliveryError, send_verification_email
from app.google_identity import GoogleIdentityError, verify_google_id_token
from app.pdf_utils import PDFExtractionError, extract_text_from_pdf
from app.security import (
    GENERIC_GOOGLE_AUTH_MESSAGE,
    GENERIC_LOGIN_MESSAGE,
    GENERIC_REGISTRATION_MESSAGE,
    LOGIN_CLIENT_MAX_ATTEMPTS,
    check_login_allowed,
    clear_login_failures,
    enforce_bounded_audio_upload,
    login_attempt_fingerprint,
    normalize_email_address,
    normalize_free_text,
    record_login_failure,
    request_client_address,
    sanitize_audio_filename,
    sanitize_display_filename,
    save_bounded_pdf_upload,
)
from app.storage import UPLOAD_DIR
from app.study_organizer import organize_document, prune_empty_nodes
from app.study_workflow import (
    create_and_map_assignment_chunks,
    days_overdue,
    ensure_node_visualization,
    generate_practice_for_assignment,
    grade_practice_set,
    grade_topic_test,
    node_context,
    node_chunk_rows,
    node_path,
    node_source_pages,
    pregenerate_topic_tests_for_nodes,
    public_questions,
    regenerate_learning_content,
    regenerate_learning_for_nodes,
    regenerate_study_practice_for_nodes,
    set_node_completion,
    utc_now,
)
from app.usage_limits import (
    AI_MESSAGE,
    CONTENT_GENERATION,
    NOTE_GENERATION,
    PDF_UPLOAD,
    PRACTICE_GENERATION,
    TRANSCRIPT_SECOND,
    record_usage,
    require_daily_capacity,
    require_pdf_capacity,
    usage_summary,
)

Base.metadata.create_all(bind=engine)
logger = logging.getLogger(__name__)


def _configured_megabytes(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(500, max(1, value)) * 1024 * 1024


MAX_PDF_UPLOAD_BYTES = _configured_megabytes("MAX_PDF_UPLOAD_MB", 50)
MAX_AUDIO_CHUNK_BYTES = _configured_megabytes("MAX_AUDIO_CHUNK_MB", 25)

# Add fields introduced after the first SQLite database was created.
if engine.dialect.name == "sqlite":
    with engine.begin() as connection:
        user_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(users)"
            )
        }
        if "account_type" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users "
                "ADD COLUMN account_type VARCHAR NOT NULL DEFAULT 'student'"
            )
        if "auth_provider" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users "
                "ADD COLUMN auth_provider VARCHAR NOT NULL DEFAULT 'password'"
            )
        if "email_verified" not in user_columns:
            # Accounts created before verification existed remain accessible.
            connection.exec_driver_sql(
                "ALTER TABLE users "
                "ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 1"
            )
        if "email_verified_at" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN email_verified_at DATETIME"
            )
        if "verification_sent_at" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN verification_sent_at DATETIME"
            )
        if "google_subject" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN google_subject VARCHAR"
            )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_subject "
            "ON users (google_subject) WHERE google_subject IS NOT NULL"
        )
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(node_learning_contents)"
            )
        }
        if "real_life_example" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE node_learning_contents "
                "ADD COLUMN real_life_example TEXT NOT NULL DEFAULT ''"
            )
        if "structured_sections" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE node_learning_contents "
                "ADD COLUMN structured_sections TEXT NOT NULL DEFAULT '[]'"
            )

UPLOAD_RETRY_MESSAGE = (
    "The PDF could not be fully processed into chunks. "
    "The incomplete upload was removed; please upload the PDF again."
)

app = FastAPI(
    title="AI Study Assistant API",
    description="RAG-based study assistant for students",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def select_llm_provider(request, call_next):
    token = set_request_llm_provider(request.headers.get("X-LLM-Provider"))
    try:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), payment=(), usb=()"
        )
        if request.url.path in {
            "/login",
            "/register",
            "/verify-email",
            "/resend-verification",
            "/auth/google",
        }:
            response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        reset_request_llm_provider(token)


def _remove_failed_document_upload(
    db: Session,
    user_id: int,
    subject_id: int,
    document_id: int | None,
    file_path: str,
    initial_node_ids: set[int],
):
    """Remove all persisted state created by a failed study-PDF upload."""
    db.rollback()

    if document_id is not None:
        try:
            delete_document_chunks(user_id, subject_id, document_id)
        except VectorStoreError:
            # The vector store may be the reason processing failed. The local
            # database and file must still be cleaned up in that case.
            pass

        chunk_ids = [
            row[0] for row in db.query(models.DocumentChunk.id).filter(
                models.DocumentChunk.document_id == document_id
            ).all()
        ]
        if chunk_ids:
            db.query(models.StudyNodeChunk).filter(
                models.StudyNodeChunk.chunk_id.in_(chunk_ids)
            ).delete(synchronize_session=False)
            db.query(models.DocumentChunk).filter(
                models.DocumentChunk.id.in_(chunk_ids)
            ).delete(synchronize_session=False)

        created_node_ids = [
            row[0] for row in db.query(models.StudyNode.id).filter(
                models.StudyNode.subject_id == subject_id,
                ~models.StudyNode.id.in_(initial_node_ids or {-1}),
            ).all()
        ]
        if created_node_ids:
            db.query(models.StudentNote).filter(
                models.StudentNote.node_id.in_(created_node_ids)
            ).delete(synchronize_session=False)
            db.query(models.NodeProgress).filter(
                models.NodeProgress.node_id.in_(created_node_ids)
            ).delete(synchronize_session=False)
            db.query(models.RevisionSchedule).filter(
                models.RevisionSchedule.node_id.in_(created_node_ids)
            ).delete(synchronize_session=False)
            db.query(models.PracticeSet).filter(
                models.PracticeSet.node_id.in_(created_node_ids)
            ).delete(synchronize_session=False)
            test_ids = [
                row[0] for row in db.query(models.TopicTest.id).filter(
                    models.TopicTest.node_id.in_(created_node_ids)
                ).all()
            ]
            if test_ids:
                db.query(models.TestAttempt).filter(
                    models.TestAttempt.test_id.in_(test_ids)
                ).delete(synchronize_session=False)
                db.query(models.TopicTest).filter(
                    models.TopicTest.id.in_(test_ids)
                ).delete(synchronize_session=False)
            db.query(models.NodeLearningContent).filter(
                models.NodeLearningContent.node_id.in_(created_node_ids)
            ).delete(synchronize_session=False)
            db.query(models.NodeVisualization).filter(
                models.NodeVisualization.node_id.in_(created_node_ids)
            ).delete(synchronize_session=False)
            for node in db.query(models.StudyNode).filter(
                models.StudyNode.id.in_(created_node_ids)
            ).order_by(models.StudyNode.level.desc()).all():
                db.delete(node)

        db.query(models.Document).filter(
            models.Document.id == document_id
        ).delete(synchronize_session=False)

    db.commit()
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass


def _remove_failed_assignment_upload(
    db: Session,
    user_id: int,
    subject_id: int,
    assignment_id: int | None,
    file_path: str,
):
    """Remove all persisted state created by a failed assignment upload."""
    db.rollback()
    if assignment_id is not None:
        try:
            delete_assignment_chunks(user_id, subject_id, assignment_id)
        except VectorStoreError:
            pass

        db.query(models.PracticeSet).filter(
            models.PracticeSet.source_assignment_id == assignment_id
        ).update(
            {models.PracticeSet.source_assignment_id: None},
            synchronize_session=False,
        )
        db.query(models.AssignmentDocument).filter(
            models.AssignmentDocument.id == assignment_id
        ).delete(synchronize_session=False)
    db.commit()
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass


def get_owned_subject(
    db: Session,
    subject_id: int,
    user_id: int,
) -> models.Subject:
    subject = db.query(models.Subject).join(models.Semester).filter(
        models.Subject.id == subject_id,
        models.Semester.user_id == user_id,
    ).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


def require_student_account(current_user: models.User):
    if current_user.account_type != "student":
        raise HTTPException(
            status_code=403,
            detail="This feature is available only in student workspaces",
        )


def get_owned_node(
    db: Session,
    subject_id: int,
    node_id: int,
    user_id: int,
) -> models.StudyNode:
    get_owned_subject(db, subject_id, user_id)
    node = db.query(models.StudyNode).filter(
        models.StudyNode.id == node_id,
        models.StudyNode.subject_id == subject_id,
    ).first()
    if node is None:
        raise HTTPException(status_code=404, detail="Study node not found")
    return node


def get_owned_lecture(
    db: Session,
    subject_id: int,
    lecture_id: int,
    user_id: int,
) -> models.Lecture:
    get_owned_subject(db, subject_id, user_id)
    lecture = db.query(models.Lecture).filter(
        models.Lecture.id == lecture_id,
        models.Lecture.subject_id == subject_id,
    ).first()
    if lecture is None:
        raise HTTPException(status_code=404, detail="Lecture not found")
    return lecture


def _lecture_fallback_notes(title: str, transcript: str) -> dict:
    sentences = [
        sentence.strip()
        for sentence in transcript.replace("\n", " ").split(".")
        if len(sentence.strip()) > 24
    ]
    summary = ". ".join(sentences[:5]).strip()
    if summary:
        summary += "."
    else:
        summary = f"Transcript captured for {title}."
    return {
        "overview": summary,
        "key_concepts": sentences[:8],
        "definitions": [],
        "formulas": [],
        "examples": [],
        "questions": [],
        "unclear_points": ["AI note generation was unavailable; review the transcript directly."],
        "recap": summary,
    }


@app.get("/")
def root():
    return {
        "message": "AI Study Assistant backend is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


def _normalized_email(email: str) -> str:
    return normalize_email_address(email)


def _create_initial_workspace(
    db: Session,
    user: models.User,
    account_type: str,
) -> None:
    if account_type == "professional":
        db.add(
            models.Semester(
                name="Professional library",
                description="Folders and PDF knowledge maps",
                user_id=user.id,
            )
        )


def _issue_session(user: models.User) -> dict:
    return {
        "access_token": create_access_token(data={"sub": str(user.id)}),
        "token_type": "bearer",
        "user": user,
    }


def _deliver_verification(user: models.User) -> None:
    token = create_email_verification_token(user.id, user.email)
    send_verification_email(user.email, user.full_name, token)


@app.post(
    "/register",
    response_model=schemas.MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    email = _normalized_email(user.email)
    # Hash before checking existence so duplicate registration has comparable
    # work and cannot use response timing to enumerate accounts.
    submitted_password_hash = hash_password(user.password)
    existing_user = db.query(models.User).filter(
        models.User.email == email
    ).first()

    if existing_user:
        return {"message": GENERIC_REGISTRATION_MESSAGE}

    new_user = models.User(
        full_name=user.full_name,
        email=email,
        hashed_password=submitted_password_hash,
        account_type=user.account_type,
        auth_provider="password",
        email_verified=False,
        verification_sent_at=datetime.now(timezone.utc),
    )

    db.add(new_user)
    db.flush()
    _create_initial_workspace(db, new_user, user.account_type)
    db.commit()
    db.refresh(new_user)

    try:
        _deliver_verification(new_user)
    except EmailDeliveryError:
        # Do not change the public response based on whether an account exists.
        logger.exception("Verification email delivery failed during registration")

    return {"message": GENERIC_REGISTRATION_MESSAGE}


@app.post("/login", response_model=schemas.TokenResponse)
def login_user(
    login_data: schemas.LoginRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    email = _normalized_email(login_data.email)
    client_address = request_client_address(request)
    fingerprints = (
        (
            login_attempt_fingerprint(
                email,
                client_address,
                SECRET_KEY,
                scope="account",
            ),
            None,
        ),
        (
            login_attempt_fingerprint(
                email,
                client_address,
                SECRET_KEY,
                scope="client",
            ),
            LOGIN_CLIENT_MAX_ATTEMPTS,
        ),
    )
    for fingerprint, _ in fingerprints:
        retry_after = check_login_allowed(db, fingerprint)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many sign-in attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    user = db.query(models.User).filter(
        models.User.email == email
    ).first()

    password_matches = verify_password(
        login_data.password,
        user.hashed_password if user is not None else DUMMY_PASSWORD_HASH,
    )
    if user is None or not password_matches or not user.email_verified:
        retry_values = [
            record_login_failure(
                db,
                fingerprint,
                **({"max_attempts": maximum} if maximum is not None else {}),
            )
            for fingerprint, maximum in fingerprints
        ]
        retry_after = next(
            (value for value in retry_values if value is not None),
            None,
        )
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many sign-in attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_LOGIN_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    for fingerprint, _ in fingerprints:
        clear_login_failures(db, fingerprint)
    if password_hash_needs_update(user.hashed_password):
        user.hashed_password = hash_password(login_data.password)
        db.commit()
        db.refresh(user)

    return _issue_session(user)


@app.post("/verify-email", response_model=schemas.TokenResponse)
def verify_email_address(
    verification: schemas.EmailVerificationRequest,
    db: Session = Depends(get_db),
):
    try:
        user_id, email = decode_email_verification_token(verification.token)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link is invalid or expired",
        ) from error

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.email == email,
    ).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link is invalid",
        )

    if user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link is invalid or expired",
        )

    user.email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return _issue_session(user)


@app.post("/resend-verification", response_model=schemas.MessageResponse)
def resend_email_verification(
    request: schemas.EmailRequest,
    db: Session = Depends(get_db),
):
    generic_message = (
        "If an unverified account exists, a new verification email has been sent."
    )
    email = _normalized_email(request.email)
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None or user.email_verified:
        return {"message": generic_message}

    now = datetime.now(timezone.utc)
    sent_at = user.verification_sent_at
    if sent_at is not None:
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if (now - sent_at).total_seconds() < 60:
            return {"message": generic_message}

    user.verification_sent_at = now
    db.commit()
    db.refresh(user)
    try:
        _deliver_verification(user)
    except EmailDeliveryError:
        logger.exception("Verification email delivery failed during resend")

    return {"message": generic_message}


@app.post("/auth/google", response_model=schemas.TokenResponse)
def authenticate_with_google(
    request: schemas.GoogleAuthRequest,
    db: Session = Depends(get_db),
):
    try:
        claims = verify_google_id_token(request.credential)
    except GoogleIdentityError as error:
        configuration_error = any(
            word in str(error).lower()
            for word in ("configured", "installed")
        )
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if configuration_error
                else status.HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Google sign-in is temporarily unavailable"
                if configuration_error
                else GENERIC_GOOGLE_AUTH_MESSAGE
            ),
        ) from error

    google_subject = str(claims["sub"])
    try:
        email = _normalized_email(str(claims["email"]))
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_GOOGLE_AUTH_MESSAGE,
        ) from error
    user = db.query(models.User).filter(
        models.User.google_subject == google_subject
    ).first()

    if user is None:
        email_user = db.query(models.User).filter(
            models.User.email == email
        ).first()
        if email_user is not None:
            if email_user.google_subject:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=GENERIC_GOOGLE_AUTH_MESSAGE,
                )
            google_is_email_authority = (
                email.endswith("@gmail.com")
                or bool(claims.get("hd"))
            )
            if email_user.email_verified and not google_is_email_authority:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=GENERIC_GOOGLE_AUTH_MESSAGE,
                )

            if not email_user.email_verified:
                # This password account never proved ownership of the address.
                # Google has now done so, so invalidate the unverified password.
                email_user.hashed_password = hash_password(
                    secrets.token_urlsafe(32)
                )
                email_user.auth_provider = "google"
            email_user.google_subject = google_subject
            email_user.email_verified = True
            email_user.email_verified_at = datetime.now(timezone.utc)
            user = email_user

    if user is None:
        if not request.create_account:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=GENERIC_GOOGLE_AUTH_MESSAGE,
            )

        try:
            google_name = normalize_free_text(
                str(claims.get("name") or email.split("@")[0]),
                field_name="Google profile name",
                min_length=1,
                max_length=120,
            )
        except ValueError:
            google_name = email.split("@")[0][:120]
        user = models.User(
            full_name=google_name,
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            account_type=request.account_type,
            auth_provider="google",
            email_verified=True,
            email_verified_at=datetime.now(timezone.utc),
            google_subject=google_subject,
        )
        db.add(user)
        db.flush()
        _create_initial_workspace(db, user, request.account_type)
    else:
        user.email_verified = True
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return _issue_session(user)


@app.get("/me", response_model=schemas.UserResponse)
def get_current_account(
    current_user: models.User = Depends(get_current_user),
):
    return current_user


@app.get("/me/usage", response_model=schemas.UsageSummaryResponse)
def get_current_usage(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return usage_summary(db, current_user)


@app.post("/semesters", response_model=schemas.SemesterResponse)
def create_semester(
    semester: schemas.SemesterCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    new_semester = models.Semester(
        name=semester.name,
        description=semester.description,
        user_id=current_user.id
    )

    db.add(new_semester)
    db.commit()
    db.refresh(new_semester)

    return new_semester


@app.get("/semesters", response_model=list[schemas.SemesterResponse])
def get_semesters(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return db.query(models.Semester).filter(
        models.Semester.user_id == current_user.id
    ).all()


@app.post("/subjects", response_model=schemas.SubjectResponse)
def create_subject(
    subject: schemas.SubjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    semester = db.query(models.Semester).filter(
        models.Semester.id == subject.semester_id,
        models.Semester.user_id == current_user.id
    ).first()

    if semester is None:
        raise HTTPException(status_code=404, detail="Semester not found")

    new_subject = models.Subject(
        name=subject.name,
        description=subject.description,
        semester_id=subject.semester_id
    )

    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)

    return new_subject


@app.delete("/subjects/{subject_id}")
def delete_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    subject = get_owned_subject(db, subject_id, current_user.id)
    documents = db.query(models.Document).filter(
        models.Document.subject_id == subject_id
    ).all()
    assignments = db.query(models.AssignmentDocument).filter(
        models.AssignmentDocument.subject_id == subject_id
    ).all()
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.subject_id == subject_id
    ).all()
    node_ids = [node.id for node in nodes]
    document_ids = [document.id for document in documents]
    assignment_ids = [assignment.id for assignment in assignments]
    file_paths = [
        item.file_path for item in [*documents, *assignments]
        if item.file_path
    ]

    try:
        for document_id in document_ids:
            delete_document_chunks(current_user.id, subject_id, document_id)
        for assignment_id in assignment_ids:
            delete_assignment_chunks(current_user.id, subject_id, assignment_id)
    except VectorStoreError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    document_chunk_ids = [
        row[0] for row in db.query(models.DocumentChunk.id).filter(
            models.DocumentChunk.document_id.in_(document_ids)
        ).all()
    ] if document_ids else []
    assignment_chunk_ids = [
        row[0] for row in db.query(models.AssignmentChunk.id).filter(
            models.AssignmentChunk.assignment_document_id.in_(assignment_ids)
        ).all()
    ] if assignment_ids else []

    if document_chunk_ids:
        db.query(models.StudyNodeChunk).filter(
            models.StudyNodeChunk.chunk_id.in_(document_chunk_ids)
        ).delete(synchronize_session=False)
        db.query(models.DocumentChunk).filter(
            models.DocumentChunk.id.in_(document_chunk_ids)
        ).delete(synchronize_session=False)
    if assignment_chunk_ids:
        db.query(models.AssignmentChunkNode).filter(
            models.AssignmentChunkNode.chunk_id.in_(assignment_chunk_ids)
        ).delete(synchronize_session=False)
        db.query(models.AssignmentChunk).filter(
            models.AssignmentChunk.id.in_(assignment_chunk_ids)
        ).delete(synchronize_session=False)

    if assignment_ids:
        db.query(models.PracticeSet).filter(
            models.PracticeSet.source_assignment_id.in_(assignment_ids)
        ).update({models.PracticeSet.source_assignment_id: None}, synchronize_session=False)
        db.query(models.AssignmentDocument).filter(
            models.AssignmentDocument.id.in_(assignment_ids)
        ).delete(synchronize_session=False)

    if node_ids:
        db.query(models.StudentNote).filter(models.StudentNote.node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(models.NodeNoteDocument).filter(models.NodeNoteDocument.node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(models.NodeProgress).filter(models.NodeProgress.node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(models.RevisionSchedule).filter(models.RevisionSchedule.node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(models.PracticeSet).filter(models.PracticeSet.node_id.in_(node_ids)).delete(synchronize_session=False)
        topic_test_ids = [
            row[0] for row in db.query(models.TopicTest.id).filter(
                models.TopicTest.node_id.in_(node_ids)
            ).all()
        ]
        if topic_test_ids:
            db.query(models.TestAttempt).filter(
                models.TestAttempt.test_id.in_(topic_test_ids)
            ).delete(synchronize_session=False)
            db.query(models.TopicTest).filter(
                models.TopicTest.id.in_(topic_test_ids)
            ).delete(synchronize_session=False)
        db.query(models.NodeLearningContent).filter(
            models.NodeLearningContent.node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        db.query(models.NodeVisualization).filter(
            models.NodeVisualization.node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        db.query(models.StudyNode).filter(
            models.StudyNode.subject_id == subject_id
        ).delete(synchronize_session=False)

    if document_ids:
        db.query(models.Document).filter(
            models.Document.id.in_(document_ids)
        ).delete(synchronize_session=False)
    db.query(models.Lecture).filter(
        models.Lecture.subject_id == subject_id
    ).delete(synchronize_session=False)
    db.delete(subject)
    db.commit()

    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
    return {"message": "Subject deleted"}


@app.get("/semesters/{semester_id}/subjects", response_model=list[schemas.SubjectResponse])
def get_subjects(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    semester = db.query(models.Semester).filter(
        models.Semester.id == semester_id,
        models.Semester.user_id == current_user.id,
    ).first()
    if semester is None:
        raise HTTPException(status_code=404, detail="Semester not found")
    return db.query(models.Subject).filter(
        models.Subject.semester_id == semester_id
    ).order_by(models.Subject.name).all()


@app.post("/subjects/{subject_id}/documents", response_model=schemas.DocumentResponse)
def upload_document(
    subject_id: int,
    document_type: Literal["textbook"] = "textbook",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    get_owned_subject(db, subject_id, current_user.id)
    require_pdf_capacity(db, current_user)

    display_filename = sanitize_display_filename(file.filename, ".pdf")
    user_upload_dir = os.path.join(
        UPLOAD_DIR,
        f"user_{current_user.id}",
        f"subject_{subject_id}"
    )
    os.makedirs(user_upload_dir, exist_ok=True)

    file_path = os.path.join(user_upload_dir, f"{uuid4().hex}.pdf")
    save_bounded_pdf_upload(
        file,
        file_path,
        max_bytes=MAX_PDF_UPLOAD_BYTES,
    )

    try:
        extracted_text = extract_text_from_pdf(file_path)
    except PDFExtractionError as error:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not extracted_text.strip():
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=422, detail=UPLOAD_RETRY_MESSAGE)

    document = models.Document(
        filename=display_filename,
        file_path=file_path,
        document_type=document_type,
        extracted_text=extracted_text,
        subject_id=subject_id
    )

    db.add(document)
    # Commit the upload before outline/content generation so SQLite is not
    # held by a long-running AI or PDF organization step.
    db.commit()
    db.refresh(document)

    initial_node_ids = {
        row[0] for row in db.query(models.StudyNode.id).filter(
            models.StudyNode.subject_id == subject_id
        ).all()
    }
    try:
        # Upload organization is deliberately local-first. The explicit
        # false prevents a fallback outline request from spending API credits.
        organization = organize_document(db=db, document=document, use_llm=False)
        if (
            not organization.chunk_texts
            or len(organization.chunk_texts) != len(organization.subtopic_ids)
        ):
            raise ValueError("The document did not produce a complete chunk set")
        db.commit()

        require_daily_capacity(
            db,
            current_user,
            CONTENT_GENERATION,
            len(organization.subtopic_ids),
        )
        if current_user.account_type == "student":
            require_daily_capacity(
                db,
                current_user,
                PRACTICE_GENERATION,
                len(organization.subtopic_ids),
            )

        regenerate_learning_for_nodes(db, organization.subtopic_ids)
        if current_user.account_type == "student":
            regenerate_study_practice_for_nodes(db, organization.subtopic_ids)
            pregenerate_topic_tests_for_nodes(
                db,
                current_user.id,
                organization.subtopic_ids,
            )
        db.commit()
        db.refresh(document)

        index_chunks(
            user_id=current_user.id,
            subject_id=subject_id,
            document_id=document.id,
            filename=document.filename,
            chunks=organization.chunk_texts,
            subtopic_ids=organization.subtopic_ids,
        )
        record_usage(db, current_user, PDF_UPLOAD)
        record_usage(
            db,
            current_user,
            CONTENT_GENERATION,
            len(organization.subtopic_ids),
        )
        if current_user.account_type == "student":
            record_usage(
                db,
                current_user,
                PRACTICE_GENERATION,
                len(organization.subtopic_ids),
            )
        db.commit()
    except HTTPException as error:
        _remove_failed_document_upload(
            db=db,
            user_id=current_user.id,
            subject_id=subject_id,
            document_id=document.id,
            file_path=file_path,
            initial_node_ids=initial_node_ids,
        )
        raise error
    except Exception as error:
        _remove_failed_document_upload(
            db=db,
            user_id=current_user.id,
            subject_id=subject_id,
            document_id=document.id,
            file_path=file_path,
            initial_node_ids=initial_node_ids,
        )
        raise HTTPException(status_code=422, detail=UPLOAD_RETRY_MESSAGE) from error

    return document


@app.get(
    "/subjects/{subject_id}/documents",
    response_model=list[schemas.DocumentResponse],
)
def get_subject_documents(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_subject(db, subject_id, current_user.id)
    return db.query(models.Document).filter(
        models.Document.subject_id == subject_id
    ).order_by(models.Document.created_at.desc()).all()


@app.get("/subjects/{subject_id}/documents/{document_id}/file")
def view_document_file(
    subject_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_subject(db, subject_id, current_user.id)
    document = db.query(models.Document).filter(
        models.Document.id == document_id,
        models.Document.subject_id == subject_id,
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Study material not found")
    if not os.path.isfile(document.file_path):
        raise HTTPException(status_code=404, detail="PDF file not found")

    return FileResponse(
        path=document.file_path,
        media_type="application/pdf",
        filename=document.filename,
        content_disposition_type="inline",
    )


@app.delete("/subjects/{subject_id}/documents/{document_id}")
def delete_document(
    subject_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_subject(db, subject_id, current_user.id)
    document = db.query(models.Document).filter(
        models.Document.id == document_id,
        models.Document.subject_id == subject_id,
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Study material not found")

    chunk_ids = [
        row[0] for row in db.query(models.DocumentChunk.id).filter(
            models.DocumentChunk.document_id == document_id
        ).all()
    ]
    file_path = document.file_path

    try:
        delete_document_chunks(current_user.id, subject_id, document_id)
    except VectorStoreError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    if chunk_ids:
        db.query(models.StudyNodeChunk).filter(
            models.StudyNodeChunk.chunk_id.in_(chunk_ids)
        ).delete(synchronize_session=False)
        db.query(models.DocumentChunk).filter(
            models.DocumentChunk.id.in_(chunk_ids)
        ).delete(synchronize_session=False)

    db.delete(document)
    db.flush()
    # Remove branches that no longer have study-material chunks. Shared
    # branches remain when another uploaded PDF still supports them.
    prune_empty_nodes(db, subject_id)
    db.commit()

    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
    return {"message": "Study material deleted"}


@app.post(
    "/subjects/{subject_id}/lectures",
    response_model=schemas.LectureResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lecture(
    subject_id: int,
    request: schemas.LectureCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    latest = db.query(models.Lecture).filter(
        models.Lecture.subject_id == subject_id,
    ).order_by(models.Lecture.lecture_number.desc()).first()
    lecture_number = (latest.lecture_number + 1) if latest else 1
    lecture = models.Lecture(
        subject_id=subject_id,
        lecture_number=lecture_number,
        title=(request.title or f"Lecture {lecture_number}").strip()[:240],
        status="recording",
        transcript="",
        transcript_segments=[],
    )
    db.add(lecture)
    db.commit()
    db.refresh(lecture)
    return lecture


@app.get(
    "/subjects/{subject_id}/lectures",
    response_model=list[schemas.LectureResponse],
)
def get_subject_lectures(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    return db.query(models.Lecture).filter(
        models.Lecture.subject_id == subject_id,
    ).order_by(models.Lecture.lecture_number).all()


@app.get(
    "/subjects/{subject_id}/lectures/{lecture_id}",
    response_model=schemas.LectureResponse,
)
def get_lecture(
    subject_id: int,
    lecture_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    return get_owned_lecture(db, subject_id, lecture_id, current_user.id)


@app.put(
    "/subjects/{subject_id}/lectures/{lecture_id}/notes",
    response_model=schemas.LectureResponse,
)
def update_lecture_notes(
    subject_id: int,
    lecture_id: int,
    notes: schemas.LectureNote,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    lecture = get_owned_lecture(db, subject_id, lecture_id, current_user.id)
    if lecture.status != "ready":
        raise HTTPException(status_code=400, detail="Lecture notes are not ready yet")
    lecture.notes = notes.model_dump()
    db.commit()
    db.refresh(lecture)
    return lecture


@app.delete("/subjects/{subject_id}/lectures/{lecture_id}")
def delete_lecture(
    subject_id: int,
    lecture_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    lecture = get_owned_lecture(db, subject_id, lecture_id, current_user.id)
    db.delete(lecture)
    db.commit()
    return {"message": "Lecture deleted"}


@app.post(
    "/subjects/{subject_id}/lectures/{lecture_id}/transcribe",
    response_model=schemas.LectureChunkResponse,
)
def transcribe_lecture_chunk(
    subject_id: int,
    lecture_id: int,
    file: UploadFile = File(...),
    chunk_index: int = Query(default=0, ge=0, le=100000),
    offset_seconds: float = Query(default=0.0, ge=0.0, le=86400.0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    lecture = get_owned_lecture(db, subject_id, lecture_id, current_user.id)
    if lecture.status == "ready":
        raise HTTPException(status_code=409, detail="Lecture has already been finalized")
    require_daily_capacity(db, current_user, TRANSCRIPT_SECOND, 20)

    audio_filename = sanitize_audio_filename(
        file.filename,
        f"lecture-{lecture_id}-{chunk_index}.webm",
    )
    enforce_bounded_audio_upload(file, max_bytes=MAX_AUDIO_CHUNK_BYTES)

    try:
        text = transcribe_lecture_audio(
            file.file,
            audio_filename,
            file.content_type,
        )
    except LLMProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        file.file.close()

    segments = list(lecture.transcript_segments or [])
    segment = {
        "chunk_index": chunk_index,
        "offset_seconds": round(max(offset_seconds, 0.0), 2),
        "text": text,
    }
    segments = [item for item in segments if item.get("chunk_index") != chunk_index]
    if text:
        segments.append(segment)
    segments.sort(key=lambda item: item.get("chunk_index", 0))
    lecture.transcript_segments = segments
    lecture.transcript = "\n".join(item["text"] for item in segments if item.get("text"))
    lecture.status = "recording"
    record_usage(db, current_user, TRANSCRIPT_SECOND, 20)
    db.commit()
    db.refresh(lecture)
    return {
        "lecture_id": lecture.id,
        "chunk_index": chunk_index,
        "text": text,
        "transcript": lecture.transcript,
        "status": lecture.status,
    }


@app.post(
    "/subjects/{subject_id}/lectures/{lecture_id}/finalize",
    response_model=schemas.LectureFinalizeResponse,
)
def finalize_lecture(
    subject_id: int,
    lecture_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    lecture = get_owned_lecture(db, subject_id, lecture_id, current_user.id)
    if not lecture.transcript.strip():
        raise HTTPException(status_code=400, detail="No transcript has been captured yet")
    if lecture.status == "ready" and lecture.notes:
        return lecture
    require_daily_capacity(db, current_user, NOTE_GENERATION)

    notes = generate_lecture_notes(lecture.title, lecture.transcript)
    lecture.notes = notes or _lecture_fallback_notes(lecture.title, lecture.transcript)
    lecture.status = "ready"
    lecture.ended_at = utc_now()
    record_usage(db, current_user, NOTE_GENERATION)
    db.commit()
    db.refresh(lecture)
    return lecture


@app.post(
    "/subjects/{subject_id}/organize",
    response_model=schemas.OrganizeSubjectResponse,
)
def organize_subject_documents(
    subject_id: int,
    request: schemas.OrganizeSubjectRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    subject = get_owned_subject(db, subject_id, current_user.id)
    processed = 0
    skipped = 0
    nodes_created = 0
    chunks_linked = 0
    vector_jobs = []
    content_node_ids = set()

    for document in subject.documents:
        result = organize_document(
            db=db,
            document=document,
            force=request.force,
            use_llm=request.use_llm,
        )
        content_node_ids.update(result.subtopic_ids)
        if result.skipped:
            skipped += 1
            if request.reindex_vectors:
                vector_jobs.append((document, result))
            continue
        processed += 1
        nodes_created += result.nodes_created
        chunks_linked += result.chunks_linked
        vector_jobs.append((document, result))

    prune_empty_nodes(db, subject_id)
    regenerate_learning_for_nodes(db, sorted(content_node_ids))
    if current_user.account_type == "student":
        regenerate_study_practice_for_nodes(db, sorted(content_node_ids))
        pregenerate_topic_tests_for_nodes(
            db,
            current_user.id,
            sorted(content_node_ids),
        )
    db.commit()

    if request.reindex_vectors:
        try:
            for document, result in vector_jobs:
                delete_document_chunks(
                    user_id=current_user.id,
                    subject_id=subject_id,
                    document_id=document.id,
                )
                index_chunks(
                    user_id=current_user.id,
                    subject_id=subject_id,
                    document_id=document.id,
                    filename=document.filename,
                    chunks=result.chunk_texts,
                    subtopic_ids=result.subtopic_ids,
                )
        except VectorStoreError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "subject_id": subject_id,
        "documents_processed": processed,
        "documents_skipped": skipped,
        "nodes_created": nodes_created,
        "chunks_linked": chunks_linked,
        "vector_indexed": request.reindex_vectors,
    }


@app.get(
    "/subjects/{subject_id}/study-tree",
    response_model=list[schemas.StudyTreeNode],
)
def get_subject_study_tree(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_subject(db, subject_id, current_user.id)
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.subject_id == subject_id
    ).order_by(models.StudyNode.sort_order, models.StudyNode.id).all()

    children_by_parent = {}
    for node in nodes:
        children_by_parent.setdefault(node.parent_id, []).append(node)

    links = (
        db.query(models.StudyNodeChunk.node_id, models.DocumentChunk.document_id)
        .select_from(models.StudyNodeChunk)
        .join(
            models.DocumentChunk,
            models.DocumentChunk.id == models.StudyNodeChunk.chunk_id,
        )
        .join(models.StudyNode, models.StudyNode.id == models.StudyNodeChunk.node_id)
        .filter(models.StudyNode.subject_id == subject_id)
        .all()
    )
    direct_documents = {}
    direct_chunk_counts = {}
    for node_id, document_id in links:
        direct_documents.setdefault(node_id, set()).add(document_id)
        direct_chunk_counts[node_id] = direct_chunk_counts.get(node_id, 0) + 1

    def serialize_node(node: models.StudyNode):
        children = [serialize_node(child) for child in children_by_parent.get(node.id, [])]
        document_ids = set(direct_documents.get(node.id, set()))
        chunk_count = direct_chunk_counts.get(node.id, 0)
        for child in children:
            document_ids.update(child["document_ids"])
            chunk_count += child["chunk_count"]
        return {
            "id": node.id,
            "title": node.title,
            "node_type": node.node_type,
            "level": node.level,
            "heading_number": node.heading_number,
            "sort_order": node.sort_order,
            "is_generated": node.is_generated,
            "confidence": node.confidence,
            "chunk_count": chunk_count,
            "document_ids": sorted(document_ids),
            "children": children,
        }

    return [serialize_node(node) for node in children_by_parent.get(None, [])]


@app.get(
    "/subjects/{subject_id}/study-nodes/{node_id}",
    response_model=schemas.StudyNodeDetail,
)
def get_study_node_detail(
    subject_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_subject(db, subject_id, current_user.id)
    node = db.query(models.StudyNode).filter(
        models.StudyNode.id == node_id,
        models.StudyNode.subject_id == subject_id,
    ).first()
    if node is None:
        raise HTTPException(status_code=404, detail="Study node not found")

    breadcrumb = []
    cursor = node
    while cursor is not None:
        breadcrumb.append(
            {
                "id": cursor.id,
                "title": cursor.title,
                "node_type": cursor.node_type,
                "level": cursor.level,
            }
        )
        cursor = cursor.parent
    breadcrumb.reverse()

    chunk_rows = (
        db.query(models.DocumentChunk, models.Document.filename)
        .join(
            models.StudyNodeChunk,
            models.StudyNodeChunk.chunk_id == models.DocumentChunk.id,
        )
        .join(models.Document, models.Document.id == models.DocumentChunk.document_id)
        .filter(models.StudyNodeChunk.node_id == node_id)
        .order_by(models.DocumentChunk.document_id, models.DocumentChunk.chunk_index)
        .all()
    )
    chunks = [
        {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "filename": filename,
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.chunk_text,
        }
        for chunk, filename in chunk_rows
    ]

    return {
        "id": node.id,
        "subject_id": node.subject_id,
        "parent_id": node.parent_id,
        "title": node.title,
        "node_type": node.node_type,
        "level": node.level,
        "heading_number": node.heading_number,
        "is_generated": node.is_generated,
        "confidence": node.confidence,
        "breadcrumb": breadcrumb,
        "chunks": chunks,
        "source_pages": node_source_pages(db, node),
    }

@app.post("/subjects/{subject_id}/retrieve", response_model=list[schemas.RetrievalResultResponse])
def retrieve_subject_chunks(
    subject_id: int,
    retrieval_request: schemas.RetrievalRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    subject = db.query(models.Subject).join(models.Semester).filter(
        models.Subject.id == subject_id,
        models.Semester.user_id == current_user.id
    ).first()

    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    require_daily_capacity(db, current_user, AI_MESSAGE)

    try:
        retrieved_chunks = retrieve_chunks(
            user_id=current_user.id,
            subject_id=subject_id,
            query=retrieval_request.query,
            top_k=retrieval_request.top_k
        )
    except VectorStoreError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    enriched_chunks = []

    for chunk in retrieved_chunks:
        rerank_score = float(
            calculate_relevance_score(
                retrieval_request.query,
                chunk["chunk_text"]
            )
        )
        enriched_chunks.append(
            {
                **chunk,
                "rerank_score": rerank_score,
                "matched_query": retrieval_request.query,
                "expanded_queries": [retrieval_request.query],
            }
        )

    enriched_chunks.sort(key=lambda chunk: (-chunk["rerank_score"], chunk["distance"]))
    return enriched_chunks

@app.post("/subjects/{subject_id}/chat", response_model=schemas.ChatResponse)
def chat_with_subject_documents(
    subject_id: int,
    chat_request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    subject = db.query(models.Subject).join(models.Semester).filter(
        models.Subject.id == subject_id,
        models.Semester.user_id == current_user.id
    ).first()

    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")

    try:
        retrieved_chunks = retrieve_chunks(
            user_id=current_user.id,
            subject_id=subject_id,
            query=chat_request.question,
            top_k=chat_request.top_k
        )
    except VectorStoreError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    try:
        answer = generate_strict_answer(
            question=chat_request.question,
            retrieved_chunks=retrieved_chunks
        )
    except LLMProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    sources = [
        {
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "chunk_index": chunk["chunk_index"],
            "distance": chunk["distance"]
        }
        for chunk in retrieved_chunks
    ]

    record_usage(db, current_user, AI_MESSAGE)
    db.commit()
    return {
        "answer": answer,
        "sources": sources
    }


def _revision_payload(
    revision: models.RevisionSchedule,
    node_title: str,
    learning: models.NodeLearningContent | None = None,
    practice: models.PracticeSet | None = None,
) -> dict:
    overdue = days_overdue(revision.due_at)
    is_past_due = revision.due_at < utc_now()
    display_status = (
        "overdue" if revision.status == "pending" and is_past_due else revision.status
    )
    return {
        "id": revision.id,
        "node_id": revision.node_id,
        "node_title": node_title,
        "interval_days": revision.interval_days,
        "due_at": revision.due_at,
        "status": display_status,
        "days_overdue": overdue,
        "revision_note": (learning.explanation or "")[:500] if learning else "",
        "revision_points": (learning.key_points or [])[:4] if learning else [],
        "practice_set_id": practice.id if practice else None,
        "practice_questions": (
            public_questions((practice.questions or [])[:3]) if practice else []
        ),
    }


def _practice_payload(practice: models.PracticeSet) -> dict:
    return {
        "id": practice.id,
        "node_id": practice.node_id,
        "source_assignment_id": practice.source_assignment_id,
        "title": practice.title,
        "questions": public_questions(practice.questions),
        "generated_at": practice.generated_at,
    }


def _test_payload(test: models.TopicTest, node_title: str) -> dict:
    overdue = days_overdue(test.due_at)
    is_past_due = test.due_at < utc_now()
    display_status = "overdue" if test.status == "pending" and is_past_due else test.status
    return {
        "id": test.id,
        "node_id": test.node_id,
        "node_title": node_title,
        "title": test.title,
        "status": display_status,
        "created_at": test.created_at,
        "due_at": test.due_at,
        "days_overdue": overdue,
        "questions": public_questions(test.questions),
    }


def _visualization_payload(visualization: models.NodeVisualization) -> dict:
    return {
        "type": visualization.visual_type,
        "title": visualization.title,
        "main_idea": visualization.main_idea,
        "nodes": visualization.nodes,
        "connections": visualization.connections,
    }


@app.post(
    "/subjects/{subject_id}/assignments",
    response_model=schemas.AssignmentUploadResponse,
)
def upload_assignment(
    subject_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    require_pdf_capacity(db, current_user)
    display_filename = sanitize_display_filename(file.filename, ".pdf")
    assignment_dir = os.path.join(
        UPLOAD_DIR,
        f"user_{current_user.id}",
        f"subject_{subject_id}",
        "assignments",
    )
    os.makedirs(assignment_dir, exist_ok=True)
    file_path = os.path.join(assignment_dir, f"{uuid4().hex}.pdf")
    save_bounded_pdf_upload(
        file,
        file_path,
        max_bytes=MAX_PDF_UPLOAD_BYTES,
    )

    try:
        extracted_text = extract_text_from_pdf(file_path)
    except PDFExtractionError as error:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not extracted_text.strip():
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=422, detail=UPLOAD_RETRY_MESSAGE)

    assignment = models.AssignmentDocument(
        subject_id=subject_id,
        filename=display_filename,
        file_path=file_path,
        extracted_text=extracted_text,
        processing_status="processing",
    )
    db.add(assignment)
    db.flush()

    try:
        chunks, affected_node_ids = create_and_map_assignment_chunks(db, assignment)
        if not chunks:
            raise ValueError("The assignment did not produce any chunks")
        require_daily_capacity(
            db,
            current_user,
            PRACTICE_GENERATION,
            max(1, len(affected_node_ids)),
        )
        generate_practice_for_assignment(db, assignment, affected_node_ids)
        pregenerate_topic_tests_for_nodes(
            db,
            current_user.id,
            affected_node_ids,
        )
        assignment.processing_status = "processed"
        db.commit()
        db.refresh(assignment)

        link_rows = (
            db.query(models.AssignmentChunkNode.chunk_id, models.AssignmentChunkNode.node_id)
            .join(models.AssignmentChunk)
            .filter(models.AssignmentChunk.assignment_document_id == assignment.id)
            .all()
        )
        node_ids_by_chunk = {}
        for chunk_id, node_id in link_rows:
            node_ids_by_chunk.setdefault(chunk_id, []).append(node_id)

        index_assignment_chunks(
            user_id=current_user.id,
            subject_id=subject_id,
            assignment_id=assignment.id,
            filename=assignment.filename,
            chunks=[
                {
                    "id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "chunk_text": chunk.chunk_text,
                    "node_ids": node_ids_by_chunk.get(chunk.id, []),
                }
                for chunk in chunks
            ],
        )
    except HTTPException as error:
        _remove_failed_assignment_upload(
            db=db,
            user_id=current_user.id,
            subject_id=subject_id,
            assignment_id=assignment.id,
            file_path=file_path,
        )
        raise error
    except Exception as error:
        _remove_failed_assignment_upload(
            db=db,
            user_id=current_user.id,
            subject_id=subject_id,
            assignment_id=assignment.id,
            file_path=file_path,
        )
        raise HTTPException(status_code=422, detail=UPLOAD_RETRY_MESSAGE) from error

    mapped_count = sum(chunk.mapping_status == "mapped" for chunk in chunks)
    record_usage(db, current_user, PDF_UPLOAD)
    record_usage(
        db,
        current_user,
        PRACTICE_GENERATION,
        max(1, len(affected_node_ids)),
    )
    db.commit()
    return {
        "id": assignment.id,
        "subject_id": subject_id,
        "filename": assignment.filename,
        "processing_status": assignment.processing_status,
        "chunk_count": len(chunks),
        "mapped_chunk_count": mapped_count,
        "unmapped_chunk_count": len(chunks) - mapped_count,
        "affected_subtopic_ids": affected_node_ids,
    }


@app.get(
    "/subjects/{subject_id}/assignments",
    response_model=list[schemas.AssignmentUploadResponse],
)
def get_assignments(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    subject = get_owned_subject(db, subject_id, current_user.id)
    output = []
    for assignment in sorted(
        subject.assignment_documents,
        key=lambda item: item.created_at,
        reverse=True,
    ):
        mapped_chunks = [
            chunk for chunk in assignment.chunks if chunk.mapping_status == "mapped"
        ]
        affected_ids = sorted({
            link.node_id for chunk in assignment.chunks for link in chunk.node_links
        })
        output.append(
            {
                "id": assignment.id,
                "subject_id": assignment.subject_id,
                "filename": assignment.filename,
                "processing_status": assignment.processing_status,
                "chunk_count": len(assignment.chunks),
                "mapped_chunk_count": len(mapped_chunks),
                "unmapped_chunk_count": len(assignment.chunks) - len(mapped_chunks),
                "affected_subtopic_ids": affected_ids,
            }
        )
    return output


@app.get(
    "/subjects/{subject_id}/assignments/{assignment_id}",
    response_model=schemas.AssignmentDocumentDetail,
)
def get_assignment_detail(
    subject_id: int,
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    assignment = db.query(models.AssignmentDocument).filter_by(
        id=assignment_id,
        subject_id=subject_id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    chunks = []
    for chunk in sorted(assignment.chunks, key=lambda item: item.chunk_index):
        chunks.append(
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "mapping_status": chunk.mapping_status,
                "mappings": [
                    {
                        "node_id": link.node_id,
                        "title": link.node.title,
                        "confidence": link.confidence,
                        "mapping_method": link.mapping_method,
                    }
                    for link in chunk.node_links
                ],
            }
        )
    return {
        "id": assignment.id,
        "subject_id": assignment.subject_id,
        "filename": assignment.filename,
        "processing_status": assignment.processing_status,
        "created_at": assignment.created_at,
        "chunks": chunks,
    }


@app.get(
    "/subjects/{subject_id}/study-nodes/{node_id}/content",
    response_model=schemas.LearningContentResponse,
)
def get_node_learning_content(
    subject_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = get_owned_node(db, subject_id, node_id, current_user.id)
    if node.learning_content is None:
        raise HTTPException(
            status_code=404,
            detail="Learning content has not been generated for this node",
        )
    content = node.learning_content
    if not content.real_life_example or not content.structured_sections:
        # Upgrade older content once so the structured notes are populated.
        require_daily_capacity(db, current_user, CONTENT_GENERATION)
        content = regenerate_learning_content(db, node)
        record_usage(db, current_user, CONTENT_GENERATION)
        db.commit()
        db.refresh(content)
    visualization = ensure_node_visualization(db, node)
    db.commit()
    return {
        "node_id": node.id,
        "explanation": content.explanation,
        "analogy": content.analogy,
        "worked_example": content.worked_example,
        "real_life_example": content.real_life_example,
        "structured_sections": content.structured_sections,
        "formulas": content.formulas,
        "key_points": content.key_points,
        "conceptual_questions": content.conceptual_questions,
        "visualization": _visualization_payload(visualization),
        "version": content.version,
        "generated_at": content.generated_at,
    }


@app.post(
    "/subjects/{subject_id}/study-nodes/{node_id}/content/generate",
    response_model=schemas.LearningContentResponse,
)
def generate_node_content(
    subject_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = get_owned_node(db, subject_id, node_id, current_user.id)
    if node.node_type != "subtopic":
        raise HTTPException(status_code=400, detail="Content is generated for subtopics")
    require_daily_capacity(db, current_user, CONTENT_GENERATION)
    content = regenerate_learning_content(db, node)
    record_usage(db, current_user, CONTENT_GENERATION)
    db.commit()
    db.refresh(content)
    visualization = ensure_node_visualization(db, node)
    db.commit()
    return {
        "node_id": node.id,
        "explanation": content.explanation,
        "analogy": content.analogy,
        "worked_example": content.worked_example,
        "real_life_example": content.real_life_example,
        "structured_sections": content.structured_sections,
        "formulas": content.formulas,
        "key_points": content.key_points,
        "conceptual_questions": content.conceptual_questions,
        "visualization": _visualization_payload(visualization),
        "version": content.version,
        "generated_at": content.generated_at,
    }


def _initial_prompt_note_data(node: models.StudyNode) -> dict:
    content = node.learning_content
    if content is None:
        return {
            "overview": f"Build your notes for {node.title}.",
            "sections": [],
            "key_points": [],
            "questions": [],
        }

    sections = []
    for index, section in enumerate(content.structured_sections or []):
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or f"Section {index + 1}").strip()
        points = [
            str(point).strip()
            for point in section.get("points", [])
            if str(point).strip()
        ]
        sections.append(
            {
                "heading": heading[:240],
                "summary": str(section.get("summary") or "").strip()[:4000],
                "points": points[:30],
            }
        )
    if not sections and content.key_points:
        sections.append(
            {
                "heading": "Core ideas",
                "summary": f"The essential ideas for {node.title}.",
                "points": [str(point) for point in content.key_points[:30]],
            }
        )

    return {
        "overview": content.explanation,
        "sections": sections[:20],
        "key_points": [str(point) for point in (content.key_points or [])[:40]],
        "questions": [
            str(question)
            for question in (content.conceptual_questions or [])[:30]
        ],
    }


def _node_note_document_payload(
    node: models.StudyNode,
    document: models.NodeNoteDocument | None,
) -> dict:
    return {
        "node_id": node.id,
        "notes": document.notes if document is not None else _initial_prompt_note_data(node),
        "version": document.version if document is not None else 0,
        "saved": document is not None,
        "updated_at": document.updated_at if document is not None else None,
    }


@app.get(
    "/subjects/{subject_id}/study-nodes/{node_id}/notes",
    response_model=list[schemas.StudentNoteResponse],
)
def get_student_notes(
    subject_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_node(db, subject_id, node_id, current_user.id)
    return db.query(models.StudentNote).filter_by(
        user_id=current_user.id,
        node_id=node_id,
    ).order_by(models.StudentNote.updated_at.desc()).all()


@app.post(
    "/subjects/{subject_id}/study-nodes/{node_id}/notes",
    response_model=schemas.StudentNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_student_note(
    subject_id: int,
    node_id: int,
    request: schemas.StudentNoteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_node(db, subject_id, node_id, current_user.id)
    note = models.StudentNote(
        user_id=current_user.id,
        node_id=node_id,
        content=request.content,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.get(
    "/subjects/{subject_id}/study-nodes/{node_id}/note-document",
    response_model=schemas.NodeNoteDocumentResponse,
)
def get_node_note_document(
    subject_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = get_owned_node(db, subject_id, node_id, current_user.id)
    if node.node_type != "subtopic":
        raise HTTPException(
            status_code=400,
            detail="Structured notes are available for subtopics",
        )
    document = db.query(models.NodeNoteDocument).filter_by(
        user_id=current_user.id,
        node_id=node_id,
    ).first()
    return _node_note_document_payload(node, document)


@app.put(
    "/subjects/{subject_id}/study-nodes/{node_id}/note-document",
    response_model=schemas.NodeNoteDocumentResponse,
)
def save_node_note_document(
    subject_id: int,
    node_id: int,
    request: schemas.NodeNoteDocumentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = get_owned_node(db, subject_id, node_id, current_user.id)
    if node.node_type != "subtopic":
        raise HTTPException(
            status_code=400,
            detail="Structured notes are available for subtopics",
        )
    document = db.query(models.NodeNoteDocument).filter_by(
        user_id=current_user.id,
        node_id=node_id,
    ).first()
    if document is None:
        document = models.NodeNoteDocument(
            user_id=current_user.id,
            node_id=node_id,
            notes=request.notes.model_dump(),
            version=1,
        )
        db.add(document)
    else:
        document.notes = request.notes.model_dump()
        document.version += 1
    db.commit()
    db.refresh(document)
    return _node_note_document_payload(node, document)


@app.post(
    "/subjects/{subject_id}/study-nodes/{node_id}/note-document/compose",
    response_model=schemas.PromptNoteComposeResponse,
)
def compose_node_note_document(
    subject_id: int,
    node_id: int,
    request: schemas.PromptNoteComposeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = get_owned_node(db, subject_id, node_id, current_user.id)
    if node.node_type != "subtopic":
        raise HTTPException(
            status_code=400,
            detail="Structured notes are available for subtopics",
        )
    require_daily_capacity(db, current_user, NOTE_GENERATION)
    try:
        result = edit_structured_notes(
            node_path(node),
            node_context(db, node),
            request.notes.model_dump(),
            request.instruction,
        )
        validated_notes = schemas.PromptNoteData.model_validate(result["notes"])
    except LLMProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (KeyError, ValidationError) as error:
        raise HTTPException(
            status_code=502,
            detail="The AI notes editor returned an invalid note structure.",
        ) from error
    record_usage(db, current_user, NOTE_GENERATION)
    db.commit()
    return {
        "notes": validated_notes.model_dump(),
        "message": str(result.get("message") or "Notes updated."),
    }


@app.put(
    "/subjects/{subject_id}/study-nodes/{node_id}/notes/{note_id}",
    response_model=schemas.StudentNoteResponse,
)
def update_student_note(
    subject_id: int,
    node_id: int,
    note_id: int,
    request: schemas.StudentNoteUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_node(db, subject_id, node_id, current_user.id)
    note = db.query(models.StudentNote).filter_by(
        id=note_id,
        node_id=node_id,
        user_id=current_user.id,
    ).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    note.content = request.content
    db.commit()
    db.refresh(note)
    return note


@app.delete("/subjects/{subject_id}/study-nodes/{node_id}/notes/{note_id}")
def delete_student_note(
    subject_id: int,
    node_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_node(db, subject_id, node_id, current_user.id)
    note = db.query(models.StudentNote).filter_by(
        id=note_id,
        node_id=node_id,
        user_id=current_user.id,
    ).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    db.delete(note)
    db.commit()
    return {"deleted": True}


@app.post(
    "/subjects/{subject_id}/study-nodes/{node_id}/chat",
    response_model=schemas.NodeChatResponse,
)
def chat_with_study_node(
    subject_id: int,
    node_id: int,
    request: schemas.NodeChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = get_owned_node(db, subject_id, node_id, current_user.id)
    if node.node_type != "subtopic":
        raise HTTPException(status_code=400, detail="Open a subtopic to use scoped chat")
    require_daily_capacity(db, current_user, AI_MESSAGE)

    rows = node_chunk_rows(db, node)
    ranked_rows = sorted(
        rows,
        key=lambda row: calculate_relevance_score(request.question, row[0].chunk_text),
        reverse=True,
    )[:request.max_context_chunks]
    context_chunks = [
        {
            "chunk_text": chunk.chunk_text,
            "filename": filename,
            "chunk_index": chunk.chunk_index,
        }
        for chunk, filename in ranked_rows
    ]
    try:
        answer = generate_strict_answer(request.question, context_chunks)
    except LLMProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    record_usage(db, current_user, AI_MESSAGE)
    db.commit()
    return {
        "node_id": node.id,
        "answer": answer,
        "sources": [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "filename": filename,
                "chunk_index": chunk.chunk_index,
            }
            for chunk, filename in ranked_rows
        ],
    }


@app.put(
    "/subjects/{subject_id}/study-nodes/{node_id}/progress",
    response_model=schemas.ProgressUpdateResponse,
)
def update_node_progress(
    subject_id: int,
    node_id: int,
    request: schemas.ProgressUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    node = get_owned_node(db, subject_id, node_id, current_user.id)
    progress, revisions, topic_test = set_node_completion(
        db,
        current_user.id,
        node,
        request.completed,
    )
    db.commit()
    db.refresh(progress)
    return {
        "node_id": node.id,
        "status": progress.status,
        "completed_at": progress.completed_at,
        "revisions": [_revision_payload(item, node.title) for item in revisions],
        "topic_test_id": topic_test.id if topic_test else None,
    }


@app.get(
    "/subjects/{subject_id}/progress",
    response_model=list[schemas.NodeProgressResponse],
)
def get_subject_progress(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    rows = (
        db.query(models.NodeProgress, models.StudyNode)
        .join(models.StudyNode, models.StudyNode.id == models.NodeProgress.node_id)
        .filter(
            models.NodeProgress.user_id == current_user.id,
            models.StudyNode.subject_id == subject_id,
        )
        .order_by(models.StudyNode.level, models.StudyNode.sort_order)
        .all()
    )
    return [
        {
            "node_id": progress.node_id,
            "node_title": node.title,
            "node_type": node.node_type,
            "status": progress.status,
            "completed_at": progress.completed_at,
        }
        for progress, node in rows
    ]


@app.post("/subjects/{subject_id}/revisions/{revision_id}/complete")
def complete_revision(
    subject_id: int,
    revision_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    revision = (
        db.query(models.RevisionSchedule)
        .join(models.StudyNode)
        .filter(
            models.RevisionSchedule.id == revision_id,
            models.RevisionSchedule.user_id == current_user.id,
            models.StudyNode.subject_id == subject_id,
        )
        .first()
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="Revision not found")
    revision.status = "completed"
    revision.completed_at = utc_now()
    db.commit()
    return {"id": revision.id, "status": revision.status}


@app.get(
    "/subjects/{subject_id}/study-nodes/{node_id}/practice-sets",
    response_model=list[schemas.PracticeSetResponse],
)
def get_node_practice_sets(
    subject_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_node(db, subject_id, node_id, current_user.id)
    practices = db.query(models.PracticeSet).filter_by(node_id=node_id).order_by(
        models.PracticeSet.generated_at.desc()
    ).all()
    return [_practice_payload(item) for item in practices]


@app.get(
    "/subjects/{subject_id}/topic-tests",
    response_model=list[schemas.TopicTestResponse],
)
def get_topic_tests(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    rows = (
        db.query(models.TopicTest, models.StudyNode.title)
        .join(models.StudyNode, models.StudyNode.id == models.TopicTest.node_id)
        .filter(
            models.TopicTest.user_id == current_user.id,
            models.TopicTest.status != "locked",
            models.StudyNode.subject_id == subject_id,
        )
        .order_by(models.TopicTest.created_at.desc())
        .all()
    )
    return [_test_payload(test, title) for test, title in rows]


@app.post(
    "/subjects/{subject_id}/practice-sets/{practice_id}/submit",
    response_model=schemas.PracticeAttemptResponse,
)
def submit_practice_set(
    subject_id: int,
    practice_id: int,
    request: schemas.TestSubmitRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    practice = (
        db.query(models.PracticeSet)
        .join(models.StudyNode)
        .filter(
            models.PracticeSet.id == practice_id,
            models.StudyNode.subject_id == subject_id,
        )
        .first()
    )
    if practice is None:
        raise HTTPException(status_code=404, detail="Practice set not found")
    attempt = grade_practice_set(db, practice, current_user.id, request.answers)
    db.commit()
    db.refresh(attempt)
    return attempt


@app.post(
    "/subjects/{subject_id}/topic-tests/{test_id}/submit",
    response_model=schemas.TestAttemptResponse,
)
def submit_topic_test(
    subject_id: int,
    test_id: int,
    request: schemas.TestSubmitRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    test = (
        db.query(models.TopicTest)
        .join(models.StudyNode)
        .filter(
            models.TopicTest.id == test_id,
            models.TopicTest.user_id == current_user.id,
            models.StudyNode.subject_id == subject_id,
        )
        .first()
    )
    if test is None:
        raise HTTPException(status_code=404, detail="Topic test not found")
    attempt = grade_topic_test(db, test, current_user.id, request.answers)
    db.commit()
    db.refresh(attempt)
    return attempt


@app.get(
    "/subjects/{subject_id}/topic-tests/{test_id}/attempts",
    response_model=list[schemas.TestAttemptResponse],
)
def get_topic_test_attempts(
    subject_id: int,
    test_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    test = (
        db.query(models.TopicTest)
        .join(models.StudyNode)
        .filter(
            models.TopicTest.id == test_id,
            models.TopicTest.user_id == current_user.id,
            models.StudyNode.subject_id == subject_id,
        )
        .first()
    )
    if test is None:
        raise HTTPException(status_code=404, detail="Topic test not found")
    return db.query(models.TestAttempt).filter_by(
        test_id=test.id,
        user_id=current_user.id,
    ).order_by(models.TestAttempt.submitted_at.desc()).all()


@app.get(
    "/subjects/{subject_id}/daily-plan",
    response_model=schemas.DailyPlanResponse,
)
def get_daily_plan(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_student_account(current_user)
    get_owned_subject(db, subject_id, current_user.id)
    now = utc_now()
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    revision_query = (
        db.query(models.RevisionSchedule, models.StudyNode.title)
        .join(models.StudyNode, models.StudyNode.id == models.RevisionSchedule.node_id)
        .filter(
            models.RevisionSchedule.user_id == current_user.id,
            models.RevisionSchedule.status == "pending",
            models.StudyNode.subject_id == subject_id,
        )
    )
    if not test_mode:
        revision_query = revision_query.filter(models.RevisionSchedule.due_at <= now)
    revision_rows = revision_query.order_by(models.RevisionSchedule.due_at).all()
    due_node_ids = {revision.node_id for revision, _ in revision_rows}
    practices = []
    if test_mode:
        practices = db.query(models.PracticeSet).join(
            models.StudyNode,
            models.StudyNode.id == models.PracticeSet.node_id,
        ).filter(
            models.StudyNode.subject_id == subject_id,
        ).order_by(models.PracticeSet.generated_at.desc()).all()
    elif due_node_ids:
        all_practices = db.query(models.PracticeSet).filter(
            models.PracticeSet.node_id.in_(due_node_ids)
        ).order_by(models.PracticeSet.generated_at.desc()).all()
        seen_nodes = set()
        for practice in all_practices:
            if practice.node_id not in seen_nodes:
                practices.append(practice)
                seen_nodes.add(practice.node_id)

    test_rows = (
        db.query(models.TopicTest, models.StudyNode.title)
        .join(models.StudyNode, models.StudyNode.id == models.TopicTest.node_id)
        .filter(
            models.TopicTest.user_id == current_user.id,
            models.TopicTest.status == "pending",
            models.StudyNode.subject_id == subject_id,
        )
        .order_by(models.TopicTest.due_at)
        .all()
    )
    learning_by_node = {
        item.node_id: item
        for item in db.query(models.NodeLearningContent).filter(
            models.NodeLearningContent.node_id.in_(
                {revision.node_id for revision, _ in revision_rows}
            )
        ).all()
    }
    practice_by_node = {}
    for practice in practices:
        current = practice_by_node.get(practice.node_id)
        if current is None or (
            current.source_assignment_id is not None
            and practice.source_assignment_id is None
        ):
            practice_by_node[practice.node_id] = practice

    return {
        "generated_for": now,
        "revisions": [
            _revision_payload(
                revision,
                title,
                learning_by_node.get(revision.node_id),
                practice_by_node.get(revision.node_id),
            )
            for revision, title in revision_rows
        ],
        "practice_sets": [_practice_payload(item) for item in practices],
        "topic_tests": [_test_payload(test, title) for test, title in test_rows],
    }
