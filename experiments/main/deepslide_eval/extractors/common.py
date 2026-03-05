from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SlideText:
    slide_index: int
    text: str
    text_ocr: str
    text_final: str
    notes: str
    word_count: int
    min_font_pt: Optional[float]
    num_shapes: int
    num_images: int
    ocr_used: bool
    ocr_confidence: Optional[float]


@dataclass(frozen=True)
class DeckContent:
    artifact_path: str
    artifact_type: str
    slides: List[SlideText]
    deck_text: str
    deck_text_final: str
    deck_notes: str
    image_hashes: List[str]



@dataclass(frozen=True)
class SourceDocContent:
    pdf_path: str
    page_texts: List[str]
    chunks: List[str]
    image_hashes: List[str]


@dataclass(frozen=True)
class ExtractorResult:
    ok: bool
    error: Optional[str]
    content: Optional[object]
    diagnostics: Dict
