import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security import normalize_email_address, normalize_free_text


PASSWORD_POLICY_MESSAGE = (
    "Password must be 8–72 characters and include a lowercase letter, "
    "an uppercase letter, a number, and a special character"
)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validated_password(password: str, *, enforce_strength: bool) -> str:
    if "\x00" in password or len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes")
    if enforce_strength and (
        not re.search(r"[a-z]", password)
        or not re.search(r"[A-Z]", password)
        or not re.search(r"\d", password)
        or not re.search(r"[^\w\s]", password)
    ):
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    return password


def _normalize_text_list(
    values: list[str],
    *,
    field_name: str,
    item_max_length: int,
) -> list[str]:
    return [
        normalize_free_text(
            value,
            field_name=field_name,
            min_length=1,
            max_length=item_max_length,
            multiline=True,
        )
        for value in values
    ]


class UserCreate(RequestModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=72)
    account_type: Literal["student", "professional"] = "student"

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Full name",
            min_length=1,
            max_length=120,
        )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email_address(value)

    @field_validator("password")
    @classmethod
    def enforce_password_policy(cls, password: str) -> str:
        return _validated_password(password, enforce_strength=True)


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    account_type: Literal["student", "professional"]
    auth_provider: Literal["password", "google"] = "password"
    email_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(RequestModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email_address(value)


    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validated_password(value, enforce_strength=False)


class EmailRequest(RequestModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email_address(value)


class EmailVerificationRequest(RequestModel):
    token: str = Field(min_length=20, max_length=4096)

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Verification token",
            min_length=20,
            max_length=4096,
        )


class GoogleAuthRequest(RequestModel):
    credential: str = Field(min_length=20, max_length=16384)
    account_type: Literal["student", "professional"] = "student"
    create_account: bool = False

    @field_validator("credential")
    @classmethod
    def validate_credential(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Google credential",
            min_length=20,
            max_length=16384,
        )


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class SemesterCreate(RequestModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Workspace name",
            min_length=1,
            max_length=120,
        )

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_free_text(
            value,
            field_name="Workspace description",
            max_length=2000,
            multiline=True,
        )
        return normalized or None


class SemesterResponse(BaseModel):
    id: int
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SubjectCreate(RequestModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    semester_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Subject name",
            min_length=1,
            max_length=160,
        )

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_free_text(
            value,
            field_name="Subject description",
            max_length=2000,
            multiline=True,
        )
        return normalized or None


class SubjectResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    semester_id: int

    model_config = ConfigDict(from_attributes=True)

class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_path: str
    document_type: str
    subject_id: int
    description: str

    model_config = ConfigDict(from_attributes=True)


class StudyTreeNode(BaseModel):
    id: int
    title: str
    node_type: str
    level: int
    heading_number: str | None = None
    sort_order: int
    is_generated: bool
    confidence: float
    chunk_count: int
    document_ids: list[int]
    children: list["StudyTreeNode"] = Field(default_factory=list)


class StudyNodeSummary(BaseModel):
    id: int
    title: str
    node_type: str
    level: int


class StudyNodeChunkResponse(BaseModel):
    id: int
    document_id: int
    filename: str
    chunk_index: int
    chunk_text: str


class StudyNodeSourcePage(BaseModel):
    document_id: int
    filename: str
    page_number: int


class StudyNodeDetail(BaseModel):
    id: int
    subject_id: int
    parent_id: int | None = None
    title: str
    node_type: str
    level: int
    heading_number: str | None = None
    is_generated: bool
    confidence: float
    breadcrumb: list[StudyNodeSummary]
    chunks: list[StudyNodeChunkResponse]
    source_pages: list[StudyNodeSourcePage] = Field(default_factory=list)


class OrganizeSubjectRequest(RequestModel):
    force: bool = False
    reindex_vectors: bool = True
    use_llm: bool | None = None


class OrganizeSubjectResponse(BaseModel):
    subject_id: int
    documents_processed: int
    documents_skipped: int
    nodes_created: int
    chunks_linked: int
    vector_indexed: bool

class RetrievalRequest(RequestModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Query",
            min_length=1,
            max_length=4000,
            multiline=True,
        )


class RetrievalResultResponse(BaseModel):
    id: str
    document_id: int
    filename: str
    chunk_index: int
    chunk_text: str
    distance: float
    rerank_score: float
    matched_query: str
    expanded_queries: list[str]
    subtopic_id: int | None = None

class ChatRequest(RequestModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Question",
            min_length=1,
            max_length=4000,
            multiline=True,
        )


class ChatSource(BaseModel):
    document_id: int
    filename: str
    chunk_index: int
    distance: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]


