from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple

from ..extractors.common import DeckContent, SlideText
from ..io_utils import ensure_dir, sha1_bytes
from .client import call_aliyun_vlm_ocr, call_ocr, summarize_blocks
from .config import OCRConfig
from .render import convert_pptx_to_pdf, extract_pptx_slide_images, render_pdf_to_images


def _need_ocr_slide(slide: SlideText, text_min_chars: int) -> bool:
    if slide.text and len(slide.text.strip()) >= text_min_chars:
        return False
    if slide.num_images <= 0:
        return False
    return True


def _merge_text(native: str, ocr: str) -> str:
    a = (native or "").strip()
    b = (ocr or "").strip()
    if not a:
        return b
    if not b:
        return a
    return (a + "\n" + b).strip()


def _cache_path(cache_dir: Path, image_path: Path, ocr_cfg: OCRConfig) -> Path:
    key_src = f"{image_path}:{image_path.stat().st_mtime_ns}:{image_path.stat().st_size}:{ocr_cfg.url}:{ocr_cfg.timeout_seconds}:{ocr_cfg.render_dpi}".encode(
        "utf-8"
    )
    key = sha1_bytes(key_src)
    return cache_dir / f"ocr_{key}.json"


def augment_deck_with_ocr(
    deck: DeckContent,
    cache_root: Path,
    ocr_cfg: OCRConfig,
) -> DeckContent:
    if ocr_cfg.mode == "off" or ocr_cfg.provider == "none":
        return deck
    if ocr_cfg.provider == "rest" and not ocr_cfg.url and ocr_cfg.mode in {"auto", "on"}:
        return deck
    if ocr_cfg.provider == "aliyun_vlm" and (not ocr_cfg.vlm_api_key or not ocr_cfg.vlm_model):
        return deck

    needs = [s for s in deck.slides if _need_ocr_slide(s, text_min_chars=ocr_cfg.text_min_chars)]
    if ocr_cfg.mode == "auto" and not needs:
        return deck
    if ocr_cfg.mode == "on":
        needs = list(deck.slides)

    render_dir = cache_root / "renders" / sha1_bytes(deck.artifact_path.encode("utf-8"))
    ensure_dir(render_dir)

    image_paths: List[Path]
    if deck.artifact_type == "pdf":
        image_paths = render_pdf_to_images(Path(deck.artifact_path), render_dir, dpi=ocr_cfg.render_dpi)
    elif deck.artifact_type == "pptx":
        pdf_dir = cache_root / "renders" / (sha1_bytes(deck.artifact_path.encode("utf-8")) + "_pdf")
        try:
            pdf_path = convert_pptx_to_pdf(Path(deck.artifact_path), pdf_dir)
            image_paths = render_pdf_to_images(pdf_path, render_dir, dpi=ocr_cfg.render_dpi)
        except Exception:
            image_paths = extract_pptx_slide_images(Path(deck.artifact_path), render_dir)
    else:
        return deck

    ocr_cache_dir = cache_root / "ocr"
    ensure_dir(ocr_cache_dir)

    deck_key = sha1_bytes(deck.artifact_path.encode("utf-8"))
    deck_ocr_items = []

    slides_out: List[SlideText] = []
    for s in deck.slides:
        idx = int(s.slide_index)
        img = image_paths[idx] if 0 <= idx < len(image_paths) else None
        if img is None or not _need_ocr_slide(s, text_min_chars=ocr_cfg.text_min_chars) and ocr_cfg.mode != "on":
            slides_out.append(s)
            continue

        cp = _cache_path(ocr_cache_dir, img, ocr_cfg=ocr_cfg)
        if cp.exists():
            obj = json.loads(cp.read_text(encoding="utf-8"))
            full_text = (obj.get("full_text") or "").strip()
            conf = obj.get("confidence")
        else:
            if ocr_cfg.provider == "aliyun_vlm":
                res = call_aliyun_vlm_ocr(
                    api_url=ocr_cfg.vlm_api_url,
                    api_key=ocr_cfg.vlm_api_key,
                    model=ocr_cfg.vlm_model,
                    image_path=img,
                    timeout_seconds=ocr_cfg.timeout_seconds,
                    prompt=ocr_cfg.vlm_prompt,
                )
            else:
                res = call_ocr(ocr_cfg.url, img, timeout_seconds=ocr_cfg.timeout_seconds)
            full_text, conf = summarize_blocks(res.blocks)
            if res.full_text and len(res.full_text.strip()) > len(full_text.strip()):
                full_text = res.full_text.strip()
            cp.write_text(
                json.dumps(
                    {
                        "ok": res.ok,
                        "full_text": full_text,
                        "confidence": conf,
                        "engine_version": res.engine_version,
                        "elapsed_ms": res.elapsed_ms,
                        "raw": res.raw,
                        "image_path": str(img),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        deck_ocr_items.append(
            {
                "slide_index": idx,
                "image_path": str(img),
                "ocr_cache_path": str(cp),
                "full_text": full_text,
                "confidence": float(conf) if conf is not None else None,
            }
        )

        final = _merge_text(s.text, full_text)
        words = len([w for w in final.replace("\n", " ").split(" ") if w])
        slides_out.append(
            SlideText(
                slide_index=s.slide_index,
                text=s.text,
                text_ocr=full_text,
                text_final=final,
                notes=s.notes,
                word_count=words,
                min_font_pt=s.min_font_pt,
                num_shapes=s.num_shapes,
                num_images=s.num_images,
                ocr_used=True,
                ocr_confidence=float(conf) if conf is not None else None,
            )
        )

    deck_text_final = "\n\n".join([s.text_final for s in slides_out if s.text_final]).strip()

    if deck_ocr_items:
        deck_ocr_path = ocr_cache_dir / f"deck_ocr_{deck_key}.json"
        deck_ocr_path.write_text(
            json.dumps(
                {
                    "artifact_path": deck.artifact_path,
                    "artifact_type": deck.artifact_type,
                    "ocr_url": ocr_cfg.url,
                    "render_dpi": ocr_cfg.render_dpi,
                    "text_min_chars": ocr_cfg.text_min_chars,
                    "items": deck_ocr_items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return DeckContent(
        artifact_path=deck.artifact_path,
        artifact_type=deck.artifact_type,
        slides=slides_out,
        deck_text=deck.deck_text,
        deck_text_final=deck_text_final,
        deck_notes=deck.deck_notes,
        image_hashes=deck.image_hashes,
    )
