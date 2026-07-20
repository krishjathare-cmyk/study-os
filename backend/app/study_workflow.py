import os
import re
from datetime import datetime, timedelta
from functools import lru_cache
from math import sqrt

from sqlalchemy.orm import Session

from app import models
from app.chunk_utils import split_text_into_chunks
from app.llm_provider import (
    generate_node_learning_content,
    generate_question_set,
    map_assignment_chunks,
)
from app.pdf_utils import PDFExtractionError, extract_pdf_pages
from app.retrieval_utils import calculate_relevance_score, tokenize


REVISION_INTERVALS = (4, 7, 15)
TOPIC_TEST_DEADLINE_DAYS = 15


def utc_now() -> datetime:
    return datetime.utcnow()


def node_path(node: models.StudyNode) -> str:
    titles = []
    cursor = node
    while cursor is not None:
        titles.append(cursor.title)
        cursor = cursor.parent
    return " > ".join(reversed(titles))


def descendant_leaf_ids(db: Session, node: models.StudyNode) -> list[int]:
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.subject_id == node.subject_id
    ).all()
    children = {}
    for item in nodes:
        children.setdefault(item.parent_id, []).append(item)

    leaves = []
    stack = [node]
    while stack:
        current = stack.pop()
        descendants = children.get(current.id, [])
        if current.node_type == "subtopic" or not descendants:
            leaves.append(current.id)
        else:
            stack.extend(descendants)
    return leaves


def node_chunk_rows(
    db: Session,
    node: models.StudyNode,
    include_descendants: bool = False,
) -> list[tuple]:
    node_ids = descendant_leaf_ids(db, node) if include_descendants else [node.id]
    return (
        db.query(models.DocumentChunk, models.Document.filename)
        .join(
            models.StudyNodeChunk,
            models.StudyNodeChunk.chunk_id == models.DocumentChunk.id,
        )
        .join(models.Document, models.Document.id == models.DocumentChunk.document_id)
        .filter(models.StudyNodeChunk.node_id.in_(node_ids))
        .order_by(models.DocumentChunk.document_id, models.DocumentChunk.chunk_index)
        .all()
    )


def node_context(
    db: Session,
    node: models.StudyNode,
    include_descendants: bool = False,
    max_chars: int = 22000,
) -> str:
    rows = node_chunk_rows(db, node, include_descendants=include_descendants)
    parts = [
        f"Source: {filename}\n{chunk.chunk_text}"
        for chunk, filename in rows
    ]
    return "\n\n".join(parts)[:max_chars]


@lru_cache(maxsize=32)
def _cached_pdf_pages(file_path: str, modified_at_ns: int) -> tuple[str, ...]:
    del modified_at_ns
    return tuple(extract_pdf_pages(file_path))


def node_source_pages(
    db: Session,
    node: models.StudyNode,
    limit: int = 4,
) -> list[dict]:
    """Locate the most relevant original PDF page for each document linked to a node."""
    rows = (
        db.query(models.DocumentChunk, models.Document)
        .join(
            models.StudyNodeChunk,
            models.StudyNodeChunk.chunk_id == models.DocumentChunk.id,
        )
        .join(models.Document, models.Document.id == models.DocumentChunk.document_id)
        .filter(models.StudyNodeChunk.node_id == node.id)
        .order_by(models.DocumentChunk.document_id, models.DocumentChunk.chunk_index)
        .all()
    )
    grouped: dict[int, dict] = {}
    for chunk, document in rows:
        entry = grouped.setdefault(document.id, {"document": document, "chunks": []})
        entry["chunks"].append(chunk.chunk_text)

    matches = []
    for entry in grouped.values():
        document = entry["document"]
        if not document.file_path or not os.path.isfile(document.file_path):
            continue
        try:
            modified_at_ns = os.stat(document.file_path).st_mtime_ns
            pages = _cached_pdf_pages(document.file_path, modified_at_ns)
        except (OSError, PDFExtractionError):
            continue
        if not pages:
            continue

        query = f"{node.title}\n" + "\n".join(entry["chunks"])
        ranked_pages = [
            (calculate_relevance_score(query[:16000], page_text), page_number)
            for page_number, page_text in enumerate(pages, start=1)
        ]
        score, page_number = max(ranked_pages, key=lambda item: (item[0], -item[1]))
        matches.append(
            {
                "document_id": document.id,
                "filename": document.filename,
                "page_number": page_number,
                "_score": score,
            }
        )

    matches.sort(key=lambda item: (-item["_score"], item["filename"].lower()))
    sources = []
    seen_filenames = set()
    for match in matches:
        filename_key = match["filename"].casefold()
        if filename_key in seen_filenames:
            continue
        seen_filenames.add(filename_key)
        sources.append(
            {key: value for key, value in match.items() if key != "_score"}
        )
        if len(sources) >= limit:
            break
    return sources


