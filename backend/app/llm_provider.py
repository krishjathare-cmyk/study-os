import json
import os
import re
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI, OpenAIError
from app.prompts import (
    ASSIGNMENT_MAPPING_SYSTEM_PROMPT,
    LECTURE_NOTES_SYSTEM_PROMPT,
    NODE_LEARNING_CONTENT_SYSTEM_PROMPT,
    NOTE_EDITOR_SYSTEM_PROMPT,
    QUESTION_SET_SYSTEM_PROMPT,
    RAG_ANSWER_SYSTEM_PROMPT,
    STUDY_PATH_SYSTEM_PROMPT,
    VISUALIZATION_SYSTEM_PROMPT,
)
from app.retrieval_utils import tokenize

BACKEND_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV_PATH, override=True)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
SUPPORTED_LLM_PROVIDERS = {"openai", "deepseek"}
_REQUEST_LLM_PROVIDER = ContextVar("request_llm_provider", default=None)
try:
    CHAT_RELEVANCE_THRESHOLD = max(
        1,
        int(os.getenv("CHAT_RELEVANCE_THRESHOLD", "1")),
    )
except ValueError:
    CHAT_RELEVANCE_THRESHOLD = 1


class LLMProviderError(RuntimeError):
    pass


def set_request_llm_provider(provider: str | None):
    normalized = (provider or "").strip().lower()
    return _REQUEST_LLM_PROVIDER.set(
        normalized if normalized in SUPPORTED_LLM_PROVIDERS else None
    )


def reset_request_llm_provider(token):
    _REQUEST_LLM_PROVIDER.reset(token)


def get_active_llm_provider() -> str:
    requested = _REQUEST_LLM_PROVIDER.get()
    if requested:
        return requested
    return (LLM_PROVIDER or "mock").strip().lower()


def _remote_llm_enabled() -> bool:
    return get_active_llm_provider() in SUPPORTED_LLM_PROVIDERS


def _model_for(env_name: str, openai_default: str) -> str:
    if get_active_llm_provider() == "deepseek":
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    return os.getenv(env_name, openai_default)


class _DeepSeekCompletions:
    def __init__(self, completions):
        self._completions = completions

    def create(self, **kwargs):
        response_format = kwargs.get("response_format")
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            kwargs["response_format"] = {"type": "json_object"}
        return self._completions.create(**kwargs)


class _DeepSeekChat:
    def __init__(self, chat):
        self.completions = _DeepSeekCompletions(chat.completions)


class _DeepSeekClient:
    def __init__(self, client):
        self.chat = _DeepSeekChat(client.chat)


CASUAL_QUERY_PATTERNS = (
    r"\bhow are you\b",
    r"\bwhat(?:'s| is) up\b",
    r"\bwho are you\b",
    r"\bhello\b",
    r"\bhi there\b",
    r"\bthank you\b",
    r"\bthanks\b",
)


def _local_context_relevance_score(
    question: str,
    retrieved_chunks: list[dict],
) -> int:
    question_tokens = tokenize(question)
    context_tokens = tokenize(
        " ".join(chunk.get("chunk_text", "") for chunk in retrieved_chunks)
    )
    return len(question_tokens & context_tokens)


def _has_local_context_match(question: str, retrieved_chunks: list[dict]) -> bool:
    """Avoid paying for an LLM call below the local relevance threshold."""
    normalized_question = question.strip().lower()
    if any(re.search(pattern, normalized_question) for pattern in CASUAL_QUERY_PATTERNS):
        return False

    return _local_context_relevance_score(question, retrieved_chunks) >= CHAT_RELEVANCE_THRESHOLD


