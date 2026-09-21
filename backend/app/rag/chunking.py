def chunk_text(text: str, max_words: int = 180, overlap_words: int = 30) -> list[str]:
    """rag_pipeline: CLEANING (caller's job) -> CHUNKING (this). Fixed-size word windows with
    overlap — simple and source-agnostic, works for MedlinePlus's short summaries today and
    longer PubMed articles later without changes."""

    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    step = max_words - overlap_words
    while start < len(words):
        chunk_words = words[start : start + max_words]
        chunks.append(" ".join(chunk_words))
        if start + max_words >= len(words):
            break
        start += step
    return chunks
