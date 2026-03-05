from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from app.services.deck_style_agent import generate_deck_style
from app.services.image_gen_client import ImageGenClient
from app.services.visual_asset_models import DeckStyleDNA, SlideVisualAssets, VisualAssetItem, VisualAssetManifest
from app.services.visual_safety import is_safe_for_text

logger = logging.getLogger(__name__)


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _hash_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _norm_theme(theme: str) -> str:
    return "light" if str(theme).lower() == "light" else "dark"


def load_or_create_deck_style(*, project_path: str, requirements_context: str, persona: str = "", theme: str = "light") -> Tuple[DeckStyleDNA, str]:
    recipe_dir = os.path.join(str(project_path), "recipe")
    os.makedirs(recipe_dir, exist_ok=True)
    path = os.path.join(recipe_dir, "deck_style.json")
    dna: Optional[DeckStyleDNA] = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            dna = DeckStyleDNA.model_validate(obj)
        except Exception:
            dna = None
    if dna is None:
        dna = generate_deck_style(requirements_context=requirements_context, persona=persona, theme=theme)
        _atomic_write_json(path, dna.model_dump())
    dna.theme = _norm_theme(dna.theme or theme)
    style_hash = _hash_obj({"v": dna.version, "persona": dna.persona, "theme": dna.theme, "palette": dna.palette, "material": dna.material, "illustration_style": dna.illustration_style, "stroke": dna.stroke_strength, "radius": dna.radius_strength, "shadow": dna.shadow_strength, "motion": dna.motion_baseline})
    return dna, style_hash[:24]


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _abs_from_rel(project_path: str, rel: str) -> str:
    root = os.path.abspath(str(project_path or ""))
    r = str(rel or "").strip().lstrip("/")
    return os.path.join(root, r) if r else ""


def _legacy_abs_from_rel(project_path: str, rel: str) -> str:
    root = os.path.abspath(str(project_path or ""))
    r = str(rel or "").strip().lstrip("/")
    if not r:
        return ""
    return os.path.join(root, "recipe", r)


def _repair_legacy_double_recipe(project_path: str, rel: str) -> bool:
    dst = _abs_from_rel(project_path, rel)
    if not dst:
        return False
    if os.path.exists(dst):
        return True
    src = _legacy_abs_from_rel(project_path, rel)
    if not src or not os.path.exists(src) or not os.path.isfile(src):
        return False
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        logger.info(f"[vfx_assets] repaired legacy path src={src!r} -> dst={dst!r}")
        return True
    except Exception as e:
        logger.warning(f"[vfx_assets] failed to repair legacy path src={src!r} -> dst={dst!r}: {e}")
        return False


def _safe_area_boxes_px(safe_areas: List[List[float]], w: int, h: int) -> List[Tuple[int, int, int, int]]:
    out = []
    for r in safe_areas or []:
        if not isinstance(r, list) or len(r) < 4:
            continue
        try:
            x, y, rw, rh = float(r[0]), float(r[1]), float(r[2]), float(r[3])
        except Exception:
            continue
        x0 = int(round(max(0.0, min(1.0, x)) * w))
        y0 = int(round(max(0.0, min(1.0, y)) * h))
        x1 = int(round(max(0.0, min(1.0, x + rw)) * w))
        y1 = int(round(max(0.0, min(1.0, y + rh)) * h))
        if x1 <= x0 or y1 <= y0:
            continue
        out.append((x0, y0, x1, y1))
    return out


def _hex_to_rgb(hx: str, default: Tuple[int, int, int]) -> Tuple[int, int, int]:
    s = str(hx or "").strip()
    if not s.startswith("#") or len(s) not in (7, 4):
        return default
    if len(s) == 4:
        s = "#" + s[1] * 2 + s[2] * 2 + s[3] * 2
    try:
        r = int(s[1:3], 16)
        g = int(s[3:5], 16)
        b = int(s[5:7], 16)
        return (r, g, b)
    except Exception:
        return default


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * float(t)))


