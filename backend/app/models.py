from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    account_type = Column(String, nullable=False, default="student")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    semesters = relationship("Semester", back_populates="user")

class Semester(Base):
    __tablename__ = "semesters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="semesters")
    subjects = relationship("Subject", back_populates="semester")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    semester_id = Column(Integer, ForeignKey("semesters.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    semester = relationship("Semester", back_populates="subjects")
    documents = relationship("Document", back_populates="subject")
    study_nodes = relationship("StudyNode", back_populates="subject")
    assignment_documents = relationship(
        "AssignmentDocument",
        back_populates="subject",
        cascade="all, delete-orphan",
    )
    lectures = relationship(
        "Lecture",
        back_populates="subject",
        cascade="all, delete-orphan",
        order_by="Lecture.lecture_number",
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    document_type = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subject = relationship("Subject", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document")

    @property
    def description(self) -> str:
        """Return a lightweight document preview without another model call."""
        text = " ".join((self.extracted_text or "").split())
        if not text:
            return "No readable text was extracted from this PDF."
        return f"{text[:220].rstrip()}..." if len(text) > 220 else text


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)

    document = relationship("Document", back_populates="chunks")
    study_node_links = relationship(
        "StudyNodeChunk",
        back_populates="chunk",
        cascade="all, delete-orphan",
    )


class StudyNode(Base):
    __tablename__ = "study_nodes"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    parent_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title = Column(String, nullable=False)
    normalized_title = Column(String, nullable=False)
    node_type = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    heading_number = Column(String, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_generated = Column(Boolean, nullable=False, default=False)
    confidence = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subject = relationship("Subject", back_populates="study_nodes")
    parent = relationship("StudyNode", remote_side=[id], back_populates="children")
    children = relationship(
        "StudyNode",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="StudyNode.sort_order",
    )
    chunk_links = relationship(
        "StudyNodeChunk",
        back_populates="node",
        cascade="all, delete-orphan",
    )
    learning_content = relationship(
        "NodeLearningContent",
        back_populates="node",
        cascade="all, delete-orphan",
        uselist=False,
    )
    visualization = relationship(
        "NodeVisualization",
        back_populates="node",
        cascade="all, delete-orphan",
        uselist=False,
    )


class StudyNodeChunk(Base):
    __tablename__ = "study_node_chunks"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_study_node_chunk_chunk"),
    )

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id = Column(
        Integer,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    node = relationship("StudyNode", back_populates="chunk_links")
    chunk = relationship("DocumentChunk", back_populates="study_node_links")


class AssignmentDocument(Base):
    __tablename__ = "assignment_documents"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=True)
    processing_status = Column(String, nullable=False, default="processed")
    created_at = Column(DateTime, server_default=func.now())

    subject = relationship("Subject", back_populates="assignment_documents")
    chunks = relationship(
        "AssignmentChunk",
        back_populates="assignment_document",
        cascade="all, delete-orphan",
    )


class AssignmentChunk(Base):
    __tablename__ = "assignment_chunks"
    __table_args__ = (
        UniqueConstraint(
            "assignment_document_id",
            "chunk_index",
            name="uq_assignment_chunk_index",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    assignment_document_id = Column(
        Integer,
        ForeignKey("assignment_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    mapping_status = Column(String, nullable=False, default="unmapped")

    assignment_document = relationship("AssignmentDocument", back_populates="chunks")
    node_links = relationship(
        "AssignmentChunkNode",
        back_populates="chunk",
        cascade="all, delete-orphan",
    )


class AssignmentChunkNode(Base):
    __tablename__ = "assignment_chunk_nodes"
    __table_args__ = (
        UniqueConstraint("chunk_id", "node_id", name="uq_assignment_chunk_node"),
    )

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(
        Integer,
        ForeignKey("assignment_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    confidence = Column(Float, nullable=False, default=0.0)
    mapping_method = Column(String, nullable=False, default="local")

    chunk = relationship("AssignmentChunk", back_populates="node_links")
    node = relationship("StudyNode")


class NodeLearningContent(Base):
    __tablename__ = "node_learning_contents"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    explanation = Column(Text, nullable=False)
    analogy = Column(Text, nullable=False)
    worked_example = Column(Text, nullable=False)
    real_life_example = Column(Text, nullable=False, default="")
    structured_sections = Column(JSON, nullable=False, default=list)
    formulas = Column(JSON, nullable=False, default=list)
    key_points = Column(JSON, nullable=False, default=list)
    conceptual_questions = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    generated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    node = relationship("StudyNode", back_populates="learning_content")


class NodeVisualization(Base):
    __tablename__ = "node_visualizations"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    visual_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    main_idea = Column(Text, nullable=False)
    nodes = Column(JSON, nullable=False, default=list)
    connections = Column(JSON, nullable=False, default=list)
    generated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    node = relationship("StudyNode", back_populates="visualization")


class StudentNote(Base):
    __tablename__ = "student_notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class NodeNoteDocument(Base):
    __tablename__ = "node_note_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_user_node_note_document"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notes = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class NodeProgress(Base):
    __tablename__ = "node_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_user_node_progress"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False, default="not_started")
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RevisionSchedule(Base):
    __tablename__ = "revision_schedules"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "node_id",
            "interval_days",
            name="uq_user_node_revision_interval",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interval_days = Column(Integer, nullable=False)
    due_at = Column(DateTime, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending")
    completed_at = Column(DateTime, nullable=True)


class PracticeSet(Base):
    __tablename__ = "practice_sets"
    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "source_assignment_id",
            name="uq_node_assignment_practice_set",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_assignment_id = Column(
        Integer,
        ForeignKey("assignment_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String, nullable=False)
    questions = Column(JSON, nullable=False, default=list)
    generated_at = Column(DateTime, server_default=func.now())


class PracticeAttempt(Base):
    __tablename__ = "practice_attempts"

    id = Column(Integer, primary_key=True, index=True)
    practice_set_id = Column(
        Integer,
        ForeignKey("practice_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    answers = Column(JSON, nullable=False, default=dict)
    score = Column(Float, nullable=False)
    max_score = Column(Float, nullable=False)
    percentage = Column(Float, nullable=False)
    analytics = Column(JSON, nullable=False, default=dict)
    submitted_at = Column(DateTime, server_default=func.now())


class TopicTest(Base):
    __tablename__ = "topic_tests"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_user_topic_test"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    node_id = Column(
        Integer,
        ForeignKey("study_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    questions = Column(JSON, nullable=False, default=list)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, server_default=func.now())
    due_at = Column(DateTime, nullable=False, index=True)
    submitted_at = Column(DateTime, nullable=True)

    attempts = relationship(
        "TestAttempt",
        back_populates="test",
        cascade="all, delete-orphan",
    )


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(
        Integer,
        ForeignKey("topic_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    answers = Column(JSON, nullable=False, default=dict)
    score = Column(Float, nullable=False)
    max_score = Column(Float, nullable=False)
    percentage = Column(Float, nullable=False)
    analytics = Column(JSON, nullable=False, default=dict)
    submitted_at = Column(DateTime, server_default=func.now())

    test = relationship("TopicTest", back_populates="attempts")


class Lecture(Base):
    __tablename__ = "lectures"
    __table_args__ = (
        UniqueConstraint("subject_id", "lecture_number", name="uq_subject_lecture_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    lecture_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="recording")
    transcript = Column(Text, nullable=False, default="")
    transcript_segments = Column(JSON, nullable=False, default=list)
    notes = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    ended_at = Column(DateTime, nullable=True)

    subject = relationship("Subject", back_populates="lectures")
