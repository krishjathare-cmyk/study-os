from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str = Field(min_length=6, max_length=72)
    account_type: Literal["student", "professional"] = "student"

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    account_type: Literal["student", "professional"]

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class SemesterCreate(BaseModel):
    name: str
    description: str | None = None


class SemesterResponse(BaseModel):
    id: int
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SubjectCreate(BaseModel):
    name: str
    description: str | None = None
    semester_id: int


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


class OrganizeSubjectRequest(BaseModel):
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

class RetrievalRequest(BaseModel):
    query: str
    top_k: int = 5


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

class ChatRequest(BaseModel):
    question: str
    top_k: int = 5


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


class StudentNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class StudentNoteUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class StudentNoteResponse(BaseModel):
    id: int
    node_id: int
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StructuredNoteSection(BaseModel):
    heading: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=4000)
    points: list[str] = Field(default_factory=list, max_length=30)


class PromptNoteData(BaseModel):
    overview: str = Field(default="", max_length=8000)
    sections: list[StructuredNoteSection] = Field(default_factory=list, max_length=20)
    key_points: list[str] = Field(default_factory=list, max_length=40)
    questions: list[str] = Field(default_factory=list, max_length=30)


class NodeNoteDocumentUpdate(BaseModel):
    notes: PromptNoteData


class NodeNoteDocumentResponse(BaseModel):
    node_id: int
    notes: PromptNoteData
    version: int
    saved: bool
    updated_at: datetime | None = None


class PromptNoteComposeRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)
    notes: PromptNoteData


class PromptNoteComposeResponse(BaseModel):
    notes: PromptNoteData
    message: str


class NodeChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    max_context_chunks: int = Field(default=8, ge=1, le=20)


class NodeChatSource(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int


class NodeChatResponse(BaseModel):
    node_id: int
    answer: str
    sources: list[NodeChatSource]


class ProgressUpdateRequest(BaseModel):
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


class TestSubmitRequest(BaseModel):
    answers: dict[str, str]


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


class LectureCreate(BaseModel):
    title: str | None = Field(default=None, max_length=240)


class LectureNote(BaseModel):
    overview: str = ""
    key_concepts: list[str] = Field(default_factory=list)
    definitions: list[str] = Field(default_factory=list)
    formulas: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    unclear_points: list[str] = Field(default_factory=list)
    recap: str = ""


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
