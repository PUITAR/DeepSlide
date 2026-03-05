import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.services.visual_asset_models import SlideVisualAssets

class PlanMetric(BaseModel):
    label: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=64)
    delta: Optional[str] = Field(default=None, max_length=64)


class PlanImage(BaseModel):
    url: str
    caption: str = ""
    focus_template_id: Optional[str] = None
    focus_regions: List[List[float]] = Field(default_factory=list)


class PlanTableViz(BaseModel):
    payload: Optional[Dict[str, Any]] = None
    spec: Optional[Dict[str, Any]] = None


class PlanDiagramSpec(BaseModel):
    title: str = ""
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    layout: Dict[str, Any] = Field(default_factory=dict)


LayoutName = Literal[
    "cover",
    "section_transition",
    "toc",
    "references",
    "hero_figure",
    "metric_cards",
    "two_col_compare",
    "table_focus",
    "one_sentence",
    "tri_cards",
    "timeline",
    "process_stack",
    "diagram_flow",
    "solo",
]


class RenderPlan(BaseModel):
    slide_role: str = Field(default="content")
    kicker: str = Field(default="", max_length=32)
    title: str = Field(..., min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=180)
    core_message: str = Field(default="", max_length=220)
    author: str = Field(default="", max_length=120)
    date: str = Field(default="", max_length=64)
    layout: LayoutName
    effects_used: List[str] = Field(default_factory=list)

    # --- New fields for intent-driven visuals ---
    layout_config: Dict[str, Any] = Field(
        default_factory=lambda: {"split_ratio": "50:50", "content_align": "center"}
    )
    style_config: Dict[str, Any] = Field(
        default_factory=lambda: {"theme_variant": "default", "accent_color": "primary"}
    )
    # --------------------------------------------

    bullets: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    metrics: List[PlanMetric] = Field(default_factory=list)
    image: Optional[PlanImage] = None
    table_viz: Optional[PlanTableViz] = None
    diagram_spec: Optional[PlanDiagramSpec] = None
    visual_assets: Optional[SlideVisualAssets] = None

    def require(self) -> None:
        lay = str(self.layout or "").strip()
        if lay == "cover":
            if any(str(x or "").strip() for x in (self.steps or [])):
                raise ValueError("cover must not include steps")
            if any(str(x or "").strip() for x in (self.bullets or [])):
                raise ValueError("cover must not include bullets")
        if lay == "section_transition":
            if not str(self.core_message or self.subtitle or "").strip():
                raise ValueError("section_transition requires core_message or subtitle")
            if any(str(x or "").strip() for x in (self.steps or [])):
                raise ValueError("section_transition must not include steps")
        if lay == "toc":
            if len([b for b in (self.bullets or []) if str(b or "").strip()]) < 2:
                raise ValueError("toc requires bullets (>=2)")
            if any(str(x or "").strip() for x in (self.steps or [])):
                raise ValueError("toc must not include steps")
        if lay == "references":
            if len([b for b in (self.bullets or []) if str(b or "").strip()]) < 1:
                raise ValueError("references requires bullets (>=1)")
            if any(str(x or "").strip() for x in (self.steps or [])):
                raise ValueError("references must not include steps")
        if lay == "hero_figure":
            if not self.image or not str(self.image.url or "").strip():
                raise ValueError("hero_figure requires image.url")
        if lay == "metric_cards":
            if len(self.metrics or []) < 2:
                raise ValueError("metric_cards requires metrics (>=2)")
        if lay == "two_col_compare":
            if len([b for b in (self.bullets or []) if str(b or "").strip()]) < 3:
                raise ValueError("two_col_compare requires bullets (>=3)")
        if lay == "table_focus":
            has_spec = bool(
                self.table_viz
                and isinstance(self.table_viz.spec, dict)
                and isinstance(self.table_viz.spec.get("option"), dict)
                and bool(self.table_viz.spec.get("option"))
            )
            has_payload = bool(self.table_viz and isinstance(self.table_viz.payload, dict) and bool(self.table_viz.payload))
            if not (has_spec or has_payload):
                raise ValueError("table_focus requires table_viz.spec.option or table_viz.payload")
        if lay == "one_sentence":
            if not str(self.core_message or "").strip():
                raise ValueError("one_sentence requires core_message")
            if any(str(b or "").strip() for b in (self.bullets or [])):
                raise ValueError("one_sentence must not include bullets")
        if lay in {"tri_cards", "timeline", "process_stack"}:
            if len([s for s in (self.steps or []) if str(s or "").strip()]) < 2:
                raise ValueError(f"{lay} requires steps (>=2)")
            if lay == "tri_cards" and len([s for s in (self.steps or []) if str(s or "").strip()]) < 3:
                raise ValueError("tri_cards requires steps (>=3)")
        if lay == "diagram_flow":
            if not self.diagram_spec:
                raise ValueError("diagram_flow requires diagram_spec")
            if not (self.diagram_spec.nodes and isinstance(self.diagram_spec.nodes, list) and len(self.diagram_spec.nodes) >= 2):
                raise ValueError("diagram_flow requires diagram_spec.nodes (>=2)")
        if lay == "solo":
            if not str(self.core_message or "").strip() and not any(str(b or "").strip() for b in (self.bullets or [])):
                raise ValueError("solo requires core_message or bullets")

    def validate_urls(self, *, allowed_image_urls: List[str]) -> None:
        bad = []
        if self.image and self.image.url:
            u = str(self.image.url)
            if "/preview/" in u:
                bad.append("image.url must not reference /preview/")
            if allowed_image_urls and u not in set(allowed_image_urls):
                bad.append("image.url must be one of allowed_image_urls")
            if not (u.startswith("/api/v1/projects/") and "asset?path=" in u):
                bad.append("image.url must be a project asset URL")
        if bad:
            raise ValueError("; ".join(bad))

    def validate_effects(self, *, enabled_effects_hint: List[str]) -> None:
        hint = {str(x) for x in (enabled_effects_hint or []) if str(x or "").strip()}
        used = {str(x) for x in (self.effects_used or []) if str(x or "").strip()}
        if hint and not used.issubset(hint):
            extra = sorted(list(used - hint))[:8]
            raise ValueError(f"effects_used must be a subset of enabled_effects_hint; extra={extra}")

    def normalize(self) -> None:
        self.effects_used = [str(x) for x in (self.effects_used or []) if str(x or "").strip()]
        self.bullets = [str(x).strip() for x in (self.bullets or []) if str(x or "").strip()]
        self.steps = [str(x).strip() for x in (self.steps or []) if str(x or "").strip()]
        if self.image:
            self.image.caption = str(self.image.caption or "")[:140]
            regs = []
            for r in (self.image.focus_regions or [])[:8]:
                if not (isinstance(r, list) and len(r) >= 4):
                    continue
                try:
                    x, y, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                except Exception:
                    continue
                x2 = max(0.0, min(1.0, x))
                y2 = max(0.0, min(1.0, y))
                w2 = max(0.0, min(1.0, w))
                h2 = max(0.0, min(1.0, h))
                if min(w2, h2) < 0.12:
                    continue
                if (w2 * h2) < 0.03:
                    continue
                regs.append([x2, y2, w2, h2])
            self.image.focus_regions = regs

    @staticmethod
    def safe_error_summary(e: Exception) -> str:
        s = str(e or "").strip()
        s = re.sub(r"\s+", " ", s)
        return s[:900] if s else "unknown_error"
