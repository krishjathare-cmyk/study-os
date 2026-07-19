import re


def tokenize(text: str) -> set[str]:
    words = re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())

    stopwords = {
        "the", "is", "are", "a", "an", "and", "or", "of", "to", "in",
        "for", "on", "with", "as", "by", "from", "this", "that", "it",
        "be", "can", "will", "was", "were", "at", "which"
    }

    return {word for word in words if word not in stopwords}


def calculate_relevance_score(query: str, chunk_text: str) -> int:
    query_tokens = tokenize(query)
    chunk_tokens = tokenize(chunk_text)

    return len(query_tokens.intersection(chunk_tokens))