def _source_pages_for_question(
    db: Session,
    node: models.StudyNode,
    question: dict,
    page_cache: dict[str, list[str]],
) -> list[dict]:
    """Find likely textbook pages locally for a submitted practice question."""
    query = " ".join(
        str(question.get(field, ""))
        for field in ("question", "concept", "explanation")
    )
    document_rows = (
        db.query(models.Document)
        .join(models.DocumentChunk, models.DocumentChunk.document_id == models.Document.id)
        .join(models.StudyNodeChunk, models.StudyNodeChunk.chunk_id == models.DocumentChunk.id)
        .filter(models.StudyNodeChunk.node_id == node.id)
        .distinct()
        .all()
    )
    matches = []
    for document in document_rows:
        if document.file_path not in page_cache:
            try:
                page_cache[document.file_path] = extract_pdf_pages(document.file_path)
            except PDFExtractionError:
                page_cache[document.file_path] = []
        for page_number, page_text in enumerate(page_cache[document.file_path], start=1):
            score = calculate_relevance_score(query, page_text)
            if score:
                matches.append(
                    {
                        "filename": document.filename,
                        "page_number": page_number,
                        "score": score,
                    }
                )
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:2]


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
        if len(sentence.strip()) > 20
    ]


def _normalize_structured_sections(
    candidate: object,
    summary: str,
    key_points: list[str],
) -> list[dict]:
    if not isinstance(candidate, list):
        candidate = []
    sections = []
    for item in candidate[:8]:
        if not isinstance(item, dict):
            continue
        heading = " ".join(str(item.get("heading") or "").split())[:120]
        section_summary = " ".join(str(item.get("summary") or "").split())[:500]
        points = [
            " ".join(str(point).split())[:600]
            for point in (item.get("points") or [])[:8]
            if str(point).strip()
        ]
        if heading and (section_summary or points):
            sections.append(
                {
                    "heading": heading,
                    "summary": section_summary,
                    "points": points,
                }
            )
    if sections:
        return sections
    return [
        {
            "heading": "Core idea",
            "summary": summary[:500],
            "points": key_points[:8],
        }
    ]


def _fallback_learning_content(node: models.StudyNode, context: str) -> dict:
    sentences = _sentences(context)
    summary = " ".join(sentences[:5])[:1800]
    if not summary:
        summary = f"No readable source content is currently linked to {node.title}."

    formula_matches = re.findall(
        r"\b[A-Za-z][A-Za-z0-9_]*(?:\s*[+\-*/])?\s*=\s*[^.;\n]{2,100}",
        context,
    )
    formulas = [
        {"expression": value.strip(), "symbols": "", "use_case": "See source context."}
        for value in dict.fromkeys(formula_matches)
    ][:8]
    key_points = sentences[:6] or [summary]
    return {
        "explanation": summary,
        "analogy": (
            f"Think of {node.title} as one branch of the subject tree: first understand "
            "what enters the idea, what changes, and what result comes out."
        ),
        "worked_example": (
            f"Use the uploaded examples for {node.title}: identify the known values or "
            "claims, apply the rule from the notes, and check the result against its units."
        ),
        "real_life_example": (
            f"A familiar way to see {node.title} is to notice how it appears in an "
            "everyday activity or device. Identify what changes, what causes the "
            "change, and what result you observe."
        ),
        "structured_sections": [
            {
                "heading": "Core idea",
                "summary": summary[:500],
                "points": key_points[:8],
            }
        ],
        "formulas": formulas,
        "key_points": key_points,
        "conceptual_questions": [
            f"What is the main idea behind {node.title}?",
            f"When would you use {node.title}?",
            f"What common mistake could occur in {node.title}?",
        ],
    }


