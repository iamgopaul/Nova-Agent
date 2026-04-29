from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Target chunk size in characters (~500 tokens ≈ 2000 chars)
CHUNK_SIZE = 1800
CHUNK_OVERLAP = 200


def extract_text(path: Path, content_type: str) -> str:
    """Extract plain text from a file. Supports PDF, Markdown, and plain text."""
    suffix = path.suffix.lower()

    if suffix == ".pdf" or content_type == "application/pdf":
        return _extract_pdf(path)
    if suffix in (".md", ".markdown"):
        return path.read_text(errors="replace")
    # Plain text, code files, etc.
    return path.read_text(errors="replace")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("[FileProcessor] pypdf not installed — cannot extract PDF text")
        return ""
    except Exception as exc:
        logger.error("[FileProcessor] PDF extraction failed: %s", exc)
        return ""


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks, respecting paragraph boundaries."""
    # Normalise whitespace
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    paragraphs = text.split("\n\n")

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= CHUNK_SIZE:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds CHUNK_SIZE, hard-split it
            if len(para) > CHUNK_SIZE:
                for i in range(0, len(para), CHUNK_SIZE - CHUNK_OVERLAP):
                    chunks.append(para[i: i + CHUNK_SIZE])
                current = ""
            else:
                # Carry overlap from the end of the previous chunk
                overlap_text = current[-CHUNK_OVERLAP:] if current else ""
                current = (overlap_text + "\n\n" + para).strip()

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


def process_file(path: Path, content_type: str) -> list[str]:
    """Extract text from *path* and return a list of chunks ready for embedding."""
    text = extract_text(path, content_type)
    if not text.strip():
        return []
    return chunk_text(text)