def _raise_openai_error(error: OpenAIError, operation: str = "request"):
    provider_name = get_active_llm_provider().title()
    if isinstance(error, AuthenticationError):
        raise LLMProviderError(
            f"{provider_name} authentication failed. Check its API key in backend/.env."
        ) from error

    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        raise LLMProviderError(
            f"{provider_name} rate limit or usage quota reached during {operation}. Check the provider usage and billing."
        ) from error
    if status_code == 400 and operation == "lecture transcription":
        raise LLMProviderError(
            "OpenAI rejected this lecture audio chunk. Try recording again with microphone access enabled."
        ) from error

    raise LLMProviderError(f"{provider_name} {operation} failed. Please try again.") from error


def _get_openai_api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")


def _get_openai_client() -> OpenAI | None:
    provider = get_active_llm_provider()
    api_key_name = "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY"
    api_key = (os.getenv(api_key_name) or "").strip().strip('"').strip("'")
    if not api_key:
        return None
    if provider == "deepseek":
        return _DeepSeekClient(
            OpenAI(
                api_key=api_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )
        )
    return OpenAI(api_key=api_key)


@lru_cache(maxsize=1)
def _get_local_transcription_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise LLMProviderError(
            "Local transcription is not installed. Run pip install faster-whisper in backend\\venv."
        ) from error

    model_name = os.getenv("LOCAL_TRANSCRIPTION_MODEL", "small")
    device = os.getenv("LOCAL_TRANSCRIPTION_DEVICE", "cpu")
    compute_type = os.getenv(
        "LOCAL_TRANSCRIPTION_COMPUTE_TYPE",
        "int8" if device == "cpu" else "float16",
    )
    try:
        return WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )
    except Exception as error:
        raise LLMProviderError(
            f"Could not load local transcription model '{model_name}'."
        ) from error