VISUAL_TYPES = {"hierarchy", "process", "comparison", "cycle", "system", "concept_map"}


def _compact_visual_label(value: str, limit: int = 48) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else f"{value[:limit - 3].rstrip()}..."


def _fallback_visualization(node: models.StudyNode, payload: dict) -> dict:
    """Build a useful local concept map when the visual planner is unavailable."""
    nodes = [
        {
            "id": "main",
            "label": _compact_visual_label(node.title, 32),
            "kind": "main",
            "description": payload.get("explanation", "The main idea of this subtopic."),
            "group": "main",
            "order": 0,
        }
    ]
    for index, point in enumerate(payload.get("key_points", [])[:6], start=1):
        nodes.append(
            {
                "id": f"idea_{index}",
                "label": _compact_visual_label(point, 42),
                "kind": "concept",
                "description": point,
                "group": "ideas",
                "order": index,
            }
        )
    for index, formula in enumerate(payload.get("formulas", [])[:2], start=1):
        expression = formula.get("expression", "") if isinstance(formula, dict) else str(formula)
        nodes.append(
            {
                "id": f"formula_{index}",
                "label": _compact_visual_label(expression, 42),
                "kind": "formula",
                "description": formula.get("use_case", "") if isinstance(formula, dict) else "",
                "group": "formulas",
                "order": len(nodes),
            }
        )
    return {
        "type": "concept_map",
        "title": node.title,
        "main_idea": payload.get("explanation", ""),
        "nodes": nodes,
        "connections": [
            {
                "source": "main",
                "target": item["id"],
                "label": "explains",
            }
            for item in nodes[1:]
        ],
    }


def _normalize_visualization(
    node: models.StudyNode,
    candidate: dict | None,
    payload: dict,
) -> dict:
    fallback = _fallback_visualization(node, payload)
    if not isinstance(candidate, dict) or candidate.get("type") not in VISUAL_TYPES:
        return fallback

    raw_nodes = candidate.get("nodes")
    if not isinstance(raw_nodes, list):
        return fallback
    nodes = []
    seen_ids = set()
    for index, item in enumerate(raw_nodes[:10]):
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or f"node_{index}")[:80]
        label = _compact_visual_label(item.get("label"), 56)
        if not label or node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "label": label,
                "kind": str(item.get("kind") or "concept")[:40],
                "description": str(item.get("description") or "")[:1200],
                "group": str(item.get("group") or "main")[:40],
                "order": int(item.get("order", index)),
            }
        )
    if not nodes:
        return fallback

    connections = []
    for item in candidate.get("connections", [])[:20]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        if source in seen_ids and target in seen_ids and source != target:
            connections.append(
                {
                    "source": source,
                    "target": target,
                    "label": _compact_visual_label(item.get("label"), 32),
                }
            )
    return {
        "type": candidate["type"],
        "title": _compact_visual_label(candidate.get("title") or node.title, 120),
        "main_idea": str(candidate.get("main_idea") or payload.get("explanation") or "")[:2400],
        "nodes": nodes,
        "connections": connections,
    }


