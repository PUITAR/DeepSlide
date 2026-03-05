from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from app.services.visual_asset_models import DeckStyleDNA, SlideVisualAssets
from app.services.visual_asset_service import ensure_slide_assets
from app.services.visual_intent_agent import generate_visual_intent


def _safe_areas_for_layout(layout_name: str) -> List[List[float]]:
    lay = str(layout_name or "").strip()
    if lay in {"cover"}:
        return [[0.06, 0.08, 0.88, 0.34], [0.10, 0.48, 0.80, 0.26]]
    if lay in {"section_transition"}:
        return [[0.08, 0.14, 0.84, 0.44]]
    if lay in {"hero_figure", "hero_figure_vertical"}:
        return [[0.06, 0.08, 0.88, 0.28], [0.06, 0.34, 0.52, 0.56]]
    if lay in {"table_focus", "diagram_flow", "timeline", "process_stack", "tri_cards"}:
        return [[0.06, 0.08, 0.88, 0.30], [0.06, 0.34, 0.88, 0.58]]
    return [[0.06, 0.08, 0.88, 0.30], [0.06, 0.34, 0.88, 0.58]]


def _norm_intensity(s: str) -> str:
    t = str(s or "").strip().lower()
    if t in {"low", "mid", "high"}:
        return t
    return "low"


def compute_visual_fx_params(
    *,
    layout: str,
    page_idx: int,
    visual_fx_intensity: str,
    visual_fx_by_page: Optional[Dict[int, str]],
    visual_fx_enabled: Optional[Dict[str, bool]],
) -> Tuple[str, Dict[str, bool], List[List[float]], bool, int]:
    inten = _norm_intensity((visual_fx_by_page or {}).get(int(page_idx)) if visual_fx_by_page else visual_fx_intensity)
    enabled = dict(visual_fx_enabled or {})
    if not enabled:
        enabled = {"bg": True, "overlay": True, "mask": False, "frames": False}
    want_frames = bool(enabled.get("frames"))
    if str(layout or "") == "section_transition":
        want_frames = True if ("frames" not in (visual_fx_enabled or {})) else want_frames
        enabled["frames"] = want_frames
    fps = 10 if inten == "low" else 12 if inten == "mid" else 14
    return inten, enabled, _safe_areas_for_layout(layout), want_frames, fps


def attach_visual_assets(
    *,
    project_id: str,
    project_path: str,
    slide_no: int,
    page_idx: int,
    layout: str,
    slide_role: str,
    title: str,
    subtitle: str,
    core_message: str,
    bullets: Optional[List[str]],
    deck_dna: DeckStyleDNA,
    deck_hash: str,
    visual_fx_intensity: str,
    visual_fx_by_page: Optional[Dict[int, str]],
    visual_fx_enabled: Optional[Dict[str, bool]],
) -> SlideVisualAssets:
    intent_payload = {
        "slide_no": int(slide_no),
        "slide_role": str(slide_role or ""),
        "layout": str(layout or ""),
        "title": str(title or ""),
        "subtitle": str(subtitle or ""),
        "core_message": str(core_message or ""),
        "bullets": [str(x) for x in (bullets or []) if str(x or "").strip()][:8],
    }
    vi, vi_hash = generate_visual_intent(slide_payload=intent_payload)

    inten, enabled, safe_areas, want_frames, fps = compute_visual_fx_params(
        layout=layout,
        page_idx=page_idx,
        visual_fx_intensity=visual_fx_intensity,
        visual_fx_by_page=visual_fx_by_page,
        visual_fx_enabled=visual_fx_enabled,
    )

    lay = str(layout or "")
    role = str(slide_role or "")
    mode_override = str(os.getenv("DS_VFX_MODE") or "").strip().lower()
    if mode_override in {"poster", "bg"}:
        mode = mode_override
    else:
        mode = "poster" if (role in {"cover", "references", "ending"} or lay in {"cover", "references"}) else "bg"

    if mode == "poster":
        enabled = {"bg": False, "overlay": False, "mask": False, "frames": True}
        want_frames = True
        fps = 1
    else:
        enabled = {"bg": True, "overlay": False, "mask": False, "frames": False}
        want_frames = False
    return ensure_slide_assets(
        project_id=project_id,
        project_path=project_path,
        slide_no=int(slide_no),
        style_dna=deck_dna,
        deck_style_hash=deck_hash,
        safe_areas=safe_areas,
        enabled=enabled,
        mode=mode,
        visual_intent=vi.to_dict(),
        visual_intent_hash=vi_hash,
        overlay_intensity=inten,
        mask_kind="spotlight",
        feather_px=72,
        want_frames=want_frames,
        fps=fps,
    )