class AssignmentNodeMapping(BaseModel):
    node_id: int
    title: str
    confidence: float
    mapping_method: str


class AssignmentChunkResponse(BaseModel):
    id: int
    chunk_index: int
    mapping_status: str
    mappings: list[AssignmentNodeMapping]


class AssignmentUploadResponse(BaseModel):
    id: int
    subject_id: int
    filename: str
    processing_status: str
    chunk_count: int
    mapped_chunk_count: int
    unmapped_chunk_count: int
    affected_subtopic_ids: list[int]


class AssignmentDocumentDetail(BaseModel):
    id: int
    subject_id: int
    filename: str
    processing_status: str
    created_at: datetime
    chunks: list[AssignmentChunkResponse]


class FormulaItem(BaseModel):
    expression: str
    symbols: str = ""
    use_case: str = ""


class VisualizationNode(BaseModel):
    id: str
    label: str
    kind: str
    description: str = ""
    group: str = "main"
    order: int = 0


class VisualizationConnection(BaseModel):
    source: str
    target: str
    label: str = ""


class VisualizationPlan(BaseModel):
    type: str
    title: str
    main_idea: str
    nodes: list[VisualizationNode]
    connections: list[VisualizationConnection]


class LearningContentResponse(BaseModel):
    node_id: int
    explanation: str
    analogy: str
    worked_example: str
    real_life_example: str
    structured_sections: list[dict] = Field(default_factory=list)
    formulas: list[FormulaItem]
    key_points: list[str]
    conceptual_questions: list[str]
    visualization: VisualizationPlan
    version: int
    generated_at: datetime


class StudentNoteCreate(RequestModel):
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Note",
            min_length=1,
            max_length=20000,
            multiline=True,
        )


class StudentNoteUpdate(RequestModel):
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Note",
            min_length=1,
            max_length=20000,
            multiline=True,
        )