def _transcribe_locally(file_obj) -> str:
    model = _get_local_transcription_model()
    try:
        file_obj.seek(0)
        segments, _ = model.transcribe(
            file_obj,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(
            segment.text.strip()
            for segment in segments
            if segment.text and segment.text.strip()
        ).strip()
    except Exception as error:
        raise LLMProviderError(
            "Local transcription failed for this audio chunk."
        ) from error


def transcribe_lecture_audio(file_obj, filename: str, content_type: str | None = None) -> str:
    """Transcribe a temporary audio chunk locally or through OpenAI when configured."""
    transcription_provider = os.getenv(
        "LECTURE_TRANSCRIPTION_PROVIDER",
        "local",
    ).strip().lower()
    if transcription_provider == "local":
        return _transcribe_locally(file_obj)
    if transcription_provider != "openai":
        raise LLMProviderError(
            "LECTURE_TRANSCRIPTION_PROVIDER must be 'local' or 'openai'."
        )

    client = _get_openai_client()
    if get_active_llm_provider() != "openai" or client is None:
        raise LLMProviderError("Lecture transcription requires an OpenAI API key.")

    try:
        normalized_content_type = (content_type or "").split(";", 1)[0].strip()
        response = client.audio.transcriptions.create(
            model=os.getenv("LECTURE_TRANSCRIPTION_MODEL", "whisper-1"),
            file=(filename, file_obj, normalized_content_type or "application/octet-stream"),
            response_format="text",
        )
    except OpenAIError as error:
        _raise_openai_error(error, "lecture transcription")

    return str(getattr(response, "text", response) or "").strip()


def generate_lecture_notes(title: str, transcript: str) -> dict | None:
    client = _get_openai_client()
    if not _remote_llm_enabled() or client is None or not transcript.strip():
        return None

    prompt = f"""
Turn this lecture transcript into accurate, structured study notes.
Use only the transcript. Do not invent missing facts. If something is incomplete,
put it in unclear_points instead of guessing. Keep formulas exactly as spoken when
possible and explain their symbols only when the transcript explains them.

Lecture: {title}
Transcript:
{transcript[:60000]}
"""
    try:
        response = client.chat.completions.create(
            model=_model_for("LECTURE_NOTES_MODEL", "gpt-5.4-mini"),
            messages=[
                {
                    "role": "system",
                    "content": LECTURE_NOTES_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "lecture_notes",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "overview": {"type": "string"},
                            "key_concepts": {"type": "array", "items": {"type": "string"}},
                            "definitions": {"type": "array", "items": {"type": "string"}},
                            "formulas": {"type": "array", "items": {"type": "string"}},
                            "examples": {"type": "array", "items": {"type": "string"}},
                            "questions": {"type": "array", "items": {"type": "string"}},
                            "unclear_points": {"type": "array", "items": {"type": "string"}},
                            "recap": {"type": "string"},
                        },
                        "required": [
                            "overview",
                            "key_concepts",
                            "definitions",
                            "formulas",
                            "examples",
                            "questions",
                            "unclear_points",
                            "recap",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
        )
        return json.loads(response.choices[0].message.content or "{}")
    except (LLMProviderError, OpenAIError, json.JSONDecodeError, TypeError, KeyError):
        return None


def build_context(retrieved_chunks: list[dict]) -> str:
    context_parts = []

    for index, chunk in enumerate(retrieved_chunks, start=1):
        context_parts.append(
            f"""
Source {index}
Filename: {chunk["filename"]}
Chunk index: {chunk["chunk_index"]}
Text:
{chunk["chunk_text"]}
"""
        )

    return "\n".join(context_parts)


def generate_mock_answer(question: str, retrieved_chunks: list[dict]) -> str:
    if not retrieved_chunks:
        return "I could not find this in the uploaded material."

    first_chunk = retrieved_chunks[0]

    return (
        "Based on the uploaded material, the most relevant section says:\n\n"
        f"{first_chunk['chunk_text'][:900]}...\n\n"
        f"Source: {first_chunk['filename']}, chunk {first_chunk['chunk_index']}"
    )


def generate_strict_answer(question: str, retrieved_chunks: list[dict]) -> str:
    if not retrieved_chunks:
        return "I could not find this in the uploaded material."

    if not _has_local_context_match(question, retrieved_chunks):
        return "I could not find this in the uploaded material."

    client = _get_openai_client()
    if not _remote_llm_enabled() or client is None:
        return generate_mock_answer(question, retrieved_chunks)

    context = build_context(retrieved_chunks)

    user_prompt = f"""
Question:
{question}

Uploaded document context:
{context}
"""

    try:
        response = client.chat.completions.create(
            model=_model_for("CHAT_MODEL", "gpt-4.1-mini"),
            messages=[
                {
                    "role": "system",
                    "content": RAG_ANSWER_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            temperature=0
        )
    except OpenAIError as error:
        _raise_openai_error(error, "answer generation")

    return response.choices[0].message.content


def edit_structured_notes(
    path: str,
    source_context: str,
    current_notes: dict,
    instruction: str,
) -> dict:
    """Rewrite one structured note document with the same model as Ask Tutor."""
    client = _get_openai_client()
    if not _remote_llm_enabled() or client is None:
        raise LLMProviderError("The AI notes editor is not configured.")

    prompt = f"""
Subtopic:
{path}

Student instruction:
{instruction}

Current structured notes (JSON):
{json.dumps(current_notes, ensure_ascii=False)}

Source material:
{source_context[:18000]}
"""
    try:
        response = client.chat.completions.create(
            model=_model_for("CHAT_MODEL", "gpt-4.1-mini"),
            messages=[
                {"role": "system", "content": NOTE_EDITOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "prompt_note_edit",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "notes": {
                                "type": "object",
                                "properties": {
                                    "overview": {"type": "string"},
                                    "sections": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "heading": {"type": "string"},
                                                "summary": {"type": "string"},
                                                "points": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                            "required": ["heading", "summary", "points"],
                                            "additionalProperties": False,
                                        },
                                    },
                                    "key_points": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "questions": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": [
                                    "overview",
                                    "sections",
                                    "key_points",
                                    "questions",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "required": ["message", "notes"],
                        "additionalProperties": False,
                    },
                },
            },
        )
    except OpenAIError as error:
        _raise_openai_error(error, "structured notes editing")

    try:
        payload = json.loads(response.choices[0].message.content or "{}")
        if not isinstance(payload.get("notes"), dict):
            raise TypeError("notes must be an object")
        return payload
    except (json.JSONDecodeError, TypeError, KeyError) as error:
        raise LLMProviderError(
            "The AI notes editor returned an invalid response. Please try again."
        ) from error


def infer_study_path(
    text: str,
    filename: str,
    existing_paths: list[str],
    enabled: bool | None = None,
) -> tuple[str, str, str] | None:
    if enabled is None:
        enabled = os.getenv("OUTLINE_LLM_ENABLED", "false").lower() == "true"
    if not enabled:
        return None

    client = _get_openai_client()
    if not _remote_llm_enabled() or client is None:
        return None

    known_tree = "\n".join(existing_paths)[:4000] or "No existing subject tree yet."
    prompt = f"""
Classify this uploaded study material into exactly one chapter, topic, and subtopic.
Use an existing path when the material is an extension of one of those topics.
Do not invent a chapter number unless it appears in the material.

Filename: {filename}

Existing subject paths:
{known_tree}

Material sample:
{text[:8000]}
"""

    try:
        response = client.chat.completions.create(
            model=_model_for("OUTLINE_MODEL", "gpt-5.4-nano"),
            messages=[
                {
                    "role": "system",
                    "content": STUDY_PATH_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "study_path",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "chapter": {"type": "string"},
                            "topic": {"type": "string"},
                            "subtopic": {"type": "string"},
                        },
                        "required": ["chapter", "topic", "subtopic"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
    except (OpenAIError, json.JSONDecodeError, TypeError, KeyError):
        # Outline refinement is optional; local organization must still complete.
        return None

    path = tuple(
        str(result[key]).strip()[:240]
        for key in ("chapter", "topic", "subtopic")
    )
    if not all(path):
        return None
    return path


def map_assignment_chunks(
    chunks: list[dict],
    candidate_nodes: list[dict],
) -> list[dict] | None:
    client = _get_openai_client()
    if not _remote_llm_enabled() or client is None or not candidate_nodes:
        return None

    candidates = "\n".join(
        f"{node['id']}: {node['path']}" for node in candidate_nodes
    )
    excerpts = "\n\n".join(
        f"Chunk {chunk['index']}:\n{chunk['text'][:1400]}" for chunk in chunks
    )
    prompt = f"""
Map each assignment chunk only to the leaf subtopics it clearly covers.
An empty node_ids list is correct when there is not enough evidence.
Never choose a merely related subtopic. Use multiple IDs only when a chunk explicitly
contains questions from multiple subtopics.

Allowed subtopics:
{candidates[:12000]}

Assignment chunks:
{excerpts[:24000]}
"""

    try:
        response = client.chat.completions.create(
            model=_model_for("ASSIGNMENT_MODEL", "gpt-5.4-nano"),
            messages=[
                {
                    "role": "system",
                    "content": ASSIGNMENT_MAPPING_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "assignment_mappings",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "mappings": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "chunk_index": {"type": "integer"},
                                        "node_ids": {
                                            "type": "array",
                                            "items": {"type": "integer"},
                                        },
                                        "confidence": {"type": "number"},
                                    },
                                    "required": [
                                        "chunk_index",
                                        "node_ids",
                                        "confidence",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["mappings"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        result = json.loads(response.choices[0].message.content or "{}")
        return result.get("mappings", [])
    except (OpenAIError, json.JSONDecodeError, TypeError, KeyError):
        return None


def generate_node_learning_content(
    path: str,
    context: str,
) -> dict | None:
    client = _get_openai_client()
    if not _remote_llm_enabled() or client is None:
        return None

    prompt = f"""
Create a compact learning page for this exact subtopic.
Stay grounded in the uploaded context. Explain formulas only when the context supports them.

Subtopic path: {path}

Uploaded context:
{context[:18000]}
"""
    try:
        response = client.chat.completions.create(
            model=_model_for("CONTENT_MODEL", "gpt-5.4-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{NODE_LEARNING_CONTENT_SYSTEM_PROMPT}\n\n"
                        f"{VISUALIZATION_SYSTEM_PROMPT}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "node_learning_content",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "explanation": {"type": "string"},
                            "analogy": {"type": "string"},
                            "worked_example": {"type": "string"},
                            "real_life_example": {"type": "string"},
                            "structured_sections": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "heading": {"type": "string"},
                                        "summary": {"type": "string"},
                                        "points": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": ["heading", "summary", "points"],
                                    "additionalProperties": False,
                                },
                            },
                            "formulas": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "expression": {"type": "string"},
                                        "symbols": {"type": "string"},
                                        "use_case": {"type": "string"},
                                    },
                                    "required": ["expression", "symbols", "use_case"],
                                    "additionalProperties": False,
                                },
                            },
                            "key_points": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "conceptual_questions": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "visualization": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "hierarchy",
                                            "process",
                                            "comparison",
                                            "cycle",
                                            "system",
                                            "concept_map",
                                        ],
                                    },
                                    "title": {"type": "string"},
                                    "main_idea": {"type": "string"},
                                    "nodes": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "string"},
                                                "label": {"type": "string"},
                                                "kind": {"type": "string"},
                                                "description": {"type": "string"},
                                                "group": {"type": "string"},
                                                "order": {"type": "integer"},
                                            },
                                            "required": [
                                                "id",
                                                "label",
                                                "kind",
                                                "description",
                                                "group",
                                                "order",
                                            ],
                                            "additionalProperties": False,
                                        },
                                    },
                                    "connections": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "source": {"type": "string"},
                                                "target": {"type": "string"},
                                                "label": {"type": "string"},
                                            },
                                            "required": ["source", "target", "label"],
                                            "additionalProperties": False,
                                        },
                                    },
                                },
                                "required": [
                                    "type",
                                    "title",
                                    "main_idea",
                                    "nodes",
                                    "connections",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "required": [
                            "explanation",
                            "analogy",
                            "worked_example",
                            "real_life_example",
                            "structured_sections",
                            "formulas",
                            "key_points",
                            "conceptual_questions",
                            "visualization",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
        )
        return json.loads(response.choices[0].message.content or "{}")
    except (OpenAIError, json.JSONDecodeError, TypeError, KeyError):
        return None


def generate_question_set(
    path: str,
    context: str,
    purpose: str,
    count: int = 5,
) -> list[dict] | None:
    client = _get_openai_client()
    if not _remote_llm_enabled() or client is None:
        return None

    prompt = f"""
Create {count} grounded multiple-choice questions for {purpose}.
Each question must have exactly four options and one exact correct_answer copied from
the options. Cover the supplied path only. Include the narrow concept being assessed.

Path: {path}

Source context:
{context[:22000]}
"""
    try:
        response = client.chat.completions.create(
            model=_model_for("QUESTION_MODEL", "gpt-5.4-nano"),
            messages=[
                {
                    "role": "system",
                    "content": QUESTION_SET_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "question_set",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "questions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "type": {
                                            "type": "string",
                                            "enum": ["multiple_choice"],
                                        },
                                        "question": {"type": "string"},
                                        "options": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "correct_answer": {"type": "string"},
                                        "explanation": {"type": "string"},
                                        "concept": {"type": "string"},
                                    },
                                    "required": [
                                        "id",
                                        "type",
                                        "question",
                                        "options",
                                        "correct_answer",
                                        "explanation",
                                        "concept",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["questions"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        result = json.loads(response.choices[0].message.content or "{}")
        return result.get("questions", [])
    except (OpenAIError, json.JSONDecodeError, TypeError, KeyError):
        return None
