"""PDF / text transcript ingest."""

from __future__ import annotations

from pathlib import Path


def extract_text_from_pdf(path: Path) -> str:
    import fitz  # pymupdf

    doc = fitz.open(path)
    pages: list[str] = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            pages.append(f"--- PAGE {i + 1} ---\n{text}")
    doc.close()
    return "\n\n".join(pages).strip()


def extract_transcript(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = extract_text_from_pdf(path)
        if len(text) < 40:
            raise ValueError(
                "PDF has almost no extractable text (may be scanned images). "
                "Export a text-based PDF or paste the script as .txt / .md."
            )
        return text
    if suffix in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    raise ValueError(f"Unsupported file type: {suffix}. Use PDF, TXT, or MD.")