def regenerate_learning_content(
    db: Session,
    node: models.StudyNode,
) -> models.NodeLearningContent:
    context = node_context(db, node)
    generated = generate_node_learning_content(node_path(node), context)
    payload = generated or _fallback_learning_content(node, context)
    payload["structured_sections"] = _normalize_structured_sections(
        payload.get("structured_sections"),
        payload.get("explanation", ""),
        payload.get("key_points", []),
    )
    visualization = _normalize_visualization(
        node,
        payload.pop("visualization", None),
        payload,
    )

    content = db.query(models.NodeLearningContent).filter_by(node_id=node.id).first()
    if content is None:
        content = models.NodeLearningContent(node_id=node.id, version=1, **payload)
        db.add(content)
    else:
        content.explanation = payload["explanation"]
        content.analogy = payload["analogy"]
        content.worked_example = payload["worked_example"]
        content.real_life_example = payload["real_life_example"]
        content.structured_sections = payload["structured_sections"]
        content.formulas = payload["formulas"]
        content.key_points = payload["key_points"]
        content.conceptual_questions = payload["conceptual_questions"]
        content.version += 1
        content.generated_at = utc_now()
    visual_record = db.query(models.NodeVisualization).filter_by(node_id=node.id).first()
    if visual_record is None:
        visual_record = models.NodeVisualization(node_id=node.id, **{
            "visual_type": visualization["type"],
            "title": visualization["title"],
            "main_idea": visualization["main_idea"],
            "nodes": visualization["nodes"],
            "connections": visualization["connections"],
        })
        db.add(visual_record)
    else:
        visual_record.visual_type = visualization["type"]
        visual_record.title = visualization["title"]
        visual_record.main_idea = visualization["main_idea"]
        visual_record.nodes = visualization["nodes"]
        visual_record.connections = visualization["connections"]
        visual_record.generated_at = utc_now()
    db.flush()
    return content


def ensure_node_visualization(
    db: Session,
    node: models.StudyNode,
) -> models.NodeVisualization:
    """Backfill a local visual plan for content created before this feature."""
    visual_record = db.query(models.NodeVisualization).filter_by(node_id=node.id).first()
    if visual_record is not None:
        return visual_record
    content = node.learning_content
    payload = {
        "explanation": content.explanation if content else "",
        "key_points": content.key_points if content else [],
        "formulas": content.formulas if content else [],
    }
    visualization = _fallback_visualization(node, payload)
    visual_record = models.NodeVisualization(
        node_id=node.id,
        visual_type=visualization["type"],
        title=visualization["title"],
        main_idea=visualization["main_idea"],
        nodes=visualization["nodes"],
        connections=visualization["connections"],
    )
    db.add(visual_record)
    db.flush()
    return visual_record


def regenerate_learning_for_nodes(db: Session, node_ids: list[int]) -> list[int]:
    generated_ids = []
    for node in db.query(models.StudyNode).filter(
        models.StudyNode.id.in_(set(node_ids)),
        models.StudyNode.node_type == "subtopic",
    ).all():
        regenerate_learning_content(db, node)
        generated_ids.append(node.id)
    return generated_ids


def _candidate_profiles(db: Session, subject_id: int) -> list[dict]:
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.subject_id == subject_id,
        models.StudyNode.node_type == "subtopic",
    ).order_by(models.StudyNode.id).all()
    profiles = []
    for node in nodes:
        path = node_path(node)
        context = node_context(db, node, max_chars=5000)
        profiles.append(
            {
                "id": node.id,
                "path": path,
                "path_tokens": tokenize(path),
                "context_tokens": tokenize(context),
            }
        )
    return profiles


def _local_mapping(text: str, profiles: list[dict]) -> tuple[list[int], float]:
    chunk_tokens = tokenize(text)
    ranked = []
    for profile in profiles:
        score, title_overlap, context_overlap = _profile_score(chunk_tokens, profile)
        confidence = min(
            0.95,
            score / max(8.0, sqrt(max(1, len(chunk_tokens))) * 3.0),
        )
        ranked.append((score, confidence, profile["id"], title_overlap, context_overlap))
    ranked.sort(reverse=True)
    if not ranked:
        return [], 0.0

    best = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0
    clearly_distinct = best[0] >= second_score + 3 or second_score == 0
    enough_evidence = best[3] >= 1 and best[4] >= 3 and best[1] >= 0.55
    if not clearly_distinct or not enough_evidence:
        return [], best[1]
    return [best[2]], best[1]


def _profile_score(chunk_tokens: set[str], profile: dict) -> tuple[int, int, int]:
    title_overlap = len(chunk_tokens & profile["path_tokens"])
    context_overlap = len(chunk_tokens & profile["context_tokens"])
    return (title_overlap * 4) + min(context_overlap, 12), title_overlap, context_overlap


