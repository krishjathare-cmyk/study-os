from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - the plain-text fallback remains usable
    fitz = None


class PDFExtractionError(ValueError):
    """Raised when a PDF cannot be opened or parsed for text extraction."""


@dataclass(frozen=True)
class StyledPDFLine:
    """A visual text line used for local heading detection."""

    text: str
    page_number: int
    font_size: float
    font_name: str
    is_bold: bool
    block_number: int
    y_position: float


def extract_pdf_pages(file_path: str) -> list[str]:
    try:
        # Non-strict mode lets pypdf recover from broken cross-reference tables.
        # It is why "wrong pointing object" messages are non-fatal.
        reader = PdfReader(file_path, strict=False)
        return [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, OSError) as error:
        raise PDFExtractionError(
            "This PDF could not be read. Try exporting it again as a standard PDF."
        ) from error


def extract_text_from_pdf(file_path: str) -> str:
    return "\n".join(page for page in extract_pdf_pages(file_path) if page)


def extract_styled_pdf_lines(file_path: str) -> list[StyledPDFLine]:
    """Extract text lines with font metadata for local outline detection.

    Scanned PDFs and environments without PyMuPDF return an empty list so the
    existing pypdf text-based organizer can continue to handle the document.
    """
    if fitz is None:
        return []

    try:
        document = fitz.open(file_path)
        lines: list[StyledPDFLine] = []
        for page_index, page in enumerate(document):
            page_dict = page.get_text("dict", sort=True)
            for block_number, block in enumerate(page_dict.get("blocks", [])):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                    if not spans:
                        continue
                    text = "".join(span.get("text", "") for span in spans).strip()
                    if not text:
                        continue
                    character_count = sum(len(span.get("text", "")) for span in spans) or 1
                    font_size = sum(
                        float(span.get("size", 0.0)) * len(span.get("text", ""))
                        for span in spans
                    ) / character_count
                    font_name = str(spans[0].get("font", ""))
                    is_bold = any(
                        bool(span.get("flags", 0) & 16)
                        or "bold" in str(span.get("font", "")).lower()
                        for span in spans
                    )
                    bbox = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
                    lines.append(
                        StyledPDFLine(
                            text=text,
                            page_number=page_index + 1,
                            font_size=font_size,
                            font_name=font_name,
                            is_bold=is_bold,
                            block_number=block_number,
                            y_position=float(bbox[1]),
                        )
                    )
        document.close()
        return lines
    except (OSError, RuntimeError, ValueError):
        return []
