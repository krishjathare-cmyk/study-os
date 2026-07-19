import re


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_text_into_chunks(
    text: str,
    chunk_size: int = 800,
    overlap: int = 150
) -> list[str]:
    cleaned_text = clean_text(text)
    words = cleaned_text.split()

    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])

        if chunk.strip():
            chunks.append(chunk)

        start = end - overlap

    return chunks