def _batch_candidates(chunks: list[models.AssignmentChunk], profiles: list[dict]) -> list[dict]:
    selected_ids = set()
    for chunk in chunks:
        chunk_tokens = tokenize(chunk.chunk_text)
        ranked = sorted(
            profiles,
            key=lambda profile: _profile_score(chunk_tokens, profile)[0],
            reverse=True,
        )
        selected_ids.update(profile["id"] for profile in ranked[:10])
    return [profile for profile in profiles if profile["id"] in selected_ids][:200]


def create_and_map_assignment_chunks(
    db: Session,
    assignment: models.AssignmentDocument,
) -> tuple[list[models.AssignmentChunk], list[int]]:
    texts = split_text_into_chunks(
        assignment.extracted_text or "",
        chunk_size=450,
        overlap=60,
    )
    chunks = []
    for index, text in enumerate(texts):
        chunk = models.AssignmentChunk(
            assignment_document_id=assignment.id,
            subject_id=assignment.subject_id,
            chunk_text=text,
            chunk_index=index,
        )
        db.add(chunk)
        chunks.append(chunk)
    db.flush()

    profiles = _candidate_profiles(db, assignment.subject_id)
    allowed_ids = {profile["id"] for profile in profiles}
    ai_mappings = {}
    ai_was_available = False
    for start in range(0, len(chunks), 20):
        batch = chunks[start:start + 20]
        batch_profiles = _batch_candidates(batch, profiles)
        result = map_assignment_chunks(
            chunks=[{"index": item.chunk_index, "text": item.chunk_text} for item in batch],
            candidate_nodes=[
                {"id": profile["id"], "path": profile["path"]}
                for profile in batch_profiles
            ],
        )
        if result is None:
            continue
        ai_was_available = True
        for mapping in result:
            ai_mappings[mapping.get("chunk_index")] = mapping

    affected = set()
    for chunk in chunks:
        mapping = ai_mappings.get(chunk.chunk_index) if ai_was_available else None
        if mapping is not None:
            confidence = max(0.0, min(float(mapping.get("confidence", 0.0)), 1.0))
            node_ids = [
                node_id for node_id in mapping.get("node_ids", [])
                if node_id in allowed_ids
            ]
            if confidence < 0.65:
                node_ids = []
            method = "ai"
        else:
            node_ids, confidence = _local_mapping(chunk.chunk_text, profiles)
            method = "local"

        for node_id in dict.fromkeys(node_ids):
            db.add(
                models.AssignmentChunkNode(
                    chunk_id=chunk.id,
                    node_id=node_id,
                    confidence=confidence,
                    mapping_method=method,
                )
            )
            affected.add(node_id)
        chunk.mapping_status = "mapped" if node_ids else "unmapped"

    db.flush()
    return chunks, sorted(affected)


def _fallback_questions(title: str, context: str, count: int) -> list[dict]:
    sentences = _sentences(context)
    if not sentences:
        sentences = [f"The uploaded material covers {title}."]
    questions = []
    for index in range(count):
        correct = sentences[index % len(sentences)][:300]
        options = [
            correct,
            f"This statement is not supported for {title}.",
            f"A different chapter defines {title} this way.",
            f"There is no information about {title}.",
        ]
        questions.append(
            {
                "id": index + 1,
                "type": "multiple_choice",
                "question": f"Which statement is supported by the uploaded material about {title}?",
                "options": options,
                "correct_answer": correct,
                "explanation": correct,
                "concept": title,
            }
        )
    return questions


def _validated_questions(
    generated: list[dict] | None,
    title: str,
    context: str,
    count: int,
) -> list[dict]:
    if not generated:
        return _fallback_questions(title, context, count)
    output = []
    for index, question in enumerate(generated[:count], start=1):
        options = [str(value) for value in question.get("options", [])]
        correct = str(question.get("correct_answer", ""))
        if len(options) != 4 or correct not in options:
            continue
        output.append(
            {
                "id": index,
                "type": "multiple_choice",
                "question": str(question.get("question", "")),
                "options": options,
                "correct_answer": correct,
                "explanation": str(question.get("explanation", "")),
                "concept": str(question.get("concept", title)),
            }
        )
    return output or _fallback_questions(title, context, count)


