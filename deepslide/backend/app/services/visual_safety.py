from __future__ import annotations

from typing import List, Tuple

from PIL import Image, ImageFilter


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _rect_px(rect01: List[float], w: int, h: int) -> Tuple[int, int, int, int]:
    if not rect01 or len(rect01) < 4:
        return (0, 0, 0, 0)
    x, y, rw, rh = (_clamp01(rect01[0]), _clamp01(rect01[1]), _clamp01(rect01[2]), _clamp01(rect01[3]))
    x0 = int(round(x * w))
    y0 = int(round(y * h))
    x1 = int(round((x + rw) * w))
    y1 = int(round((y + rh) * h))
    x0 = max(0, min(w, x0))
    y0 = max(0, min(h, y0))
    x1 = max(0, min(w, x1))
    y1 = max(0, min(h, y1))
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0, 0)
    return (x0, y0, x1, y1)


def edge_density(img: Image.Image, rect01: List[float]) -> float:
    im = img.convert("L")
    w, h = im.size
    x0, y0, x1, y1 = _rect_px(rect01, w, h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    crop = im.crop((x0, y0, x1, y1))
    crop = crop.filter(ImageFilter.FIND_EDGES)
    crop = crop.point(lambda p: 255 if p > 36 else 0)
    hist = crop.histogram()
    if not hist or len(hist) < 256:
        return 0.0
    on = float(sum(hist[200:256]))
    total = float((x1 - x0) * (y1 - y0))
    return (on / total) if total > 0 else 0.0


def is_safe_for_text(img: Image.Image, safe_areas: List[List[float]], *, max_edge_density: float = 0.055) -> bool:
    if not safe_areas:
        return True
    for r in safe_areas:
        if edge_density(img, r) > float(max_edge_density):
            return False
    return True