def _gradient_bg(size: Tuple[int, int], c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> Image.Image:
    w, h = int(size[0]), int(size[1])
    im = Image.new("RGB", (w, h), c1)
    px = im.load()
    for y in range(h):
        t = y / float(max(h - 1, 1))
        for x in range(w):
            tt = (t * 0.85) + (x / float(max(w - 1, 1))) * 0.15
            r = _lerp(c1[0], c2[0], tt)
            g = _lerp(c1[1], c2[1], tt)
            b = _lerp(c1[2], c2[2], tt)
            px[x, y] = (r, g, b)
    return im


def _draw_blobs(im: Image.Image, *, seed: int, strength: float) -> Image.Image:
    w, h = im.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    rng = seed & 0xFFFFFFFF
    def _rand() -> float:
        nonlocal rng
        rng = (1664525 * rng + 1013904223) & 0xFFFFFFFF
        return rng / 4294967295.0
    for _ in range(7):
        cx = int(_rand() * w)
        cy = int(_rand() * h)
        rr = int((0.22 + _rand() * 0.35) * min(w, h))
        a = int(255 * (0.10 + 0.18 * strength) * (0.7 + 0.6 * _rand()))
        col = (255, 255, 255, a)
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=col)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=42))
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")


def _make_bg(dna: DeckStyleDNA, *, safe_areas: List[List[float]], slide_no: int) -> Image.Image:
    w, h = (1600, 900)
    p1 = _hex_to_rgb(dna.palette.get("primary"), (59, 130, 246))
    p2 = _hex_to_rgb(dna.palette.get("secondary") or dna.palette.get("accent"), (6, 182, 212))
    bg = _gradient_bg((w, h), p1, p2)
    bg = _draw_blobs(bg, seed=slide_no * 7919 + 17, strength=0.9)
    if safe_areas:
        boxes = _safe_area_boxes_px(safe_areas, w, h)
        if boxes:
            scrim = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            d = ImageDraw.Draw(scrim)
            alpha = 235 if _norm_theme(dna.theme) == "light" else 210
            for x0, y0, x1, y1 in boxes:
                d.rounded_rectangle((x0, y0, x1, y1), radius=28, fill=(255, 255, 255, alpha))
            scrim = scrim.filter(ImageFilter.GaussianBlur(radius=10))
            bg = Image.alpha_composite(bg.convert("RGBA"), scrim).convert("RGB")
    return bg


def _make_overlay(dna: DeckStyleDNA, *, intensity: str, slide_no: int) -> Image.Image:
    w, h = (1600, 900)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    inten = str(intensity or "low").lower()
    if inten not in {"low", "mid", "high"}:
        inten = "low"
    a_base = 26 if inten == "low" else 44 if inten == "mid" else 70
    c = _hex_to_rgb(dna.palette.get("accent") or dna.palette.get("primary"), (6, 182, 212))
    col = (c[0], c[1], c[2], a_base)
    step = 36 if inten == "low" else 28 if inten == "mid" else 22
    for x in range(-h, w, step):
        d.line((x, 0, x + h, h), fill=col, width=2)
    d.rectangle((0, 0, w, h), outline=(255, 255, 255, 18), width=2)
    im = im.filter(ImageFilter.GaussianBlur(radius=0.8))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for k in range(3):
        rr = 260 + 90 * k
        a = int((60 - 12 * k) * (1.0 if inten == "high" else 0.75 if inten == "mid" else 0.55))
        gd.ellipse((w - rr - 120, 80, w - 120, 80 + rr), fill=(c[0], c[1], c[2], a))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=38))
    im = Image.alpha_composite(im, glow)
    return im


def _make_mask(*, kind: str, feather_px: int) -> Image.Image:
    w, h = (1600, 900)
    k = str(kind or "spotlight").strip().lower()
    if k not in {"spotlight", "wipe", "reveal"}:
        k = "spotlight"
    feather = max(8, min(220, int(feather_px or 60)))
    if k == "wipe":
        im = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, int(w * 0.62), h), fill=255)
        im = im.filter(ImageFilter.GaussianBlur(radius=feather))
        return im
    if k == "reveal":
        im = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(im)
        d.ellipse((int(w * 0.18), int(h * 0.10), int(w * 0.95), int(h * 0.90)), fill=255)
        im = im.filter(ImageFilter.GaussianBlur(radius=feather))
        return im
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    d.ellipse((int(w * 0.18), int(h * 0.12), int(w * 0.82), int(h * 0.88)), fill=255)
    im = im.filter(ImageFilter.GaussianBlur(radius=feather))
    return im


def _save_image(im: Image.Image, path: str, fmt: str) -> Tuple[int, int]:
    _ensure_dir(os.path.dirname(path))
    if fmt.lower() == "png":
        im.save(path, format="PNG", optimize=True)
    else:
        im.save(path, format="WEBP", quality=92, method=6)
    return im.size