def generate_practice_set(
    db: Session,
    node: models.StudyNode,
    assignment: models.AssignmentDocument,
) -> models.PracticeSet:
    existing = db.query(models.PracticeSet).filter_by(
        node_id=node.id,
        source_assignment_id=assignment.id,
    ).first()
    if existing is not None:
        return existing

    assignment_chunks = (
        db.query(models.AssignmentChunk)
        .join(models.AssignmentChunkNode)
        .filter(
            models.AssignmentChunk.assignment_document_id == assignment.id,
            models.AssignmentChunkNode.node_id == node.id,
        )
        .order_by(models.AssignmentChunk.chunk_index)
        .all()
    )
    assignment_context = "\n\n".join(chunk.chunk_text for chunk in assignment_chunks)
    context = f"Study material:\n{node_context(db, node)}\n\nAssignment material:\n{assignment_context}"
    generated = generate_question_set(
        node_path(node),
        context,
        purpose="subtopic practice",
        count=5,
    )
    practice = models.PracticeSet(
        node_id=node.id,
        source_assignment_id=assignment.id,
        title=f"Practice: {node.title}",
        questions=_validated_questions(generated, node.title, context, 5),
    )
    db.add(practice)
    db.flush()
    return practice


def generate_study_practice_set(
    db: Session,
    node: models.StudyNode,
    refresh: bool = False,
) -> models.PracticeSet:
    existing = db.query(models.PracticeSet).filter(
        models.PracticeSet.node_id == node.id,
        models.PracticeSet.source_assignment_id.is_(None),
    ).first()
    if existing is not None and not refresh:
        return existing

    context = node_context(db, node)
    generated = generate_question_set(
        node_path(node),
        context,
        purpose="subtopic practice from study material",
        count=5,
    )
    questions = _validated_questions(generated, node.title, context, 5)
    if existing is None:
        practice = models.PracticeSet(
            node_id=node.id,
            source_assignment_id=None,
            title=f"Practice: {node.title}",
            questions=questions,
        )
        db.add(practice)
    else:
        practice = existing
        practice.questions = questions
        practice.generated_at = utc_now()
    db.flush()
    return practice


def regenerate_study_practice_for_nodes(db: Session, node_ids: list[int]) -> list[int]:
    generated_ids = []
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.id.in_(set(node_ids)),
        models.StudyNode.node_type == "subtopic",
    ).all()
    for node in nodes:
        generate_study_practice_set(db, node, refresh=True)
        generated_ids.append(node.id)
    return generated_ids


def generate_practice_for_assignment(
    db: Session,
    assignment: models.AssignmentDocument,
    node_ids: list[int],
) -> list[models.PracticeSet]:
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.id.in_(node_ids),
        models.StudyNode.node_type == "subtopic",
    ).all()
    return [generate_practice_set(db, node, assignment) for node in nodes]


