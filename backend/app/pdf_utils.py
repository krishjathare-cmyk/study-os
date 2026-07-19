from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PDFExtractionError(ValueError):
    """Raised when a PDF cannot be opened or parsed for text extraction."""


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
