import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.pdf_utils import PDFExtractionError, extract_text_from_pdf
from app.study_organizer import organize_document
from app.study_workflow import (
    create_and_map_assignment_chunks,
    generate_practice_for_assignment,
    pregenerate_topic_tests_for_nodes,
    regenerate_learning_for_nodes,
    regenerate_study_practice_for_nodes,
)
from app.usage_limits import (
    CONTENT_GENERATION,
    PDF_UPLOAD,
    PRACTICE_GENERATION,
    record_usage,
    require_daily_capacity,
)
from app.vecor_store import (
    VectorStoreError,
    delete_assignment_chunks,
    delete_document_chunks,
    index_assignment_chunks,
    index_chunks,
)


logger = logging.getLogger(__name__)
SAFE_FAILURE_MESSAGE = (
    "The PDF could not be processed. The incomplete upload was removed; "
    "please try again."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def recover_stale_jobs(db: Session, stale_after_seconds: int = 900) -> int:
    cutoff = _utc_now() - timedelta(seconds=max(60, stale_after_seconds))
    jobs = db.query(models.UploadJob).filter(
        models.UploadJob.status == "processing",
        models.UploadJob.heartbeat_at < cutoff,
        models.UploadJob.attempts < 3,
    ).all()
    for job in jobs:
        job.status = "queued"
        job.stage = "retrying"
        job.started_at = None
        job.heartbeat_at = None
    db.commit()
    return len(jobs)


def claim_next_job(db: Session) -> str | None:
    query = db.query(models.UploadJob).filter(
        models.UploadJob.status == "queued",
        models.UploadJob.attempts < 3,
    ).order_by(models.UploadJob.created_at)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    job = query.first()
    if job is None:
        return None
    now = _utc_now()
    job.status = "processing"
    job.stage = "starting"
    job.progress = 5
    job.attempts += 1
    job.started_at = now
    job.heartbeat_at = now
    db.commit()
    return job.id


def _advance(db: Session, job: models.UploadJob, stage: str, progress: int) -> None:
    job.stage = stage
    job.progress = progress
    job.heartbeat_at = _utc_now()
    db.commit()


def _delete_file(file_path: str | None) -> None:
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        logger.warning("Could not remove failed upload file", exc_info=True)


def _remove_failed_document(
    db: Session,
    job: models.UploadJob,
    document: models.Document | None,
    initial_node_ids: set[int],
) -> None:
    db.rollback()
    if document is None:
        return
    try:
        delete_document_chunks(job.user_id, job.subject_id, document.id)
    except VectorStoreError:
        pass

    chunk_ids = [
        row[0]
        for row in db.query(models.DocumentChunk.id).filter_by(
            document_id=document.id
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
        row[0]
        for row in db.query(models.StudyNode.id).filter(
            models.StudyNode.subject_id == job.subject_id,
            ~models.StudyNode.id.in_(initial_node_ids or {-1}),
        ).all()
    ]
    if created_node_ids:
        for model, column in (
            (models.StudentNote, models.StudentNote.node_id),
            (models.NodeNoteDocument, models.NodeNoteDocument.node_id),
            (models.NodeProgress, models.NodeProgress.node_id),
            (models.RevisionSchedule, models.RevisionSchedule.node_id),
            (models.PracticeSet, models.PracticeSet.node_id),
            (models.NodeLearningContent, models.NodeLearningContent.node_id),
            (models.NodeVisualization, models.NodeVisualization.node_id),
        ):
            db.query(model).filter(column.in_(created_node_ids)).delete(
                synchronize_session=False
            )
        test_ids = [
            row[0]
            for row in db.query(models.TopicTest.id).filter(
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
        for node in db.query(models.StudyNode).filter(
            models.StudyNode.id.in_(created_node_ids)
        ).order_by(models.StudyNode.level.desc()).all():
            db.delete(node)

    file_path = document.file_path
    job.document_id = None
    db.delete(document)
    db.commit()
    _delete_file(file_path)


def _remove_failed_assignment(
    db: Session,
    job: models.UploadJob,
    assignment: models.AssignmentDocument | None,
) -> None:
    db.rollback()
    if assignment is None:
        return
    try:
        delete_assignment_chunks(job.user_id, job.subject_id, assignment.id)
    except VectorStoreError:
        pass
    db.query(models.PracticeSet).filter(
        models.PracticeSet.source_assignment_id == assignment.id
    ).update(
        {models.PracticeSet.source_assignment_id: None},
        synchronize_session=False,
    )
    file_path = assignment.file_path
    job.assignment_id = None
    db.delete(assignment)
    db.commit()
    _delete_file(file_path)


def _process_study_job(db: Session, job: models.UploadJob) -> dict:
    document = db.get(models.Document, job.document_id)
    user = db.get(models.User, job.user_id)
    if document is None or user is None:
        raise ValueError("The queued document or owner no longer exists")

    initial_node_ids = {
        row[0]
        for row in db.query(models.StudyNode.id).filter_by(
            subject_id=job.subject_id
        ).all()
    }
    try:
        _advance(db, job, "extracting", 15)
        document.extracted_text = extract_text_from_pdf(document.file_path)
        if not (document.extracted_text or "").strip():
            raise ValueError("No readable PDF text was extracted")
        document.processing_status = "processing"
        db.commit()

        _advance(db, job, "organizing", 35)
        organization = organize_document(
            db=db,
            document=document,
            use_llm=False,
            document_as_topic=True,
        )
        if (
            not organization.chunk_texts
            or len(organization.chunk_texts) != len(organization.subtopic_ids)
        ):
            raise ValueError("The document did not produce a complete chunk set")
        db.commit()

        require_daily_capacity(
            db, user, CONTENT_GENERATION, len(organization.subtopic_ids)
        )
        if user.account_type == "student":
            require_daily_capacity(
                db, user, PRACTICE_GENERATION, len(organization.subtopic_ids)
            )

        _advance(db, job, "generating", 60)
        regenerate_learning_for_nodes(db, organization.subtopic_ids)
        if user.account_type == "student":
            regenerate_study_practice_for_nodes(db, organization.subtopic_ids)
            pregenerate_topic_tests_for_nodes(
                db, user.id, organization.subtopic_ids
            )
        db.commit()

        _advance(db, job, "indexing", 85)
        index_chunks(
            user_id=user.id,
            subject_id=job.subject_id,
            document_id=document.id,
            filename=document.filename,
            chunks=organization.chunk_texts,
            subtopic_ids=organization.subtopic_ids,
        )
        document.processing_status = "processed"
        record_usage(db, user, PDF_UPLOAD)
        record_usage(db, user, CONTENT_GENERATION, len(organization.subtopic_ids))
        if user.account_type == "student":
            record_usage(db, user, PRACTICE_GENERATION, len(organization.subtopic_ids))
        db.commit()
        return {
            "document_id": document.id,
            "filename": document.filename,
            "subtopic_count": len(set(organization.subtopic_ids)),
        }
    except Exception:
        _remove_failed_document(db, job, document, initial_node_ids)
        raise


def _process_assignment_job(db: Session, job: models.UploadJob) -> dict:
    assignment = db.get(models.AssignmentDocument, job.assignment_id)
    user = db.get(models.User, job.user_id)
    if assignment is None or user is None:
        raise ValueError("The queued assignment or owner no longer exists")
    try:
        _advance(db, job, "extracting", 20)
        assignment.extracted_text = extract_text_from_pdf(assignment.file_path)
        if not (assignment.extracted_text or "").strip():
            raise ValueError("No readable PDF text was extracted")
        assignment.processing_status = "processing"
        db.commit()

        _advance(db, job, "mapping", 50)
        chunks, affected_node_ids = create_and_map_assignment_chunks(db, assignment)
        if not chunks:
            raise ValueError("The assignment did not produce any chunks")
        require_daily_capacity(
            db, user, PRACTICE_GENERATION, max(1, len(affected_node_ids))
        )
        generate_practice_for_assignment(db, assignment, affected_node_ids)
        pregenerate_topic_tests_for_nodes(db, user.id, affected_node_ids)
        db.commit()

        _advance(db, job, "indexing", 85)
        link_rows = (
            db.query(models.AssignmentChunkNode.chunk_id, models.AssignmentChunkNode.node_id)
            .join(models.AssignmentChunk)
            .filter(models.AssignmentChunk.assignment_document_id == assignment.id)
            .all()
        )
        node_ids_by_chunk: dict[int, list[int]] = {}
        for chunk_id, node_id in link_rows:
            node_ids_by_chunk.setdefault(chunk_id, []).append(node_id)
        index_assignment_chunks(
            user_id=user.id,
            subject_id=job.subject_id,
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
        assignment.processing_status = "processed"
        record_usage(db, user, PDF_UPLOAD)
        record_usage(db, user, PRACTICE_GENERATION, max(1, len(affected_node_ids)))
        db.commit()
        mapped_count = sum(chunk.mapping_status == "mapped" for chunk in chunks)
        return {
            "assignment_id": assignment.id,
            "filename": assignment.filename,
            "chunk_count": len(chunks),
            "mapped_chunk_count": mapped_count,
            "unmapped_chunk_count": len(chunks) - mapped_count,
            "affected_subtopic_ids": affected_node_ids,
        }
    except Exception:
        _remove_failed_assignment(db, job, assignment)
        raise


def process_job(db: Session, job_id: str) -> None:
    job = db.get(models.UploadJob, job_id)
    if job is None or job.status != "processing":
        return
    try:
        result = (
            _process_study_job(db, job)
            if job.job_type == "study"
            else _process_assignment_job(db, job)
        )
        job = db.get(models.UploadJob, job_id)
        job.status = "completed"
        job.stage = "completed"
        job.progress = 100
        job.result = result
        job.error_message = None
        job.completed_at = _utc_now()
        job.heartbeat_at = job.completed_at
        db.commit()
    except (PDFExtractionError, HTTPException, Exception):
        logger.exception("Upload job %s failed", job_id)
        db.rollback()
        job = db.get(models.UploadJob, job_id)
        if job is not None:
            job.status = "failed"
            job.stage = "failed"
            job.error_message = SAFE_FAILURE_MESSAGE
            job.completed_at = _utc_now()
            job.heartbeat_at = job.completed_at
            db.commit()