def generate_topic_test(
    db: Session,
    user_id: int,
    topic: models.StudyNode,
    completed_at: datetime | None = None,
    activate: bool = True,
    refresh: bool = False,
) -> models.TopicTest:
    existing = db.query(models.TopicTest).filter_by(
        user_id=user_id,
        node_id=topic.id,
    ).first()
    if existing is not None and activate and existing.status == "locked":
        existing.status = "pending"
        existing.due_at = (completed_at or utc_now()) + timedelta(
            days=TOPIC_TEST_DEADLINE_DAYS
        )
        db.flush()
        return existing
    if existing is not None and (not refresh or existing.status != "locked"):
        return existing

    leaf_ids = descendant_leaf_ids(db, topic)
    study_context = node_context(db, topic, include_descendants=True)
    assignment_chunks = (
        db.query(models.AssignmentChunk)
        .join(models.AssignmentChunkNode)
        .filter(models.AssignmentChunkNode.node_id.in_(leaf_ids))
        .order_by(models.AssignmentChunk.id)
        .limit(20)
        .all()
    )
    assignment_context = "\n\n".join(chunk.chunk_text for chunk in assignment_chunks)
    context = f"Study material:\n{study_context}\n\nAssignment material:\n{assignment_context}"
    generated = generate_question_set(
        node_path(topic),
        context,
        purpose="a proctored-style topic test",
        count=10,
    )
    questions = _validated_questions(generated, topic.title, context, 10)
    created = completed_at or utc_now()
    if existing is None:
        test = models.TopicTest(
            user_id=user_id,
            node_id=topic.id,
            title=f"Topic test: {topic.title}",
            questions=questions,
            status="pending" if activate else "locked",
            due_at=created + timedelta(days=TOPIC_TEST_DEADLINE_DAYS),
        )
        db.add(test)
    else:
        test = existing
        test.questions = questions
    db.flush()
    return test


def pregenerate_topic_tests_for_nodes(
    db: Session,
    user_id: int,
    node_ids: list[int],
) -> list[int]:
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.id.in_(set(node_ids))
    ).all()
    topic_ids = {
        node.id if node.node_type == "topic" else node.parent_id
        for node in nodes
        if node.node_type in {"topic", "subtopic"}
    }
    topics = db.query(models.StudyNode).filter(
        models.StudyNode.id.in_(topic_ids),
        models.StudyNode.node_type == "topic",
    ).all()
    for topic in topics:
        generate_topic_test(
            db,
            user_id,
            topic,
            activate=False,
            refresh=True,
        )
    return [topic.id for topic in topics]


def schedule_revisions(
    db: Session,
    user_id: int,
    node: models.StudyNode,
    completed_at: datetime,
) -> list[models.RevisionSchedule]:
    revisions = []
    for interval in REVISION_INTERVALS:
        revision = db.query(models.RevisionSchedule).filter_by(
            user_id=user_id,
            node_id=node.id,
            interval_days=interval,
        ).first()
        if revision is None:
            revision = models.RevisionSchedule(
                user_id=user_id,
                node_id=node.id,
                interval_days=interval,
                due_at=completed_at + timedelta(days=interval),
            )
            db.add(revision)
        else:
            revision.due_at = completed_at + timedelta(days=interval)
            revision.status = "pending"
            revision.completed_at = None
        revisions.append(revision)
    db.flush()
    return revisions


def set_node_completion(
    db: Session,
    user_id: int,
    node: models.StudyNode,
    completed: bool,
) -> tuple[models.NodeProgress, list[models.RevisionSchedule], models.TopicTest | None]:
    progress = db.query(models.NodeProgress).filter_by(
        user_id=user_id,
        node_id=node.id,
    ).first()
    if progress is None:
        progress = models.NodeProgress(user_id=user_id, node_id=node.id)
        db.add(progress)

    if not completed:
        progress.status = "not_started"
        progress.completed_at = None
        revisions = db.query(models.RevisionSchedule).filter_by(
            user_id=user_id,
            node_id=node.id,
        ).all()
        for revision in revisions:
            revision.status = "cancelled"
        db.flush()
        return progress, revisions, None

    completed_at = utc_now()
    progress.status = "completed"
    progress.completed_at = completed_at
    revisions = schedule_revisions(db, user_id, node, completed_at)
    topic_test = None

    if node.node_type == "subtopic":
        generate_study_practice_set(db, node)

    topic = node if node.node_type == "topic" else node.parent
    if topic is not None and topic.node_type == "topic":
        leaf_ids = descendant_leaf_ids(db, topic)
        completed_leaf_ids = {
            row.node_id for row in db.query(models.NodeProgress).filter(
                models.NodeProgress.user_id == user_id,
                models.NodeProgress.node_id.in_(leaf_ids),
                models.NodeProgress.status == "completed",
            ).all()
        }
        topic_is_complete = node.node_type == "topic" or set(leaf_ids) <= completed_leaf_ids
        if topic_is_complete:
            topic_progress = db.query(models.NodeProgress).filter_by(
                user_id=user_id,
                node_id=topic.id,
            ).first()
            if topic_progress is None:
                topic_progress = models.NodeProgress(user_id=user_id, node_id=topic.id)
                db.add(topic_progress)
            topic_progress.status = "completed"
            topic_progress.completed_at = completed_at
            topic_test = generate_topic_test(
                db,
                user_id,
                topic,
                completed_at,
                activate=True,
            )

    db.flush()
    return progress, revisions, topic_test