def _asset_url(project_id: str, rel_path: str) -> str:
    from urllib.parse import quote
    rel = str(rel_path or "").strip().lstrip("/")
    return f"/api/v1/projects/{project_id}/asset?path={quote(rel)}"


def _load_manifest(path: str) -> Optional[VisualAssetManifest]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return VisualAssetManifest.model_validate(obj)
    except Exception:
        return None


def ensure_slide_assets(
    *,
    project_id: str,
    project_path: str,
    slide_no: int,
    style_dna: DeckStyleDNA,
    deck_style_hash: str,
    safe_areas: List[List[float]],
    enabled: Dict[str, bool],
    mode: str = "bg",
    visual_intent: Optional[Dict[str, Any]] = None,
    visual_intent_hash: str = "",
    overlay_intensity: str = "low",
    mask_kind: str = "spotlight",
    feather_px: int = 60,
    want_frames: bool = False,
    fps: int = 10,
) -> SlideVisualAssets:
    recipe_dir = os.path.join(str(project_path), "recipe")
    root = os.path.join(recipe_dir, "visual_assets", "v1", f"deck_{deck_style_hash}", f"slide_{int(slide_no)}")
    _ensure_dir(root)
    manifest_path = os.path.join(root, "manifest.json")
    manifest = _load_manifest(manifest_path)

    enabled2 = {str(k): bool(v) for k, v in (enabled or {}).items()}
    if enabled2.get("frames"):
        want_frames = True

    def _ok_asset(rel: str) -> bool:
        if not rel:
            return False
        p = _abs_from_rel(project_path, rel)
        if os.path.exists(p) and os.path.isfile(p):
            return True
        if _repair_legacy_double_recipe(project_path, rel):
            p2 = _abs_from_rel(project_path, rel)
            return bool(os.path.exists(p2) and os.path.isfile(p2))
        return False

    if manifest and manifest.deck_style_hash == deck_style_hash and int(manifest.slide_no) == int(slide_no):
        if str(getattr(manifest, "mode", "") or "bg").strip() != str(mode or "bg").strip():
            manifest = None
        if visual_intent_hash and str(getattr(manifest, "visual_intent_hash", "") or "") != str(visual_intent_hash):
            manifest = None
        else:
            assets = manifest.assets or {}
            if mode == "poster":
                frame_list2 = (assets.get("frames") or {}).get("rel_paths") or []
                if not isinstance(frame_list2, list) or not any("poster_" in str(x or "") for x in frame_list2[:6]):
                    manifest = None
            if enabled2.get("bg") and not _ok_asset(str((assets.get("bg") or {}).get("rel_path") or "")):
                manifest = None
            if enabled2.get("overlay") and not _ok_asset(str((assets.get("overlay") or {}).get("rel_path") or "")):
                manifest = None
            if enabled2.get("mask") and not _ok_asset(str((assets.get("mask") or {}).get("rel_path") or "")):
                manifest = None
            if want_frames:
                frame_list = (assets.get("frames") or {}).get("rel_paths") or []
                if not isinstance(frame_list, list) or not frame_list:
                    manifest = None
                elif not all(_ok_asset(str(x)) for x in frame_list[:8]):
                    manifest = None

    img_client = ImageGenClient("VFX_IMG")
    frame_interval_ms = 0

    bg_rel = f"recipe/visual_assets/v1/deck_{deck_style_hash}/slide_{int(slide_no)}/bg.webp"
    overlay_rel = f"recipe/visual_assets/v1/deck_{deck_style_hash}/slide_{int(slide_no)}/overlay.webp"
    mask_rel = f"recipe/visual_assets/v1/deck_{deck_style_hash}/slide_{int(slide_no)}/mask.png"
    frames_rel_dir = f"recipe/visual_assets/v1/deck_{deck_style_hash}/slide_{int(slide_no)}/frames"

    assets_out: Dict[str, Any] = {}

    if manifest is None:
        created_at = time.time()
        prompt_meta: Dict[str, Any] = {"provider": str(img_client.cfg.platform_type or ""), "model": str(img_client.cfg.model_type or ""), "agent": "VFX_IMG"}
        vi = dict(visual_intent or {})
        vi_hash = str(visual_intent_hash or "").strip()
        allow_fallback = False
        try:
            allow_fallback = str(os.getenv("DS_VFX_ALLOW_FALLBACK") or "0").strip() == "1"
        except Exception:
            allow_fallback = False

        def _soften_safe_areas(im: Image.Image) -> Image.Image:
            if not safe_areas:
                return im
            try:
                w, h = im.size
                m = Image.new("L", (w, h), 0)
                d = ImageDraw.Draw(m)
                for r in safe_areas[:6]:
                    if not (isinstance(r, list) and len(r) >= 4):
                        continue
                    x, y, ww, hh = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                    x0 = int(max(0, min(w, x * w)))
                    y0 = int(max(0, min(h, y * h)))
                    x1 = int(max(0, min(w, (x + ww) * w)))
                    y1 = int(max(0, min(h, (y + hh) * h)))
                    if x1 <= x0 or y1 <= y0:
                        continue
                    d.rectangle([x0, y0, x1, y1], fill=255)
                m = m.filter(ImageFilter.GaussianBlur(radius=26))
                blurred = im.filter(ImageFilter.GaussianBlur(radius=10))
                return Image.composite(blurred, im, m)
            except Exception:
                return im

        def _safe_area_hint() -> str:
            if not safe_areas:
                return "Leave generous clean negative space for slide text."
            parts = []
            for r in safe_areas[:3]:
                if not (isinstance(r, list) and len(r) >= 4):
                    continue
                try:
                    x, y, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                except Exception:
                    continue
                parts.append(f"[{x:.2f},{y:.2f},{w:.2f},{h:.2f}]")
            return "Keep these regions clean and low-texture for overlaid HTML text: " + ", ".join(parts)

        def _negative_clause(extra: Optional[List[str]] = None) -> str:
            base = [
                "no text",
                "no letters",
                "no numbers",
                "no watermark",
                "no logo",
                "no captions",
                "no UI",
                "no labels",
                "no charts",
            ]
            neg = base + [str(x) for x in (vi.get("negative") or []) if str(x or "").strip()]
            if extra:
                neg += [str(x) for x in extra if str(x or "").strip()]
            neg2 = []
            seen = set()
            for x in neg:
                t = str(x).strip().lower()
                if not t or t in seen:
                    continue
                seen.add(t)
                neg2.append(t)
            return ", ".join(neg2[:18])

        def _poster_prompt(action: str, *, kind: str) -> str:
            topic = str(vi.get("topic") or "").strip()[:120]
            scene = str(vi.get("scene") or "").strip()[:360]
            mood = str(vi.get("mood") or "").strip()[:120]
            tags = ", ".join([str(x) for x in (vi.get("style_tags") or []) if str(x or "").strip()][:8])
            collage = (
                "Single image only. Compose the scene as an irregular collage / moodboard / bento grid: many small sub-images (tiles) inside one 16:9 poster. "
                "Use 8–14 tiles with varied sizes, slight overlaps, thin gutters, soft rounded corners, subtle drop shadows. "
                "Keep a cohesive color grade and lighting so the collage feels like one premium design, not a messy scrapbook."
            )
            if str(kind or "") == "bg":
                collage = collage + " Background should be slightly calmer and lower-contrast to avoid distracting from slide content."
            else:
                collage = collage + " Slight variation per frame is allowed (tile arrangement or highlighted tile), but keep the same theme and style."
            return (
                f"Create a premium scientific keynote background poster (16:9). Theme: {topic or 'research'}.\n"
                f"{collage}\n"
                f"Scene: {scene or 'abstract scientific scene'}.\n"
                f"Action (this frame): {action}.\n"
                f"Mood: {mood or 'clean academic cinematic'}.\n"
                f"Style tags: {tags or 'high-end, minimal, cinematic'}.\n"
                f"{_safe_area_hint()}\n"
                f"Strict negatives: {_negative_clause()}.\n"
                "Output image only."
            )

        if mode == "poster":
            enabled2["frames"] = True
            enabled2["bg"] = False
            enabled2["overlay"] = False
            enabled2["mask"] = False
            want_frames = True
            fps = 1
            try:
                frame_interval_ms = int(float(os.getenv("DS_VFX_POSTER_FRAME_MS") or "5000"))
            except Exception:
                frame_interval_ms = 5000
            if (not allow_fallback) and not img_client.is_enabled():
                raise RuntimeError("VFX poster mode requires IMG model, but IMG is disabled (missing API key).")

        if enabled2.get("bg", True) and mode != "poster":
            bg_abs = _abs_from_rel(project_path, bg_rel)
            bg = _make_bg(style_dna, safe_areas=safe_areas, slide_no=int(slide_no))
            if img_client.is_enabled():
                p = _poster_prompt(action=str((vi.get("action_sequence") or ["subtle motion"])[0] if (vi.get("action_sequence") or []) else "subtle motion"), kind="bg")
                bb = img_client.generate(prompt=p, size=(1600, 900), fmt="png", n=1)
                b = bb[0] if bb else b""
                if b:
                    try:
                        from io import BytesIO
                        bg2 = Image.open(BytesIO(b)).convert("RGB")
                    except Exception:
                        bg2 = None
                    if bg2 is not None:
                        bg = bg2.resize((1600, 900))
                        if safe_areas and not is_safe_for_text(bg, safe_areas):
                            bg = _soften_safe_areas(bg)
                        blur_px = 0.0
                        try:
                            blur_px = float(os.getenv("DS_VFX_BG_BLUR_PX") or "1.6")
                        except Exception:
                            blur_px = 1.6
                        blur_px = max(0.0, min(8.0, float(blur_px)))
                        if blur_px > 0:
                            bg = bg.filter(ImageFilter.GaussianBlur(radius=blur_px))
                elif not allow_fallback:
                    detail = str(getattr(img_client, "last_error", "") or "").strip()
                    raise RuntimeError(
                        "VFX bg generation failed: IMG returned empty result."
                        + (f" last_error={detail}" if detail else "")
                    )
            elif not allow_fallback:
                raise RuntimeError("VFX bg generation requires IMG model, but IMG is disabled (missing API key).")
            w, h = _save_image(bg, bg_abs, "webp")
            assets_out["bg"] = {"rel_path": bg_rel, "width": w, "height": h, "format": "webp"}

        if enabled2.get("overlay", True) and mode != "poster":
            overlay_abs = _abs_from_rel(project_path, overlay_rel)
            ov = _make_overlay(style_dna, intensity=overlay_intensity, slide_no=int(slide_no))
            w, h = _save_image(ov, overlay_abs, "webp")
            assets_out["overlay"] = {"rel_path": overlay_rel, "width": w, "height": h, "format": "webp", "intensity": overlay_intensity}

        if enabled2.get("mask", False) and mode != "poster":
            mask_abs = _abs_from_rel(project_path, mask_rel)
            mk = _make_mask(kind=mask_kind, feather_px=int(feather_px))
            w, h = _save_image(mk, mask_abs, "png")
            assets_out["mask"] = {"rel_path": mask_rel, "width": w, "height": h, "format": "png", "kind": mask_kind, "feather_px": int(feather_px)}

        if want_frames:
            frames_abs_dir = _abs_from_rel(project_path, frames_rel_dir)
            _ensure_dir(frames_abs_dir)
            rels: List[str] = []
            if mode == "poster" and img_client.is_enabled():
                actions = [str(x).strip() for x in (vi.get("action_sequence") or []) if str(x or "").strip()]
                if len(actions) < 2:
                    actions = ["pose A", "pose B", "pose C"]
                actions = actions[:3]
                for i, act in enumerate(actions):
                    p = _poster_prompt(action=act, kind="poster")
                    outs = img_client.generate(prompt=p, size=(1600, 900), fmt="png", n=1)
                    b = outs[0] if outs else b""
                    if not b:
                        continue
                    try:
                        from io import BytesIO
                        im = Image.open(BytesIO(b)).convert("RGB").resize((1600, 900))
                    except Exception:
                        continue
                    if safe_areas and not is_safe_for_text(im, safe_areas, max_edge_density=0.11):
                        im2 = _soften_safe_areas(im)
                        if safe_areas and not is_safe_for_text(im2, safe_areas, max_edge_density=0.09):
                            im = _make_bg(style_dna, safe_areas=safe_areas, slide_no=int(slide_no) * 31 + i)
                        else:
                            im = im2
                    rel = f"{frames_rel_dir}/poster_{i:03d}.webp"
                    abs_p = _abs_from_rel(project_path, rel)
                    _save_image(im, abs_p, "webp")
                    rels.append(rel)
            if (not allow_fallback) and mode == "poster" and not rels:
                detail = str(getattr(img_client, "last_error", "") or "").strip()
                raise RuntimeError(
                    "VFX poster generation failed: IMG did not produce poster frames."
                    + (f" last_error={detail}" if detail else "")
                )
            if not rels and allow_fallback:
                for i in range(3):
                    bg = _make_bg(style_dna, safe_areas=safe_areas, slide_no=int(slide_no) * 31 + i)
                    ov = _make_overlay(style_dna, intensity="mid", slide_no=int(slide_no) * 31 + i)
                    comp = Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")
                    comp = comp.filter(ImageFilter.GaussianBlur(radius=0.2 + i * 0.08))
                    rel = f"{frames_rel_dir}/frame_{i:03d}.webp"
                    abs_p = _abs_from_rel(project_path, rel)
                    _save_image(comp, abs_p, "webp")
                    rels.append(rel)
            assets_out["frames"] = {"rel_paths": rels, "fps": int(fps), "loop": True}

        manifest = VisualAssetManifest(
            version="v1",
            slide_no=int(slide_no),
            deck_style_hash=str(deck_style_hash),
            style_dna=style_dna.model_dump(),
            safe_areas=safe_areas or [],
            assets=assets_out,
            created_at=float(created_at),
            prompt_meta=prompt_meta,
            mode=str(mode or "bg")[:24],
            visual_intent=vi,
            visual_intent_hash=vi_hash,
        )
        _atomic_write_json(manifest_path, manifest.model_dump())
    else:
        assets_out = manifest.assets or {}

    def _item(kind: str, rel: str, meta: Dict[str, Any]) -> VisualAssetItem:
        if not _ok_asset(rel):
            return VisualAssetItem(kind=kind, url="", rel_path=rel, width=0, height=0, format=os.path.splitext(rel)[1].lstrip(".") or "webp", meta=meta or {})
        abs_p = _abs_from_rel(project_path, rel)
        w, h = (0, 0)
        try:
            with Image.open(abs_p) as im:
                w, h = im.size
        except Exception:
            pass
        return VisualAssetItem(kind=kind, url=_asset_url(project_id, rel), rel_path=rel, width=int(w), height=int(h), format=os.path.splitext(rel)[1].lstrip(".") or "webp", meta=meta or {})

    bg_item = None
    ov_item = None
    mask_item = None
    frames_items: List[VisualAssetItem] = []

    def _warn_missing(rel: str, label: str) -> None:
        if not rel:
            return
        if _ok_asset(rel):
            return
        try:
            logger.warning(f"[vfx_assets] missing asset slide={slide_no} kind={label} rel={rel!r}")
        except Exception:
            pass

    if enabled2.get("bg") and isinstance(assets_out.get("bg"), dict):
        rel = str(assets_out["bg"].get("rel_path") or "")
        if rel:
            _warn_missing(rel, "bg")
            bg_item = _item("bg", rel, {"format": str(assets_out["bg"].get("format") or "webp")})
    if enabled2.get("overlay") and isinstance(assets_out.get("overlay"), dict):
        rel = str(assets_out["overlay"].get("rel_path") or "")
        if rel:
            _warn_missing(rel, "overlay")
            ov_item = _item("overlay", rel, {"intensity": str(assets_out["overlay"].get("intensity") or overlay_intensity)})
    if enabled2.get("mask") and isinstance(assets_out.get("mask"), dict):
        rel = str(assets_out["mask"].get("rel_path") or "")
        if rel:
            _warn_missing(rel, "mask")
            mask_item = _item("mask", rel, {"kind": str(assets_out["mask"].get("kind") or mask_kind), "feather_px": int(assets_out["mask"].get("feather_px") or feather_px)})
    if want_frames and isinstance(assets_out.get("frames"), dict):
        rels = assets_out["frames"].get("rel_paths") or []
        if isinstance(rels, list):
            for r in rels[:8]:
                rr = str(r or "").strip()
                if rr:
                    _warn_missing(rr, "frame")
                    frames_items.append(_item("frame", rr, {}))

    return SlideVisualAssets(
        version="v1",
        slide_no=int(slide_no),
        deck_style_hash=str(deck_style_hash),
        enabled=enabled2,
        overlay_intensity=str(overlay_intensity or "low"),
        mask_kind=str(mask_kind or "spotlight"),
        feather_px=int(feather_px or 60),
        safe_areas=safe_areas or [],
        bg=bg_item,
        overlay=ov_item,
        mask=mask_item,
        frames=frames_items,
        fps=max(1, min(30, int(fps or 10))),
        frame_interval_ms=max(0, int(frame_interval_ms or 0)),
        mode=str(mode or "bg")[:24],
        visual_intent=dict((manifest.visual_intent if manifest else {}) or {}),
    )