class StudentNoteResponse(BaseModel):
    id: int
    node_id: int
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StructuredNoteSection(RequestModel):
    heading: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=4000)
    points: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("heading")
    @classmethod
    def validate_heading(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Section heading",
            min_length=1,
            max_length=240,
        )

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Section summary",
            max_length=4000,
            multiline=True,
        )

    @field_validator("points")
    @classmethod
    def validate_points(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(
            values,
            field_name="Section point",
            item_max_length=2000,
        )


class PromptNoteData(RequestModel):
    overview: str = Field(default="", max_length=8000)
    sections: list[StructuredNoteSection] = Field(default_factory=list, max_length=20)
    key_points: list[str] = Field(default_factory=list, max_length=40)
    questions: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("overview")
    @classmethod
    def validate_overview(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Notes overview",
            max_length=8000,
            multiline=True,
        )

    @field_validator("key_points")
    @classmethod
    def validate_key_points(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(
            values,
            field_name="Key point",
            item_max_length=2000,
        )

    @field_validator("questions")
    @classmethod
    def validate_questions(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(
            values,
            field_name="Question",
            item_max_length=2000,
        )


class NodeNoteDocumentUpdate(RequestModel):
    notes: PromptNoteData


class NodeNoteDocumentResponse(BaseModel):
    node_id: int
    notes: PromptNoteData
    version: int
    saved: bool
    updated_at: datetime | None = None


class PromptNoteComposeRequest(RequestModel):
    instruction: str = Field(min_length=1, max_length=4000)
    notes: PromptNoteData

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Editing instruction",
            min_length=1,
            max_length=4000,
            multiline=True,
        )

class PromptNoteComposeResponse(BaseModel):
    notes: PromptNoteData
    message: str


class NodeChatRequest(RequestModel):
    question: str = Field(min_length=1, max_length=4000)
    max_context_chunks: int = Field(default=8, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Question",
            min_length=1,
            max_length=4000,
            multiline=True,
        )

class NodeChatSource(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int


class NodeChatResponse(BaseModel):
    node_id: int
    answer: str
    sources: list[NodeChatSource]


class ProgressUpdateRequest(RequestModel):
    completed: bool


class RevisionResponse(BaseModel):
    id: int
    node_id: int
    node_title: str
    interval_days: int
    due_at: datetime
    status: str
    days_overdue: int
    revision_note: str = ""
    revision_points: list[str] = Field(default_factory=list)
    practice_set_id: int | None = None
    practice_questions: list[dict] = Field(default_factory=list)


class ProgressUpdateResponse(BaseModel):
    node_id: int
    status: str
    completed_at: datetime | None
    revisions: list[RevisionResponse]
    topic_test_id: int | None = None


class NodeProgressResponse(BaseModel):
    node_id: int
    node_title: str
    node_type: str
    status: str
    completed_at: datetime | None


class PublicQuestion(BaseModel):
    id: int
    type: str
    question: str
    options: list[str] = Field(default_factory=list)


class PracticeSetResponse(BaseModel):
    id: int
    node_id: int
    source_assignment_id: int | None
    title: str
    questions: list[PublicQuestion]
    generated_at: datetime


class TopicTestResponse(BaseModel):
    id: int
    node_id: int
    node_title: str
    title: str
    status: str
    created_at: datetime
    due_at: datetime
    days_overdue: int
    questions: list[PublicQuestion]


class TestSubmitRequest(RequestModel):
    answers: dict[str, str] = Field(max_length=100)

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, answers: dict[str, str]) -> dict[str, str]:
        validated = {}
        for key, value in answers.items():
            safe_key = normalize_free_text(
                key,
                field_name="Answer identifier",
                min_length=1,
                max_length=120,
            )
            safe_value = normalize_free_text(
                value,
                field_name="Answer",
                min_length=1,
                max_length=2000,
                multiline=True,
            )
            validated[safe_key] = safe_value
        return validated


class TestAttemptResponse(BaseModel):
    id: int
    test_id: int
    score: float
    max_score: float
    percentage: float
    analytics: dict
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PracticeAttemptResponse(BaseModel):
    id: int
    practice_set_id: int
    score: float
    max_score: float
    percentage: float
    analytics: dict
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailyPlanResponse(BaseModel):
    generated_for: datetime
    revisions: list[RevisionResponse]
    practice_sets: list[PracticeSetResponse]
    topic_tests: list[TopicTestResponse]


class LectureCreate(RequestModel):
    title: str | None = Field(default=None, max_length=240)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_free_text(
            value,
            field_name="Lecture title",
            max_length=240,
        )
        return normalized or None


class LectureNote(RequestModel):
    overview: str = Field(default="", max_length=8000)
    key_concepts: list[str] = Field(default_factory=list, max_length=50)
    definitions: list[str] = Field(default_factory=list, max_length=50)
    formulas: list[str] = Field(default_factory=list, max_length=50)
    examples: list[str] = Field(default_factory=list, max_length=50)
    questions: list[str] = Field(default_factory=list, max_length=50)
    unclear_points: list[str] = Field(default_factory=list, max_length=50)
    recap: str = Field(default="", max_length=8000)

    @field_validator("overview", "recap")
    @classmethod
    def validate_long_text(cls, value: str) -> str:
        return normalize_free_text(
            value,
            field_name="Lecture note text",
            max_length=8000,
            multiline=True,
        )

    @field_validator(
        "key_concepts",
        "definitions",
        "formulas",
        "examples",
        "questions",
        "unclear_points",
    )
    @classmethod
    def validate_note_items(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(
            values,
            field_name="Lecture note item",
            item_max_length=2000,
        )


class LectureResponse(BaseModel):
    id: int
    subject_id: int
    lecture_number: int
    title: str
    status: str
    transcript: str
    transcript_segments: list[dict] = Field(default_factory=list)
    notes: LectureNote | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class LectureChunkResponse(BaseModel):
    lecture_id: int
    chunk_index: int
    text: str
    transcript: str
    status: str


class LectureFinalizeResponse(LectureResponse):
    pass
