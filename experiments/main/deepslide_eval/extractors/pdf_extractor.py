from __future__ import annotations

from pathlib import Path
from typing import List

from ..io_utils import sha1_bytes
from .common import DeckContent, ExtractorResult, SlideText, SourceDocContent


def _chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + max_chars)
        chunk = text[i:j].strip()
        if chunk:
            out.append(chunk)
        if j >= n:
            break
        i = max(0, j - overlap)
    return out


def extract_source_from_pdf(pdf_path: Path) -> ExtractorResult:
    diagnostics = {"pdf_path": str(pdf_path)}
    try:
        import fitz
    except Exception as e:
        return ExtractorResult(ok=False, error=f"missing_pymupdf: {e}", content=None, diagnostics=diagnostics)

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        return ExtractorResult(ok=False, error=f"open_pdf_failed: {e}", content=None, diagnostics=diagnostics)

    page_texts: List[str] = []
    image_hashes: List[str] = []
    chunks: List[str] = []

    try:
        for page in doc:
            t = page.get_text("text") or ""
            t = t.strip()
            page_texts.append(t)
            chunks.extend(_chunk_text(t))

            try:
                for img in page.get_images(full=True):
                    xref = img[0]
                    base = doc.extract_image(xref)
                    b = base.get("image")
                    if isinstance(b, (bytes, bytearray)) and b:
                        image_hashes.append(sha1_bytes(bytes(b)))
            except Exception:
                pass
    finally:
        doc.close()

    content = SourceDocContent(
        pdf_path=str(pdf_path),
        page_texts=page_texts,
        chunks=chunks,
        image_hashes=image_hashes,
    )
    diagnostics["num_pages"] = len(page_texts)
    diagnostics["num_chunks"] = len(chunks)
    diagnostics["num_images"] = len(image_hashes)
    return ExtractorResult(ok=True, error=None, content=content, diagnostics=diagnostics)


def extract_deck_from_pdf(pdf_path: Path) -> ExtractorResult:
    diagnostics = {"pdf_path": str(pdf_path)}
    try:
        import fitz
    except Exception as e:
        return ExtractorResult(ok=False, error=f"missing_pymupdf: {e}", content=None, diagnostics=diagnostics)

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        return ExtractorResult(ok=False, error=f"open_pdf_failed: {e}", content=None, diagnostics=diagnostics)

    slides: List[SlideText] = []
    deck_text_parts: List[str] = []
    image_hashes: List[str] = []

    try:
        for idx, page in enumerate(doc):
            t = (page.get_text("text") or "").strip()
            words = len([w for w in t.replace("\n", " ").split(" ") if w])
            num_images = 0
            try:
                for img in page.get_images(full=True):
                    xref = img[0]
                    base = doc.extract_image(xref)
                    b = base.get("image")
                    if isinstance(b, (bytes, bytearray)) and b:
                        num_images += 1
                        image_hashes.append(sha1_bytes(bytes(b)))
            except Exception:
                pass

            slides.append(
                SlideText(
                    slide_index=idx,
                    text=t,
                    text_ocr="",
                    text_final=t,
                    notes="",
                    word_count=words,
                    min_font_pt=None,
                    num_shapes=0,
                    num_images=num_images,
                    ocr_used=False,
                    ocr_confidence=None,
                )
            )
            if t:
                deck_text_parts.append(t)
    finally:
        doc.close()

    deck_text = "\n\n".join(deck_text_parts).strip()
    content = DeckContent(
        artifact_path=str(pdf_path),
        artifact_type="pdf",
        slides=slides,
        deck_text=deck_text,
        deck_text_final=deck_text,
        deck_notes="",
        image_hashes=image_hashes,
    )
    diagnostics["num_pages"] = len(slides)
    return ExtractorResult(ok=True, error=None, content=content, diagnostics=diagnostics)
