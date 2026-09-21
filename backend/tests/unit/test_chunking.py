from app.rag.chunking import chunk_text


def test_short_text_is_a_single_chunk() -> None:
    text = "Tension headaches are the most common type of headache."
    assert chunk_text(text) == [text]


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_long_text_is_split_with_overlap() -> None:
    words = [f"word{i}" for i in range(400)]
    text = " ".join(words)

    chunks = chunk_text(text, max_words=180, overlap_words=30)

    assert len(chunks) > 1
    # every word appears in at least one chunk (nothing silently dropped)
    covered = set(" ".join(chunks).split())
    assert covered == set(words)
    # consecutive chunks actually overlap
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    assert first_words[-1] in second_words