def grade_topic_test(
    db: Session,
    test: models.TopicTest,
    user_id: int,
    answers: dict[str, str],
) -> models.TestAttempt:
    correct = 0
    concept_results = {}
    feedback = []
    for question in test.questions:
        question_id = str(question["id"])
        submitted = answers.get(question_id, "")
        is_correct = submitted.strip() == str(question["correct_answer"]).strip()
        correct += int(is_correct)
        concept = question.get("concept", "General")
        result = concept_results.setdefault(concept, {"correct": 0, "total": 0})
        result["total"] += 1
        result["correct"] += int(is_correct)
        feedback.append(
            {
                "question_id": question["id"],
                "correct": is_correct,
                "explanation": question.get("explanation", ""),
            }
        )

    total = len(test.questions)
    percentage = round((correct / total * 100) if total else 0.0, 2)
    weak_concepts = [
        concept for concept, result in concept_results.items()
        if result["correct"] < result["total"]
    ]
    attempt = models.TestAttempt(
        test_id=test.id,
        user_id=user_id,
        answers=answers,
        score=float(correct),
        max_score=float(total),
        percentage=percentage,
        analytics={
            "concepts": concept_results,
            "weak_concepts": weak_concepts,
            "question_feedback": feedback,
        },
    )
    test.status = "submitted"
    test.submitted_at = utc_now()
    db.add(attempt)
    db.flush()
    return attempt


def grade_practice_set(
    db: Session,
    practice: models.PracticeSet,
    user_id: int,
    answers: dict[str, str],
) -> models.PracticeAttempt:
    correct = 0
    concept_results = {}
    feedback = []
    page_cache: dict[str, list[str]] = {}
    node = db.query(models.StudyNode).filter_by(id=practice.node_id).first()
    for question in practice.questions:
        question_id = str(question["id"])
        submitted = answers.get(question_id, "")
        is_correct = submitted.strip() == str(question["correct_answer"]).strip()
        correct += int(is_correct)
        concept = question.get("concept", "General")
        result = concept_results.setdefault(concept, {"correct": 0, "total": 0})
        result["total"] += 1
        result["correct"] += int(is_correct)
        feedback.append(
            {
                "question_id": question["id"],
                "correct": is_correct,
                "selected_answer": submitted,
                "correct_answer": question["correct_answer"],
                "explanation": question.get("explanation", ""),
                "source_pages": _source_pages_for_question(
                    db,
                    node,
                    question,
                    page_cache,
                ) if node is not None else [],
            }
        )

    total = len(practice.questions)
    percentage = round((correct / total * 100) if total else 0.0, 2)
    weak_concepts = [
        concept for concept, result in concept_results.items()
        if result["correct"] < result["total"]
    ]
    attempt = models.PracticeAttempt(
        practice_set_id=practice.id,
        user_id=user_id,
        answers=answers,
        score=float(correct),
        max_score=float(total),
        percentage=percentage,
        analytics={
            "concepts": concept_results,
            "weak_concepts": weak_concepts,
            "question_feedback": feedback,
        },
    )
    db.add(attempt)
    db.flush()
    return attempt


def public_questions(questions: list[dict]) -> list[dict]:
    return [
        {
            "id": question["id"],
            "type": question.get("type", "multiple_choice"),
            "question": question["question"],
            "options": question.get("options", []),
        }
        for question in questions
    ]


def days_overdue(due_at: datetime, now: datetime | None = None) -> int:
    current = now or utc_now()
    if due_at >= current:
        return 0
    return (current.date() - due_at.date()).days
