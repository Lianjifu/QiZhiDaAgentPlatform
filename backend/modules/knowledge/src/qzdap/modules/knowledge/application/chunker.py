"""Fixed-window text splitter for RAG ingest."""

from __future__ import annotations


def split_text(text: str, *, size: int = 800, overlap: int = 80) -> list[str]:
    body = (text or "").strip()
    if not body:
        return []
    window = max(32, int(size))
    step = max(16, window - max(0, int(overlap)))
    chunks: list[str] = []
    start = 0
    length = len(body)
    while start < length:
        end = min(length, start + window)
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start += step
    return chunks


__all__ = ["split_text"]
