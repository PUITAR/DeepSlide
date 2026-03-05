from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeckStyleDNA(BaseModel):
    version: str = Field(default="v1", max_length=16)
    persona: str = Field(default="", max_length=64)
    theme: str = Field(default="light", max_length=16)
    palette: Dict[str, str] = Field(default_factory=dict)
    material: str = Field(default="glass", max_length=32)
    illustration_style: str = Field(default="abstract", max_length=48)
    stroke_strength: str = Field(default="medium", max_length=16)
    radius_strength: str = Field(default="medium", max_length=16)
    shadow_strength: str = Field(default="medium", max_length=16)
    motion_baseline: str = Field(default="low", max_length=16)
    notes: str = Field(default="", max_length=400)


class VisualAssetItem(BaseModel):
    kind: str = Field(default="", max_length=24)
    url: str = Field(default="", max_length=2048)
    rel_path: str = Field(default="", max_length=512)
    width: int = 0
    height: int = 0
    format: str = Field(default="webp", max_length=12)
    meta: Dict[str, Any] = Field(default_factory=dict)


class SlideVisualAssets(BaseModel):
    version: str = Field(default="v1", max_length=16)
    slide_no: int
    deck_style_hash: str = Field(default="", max_length=80)

    enabled: Dict[str, bool] = Field(default_factory=dict)
    overlay_intensity: str = Field(default="low", max_length=16)
    mask_kind: str = Field(default="spotlight", max_length=24)
    feather_px: int = 60

    safe_areas: List[List[float]] = Field(default_factory=list)
    bg: Optional[VisualAssetItem] = None
    overlay: Optional[VisualAssetItem] = None
    mask: Optional[VisualAssetItem] = None
    frames: List[VisualAssetItem] = Field(default_factory=list)
    fps: int = 10
    frame_interval_ms: int = 0
    mode: str = Field(default="bg", max_length=24)
    visual_intent: Dict[str, Any] = Field(default_factory=dict)


class VisualAssetManifest(BaseModel):
    version: str = Field(default="v1", max_length=16)
    slide_no: int
    deck_style_hash: str = Field(default="", max_length=80)
    style_dna: Dict[str, Any] = Field(default_factory=dict)
    safe_areas: List[List[float]] = Field(default_factory=list)
    assets: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = 0.0
    prompt_meta: Dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="bg", max_length=24)
    visual_intent: Dict[str, Any] = Field(default_factory=dict)
    visual_intent_hash: str = Field(default="", max_length=80)
