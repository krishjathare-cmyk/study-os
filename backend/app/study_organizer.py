import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.chunk_utils import split_text_into_chunks
from app.llm_provider import infer_study_path
from app.pdf_utils import StyledPDFLine, extract_styled_pdf_lines


NODE_TYPES = {1: "chapter", 2: "topic", 3: "subtopic"}
CHAPTER_WORD_NUMBERS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
}
IGNORED_HEADING_PREFIXES = (
    "activity",
    "caution",
    "example",
    "exercise",
    "fig.",
    "figure",
    "more to know",
    "question",
    "summary",
    "table",
)


@dataclass(frozen=True)
class NodeSpec:
    title: str
    level: int
    heading_number: str | None = None
    is_generated: bool = False
    confidence: float = 1.0

    @property
    def node_type(self) -> str:
        return NODE_TYPES[self.level]


@dataclass
class OrganizedSection:
    path: list[NodeSpec]
    text: str


@dataclass
class OrganizationResult:
    skipped: bool = False
    nodes_created: int = 0
    chunk_texts: list[str] = field(default_factory=list)
    subtopic_ids: list[int] = field(default_factory=list)

    @property
    def chunks_linked(self) -> int:
        return len(self.chunk_texts)


def normalize_title(title: str) -> str:
    value = re.sub(r"^chapter\s+\d+\s*[:.\-]?\s*", "", title, flags=re.IGNORECASE)
    value = re.sub(r"^\d+(?:\.\d+)*\s*[:.\-)]?\s*", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(value.split()) or "untitled"


def _dedupe_repeated_line(line: str) -> str:
    line = " ".join(line.split()).strip()
    for repeat_count in range(6, 1, -1):
        if len(line) % repeat_count != 0:
            continue
        part_length = len(line) // repeat_count
        part = line[:part_length]
        if part and part * repeat_count == line:
            return part.strip()
    return line


def _prepare_lines(
    text: str,
    styled_lines: list[StyledPDFLine] | None = None,
) -> tuple[list[str], list[StyledPDFLine | None]]:
    if styled_lines:
        prepared = []
        for styled_line in styled_lines:
            cleaned = _dedupe_repeated_line(styled_line.text)
            if cleaned:
                prepared.append(
                    StyledPDFLine(
                        text=cleaned,
                        page_number=styled_line.page_number,
                        font_size=styled_line.font_size,
                        font_name=styled_line.font_name,
                        is_bold=styled_line.is_bold,
                        block_number=styled_line.block_number,
                        y_position=styled_line.y_position,
                    )
                )

        lines = []
        styles = []
        index = 0
        while index < len(prepared):
            current = prepared[index]

            # Some PDFs encode a chapter number, the word CHAPTER, and its
            # title as separate visual lines. Join them before classification.
            if (
                re.fullmatch(r"\d{1,3}", current.text)
                and index + 2 < len(prepared)
                and prepared[index + 1].text.strip().lower() == "chapter"
            ):
                title_block = prepared[index + 2].block_number
                title_page = prepared[index + 2].page_number
                title_parts = []
                cursor = index + 2
                while (
                    cursor < len(prepared)
                    and prepared[cursor].page_number == title_page
                    and prepared[cursor].block_number == title_block
                ):
                    title_parts.append(prepared[cursor].text)
                    cursor += 1
                merged_text = f"Chapter {current.text}: {' '.join(title_parts)}"
                merged_style = prepared[index + 2]
                lines.append(merged_text)
                styles.append(
                    StyledPDFLine(
                        text=merged_text,
                        page_number=merged_style.page_number,
                        font_size=merged_style.font_size,
                        font_name=merged_style.font_name,
                        is_bold=merged_style.is_bold,
                        block_number=merged_style.block_number,
                        y_position=merged_style.y_position,
                    )
                )
                index = cursor
                continue

            # Repeated spans at the same position are common in textbook PDFs.
            # Keep the longest copy, which usually contains the full word.
            group = [current]
            cursor = index + 1
            while cursor < len(prepared):
                candidate = prepared[cursor]
                same_position = (
                    candidate.page_number == current.page_number
                    and candidate.block_number == current.block_number
                    and abs(candidate.y_position - current.y_position) <= 2
                    and abs(candidate.font_size - current.font_size) <= 0.5
                )
                if not same_position:
                    break
                group.append(candidate)
                cursor += 1
            selected = max(group, key=lambda item: len(item.text))
            lines.append(selected.text)
            styles.append(selected)
            index = cursor
        return lines, styles

    lines = []
    for raw_line in text.replace("\x00", "").splitlines():
        lines.append(_dedupe_repeated_line(raw_line))
    return lines, [None] * len(lines)


def _body_font_size(styled_lines: list[StyledPDFLine]) -> float | None:
    """Find the dominant font size, weighted by the amount of text."""
    if not styled_lines:
        return None
    buckets: dict[float, int] = {}
    for line in styled_lines:
        size = round(line.font_size * 2) / 2
        buckets[size] = buckets.get(size, 0) + len(line.text)
    return max(buckets, key=buckets.get)


def _style_ratio(style: StyledPDFLine | None, body_font_size: float | None) -> float:
    if style is None or not body_font_size:
        return 1.0
    return style.font_size / body_font_size


def _heading_size_levels(
    styled_lines: list[StyledPDFLine],
    body_font_size: float | None,
) -> dict[float, int]:
    """Rank rare, larger text styles instead of using fixed PDF sizes."""
    if not body_font_size:
        return {}
    candidate_sizes = {
        round(line.font_size * 2) / 2
        for line in styled_lines
        if 2 <= len(line.text.split()) <= 14
        and sum(character.isalpha() for character in line.text) >= 4
        and len(line.text) <= 120
        and not line.text.rstrip().endswith((".", "?", "!", ";"))
        and (
            line.is_bold
            or line.font_size / body_font_size >= 1.15
        )
        and line.font_size / body_font_size >= 1.08
    }
    return {
        size: level
        for level, size in enumerate(sorted(candidate_sizes, reverse=True)[:3], start=1)
    }


def _style_heading_level(
    style: StyledPDFLine,
    body_font_size: float | None,
    has_topic: bool,
    size_levels: dict[float, int] | None = None,
) -> int:
    size = round(style.font_size * 2) / 2
    if size_levels and size in size_levels:
        return size_levels[size]
    ratio = _style_ratio(style, body_font_size)
    if ratio >= 1.55:
        return 1
    if ratio >= 1.25:
        return 2
    return 3 if has_topic else 2


def _is_page_noise(line: str) -> bool:
    lowered = line.lower()
    return bool(
        re.fullmatch(r"\d{4}[\-–]\d{2}", line)
        or re.fullmatch(r"[a-z][a-z\s\-–]{1,40}\d{1,4}", lowered)
        or re.fullmatch(r"\d{1,4}", line)
    )


def _clean_heading_title(title: str) -> str:
    title = _dedupe_repeated_line(title)
    title = re.sub(r"\s+", " ", title).strip(" :-–—.\t")
    title = re.sub(
        r"\b([A-Z]{4,})\s+(AL|IC|ING|TION|ED|S)\b",
        lambda match: "".join(match.groups()),
        title,
    )
    title = re.sub(
        r"\b([B-HJ-Z])\s+([a-z]{2,})\b",
        lambda match: "".join(match.groups()),
        title,
    )
    return title[:240]


def _previous_chapter_title(lines: list[str], index: int) -> str | None:
    parts = []
    cursor = index - 1
    while cursor >= 0 and len(parts) < 3:
        candidate = lines[cursor].strip()
        cursor -= 1
        if not candidate:
            if parts:
                break
            continue
        if _is_page_noise(candidate):
            break
        if len(candidate) > 80 or candidate.endswith((".", "?", "!")):
            break
        if any(operator in candidate for operator in ("=", "+", "×", "÷", "Ω", "Ω")):
            break
        if candidate.lower().startswith(IGNORED_HEADING_PREFIXES):
            break
        if not re.search(r"[A-Za-z]", candidate):
            break
        parts.append(candidate)

    if not parts:
        return None
    return _clean_heading_title(" ".join(reversed(parts)))


def _chapter_heading(lines: list[str], index: int) -> NodeSpec | None:
    line = lines[index].strip()
    full_match = re.fullmatch(
        r"chapter\s*(\d{1,3})\s*[:.\-–]?\s*(.+)",
        line,
        flags=re.IGNORECASE,
    )
    if full_match:
        number, title = full_match.groups()
        return NodeSpec(
            title=_clean_heading_title(title) or f"Chapter {number}",
            level=1,
            heading_number=number,
        )

    word_match = re.fullmatch(
        r"chapter\s+(one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen)",
        line,
        flags=re.IGNORECASE,
    )
    if word_match:
        word_number = word_match.group(1).lower()
        number = CHAPTER_WORD_NUMBERS[word_number]
        title_parts = []
        for candidate in lines[index + 1:index + 4]:
            candidate = candidate.strip()
            if not candidate or _is_page_noise(candidate):
                continue
            if re.match(r"\d+(?:\.\d+)+\b", candidate):
                break
            if candidate.endswith((".", "?", "!")):
                break
            if not re.search(r"[A-Za-z]", candidate):
                break
            title_parts.append(candidate)
        title = _clean_heading_title(" ".join(title_parts))
        return NodeSpec(
            title=title or f"Chapter {number}",
            level=1,
            heading_number=number,
            confidence=0.98,
        )

    marker_match = re.fullmatch(
        r"(?:chapter\s*)?(\d{1,3})\s*chapter|chapter\s*(\d{1,3})",
        line,
        flags=re.IGNORECASE,
    )
    if not marker_match:
        return None

    number = marker_match.group(1) or marker_match.group(2)
    title = _previous_chapter_title(lines, index) or f"Chapter {number}"
    return NodeSpec(title=title, level=1, heading_number=number, confidence=0.95)


def _numbered_heading(
    line: str,
    style: StyledPDFLine | None = None,
    body_font_size: float | None = None,
) -> NodeSpec | None:
    number_prefix = re.match(r"(\d+(?:\.\d+){0,4})", line.strip())
    if number_prefix:
        repeated_number = number_prefix.group(1)
        occurrences = re.split(re.escape(repeated_number), line.strip())[1:]
        if len(occurrences) > 1:
            first_fragment = occurrences[0].strip()
            if first_fragment and all(
                fragment.strip().startswith(first_fragment) for fragment in occurrences
            ):
                remainder = "".join(
                    fragment.strip()[len(first_fragment):] for fragment in occurrences
                )
                rebuilt_title = _clean_heading_title(
                    f"{first_fragment} {_dedupe_repeated_line(remainder)}"
                )
                line = f"{repeated_number} {rebuilt_title}"

    match = re.fullmatch(
        r"(\d+(?:\.\d+){0,4})\s*[:.\-–)]?\s+(.+)",
        line.strip(),
    )
    if not match:
        return None

    number, title = match.groups()
    title = _clean_heading_title(title)
    if number.split(".")[0] == "0":
        return None
    letter_count = sum(character.isalpha() for character in title)
    if (
        not title
        or letter_count < 4
        or (
            not title[0].isupper()
            and not (
                style
                and (
                    style.is_bold
                    or _style_ratio(style, body_font_size) >= 1.15
                )
            )
        )
        or len(title) > 100
        or len(title.split()) > 12
        or title.lower().startswith(IGNORED_HEADING_PREFIXES)
        or any(operator in title for operator in ("=", "+", "×", "÷", "Ω", "Ω"))
    ):
        return None

    level = min(len(number.split(".")), 3)
    return NodeSpec(title=title, level=level, heading_number=number)


def _unnumbered_heading(
    line: str,
    has_topic: bool,
    style: StyledPDFLine | None = None,
    body_font_size: float | None = None,
    size_levels: dict[float, int] | None = None,
) -> NodeSpec | None:
    title = _clean_heading_title(line)
    words = title.split()
    letters = [character for character in title if character.isalpha()]
    if (
        len(letters) < 4
        or len(words) < 2
        or len(words) > 12
        or len(title) > 100
        or any(operator in title for operator in ("=", "+", "×", "÷", "Ω", "Ω"))
    ):
        return None
    if title.lower().startswith(IGNORED_HEADING_PREFIXES):
        return None
    styled_candidate = bool(
        style
        and (
            style.is_bold
            or _style_ratio(style, body_font_size) >= 1.15
        )
    )
    if not title.isupper() and not styled_candidate:
        return None

    level = (
        _style_heading_level(style, body_font_size, has_topic, size_levels)
        if styled_candidate and style
        else (3 if has_topic else 2)
    )
    return NodeSpec(title=title.title(), level=level, confidence=0.75)


def _generated_spec(title: str, level: int, confidence: float = 0.5) -> NodeSpec:
    return NodeSpec(
        title=title,
        level=level,
        is_generated=True,
        confidence=confidence,
    )


def _default_chapter(filename: str, major_number: str | None = None) -> NodeSpec:
    if major_number:
        return NodeSpec(
            title=f"Chapter {major_number}",
            level=1,
            heading_number=major_number,
            is_generated=True,
            confidence=0.7,
        )
    return _generated_spec(Path(filename).stem.replace("_", " "), 1, confidence=0.4)


def _ensure_leaf_path(path: list[NodeSpec], filename: str) -> list[NodeSpec]:
    completed = list(path[:3])
    if not completed:
        completed.append(_default_chapter(filename))
    if len(completed) == 1:
        completed.append(_generated_spec("Introduction", 2))
    if len(completed) == 2:
        completed.append(_generated_spec("Overview", 3))
    return completed


def _apply_inferred_path(
    sections: list[OrganizedSection],
    inferred_path: tuple[str, str, str] | None,
) -> list[OrganizedSection]:
    if not inferred_path:
        return sections

    inferred_specs = [
        _generated_spec(title, level, confidence=0.7)
        for level, title in enumerate(inferred_path, start=1)
    ]
    output = []
    for section in sections:
        path = [
            inferred_specs[index] if spec.is_generated else spec
            for index, spec in enumerate(section.path)
        ]
        output.append(OrganizedSection(path=path, text=section.text))
    return output


def extract_outline_sections(
    text: str,
    filename: str,
    use_llm: bool | None = None,
    existing_paths: list[str] | None = None,
    styled_lines: list[StyledPDFLine] | None = None,
) -> list[OrganizedSection]:
    lines, line_styles = _prepare_lines(text, styled_lines)
    body_font_size = _body_font_size(styled_lines or [])
    size_levels = _heading_size_levels(styled_lines or [], body_font_size)
    current_path: list[NodeSpec] = []
    body_lines: list[str] = []
    sections: list[OrganizedSection] = []
    explicit_headings = 0

    def flush_body():
        nonlocal body_lines
        body = "\n".join(body_lines).strip()
        body_lines = []
        if not body:
            return
        leaf_path = _ensure_leaf_path(current_path, filename)
        text_with_context = f"{leaf_path[-1].title}\n{body}"
        sections.append(OrganizedSection(path=leaf_path, text=text_with_context))

    for index, line in enumerate(lines):
        stripped = line.strip()
        style = line_styles[index]
        if not stripped:
            if body_lines and body_lines[-1] != "":
                body_lines.append("")
            continue

        heading = _chapter_heading(lines, index)
        if heading is None:
            heading = _numbered_heading(stripped, style, body_font_size)
        if heading is None:
            heading = _unnumbered_heading(
                stripped,
                has_topic=len(current_path) >= 2,
                style=style,
                body_font_size=body_font_size,
                size_levels=size_levels,
            )

        if heading is None:
            if not _is_page_noise(stripped):
                body_lines.append(stripped)
            continue

        if heading.level >= 2 and heading.heading_number and current_path:
            current_chapter_number = current_path[0].heading_number
            heading_chapter_number = heading.heading_number.split(".")[0]
            if (
                current_chapter_number
                and heading_chapter_number.isdigit()
                and current_chapter_number.isdigit()
                and int(heading_chapter_number) < int(current_chapter_number)
            ):
                # Lower numbered references and exercise labels belong to the
                # current chapter; they must not create a false new root.
                body_lines.append(stripped)
                continue

        explicit_headings += 1
        if current_path:
            flush_body()
        else:
            body_lines = []

        if heading.level == 1:
            current_path = [heading]
            continue

        major_number = heading.heading_number.split(".")[0] if heading.heading_number else None
        current_chapter = current_path[0] if current_path else None
        if (
            current_chapter is None
            or (
                major_number
                and current_chapter.heading_number
                and current_chapter.heading_number != major_number
            )
        ):
            chapter = _default_chapter(filename, major_number)
        else:
            chapter = current_chapter
        if heading.level == 2:
            current_path = [chapter, heading]
            continue

        if len(current_path) >= 2:
            topic = current_path[1]
        elif heading.heading_number:
            topic_number = ".".join(heading.heading_number.split(".")[:2])
            topic = NodeSpec(
                title=f"Section {topic_number}",
                level=2,
                heading_number=topic_number,
                is_generated=True,
                confidence=0.7,
            )
        else:
            topic = _generated_spec("General", 2)
        current_path = [chapter, topic, heading]

    flush_body()

    if not sections and text.strip():
        path = _ensure_leaf_path([], filename)
        sections = [OrganizedSection(path=path, text=text.strip())]

    should_infer = explicit_headings < 2 and any(section.text for section in sections)
    if should_infer:
        sample = "\n\n".join(section.text for section in sections)[:8000]
        inferred_path = infer_study_path(
            text=sample,
            filename=filename,
            existing_paths=existing_paths or [],
            enabled=use_llm,
        )
        sections = _apply_inferred_path(sections, inferred_path)

    return sections


def _find_or_create_node(
    db: Session,
    subject_id: int,
    parent_id: int | None,
    spec: NodeSpec,
) -> tuple[models.StudyNode, bool]:
    query = db.query(models.StudyNode).filter(
        models.StudyNode.subject_id == subject_id,
        models.StudyNode.parent_id.is_(None)
        if parent_id is None
        else models.StudyNode.parent_id == parent_id,
    )

    node = None
    if spec.heading_number:
        node = query.filter(models.StudyNode.heading_number == spec.heading_number).first()
    if node is None:
        node = query.filter(
            models.StudyNode.normalized_title == normalize_title(spec.title)
        ).first()
    if node is not None:
        if node.is_generated and not spec.is_generated:
            node.title = spec.title
            node.normalized_title = normalize_title(spec.title)
            node.is_generated = False
            node.confidence = spec.confidence
        return node, False

    max_order = query.with_entities(func.max(models.StudyNode.sort_order)).scalar()
    node = models.StudyNode(
        subject_id=subject_id,
        parent_id=parent_id,
        title=spec.title,
        normalized_title=normalize_title(spec.title),
        node_type=spec.node_type,
        level=spec.level,
        heading_number=spec.heading_number,
        sort_order=(max_order or 0) + 1,
        is_generated=spec.is_generated,
        confidence=spec.confidence,
    )
    db.add(node)
    db.flush()
    return node, True


def existing_subject_paths(db: Session, subject_id: int) -> list[str]:
    nodes = db.query(models.StudyNode).filter(
        models.StudyNode.subject_id == subject_id
    ).all()
    by_id = {node.id: node for node in nodes}
    paths = []
    for node in nodes:
        if node.node_type != "subtopic":
            continue
        titles = [node.title]
        parent = by_id.get(node.parent_id)
        while parent is not None:
            titles.append(parent.title)
            parent = by_id.get(parent.parent_id)
        paths.append(" > ".join(reversed(titles)))
    return paths[:200]


def organize_document(
    db: Session,
    document: models.Document,
    force: bool = False,
    use_llm: bool | None = None,
) -> OrganizationResult:
    linked_count = (
        db.query(models.StudyNodeChunk)
        .join(models.DocumentChunk)
        .filter(models.DocumentChunk.document_id == document.id)
        .count()
    )
    if linked_count and not force:
        existing_chunks = (
            db.query(models.DocumentChunk, models.StudyNodeChunk.node_id)
            .join(
                models.StudyNodeChunk,
                models.StudyNodeChunk.chunk_id == models.DocumentChunk.id,
            )
            .filter(models.DocumentChunk.document_id == document.id)
            .order_by(models.DocumentChunk.chunk_index)
            .all()
        )
        return OrganizationResult(
            skipped=True,
            chunk_texts=[chunk.chunk_text for chunk, _ in existing_chunks],
            subtopic_ids=[node_id for _, node_id in existing_chunks],
        )

    sections = extract_outline_sections(
        text=document.extracted_text or "",
        filename=document.filename,
        use_llm=use_llm,
        existing_paths=existing_subject_paths(db, document.subject_id),
        styled_lines=extract_styled_pdf_lines(document.file_path),
    )

    # Do not hold a SQLite write lock while optional outline inference runs.
    db.query(models.DocumentChunk).filter(
        models.DocumentChunk.document_id == document.id
    ).delete(synchronize_session=False)
    db.flush()

    result = OrganizationResult()
    chunk_index = 0

    for section in sections:
        parent_id = None
        leaf_node = None
        for spec in section.path:
            node, created = _find_or_create_node(
                db=db,
                subject_id=document.subject_id,
                parent_id=parent_id,
                spec=spec,
            )
            result.nodes_created += int(created)
            parent_id = node.id
            leaf_node = node

        if leaf_node is None:
            continue

        for chunk_text in split_text_into_chunks(section.text):
            chunk = models.DocumentChunk(
                document_id=document.id,
                subject_id=document.subject_id,
                chunk_text=chunk_text,
                chunk_index=chunk_index,
            )
            db.add(chunk)
            db.flush()
            db.add(models.StudyNodeChunk(node_id=leaf_node.id, chunk_id=chunk.id))
            result.chunk_texts.append(chunk_text)
            result.subtopic_ids.append(leaf_node.id)
            chunk_index += 1

    return result


def prune_empty_nodes(db: Session, subject_id: int):
    while True:
        empty_nodes = (
            db.query(models.StudyNode)
            .filter(models.StudyNode.subject_id == subject_id)
            .filter(~models.StudyNode.children.any())
            .filter(~models.StudyNode.chunk_links.any())
            .all()
        )
        if not empty_nodes:
            break
        for node in empty_nodes:
            db.delete(node)
        db.flush()
