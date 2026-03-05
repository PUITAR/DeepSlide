import html
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.diagram_kit import diagram_kit_css, render_diagram_spec
from app.services.render_plan_models import RenderPlan, LayoutName
from app.services.vlm_beautify import FOCUS_TEMPLATES, get_regions_by_template


class HtmlSlideRenderer:
    """Deterministic renderer for RenderPlan -> Modern Spec-Mode HTML."""

    @staticmethod
    def _esc(s: str) -> str:
        return html.escape(str(s or ""), quote=True)

    def _render_text(self, text: str) -> str:
        """Renders text with support for [[...]] or [[[...]]] for gradient keynote effect."""
        s = self._esc(text)
        def _repl(m: re.Match) -> str:
            left = m.group(1) or ""
            inner = m.group(2) or ""
            cls = "k1" if len(left) >= 3 else "k2"
            return f'<span class="keynote-highlight {cls}">{inner}</span>'

        return re.sub(r'(\[{2,3})(.*?)(\]{2,3})', _repl, s)

    def _auto_layout_optimize(self, plan: RenderPlan) -> RenderPlan:
        """Smartly optimizes layout if solo layout contains structured lists."""
        if plan.layout != "solo" or not plan.core_message:
            return plan
        
        # Detect numbered lists: 1. or Stage 1: or - 1.
        lines = [ln.strip() for ln in str(plan.core_message).splitlines() if ln.strip()]
        numbered = [ln for ln in lines if re.match(r'^(\d+[\.\)]|Stage\s*\d+:|Step\s*[A-Z]:)', ln, re.IGNORECASE)]
        
        if len(numbered) >= 2 and len(numbered) == len(lines):
            # Convert to process_stack or tri_cards
            plan.layout = "process_stack" if len(numbered) > 3 else "tri_cards"
            plan.steps = lines
            plan.core_message = "" # Move to steps
        return plan

    def render_plan(self, plan: RenderPlan, theme: str, speech_text: str = "", max_regions: int = 4) -> str:
        """Main entry point for rendering a RenderPlan to HTML."""
        # Optimization step
        plan = self._auto_layout_optimize(plan)

        # Theme and style extraction
        style = plan.style_config or {}
        layout_cfg = plan.layout_config or {}

        try:
            img = getattr(plan, "image", None)
            has_focus = bool(
                img
                and getattr(img, "url", "")
                and (
                    getattr(img, "focus_template_id", "")
                    or (getattr(img, "focus_regions", None) or [])
                    or ("Image Focus" in (plan.effects_used or []))
                )
            )
            if has_focus and getattr(plan, "layout", "") == "hero_figure":
                plan.layout = "hero_figure_vertical"
        except Exception:
            pass
        
        theme_variant = style.get("theme_variant", "glass")
        accent = style.get("accent_color", "primary")
        motion = style.get("motion_intensity", "low")
        highlight_variant = str(style.get("highlight_variant", "aurora") or "aurora").strip().lower()
        highlight_variant = re.sub(r"[^a-z0-9_-]+", "", highlight_variant)[:24] or "aurora"
        theme_attr = "light" if str(theme).lower() == "light" else "dark"
        
        # Build CSS classes
        classes: List[str] = ["spec", f"theme-{theme_variant}", f"accent-{accent}", f"motion-{motion}", f"hl-{highlight_variant}"]
        eff_set = set(plan.effects_used or [])
        if plan.layout == "cover":
            classes.append("layout-cover")
        
        if "Text Keynote" in eff_set:
            classes.append("fx-keynote")
        if "Auto Layout" in eff_set:
            classes.append("fx-layout")
        if "Table Viz" in eff_set:
            classes.append("fx-table-viz")
        if plan.layout in {"diagram_flow", "timeline", "tri_cards", "process_stack"}:
            classes.append("fx-diagram")

        has_image_focus_controls = self._has_image_focus_controls(plan, eff_set)
        if has_image_focus_controls:
            classes.append("ds-has-image-focus")

        # Layout Split Ratio
        split = layout_cfg.get("split_ratio", "50:50")
        l_ratio, r_ratio = split.split(":")
        if plan.layout == "hero_figure_vertical":
            stack = layout_cfg.get("stack_ratio", split) or "60:40"
            t_ratio, b_ratio = str(stack).split(":")
            grid_style = f"grid-template-columns: 1fr; grid-template-rows: {t_ratio}fr {b_ratio}fr;"
        else:
            grid_style = f"grid-template-columns: {l_ratio}fr {r_ratio}fr;"

        body = self._render_body(plan, eff_set, max_regions, grid_style)
        focus_controls = self._render_image_focus_controls(plan) if has_image_focus_controls else ""
        focus_templates_script = ""
        if has_image_focus_controls:
            try:
                payload = json.dumps(FOCUS_TEMPLATES, ensure_ascii=False)
                payload = payload.replace("</", "<\\/").replace("<", "\\u003c")
                focus_templates_script = (
                    f"  <script>window.__ds_focus_templates = {payload};</script>\n"
                    f"  <script type=\"application/json\" id=\"ds-focus-templates\">{payload}</script>\n"
                )
            except Exception:
                focus_templates_script = ""
        fx = self._render_fx(plan)
        kicker = self._render_text(plan.kicker)
        title = self._render_text(plan.title)
        subtitle = self._render_text(plan.subtitle)
        kicker_html = (
            f"<div class=\"kicker animate-in\" style=\"--delay: 0s\"><span class=\"dot\"></span><span>{kicker}</span></div>"
            if str(kicker or "").strip()
            else ""
        )
        subtitle_html = f"<div class=\"subtitle animate-in\" style=\"--delay: 0.1s\">{subtitle}</div>" if subtitle else ""

        # Lightweight render meta for diagnostics / RenderReviewAgent
        try:
            img_meta = getattr(plan, "image", None)
            focus_template_id = getattr(img_meta, "focus_template_id", "") if img_meta else ""
            focus_regions = list(getattr(img_meta, "focus_regions", None) or []) if img_meta else []
            roi_count = 0
            if focus_template_id:
                try:
                    roi_count = len(get_regions_by_template(focus_template_id) or [])
                except Exception:
                    roi_count = 0
            elif focus_regions:
                roi_count = len(focus_regions)
            meta_obj = {
                "layout": plan.layout,
                "effects_used": list(eff_set),
                "has_image": bool(getattr(plan, "image", None) and getattr(plan.image, "url", "")),
                "has_focus_template": bool(focus_template_id),
                "has_focus_regions": bool(roi_count > 0),
                "focus_regions_count": int(roi_count),
                "has_table_viz": bool(
                    getattr(plan, "table_viz", None)
                    and (
                        getattr(plan.table_viz, "payload", None)
                        or (getattr(plan.table_viz, "spec", None) or {}).get("option")
                    )
                ),
                "has_diagram_spec": bool(getattr(plan, "diagram_spec", None)),
                "slide_role": getattr(plan, "slide_role", ""),
            }
            meta_json = self._esc(json.dumps(meta_obj, ensure_ascii=False))
            meta_script = f'  <script type="application/json" id="render-meta">{meta_json}</script>\n'
        except Exception:
            meta_script = ""

        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  
  <!-- Typography: Plus Jakarta Sans & Inter -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
  
  <!-- Math Rendering: KaTeX -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" onload="renderMathInElement(document.body);"></script>

  <style>
{self._css()}
  </style>
{meta_script}{focus_templates_script}</head>
<body data-theme="{theme_attr}" class="{' '.join(classes)}">
  <div class="background-blobs">
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
    <div class="blob blob-3"></div>
  </div>
  <div class="stage">
    <div class="slide">
      {fx}
      {focus_controls}
      <div class="slide-stage">
        <header class="slide-head">
          {kicker_html}
          <h1 class="title animate-in" style="--delay: 0.05s">{title}</h1>
          {subtitle_html}
        </header>
        {body}
      </div>
    </div>
  </div>

  <!-- Lightbox Overlay -->
  <div id="lightbox" class="lightbox hidden" onclick="closeLightbox(event)">
    <div class="lightbox-content" onclick="event.stopPropagation()">
      <div class="lb-wrap">
        <img id="lb-img" src="" alt="Zoom" onclick="nextRoi(event)"/>
        <div id="lb-rois" onclick="nextRoi(event)"></div>
      </div>
    </div>
    <div class="lightbox-close" onclick="closeLightbox(event)">&times;</div>
  </div>

  <script>
    {self._js()}
  </script>
</body>
</html>"""

    def _render_fx(self, plan: RenderPlan) -> str:
        va = getattr(plan, "visual_assets", None)
        if not va:
            return ""
        enabled = getattr(va, "enabled", None) or {}
        bg = getattr(va, "bg", None)
        overlay = getattr(va, "overlay", None)
        mask = getattr(va, "mask", None)
        frames = list(getattr(va, "frames", None) or [])
        fps = int(getattr(va, "fps", 10) or 10)
        fps = max(1, min(30, fps))
        frame_ms = 0
        try:
            frame_ms = int(getattr(va, "frame_interval_ms", 0) or 0)
        except Exception:
            frame_ms = 0

        parts = ["<div class=\"fx-layer\" data-fx=\"1\""]
        parts.append(f" data-fps=\"{fps}\"")
        if frame_ms > 0:
            parts.append(f" data-frame-ms=\"{frame_ms}\"")
        parts.append(">")
        if enabled.get("bg") and bg and getattr(bg, "url", ""):
            parts.append(f"<div class=\"fx-bg\" style=\"background-image:url('{self._esc(bg.url)}')\"></div>")
        if enabled.get("frames") and frames:
            imgs = "".join([f"<img class=\"fx-frame\" src=\"{self._esc(getattr(it, 'url', '') or '')}\" alt=\"\"/>" for it in frames if getattr(it, "url", "")])
            if imgs:
                parts.append(f"<div class=\"fx-frames\" data-fxframes=\"1\">{imgs}</div>")
        if enabled.get("mask") and mask and getattr(mask, "url", ""):
            parts.append(f"<div class=\"fx-mask\" style=\"--fx-mask:url('{self._esc(mask.url)}')\"></div>")
        if enabled.get("overlay") and overlay and getattr(overlay, "url", ""):
            parts.append(f"<div class=\"fx-overlay\" style=\"background-image:url('{self._esc(overlay.url)}')\"></div>")
        parts.append("</div>")
        return "".join(parts)

    def _has_image_focus_controls(self, plan: RenderPlan, eff_set: Set[str]) -> bool:
        try:
            if "Image Focus" not in (eff_set or set()):
                return False
            img = getattr(plan, "image", None)
            if not (img and getattr(img, "url", "")):
                return False
            return True
        except Exception:
            return False

    def _render_image_focus_controls(self, plan: RenderPlan) -> str:
        default_template = "AI"
        try:
            img = getattr(plan, "image", None)
            tid = str(getattr(img, "focus_template_id", "") or "").strip()
            if tid:
                default_template = tid
        except Exception:
            default_template = "AI"
        return f"""
  <div class="ds-focus-controls" data-focus-controls data-default-template="{self._esc(default_template)}">
    <div class="ds-focus-controls-inner">
      <div class="ds-focus-controls-item">
        <span class="ds-focus-label">布局模板</span>
        <select class="ds-focus-select" data-focus-template>
          <option value="AI">AI</option>
        </select>
      </div>
      <div class="ds-focus-controls-item">
        <span class="ds-focus-label">Padding</span>
        <select class="ds-focus-select" data-focus-padding>
          <option value="auto">自动</option>
          <option value="0">0</option>
          <option value="12">12</option>
          <option value="16">16</option>
          <option value="24">24</option>
          <option value="32">32</option>
          <option value="48">48</option>
          <option value="64">64</option>
          <option value="80">80</option>
          <option value="96">96</option>
          <option value="120">120</option>
          <option value="160">160</option>
          <option value="200">200</option>
        </select>
      </div>
    </div>
  </div>"""

    def _render_body(self, plan: RenderPlan, eff_set: Set[str], max_regions: int, grid_style: str) -> str:
        layout = plan.layout
        if layout == "hero_figure":
            return self._layout_hero(plan, max_regions, grid_style)
        if layout == "hero_figure_vertical":
            return self._layout_hero_vertical(plan, max_regions, grid_style)
        if layout == "metric_cards":
            return self._layout_metrics(plan, grid_style)
        if layout == "two_col_compare":
            return self._layout_two_col(plan, grid_style)
        if layout == "table_focus":
            return self._layout_table_focus(plan, eff_set)
        if layout in {"diagram_flow", "timeline", "tri_cards", "process_stack"}:
            return self._layout_diagram_or_steps(plan)
        if layout == "one_sentence":
            return self._layout_one_sentence(plan)
        if layout == "cover":
            return self._layout_cover(plan)
        return self._layout_solo(plan)

    def _stylize_bullet_html(self, b: str) -> str:
        s = b.strip()
        if not s:
            return ""
        # Check for colon highlight
        if ":" in s and len(s.split(":", 1)[0]) <= 36:
            left, right = s.split(":", 1)
            left = left.strip()
            right = right.strip()
            if left and right:
                return f"<span class=\"kw\">{self._render_text(left)}:</span> {self._render_text(right)}"
        return self._render_text(s)

    def _bullets(self, bullets: List[str]) -> str:
        items = "".join(
            f"<div class=\"bullet animate-in\" style=\"--delay: {0.2 + i*0.05}s\"><span class=\"bdot\"></span><div>{self._stylize_bullet_html(b)}</div></div>"
            for i, b in enumerate(bullets)
            if str(b or "").strip()
        )
        return f"<div class=\"bullets\">{items}</div>" if items else ""

    def _bullets_or_core(self, plan: RenderPlan, bullets_html: str) -> str:
        core = self._render_text(plan.core_message)
        core_html = f"<div class=\"core animate-in\" style=\"--delay: 0.15s; white-space: pre-wrap;\">{core}</div>" if core else ""
        return core_html + ("<hr class=\"sep animate-in\" style=\"--delay: 0.18s\"/>" if core_html and bullets_html else "") + bullets_html

    def _layout_cover(self, plan: RenderPlan) -> str:
        title = self._render_text(plan.title)
        subtitle = self._render_text(plan.subtitle)
        author = self._render_text(plan.author)
        date = self._render_text(plan.date)
        meta_html = ""
        if author or date:
            meta_html = f"<div class=\"cover-meta animate-in\" style=\"--delay: 0.25s\">{author} &middot; {date}</div>"
        core = self._render_text(plan.core_message)
        core_html = ""
        if core and str(plan.core_message or "").strip() and str(plan.core_message or "").strip() != str(plan.subtitle or "").strip():
            core_html = f"<div class=\"cover-tagline animate-in\" style=\"--delay: 0.2s\">{core}</div>"
        return f"""
<div class=\"slide-body layout--solo\">
  <div class=\"card cover-hero animate-in\" style=\"--delay: 0.12s\">
    <div class=\"cover-kicker animate-in\" style=\"--delay: 0.14s\"><span class=\"kdot\"></span><span>DeepSlide</span></div>
    <div class=\"cover-title animate-in\" style=\"--delay: 0.16s\">{title}</div>
    <div class=\"cover-subtitle animate-in\" style=\"--delay: 0.18s\">{subtitle}</div>
    {core_html}
    {meta_html}
  </div>
</div>"""

    def _layout_hero(self, plan: RenderPlan, max_regions: int, grid_style: str) -> str:
        img = plan.image
        if not img or not img.url:
            return self._layout_solo(plan)
        
        img_url = img.url
        # Deterministic ROI selection: use template if provided, else fallback to manual regions
        rois = []
        if img.focus_template_id:
            rois = get_regions_by_template(img.focus_template_id)
        else:
            rois = img.focus_regions or []
            
        safe_rois = []
        for r in (rois or [])[:10]:
            try:
                x, y, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
            except Exception:
                continue
            w = max(0.01, min(1.0, w))
            h = max(0.01, min(1.0, h))
            x = max(0.0, min(1.0 - w, x))
            y = max(0.0, min(1.0 - h, y))
            safe_rois.append([x, y, w, h])

        safe_rois.sort(key=lambda r: (r[1], r[0]))
        rois_json = json.dumps(safe_rois)
        
        bullets = self._bullets(plan.bullets[:3])

        body_attrs = ""
        try:
            if "Image Focus" in (plan.effects_used or []):
                layout_cfg = plan.layout_config or {}
                split = str(layout_cfg.get("split_ratio", "50:50") or "50:50")
                l_ratio, r_ratio = split.split(":")
                stack = str(layout_cfg.get("stack_ratio", split) or "60:40")
                t_ratio, b_ratio = stack.split(":")
                hcols = f"{l_ratio}fr {r_ratio}fr"
                vrows = f"{t_ratio}fr {b_ratio}fr"
                body_attrs = f' data-focus-hcols="{self._esc(hcols)}" data-focus-vrows="{self._esc(vrows)}"'
        except Exception:
            body_attrs = ""

        if safe_rois:
            img_html = f"""<div class="card borderless roi-grid-wrap focus-zoom-wrap animate-in" style="--delay: 0.15s" ondblclick='openLightbox("{self._esc(img_url)}", {rois_json})'>
            <div class="focus-zoom" data-focuszoom data-regions='{self._esc(rois_json)}' data-scale="2.0">
              <img class="focus-zoom-base" src="{self._esc(img_url)}" alt="figure"/>
              <div class="focus-zoom-dim"></div>
              <div class="focus-zoom-layer"></div>
            </div>
        </div>"""
        else:
            img_html = f"""<div class="card borderless media interactive animate-in" style="--delay: 0.15s" ondblclick='openLightbox("{self._esc(img_url)}", {rois_json})'>
            <img class="hero-img" src="{self._esc(img_url)}" alt="figure"/>
            <div class="zoom-hint">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
            </div>
        </div>"""
        
        return f"""
<div class="slide-body layout--hero" style="{grid_style}"{body_attrs}>
  {img_html}
  <div class="card animate-in" style="--delay: 0.2s">
    {self._bullets_or_core(plan, bullets)}
  </div>
</div>"""

    def _layout_hero_vertical(self, plan: RenderPlan, max_regions: int, grid_style: str) -> str:
        img = plan.image
        if not img or not img.url:
            return self._layout_solo(plan)

        img_url = img.url
        rois = []
        if img.focus_template_id:
            rois = get_regions_by_template(img.focus_template_id)
        else:
            rois = img.focus_regions or []

        safe_rois = []
        for r in (rois or [])[:10]:
            try:
                x, y, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
            except Exception:
                continue
            w = max(0.01, min(1.0, w))
            h = max(0.01, min(1.0, h))
            x = max(0.0, min(1.0 - w, x))
            y = max(0.0, min(1.0 - h, y))
            safe_rois.append([x, y, w, h])

        safe_rois.sort(key=lambda r: (r[1], r[0]))
        rois_json = json.dumps(safe_rois)

        bullets = self._bullets(plan.bullets[:3])

        body_attrs = ""
        try:
            if "Image Focus" in (plan.effects_used or []):
                layout_cfg = plan.layout_config or {}
                split = str(layout_cfg.get("split_ratio", "50:50") or "50:50")
                l_ratio, r_ratio = split.split(":")
                stack = str(layout_cfg.get("stack_ratio", split) or "60:40")
                t_ratio, b_ratio = stack.split(":")
                hcols = f"{l_ratio}fr {r_ratio}fr"
                vrows = f"{t_ratio}fr {b_ratio}fr"
                body_attrs = f' data-focus-hcols="{self._esc(hcols)}" data-focus-vrows="{self._esc(vrows)}"'
        except Exception:
            body_attrs = ""

        if safe_rois:
            img_html = f"""<div class="card borderless roi-grid-wrap focus-zoom-wrap animate-in" style="--delay: 0.15s" ondblclick='openLightbox("{self._esc(img_url)}", {rois_json})'>
            <div class="focus-zoom" data-focuszoom data-regions='{self._esc(rois_json)}' data-scale="2.0">
              <img class="focus-zoom-base" src="{self._esc(img_url)}" alt="figure"/>
              <div class="focus-zoom-dim"></div>
              <div class="focus-zoom-layer"></div>
            </div>
        </div>"""
        else:
            img_html = f"""<div class="card borderless media interactive animate-in" style="--delay: 0.15s" ondblclick='openLightbox("{self._esc(img_url)}", {rois_json})'>
            <img class="hero-img" src="{self._esc(img_url)}" alt="figure"/>
            <div class="zoom-hint">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
            </div>
        </div>"""

        return f"""
<div class="slide-body layout--hero-vertical" style="{grid_style}"{body_attrs}>
  {img_html}
  <div class="card animate-in" style="--delay: 0.2s">
    {self._bullets_or_core(plan, bullets)}
  </div>
</div>"""

    def _layout_metrics(self, plan: RenderPlan, grid_style: str) -> str:
        cards = []
        for i, m in enumerate(plan.metrics[:5]):
            delta = self._render_text(m.delta or "")
            delta_html = f"<div class=\"metric-delta\">{delta}</div>" if delta else ""
            cards.append(
                f"<div class=\"metric animate-in\" style=\"--delay: {0.15 + i*0.05}s\"><div class=\"metric-label\">{self._render_text(m.label)}</div><div class=\"metric-value\">{self._render_text(m.value)}</div>{delta_html}</div>"
            )
        cards_html = "".join(cards)
        bullets = self._bullets(plan.bullets[:2])
        return f"""
<div class=\"slide-body layout--metrics\" style=\"{grid_style}\">
  <div class=\"card no-bg transparent\">
    <div class=\"metrics\">{cards_html}</div>
  </div>
  <div class=\"card animate-in\" style=\"--delay: 0.25s\">
    {self._bullets_or_core(plan, bullets)}
  </div>
</div>"""

    def _layout_two_col(self, plan: RenderPlan, grid_style: str) -> str:
        bs = plan.bullets[:4]
        left = self._bullets(bs[:2])
        right = self._bullets(bs[2:])
        core = self._render_text(plan.core_message)
        core_html = f"<div class=\"core animate-in\" style=\"--delay: 0.15s\">{core}</div>" if core else ""
        return f"""
<div class=\"slide-body layout--two\" style=\"{grid_style}\">
  <div class=\"card animate-in\" style=\"--delay: 0.2s\">{core_html}{('<hr class=\"sep\"/>' if core_html else '')}{left}</div>
  <div class=\"card animate-in\" style=\"--delay: 0.3s\">{right}</div>
</div>"""

    def _layout_table_focus(self, plan: RenderPlan, eff_set: Set[str]) -> str:
        bullets = self._bullets(plan.bullets[:2])
        viz = plan.table_viz
        chart_html = ""
        if viz:
            spec = viz.spec if isinstance(getattr(viz, "spec", None), dict) else None
            option = (spec or {}).get("option") if isinstance((spec or {}).get("option"), dict) else None
            if option:
                spec_obj = dict(spec or {})
                spec_obj.setdefault("type", "echarts")
                json_text = json.dumps(spec_obj, ensure_ascii=False)
                json_text = json_text.replace("</", "<\\/").replace("<", "\\u003c")
                hid = hashlib.md5(json_text.encode("utf-8")).hexdigest()[:10]
                elem_id = f"echart-{hid}"
                data_json = json_text
                chart_html = f"""
  <div class=\"chart-block animate-in\" style=\"--delay: 0.25s\">
    <div class=\"echart\" data-table-viz=\"1\" data-echart-id=\"{elem_id}\"></div>
    <script type=\"application/json\" id=\"{elem_id}\">{data_json}</script>
  </div>"""
            elif isinstance(getattr(viz, "payload", None), dict) and viz.payload:
                data_json = self._esc(json.dumps(viz.payload, ensure_ascii=False))
                chart_html = f"""
  <div class=\"chart-block animate-in\" style=\"--delay: 0.25s\">
    <div class=\"echart\" data-table-viz=\"1\" data-echart=\"{data_json}\"></div>
  </div>"""

        return f"""
<div class=\"slide-body layout--solo layout--table-focus\">
  <div class=\"card animate-in\" style=\"--delay: 0.15s\">
    {self._bullets_or_core(plan, bullets)}
    {chart_html}
  </div>
</div>"""

    def _layout_diagram_or_steps(self, plan: RenderPlan) -> str:
        layout = plan.layout
        core_html = f"<div class=\"core animate-in\" style=\"--delay: 0.15s\">{self._render_text(plan.core_message)}</div>" if plan.core_message else ""
        
        content_html = ""
        if layout == "diagram_flow" and plan.diagram_spec:
            spec_dict = plan.diagram_spec.model_dump() if hasattr(plan.diagram_spec, "model_dump") else plan.diagram_spec
            content_html = f"<div class='animate-in' style='--delay: 0.25s'>{render_diagram_spec(spec_dict)}</div>"
        elif layout == "timeline":
            nodes = []
            for i, s in enumerate(plan.steps[:5]):
                lab, detail = self._split_step(s)
                nodes.append(f"<div class=\"tnode animate-in\" style=\"--delay: {0.2 + i*0.08}s\"><div class=\"tnum\">{i+1}</div><div class=\"tbody\"><div class=\"ttitle\">{self._render_text(lab)}</div><div class=\"tdesc\">{self._render_text(detail)}</div></div></div>")
            content_html = f"<div class=\"timeline\">{''.join(nodes)}</div>"
        elif layout == "tri_cards":
            cards = []
            for i, s in enumerate(plan.steps[:3]):
                lab, detail = self._split_step(s)
                cards.append(f"<div class=\"tcard animate-in\" style=\"--delay: {0.2 + i*0.1}s\"><div class=\"tcard-title\">{self._render_text(lab or f'Point {i+1}')}</div><div class=\"tcard-body\">{self._render_text(detail)}</div></div>")
            content_html = f"<div class=\"tri\">{''.join(cards)}</div>"
        elif layout == "process_stack":
            rows = []
            for i, s in enumerate(plan.steps[:5]):
                lab, detail = self._split_step(s)
                rows.append(f"<div class=\"prow animate-in\" style=\"--delay: {0.2 + i*0.05}s\"><div class=\"pbadge\">{i+1}</div><div class=\"pbox\"><div class=\"ptitle\">{self._render_text(lab)}</div><div class=\"pdesc\">{self._render_text(detail)}</div></div></div>")
            content_html = f"<div class=\"process\">{''.join(rows)}</div>"

        return f"""
<div class=\"slide-body layout--solo\">
  <div class=\"card borderless animate-in\" style=\"--delay: 0.15s\">
    {core_html}
    {content_html}
  </div>
</div>"""

    def _split_step(self, s: str) -> Tuple[str, str]:
        if ":" in s and len(s.split(":", 1)[0]) <= 36:
            l, r = s.split(":", 1)
            return l.strip(), r.strip()
        return s.strip(), ""

    def _layout_one_sentence(self, plan: RenderPlan) -> str:
        core = self._render_text(plan.core_message or plan.subtitle)
        return f"""
<div class=\"slide-body layout--solo\">
  <div class=\"card borderless cover-card animate-in\" style=\"--delay: 0.15s\">
    <div class=\"core big\">{core}</div>
  </div>
</div>"""

    def _layout_solo(self, plan: RenderPlan) -> str:
        bullets = self._bullets(plan.bullets[:4])
        # If no bullets, make it borderless for a cleaner "impact" look
        card_class = "card animate-in"
        if not bullets:
            card_class += " borderless"
            
        return f"""
<div class=\"slide-body layout--solo\">
  <div class=\"{card_class}\" style=\"--delay: 0.15s\">
    {self._bullets_or_core(plan, bullets)}
  </div>
</div>"""

    @staticmethod
    def _css() -> str:
        return """
:root {
  --bg-core: #09090b;
  --bg-card: rgba(255, 255, 255, 0.03);
  --bg-card-hover: rgba(255, 255, 255, 0.07);
  --accent-primary: #3b82f6;
  --accent-cyan: #06b6d4;
  --accent-purple: #8b5cf6;
  --accent-orange: #f97316;
  --accent-emerald: #10b981;
  --text-main: rgba(255, 255, 255, 0.95);
  --text-muted: rgba(255, 255, 255, 0.55);
  --border-soft: rgba(255, 255, 255, 0.08);
  --radius-lg: 32px;
  --radius-md: 20px;
  --shadow-lg: 0 24px 48px -12px rgba(0, 0, 0, 0.7);
  --font-main: "Plus Jakarta Sans", "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: "JetBrains Mono", "SFMono-Regular", monospace;
  --stage-max: min(1600px, 94vw);
  --page-w: 1600px;
  --page-h: 900px;
  --ds-focus-pad-x: 0px;
  --ds-focus-pad-top: 0px;
  --ds-focus-pad-bottom: 0px;
}

body[data-theme="light"] {
  --bg-core: #f8fafc;
  --bg-card: rgba(255, 255, 255, 0.6);
  --bg-card-hover: rgba(255, 255, 255, 0.85);
  --text-main: #0f172a;
  --text-muted: #64748b;
  --border-soft: rgba(15, 23, 42, 0.08);
}

/* Accents */
.accent-cyan { --accent-primary: var(--accent-cyan); }
.accent-purple { --accent-primary: var(--accent-purple); }
.accent-orange { --accent-primary: var(--accent-orange); }
.accent-emerald { --accent-primary: var(--accent-emerald); }

/* Glass Variant */
.theme-glass .card {
  backdrop-filter: blur(25px) saturate(180%);
  -webkit-backdrop-filter: blur(25px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
}

.theme-glass .card:hover {
  box-shadow: 0 0 40px rgba(59, 130, 246, 0.2);
  border-color: rgba(255, 255, 255, 0.35);
}

.card.borderless {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
}

.roi-grid-wrap.card.borderless { padding: 0 !important; }
.roi-grid-wrap.focus-zoom-wrap.card.borderless { padding: var(--ds-focus-pad-top) var(--ds-focus-pad-x) var(--ds-focus-pad-bottom) !important; }

.ds-has-image-focus .slide-body > * { min-height: 0; }
.ds-has-image-focus .roi-grid-wrap.focus-zoom-wrap { min-height: 0; max-height: 100%; }
.ds-has-image-focus .focus-zoom { min-height: 0; height: 100%; }
.ds-has-image-focus .focus-zoom-base { max-width: 100%; max-height: 100%; }

.ds-focus-controls { position: absolute; top: 14px; right: 14px; z-index: 60; display: none; }
body[data-mode="preview"] .ds-focus-controls, body.ds-controls-on .ds-focus-controls { display: block; }
.ds-focus-controls-inner { display: flex; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 16px; border: 1px solid var(--border-soft); background: rgba(0,0,0,0.35); backdrop-filter: blur(14px) saturate(180%); -webkit-backdrop-filter: blur(14px) saturate(180%); }
body[data-theme="light"] .ds-focus-controls-inner { background: rgba(255,255,255,0.75); }
.ds-focus-controls-item { display: inline-flex; gap: 8px; align-items: center; }
.ds-focus-label { font-size: 11px; font-weight: 800; letter-spacing: 0.02em; color: var(--text-muted); }
.ds-focus-select { height: 30px; border-radius: 12px; padding: 0 10px; border: 1px solid var(--border-soft); background: rgba(255,255,255,0.06); color: var(--text-main); font-size: 12px; font-weight: 750; outline: none; }
body[data-theme="light"] .ds-focus-select { background: rgba(255,255,255,0.92); color: var(--text-main); }
.ds-focus-select:focus { border-color: rgba(59,130,246,0.65); box-shadow: 0 0 0 3px rgba(59,130,246,0.18); }

/* Table Viz */
.chart-block { width: 100%; margin-top: 18px; }
.echart {
  width: 100%;
  height: 420px;
  min-height: 320px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border-soft);
  background: rgba(0,0,0,0.18);
}
body[data-theme="light"] .echart { background: rgba(255,255,255,0.65); }
body[data-mode="preview"] .echart { height: 460px; min-height: 360px; }

/* Keynote Highlight */
.keynote-highlight {
  display: inline;
  padding: 0;
  border-radius: 0;
}
.keynote-highlight.k1 {
  font-weight: 900;
  font-size: 1.35em;
  letter-spacing: -0.01em;
  color: var(--accent-primary);
  text-shadow: 0 0 26px rgba(59, 130, 246, 0.18);
}
.keynote-highlight.k2 {
  font-weight: 750;
  color: var(--text-main);
  border-bottom: 2px solid rgba(59,130,246,0.35);
}

.hl-aurora .keynote-highlight.k1 { background-image: linear-gradient(135deg, var(--accent-primary), var(--accent-purple), var(--accent-cyan)); }
.hl-sunset .keynote-highlight.k1 { background-image: linear-gradient(135deg, var(--accent-orange), #fb7185, #f59e0b); }
.hl-cyber .keynote-highlight.k1 { background-image: linear-gradient(135deg, var(--accent-cyan), #22c55e, var(--accent-primary)); }
.hl-violet .keynote-highlight.k1 { background-image: linear-gradient(135deg, var(--accent-purple), #a855f7, #38bdf8); }
.hl-mono .keynote-highlight.k1 { background-image: linear-gradient(135deg, var(--text-main), var(--text-muted)); }

@supports ((-webkit-background-clip: text) or (background-clip: text)) {
  .keynote-highlight.k1 { background-repeat: no-repeat; background-size: 100% 100%; background-position: 0 50%; }
  .hl-aurora .keynote-highlight.k1,
  .hl-sunset .keynote-highlight.k1,
  .hl-cyber .keynote-highlight.k1,
  .hl-violet .keynote-highlight.k1,
  .hl-mono .keynote-highlight.k1 {
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    color: transparent;
  }
}

.hl-underline .keynote-highlight.k1 {
  background: transparent;
  color: var(--text-main);
  text-shadow: none;
  border-bottom: 3px solid var(--accent-primary);
  border-radius: 0;
  padding: 0 2px;
}
.hl-underline .keynote-highlight.k2 {
  background: transparent;
  color: var(--text-main);
  text-decoration: underline;
  text-decoration-color: rgba(255,255,255,0.35);
  text-underline-offset: 4px;
}

/* Animations */
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-in {
  opacity: 0;
  animation: fadeInUp 0.6s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
  animation-delay: var(--delay, 0s);
}

.motion-static .animate-in { animation: none; opacity: 1; }

/* Background Blobs & Grid */
.background-blobs {
  position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none;
}
.background-blobs::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: 
    linear-gradient(var(--border-soft) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-soft) 1px, transparent 1px);
  background-size: 60px 60px;
  opacity: 0.15;
}
.background-blobs::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 50%, transparent 0%, var(--bg-core) 85%);
}

.blob {
  position: absolute; border-radius: 50%; filter: blur(100px); opacity: 0.2;
}
.blob-1 { width: 600px; height: 600px; background: var(--accent-primary); top: -10%; left: -10%; }
.blob-2 { width: 500px; height: 500px; background: var(--accent-purple); bottom: -10%; right: -10%; }
.blob-3 { width: 300px; height: 300px; background: var(--accent-cyan); top: 40%; left: 60%; }

/* Core Styles */
body {
  margin: 0;
  font-family: var(--font-main);
  background: var(--bg-core);
  color: var(--text-main);
  line-height: 1.6;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

.stage { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 40px 24px; }
.slide { width: var(--stage-max); min-height: 650px; position: relative; }
.slide-stage { position: relative; z-index: 1; display: flex; flex-direction: column; gap: 40px; padding: 60px 80px; }
.fx-layer { position: absolute; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; border-radius: 40px; }
.fx-bg { position: absolute; inset: 0; background-size: cover; background-position: center; opacity: 0.78; filter: saturate(1.05) contrast(1.02); transform: scale(1.02); }
.fx-overlay { position: absolute; inset: 0; background-size: cover; background-position: center; opacity: 0.92; mix-blend-mode: screen; }
body[data-theme="light"] .fx-overlay { mix-blend-mode: multiply; opacity: 0.68; }
.fx-mask { position: absolute; inset: 0; background: rgba(0,0,0,0.20); }
body[data-theme="light"] .fx-mask { background: rgba(255,255,255,0.10); }
.fx-mask { -webkit-mask-image: var(--fx-mask); mask-image: var(--fx-mask); -webkit-mask-size: cover; mask-size: cover; -webkit-mask-position: center; mask-position: center; -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat; }
.fx-frames { position: absolute; inset: 0; }
.fx-frame { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: 0; transition: opacity 220ms ease; }
.fx-frame.is-on { opacity: 1; }
.slide-head { display: flex; flex-direction: column; gap: 10px; }
.kicker { display: inline-flex; gap: 12px; align-items: center; font-weight: 700; text-transform: uppercase; font-size: 12px; color: var(--text-muted); letter-spacing: 0.2em; }
.kicker .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-primary); box-shadow: 0 0 10px var(--accent-primary); }
.subtitle { font-size: 22px; color: var(--text-muted); max-width: 900px; }

.slide-body { display: grid; gap: 32px; flex: 1; }
.layout--solo { grid-template-columns: 1fr; }
.layout--hero { grid-template-columns: 1fr 1fr; align-items: start; }
.layout--hero-vertical { grid-template-columns: 1fr; align-items: start; }
.layout--metrics { grid-template-columns: 1fr 1fr; align-items: stretch; }
.layout--two { grid-template-columns: 1fr 1fr; align-items: stretch; }

.card { background: var(--bg-card); border-radius: var(--radius-lg); padding: 40px; border: 1px solid var(--border-soft); transition: all 0.25s ease; position: relative; overflow: hidden; }
.card:hover { background: var(--bg-card-hover); transform: translateY(-3px); }
.card.no-bg { background: transparent; border: none; padding: 0; box-shadow: none; }

.bullets { display: flex; flex-direction: column; gap: 18px; }
.kw { color: var(--accent-primary); font-weight: 750; }

.title {
  margin: 0;
  font-size: clamp(40px, 5vw, 64px);
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.03em;
  text-wrap: balance;
}

.core {
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.015em;
  border-left: 6px solid var(--accent-primary);
  padding-left: 28px;
  line-height: 1.5;
  border-image: linear-gradient(to bottom, var(--accent-primary), var(--accent-purple)) 1;
}

.bullet {
  display: flex;
  gap: 20px;
  font-size: 20px;
  font-weight: 450;
  letter-spacing: -0.01em;
  align-items: flex-start;
}

.data-highlight {
  font-weight: 700;
  color: var(--accent-cyan);
  font-family: var(--font-mono);
  background: rgba(6, 182, 212, 0.1);
  padding: 0 4px;
  border-radius: 4px;
}

.bdot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent-primary); margin-top: 12px; flex: 0 0 auto; position: relative; }
.bdot::after { content: ''; position: absolute; inset: -4px; border: 1px solid var(--accent-primary); border-radius: 50%; opacity: 0.4; }

.core.big { font-size: 48px; text-align: center; border: none; padding: 0; font-weight: 800; background: linear-gradient(to bottom, var(--text-main), var(--text-muted)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

.layout-cover .slide-stage { padding: 84px 96px; justify-content: center; gap: 0; }
.layout-cover .slide-head { display: none; }
.layout-cover .slide-body { display: flex; align-items: center; justify-content: center; }
.cover-hero { width: min(1200px, 92%); margin: 0 auto; text-align: center; padding: 88px 92px; border-radius: 44px; border: 1px solid rgba(148,163,184,0.22); background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03)); box-shadow: 0 34px 90px -40px rgba(2,6,23,0.55); }
body[data-theme="light"] .cover-hero { border-color: rgba(15,23,42,0.10); background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,255,255,0.72)); box-shadow: 0 28px 90px -44px rgba(15,23,42,0.22); }
.cover-hero::before { content: ""; position: absolute; inset: -1px; border-radius: 46px; padding: 1px; background: linear-gradient(135deg, rgba(59,130,246,0.7), rgba(139,92,246,0.5), rgba(6,182,212,0.55)); -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude; pointer-events: none; opacity: 0.7; }
.cover-hero:hover { transform: translateY(-2px); }
.cover-kicker { display: inline-flex; gap: 10px; align-items: center; justify-content: center; font-weight: 800; letter-spacing: 0.22em; text-transform: uppercase; font-size: 12px; color: var(--text-muted); }
.cover-kicker .kdot { width: 9px; height: 9px; border-radius: 999px; background: var(--accent-primary); box-shadow: 0 0 18px rgba(59,130,246,0.55); }
.cover-title { margin-top: 22px; font-size: clamp(64px, 6.5vw, 92px); font-weight: 950; letter-spacing: -0.045em; line-height: 1.02; background: linear-gradient(135deg, var(--accent-primary), var(--accent-purple), var(--accent-cyan)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; color: transparent; text-shadow: 0 24px 80px rgba(59,130,246,0.12); }
.cover-subtitle { margin-top: 14px; font-size: 22px; font-weight: 650; color: var(--text-main); opacity: 0.9; letter-spacing: -0.01em; }
.cover-tagline { margin-top: 18px; font-size: 16px; color: var(--text-muted); max-width: 820px; margin-left: auto; margin-right: auto; line-height: 1.6; }
.cover-meta { display: inline-flex; align-items: center; justify-content: center; gap: 10px; margin-top: 44px; padding: 10px 14px; border-radius: 999px; border: 1px solid rgba(148,163,184,0.28); background: rgba(0,0,0,0.10); color: var(--text-muted); font-size: 12px; font-weight: 700; letter-spacing: 0.02em; }
body[data-theme="light"] .cover-meta { background: rgba(255,255,255,0.55); border-color: rgba(15,23,42,0.10); }
body[data-mode="preview"].layout-cover .cover-hero { width: 1200px; }

/* Glimmer / Tech Glow */
@keyframes glimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.theme-glass .card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.03), transparent);
  background-size: 200% 100%;
  animation: glimmer 8s linear infinite;
  pointer-events: none;
}

.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 24px; }
.metric { padding: 32px; border-radius: var(--radius-md); background: var(--bg-card); border: 1px solid var(--border-soft); display: flex; flex-direction: column; gap: 12px; }
.metric-label { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; }
.metric-value { font-size: 40px; font-weight: 800; font-family: var(--font-mono); color: var(--accent-primary); }
.metric-delta { font-size: 14px; font-weight: 600; color: var(--accent-cyan); }

.sep { border: 0; height: 1px; background: linear-gradient(to right, var(--border-soft), transparent); margin: 32px 0; }

.timeline { display: flex; flex-direction: column; gap: 16px; }
.tnode { display: flex; gap: 24px; padding: 24px; border-radius: var(--radius-md); background: rgba(255,255,255,0.03); border: 1px solid var(--border-soft); transition: all 0.3s ease; }
.tnode:hover { background: rgba(255,255,255,0.06); border-color: var(--accent-primary); }
.tnum { width: 36px; height: 36px; background: var(--accent-primary); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 16px; flex: 0 0 auto; box-shadow: 0 0 15px var(--accent-primary); }
.ttitle { font-weight: 700; font-size: 20px; margin-bottom: 6px; }
.tdesc { font-size: 16px; color: var(--text-muted); }

.hero-img { width: 100%; height: 100%; object-fit: contain; border-radius: var(--radius-md); }
.media { overflow: hidden; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.25); }

/* Focus Zoom */
.focus-zoom { position: relative; width: 100%; height: 100%; cursor: pointer; border-radius: var(--radius-md); overflow: hidden; background: rgba(0,0,0,0.08); }
.focus-zoom-base { display: block; width: 100%; height: 100%; object-fit: contain; opacity: 1; }
.focus-zoom-dim { position: absolute; inset: 0; background: rgba(2,6,23,0.58); pointer-events: none; }
body[data-theme="light"] .focus-zoom-dim { background: rgba(2,6,23,0.42); }
.focus-zoom-layer { position: absolute; inset: 0; pointer-events: none; }
.focus-zoom-box { position: absolute; background: transparent; border-radius: var(--radius-md); overflow: hidden; border: 2px solid rgba(59,130,246,0.95); box-shadow: 0 0 0 1px rgba(15,23,42,0.65), 0 18px 60px -26px rgba(2,6,23,0.75); opacity: 0; transform: translate(var(--focus-tx, 0), var(--focus-ty, 0)); transition: opacity 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease; }
.focus-zoom-box.is-active { opacity: 1; z-index: 10; }
.focus-zoom-box img { position: absolute; max-width: none !important; max-height: none !important; }

.roi-grid-wrap { background: transparent !important; display: flex; align-items: stretch; justify-content: stretch; }
.roi-grid { width: 100%; height: auto; display: grid; grid-template-columns: repeat(var(--roi-cols, 2), 1fr); gap: 14px; padding: 14px; align-content: start; align-items: start; justify-items: stretch; }
.roi-tile { position: relative; overflow: hidden; border-radius: 16px; border: 1px solid rgba(148,163,184,0.35); background: rgba(0,0,0,0.10); box-shadow: 0 18px 40px -26px rgba(15,23,42,0.9); transform: translateZ(0); transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease; height: auto; }
.roi-tile.is-active { border-color: rgba(59,130,246,0.95); box-shadow: 0 0 0 2px rgba(59,130,246,0.55), 0 22px 60px -26px rgba(15,23,42,0.95); transform: translateY(-1px) scale(1.01); }
.roi-img { position: absolute; left: 0; top: 0; transform-origin: top left; will-change: transform; opacity: 0; filter: saturate(1.05) contrast(1.05); }
.roi-tile.is-ready .roi-img { opacity: 1; }
.roi-tile::after { content:''; position:absolute; inset:0; border-radius: 16px; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05); pointer-events:none; }
.roi-badge { position: absolute; left: 10px; top: 10px; width: 26px; height: 26px; border-radius: 999px; display:flex; align-items:center; justify-content:center; font-weight:800; font-size: 13px; color: rgba(255,255,255,0.92); background: rgba(15,23,42,0.65); border: 1px solid rgba(148,163,184,0.45); backdrop-filter: blur(8px); }

.lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.95); z-index: 9999; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(15px); }
.hidden { display: none; }
.lightbox-content img { max-width: 90vw; max-height: 90vh; width: auto; height: auto; object-fit: unset; border-radius: 12px; display: block; }
.lightbox-content { position: relative; }
.lb-wrap { position: relative; display: inline-block; }
#lb-rois { position: absolute; inset: 0; pointer-events: none; }
.lb-roi-label { position: absolute; left: 6px; top: 4px; font-size: 14px; font-weight: 700; color: #f9fafb; text-shadow: 0 1px 3px rgba(15,23,42,0.85); pointer-events: none; }

body[data-mode="preview"] .stage { min-height: 100%; padding: 0; align-items: center; justify-content: center; }
body[data-mode="preview"] .slide { width: var(--page-w); min-height: var(--page-h); }
body[data-mode="preview"] .slide-stage { padding: 56px 72px; gap: 28px; }
body[data-mode="preview"] { background: transparent; }
body[data-mode="preview"] .title { font-size: 56px; }
body[data-mode="preview"] .core { font-size: 24px; }
body[data-mode="preview"] .bullet { font-size: 18px; }
body[data-mode="preview"] .focus-zoom-base { opacity: 1; }
body[data-mode="preview"] .theme-glass .card::after { animation: none; }

""" + diagram_kit_css()

    @staticmethod
    def _js() -> str:
        return """
    let currentRois = [];
    let currentRoiIndex = -1;
    let _lbResizeObs = null;

    function openLightbox(url, rois) {
      const lb = document.getElementById('lightbox');
      const img = document.getElementById('lb-img');
      img.src = url;
      lb.classList.remove('hidden');
      currentRois = rois || [];
      currentRoiIndex = -1;
      try {
        if (_lbResizeObs) _lbResizeObs.disconnect();
        if (typeof ResizeObserver !== 'undefined') {
          _lbResizeObs = new ResizeObserver(() => renderRois());
          _lbResizeObs.observe(img);
        }
      } catch (e) {}
      let rafCount = 0;
      function kick() {
        renderRois();
        rafCount += 1;
        if (rafCount < 6) requestAnimationFrame(kick);
      }
      img.onload = () => kick();
      kick();
    }

    function closeLightbox(e) {
      if (e) e.stopPropagation();
      document.getElementById('lightbox').classList.add('hidden');
    }

    function nextRoi(e) {
      if (e) e.stopPropagation();
      if (!currentRois.length) return;
      currentRoiIndex = (currentRoiIndex + 1) % currentRois.length;
      renderRois();
    }

    function renderRois() {
      const roiCont = document.getElementById('lb-rois');
      roiCont.innerHTML = '';
      if (!currentRois.length) return;
      const img = document.getElementById('lb-img');
      if (!img) return;
      const w0 = (img && img.clientWidth) ? img.clientWidth : 0;
      const h0 = (img && img.clientHeight) ? img.clientHeight : 0;
      const imgRect = img.getBoundingClientRect();
      const drawW = w0 || imgRect.width || 0;
      const drawH = h0 || imgRect.height || 0;
      if (!drawW || !drawH) {
        setTimeout(renderRois, 50);
        return;
      }
      const contentW = drawW;
      const contentH = drawH;
      const padX = 0;
      const padY = 0;
      const toShow = (currentRoiIndex === -1) ? currentRois.map((r, i) => ({ r, i })) : [{ r: currentRois[currentRoiIndex], i: currentRoiIndex }];
      const labels = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨"];
      toShow.forEach(item => {
        const [rx, ry, rw, rh] = item.r;
        const x = padX + rx * contentW;
        const y = padY + ry * contentH;
        const w = rw * contentW;
        const h = rh * contentH;
        const div = document.createElement('div');
        div.className = 'lb-roi';
        div.style.cssText = `left:${x}px; top:${y}px; width:${w}px; height:${h}px; position:absolute; border:2px solid #3b82f6; background:rgba(59,130,246,0.12); box-shadow:0 0 0 1px rgba(15,23,42,0.7),0 18px 40px -22px rgba(15,23,42,0.9); border-radius:14px;`;
        const lab = document.createElement('div');
        lab.className = 'lb-roi-label';
        const idx = item.i || 0;
        lab.textContent = labels[idx] || String(idx + 1);
        div.appendChild(lab);
        roiCont.appendChild(div);
      });
    }

    function initFocusControls() {
      try {
        const sp = new URLSearchParams(location.search || '');
        if (sp.get('controls') === '1') document.body.classList.add('ds-controls-on');
      } catch (e) {}
      const ctl = document.querySelector('[data-focus-controls]');
      if (!ctl) return;
      const tmplSel = ctl.querySelector('[data-focus-template]');
      const padSel = ctl.querySelector('[data-focus-padding]');
      const rootStyle = document.documentElement.style;

      function applyPadding(mode) {
        const m = String(mode || 'auto').toLowerCase();
        if (m === 'auto') {
          try { rootStyle.removeProperty('--ds-focus-pad-x'); } catch (e) {}
          try { rootStyle.removeProperty('--ds-focus-pad-top'); } catch (e) {}
          try { rootStyle.removeProperty('--ds-focus-pad-bottom'); } catch (e) {}
          return;
        }
        let v = Number(m);
        if (!isFinite(v)) return;
        v = Math.max(0, Math.min(200, Math.round(v)));
        const bottom = Math.max(0, Math.min(80, Math.round(v * 0.2)));
        try { rootStyle.setProperty('--ds-focus-pad-x', `${v}px`); } catch (e) {}
        try { rootStyle.setProperty('--ds-focus-pad-top', `${v}px`); } catch (e) {}
        try { rootStyle.setProperty('--ds-focus-pad-bottom', `${bottom}px`); } catch (e) {}
        try { window.dispatchEvent(new Event('resize')); } catch (e) {}
      }

      function loadTemplates() {
        try {
          if (window.__ds_focus_templates && Array.isArray(window.__ds_focus_templates)) return window.__ds_focus_templates;
          const el = document.getElementById('ds-focus-templates');
          if (!el || !el.textContent) return [];
          const arr = JSON.parse(el.textContent || '[]');
          return Array.isArray(arr) ? arr : [];
        } catch (e) {
          return [];
        }
      }

      function normalizeId(s) {
        const raw = String(s || '').trim().toUpperCase();
        const out = [];
        let prevUs = false;
        for (let i = 0; i < raw.length; i++) {
          const ch = raw[i];
          const ok = (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9');
          if (ok) {
            out.push(ch);
            prevUs = false;
          } else if (!prevUs) {
            out.push('_');
            prevUs = true;
          }
        }
        return out.join('').replace(/^_+|_+$/g, '');
      }

      const templatesArr = loadTemplates();
      const templatesMap = {};
      templatesArr.forEach(t => {
        if (!t || typeof t !== 'object') return;
        const id = normalizeId(t.id || '');
        const desc = String(t.description || '');
        const regs = Array.isArray(t.regions) ? t.regions : [];
        if (!id || !regs.length) return;
        templatesMap[id] = { id, desc, regions: regs };
      });

      if (tmplSel) {
        const keys = Object.keys(templatesMap);
        keys.forEach(id => {
          const opt = document.createElement('option');
          opt.value = id;
          opt.textContent = id;
          try {
            const d = templatesMap[id] && templatesMap[id].desc ? String(templatesMap[id].desc) : '';
            if (d) opt.title = d;
          } catch (e) {}
          tmplSel.appendChild(opt);
        });
      }

      function setFocusRegions(regions) {
        const els = Array.from(document.querySelectorAll('[data-focuszoom]'));
        if (!els.length) return;
        els.forEach(el => {
          try {
            const cur = el.getAttribute('data-regions') || '[]';
            if (!el.getAttribute('data-regions-ai')) el.setAttribute('data-regions-ai', cur);
          } catch (e) {}
          try {
            const txt = JSON.stringify(regions || []);
            el.setAttribute('data-regions', txt);
          } catch (e) {}
          try {
            const baseImg = el.querySelector('img.focus-zoom-base');
            const wrap = el.closest('.focus-zoom-wrap');
            if (baseImg && wrap) {
              wrap.ondblclick = (ev) => {
                try { if (ev) ev.stopPropagation(); } catch (e) {}
                let rois = [];
                try { rois = JSON.parse(el.getAttribute('data-regions') || '[]'); } catch (e) { rois = []; }
                openLightbox(baseImg.currentSrc || baseImg.src, rois);
              };
            }
          } catch (e) {}
        });
        try { window.dispatchEvent(new Event('resize')); } catch (e) {}
      }

      function applyTemplate(mode) {
        const v = normalizeId(mode || '');
        if (!v || v === 'AI') {
          const el = document.querySelector('[data-focuszoom]');
          if (!el) return;
          let orig = null;
          try { orig = JSON.parse(el.getAttribute('data-regions-ai') || el.getAttribute('data-regions') || '[]'); } catch (e) { orig = []; }
          setFocusRegions(orig);
          return;
        }
        const it = templatesMap[v];
        if (!it) return;
        setFocusRegions(it.regions || []);
      }

      function safeGet(k) {
        try { return window.localStorage ? window.localStorage.getItem(k) : null; } catch (e) { return null; }
      }
      function safeSet(k, v) {
        try { if (window.localStorage) window.localStorage.setItem(k, v); } catch (e) {}
      }

      const savedPad = safeGet('ds_focus_pad') || '';
      const savedTpl = safeGet('ds_focus_template_id') || '';
      if (padSel && savedPad) padSel.value = savedPad;
      if (tmplSel && savedTpl) tmplSel.value = savedTpl;
      const defaultTpl = normalizeId(ctl.getAttribute('data-default-template') || 'AI') || 'AI';
      if (tmplSel && !tmplSel.value) tmplSel.value = defaultTpl;
      applyTemplate((tmplSel && tmplSel.value) ? tmplSel.value : defaultTpl);
      applyPadding((padSel && padSel.value) ? padSel.value : 'auto');

      if (tmplSel) {
        tmplSel.addEventListener('change', () => {
          const v = String(tmplSel.value || 'AI');
          safeSet('ds_focus_template_id', v);
          applyTemplate(v);
        });
      }
      if (padSel) {
        padSel.addEventListener('change', () => {
          const v = String(padSel.value || 'auto');
          safeSet('ds_focus_pad', v);
          applyPadding(v);
        });
      }
    }

    function initFocusZoom() {
      document.querySelectorAll('[data-focuszoom]').forEach(el => {
        const baseImg = el.querySelector('img.focus-zoom-base');
        const layer = el.querySelector('.focus-zoom-layer');
        if (!baseImg || !layer) return;
        let boxes = [];
        let idx = 0;
        let clickTimer = null;
        let lastDrawW = 0;
        let lastDrawH = 0;
        let decodeKicked = false;

        function update() {
          let regions = [];
          try { regions = JSON.parse(el.getAttribute('data-regions') || '[]'); } catch (e) { regions = []; }
          const natW = baseImg.naturalWidth || 0;
          const natH = baseImg.naturalHeight || 0;
          if (!natW || !natH) {
            if (!decodeKicked && baseImg.decode) {
              decodeKicked = true;
              try {
                baseImg.decode().then(() => { decodeKicked = false; update(); }).catch(() => { decodeKicked = false; });
              } catch (e) {
                decodeKicked = false;
              }
            }
            setTimeout(update, 60);
            return;
          }

          const w0 = (el && el.clientWidth) ? el.clientWidth : 0;
          const h0 = (el && el.clientHeight) ? el.clientHeight : 0;
          const w1 = (baseImg && baseImg.clientWidth) ? baseImg.clientWidth : 0;
          const h1 = (baseImg && baseImg.clientHeight) ? baseImg.clientHeight : 0;
          const rect = baseImg.getBoundingClientRect();
          const drawW = w0 || w1 || rect.width || 0;
          const drawH = h0 || h1 || rect.height || 0;
          if (!drawW || !drawH) {
            setTimeout(update, 60);
            return;
          }
          lastDrawW = drawW;
          lastDrawH = drawH;
          el.style.aspectRatio = `${natW} / ${natH}`;

          const imgRatio = natW / Math.max(1e-6, natH);
          const boxRatio = drawW / Math.max(1e-6, drawH);
          let contentW = 0;
          let contentH = 0;
          let padX = 0;
          let padY = 0;
          if (boxRatio > imgRatio) {
            contentH = drawH;
            contentW = drawH * imgRatio;
            padX = (drawW - contentW) / 2;
            padY = 0;
          } else {
            contentW = drawW;
            contentH = drawW / Math.max(1e-6, imgRatio);
            padX = 0;
            padY = (drawH - contentH) / 2;
          }
          boxes.forEach(b => b.remove());
          boxes = regions.map(r => {
            const box = document.createElement('div');
            box.className = 'focus-zoom-box';
            const x = padX + (r[0] * contentW);
            const y = padY + (r[1] * contentH);
            const w = r[2] * contentW;
            const h = r[3] * contentH;
            box.style.cssText = `left:${x}px; top:${y}px; width:${w}px; height:${h}px;`;
            box.dataset.x = String(x);
            box.dataset.y = String(y);
            box.dataset.w = String(w);
            box.dataset.h = String(h);
            const innerImg = document.createElement('img');
            innerImg.src = baseImg.src;
            innerImg.style.cssText = `width:${contentW}px; height:${contentH}px; left:${-(r[0] * contentW)}px; top:${-(r[1] * contentH)}px;`;
            box.appendChild(innerImg);
            layer.appendChild(box);
            return box;
          });
          if (boxes.length) setActive(0);
        }

        function clamp(v, lo, hi) {
          const a = Math.min(lo, hi);
          const b = Math.max(lo, hi);
          return Math.max(a, Math.min(b, v));
        }

        function fitInBounds(b) {
          b.style.setProperty('--focus-tx', `0px`);
          b.style.setProperty('--focus-ty', `0px`);
        }

        function setActive(i) {
          boxes.forEach((b, j) => b.classList.toggle('is-active', i === j));
          boxes.forEach((b, j) => {
            if (i === j) fitInBounds(b);
            else {
              b.style.setProperty('--focus-tx', '0px');
              b.style.setProperty('--focus-ty', '0px');
            }
          });
          idx = i;
        }

        function step() { if (boxes.length) setActive((idx + 1) % boxes.length); }

        el.addEventListener('click', () => {
          if (clickTimer) clearTimeout(clickTimer);
          clickTimer = setTimeout(() => { clickTimer = null; step(); }, 220);
        });
        el.addEventListener('dblclick', () => {
          if (clickTimer) clearTimeout(clickTimer);
          clickTimer = null;
        });

        baseImg.onload = update;
        window.addEventListener('resize', update);
        setTimeout(update, 50);
      });
    }

    function initRoiTiles() {
      document.querySelectorAll('.roi-grid-wrap').forEach(wrap => {
        const tiles = Array.from(wrap.querySelectorAll('.roi-tile'));
        if (!tiles.length) return;
        let idx = 0;
        let clickTimer = null;

        function setActive(i) {
          tiles.forEach((t, j) => t.classList.toggle('is-active', i === j));
          idx = i;
        }

        function applyCrop(t) {
          const img = t.querySelector('img.roi-img');
          if (!img) return;
          let roi = null;
          try { roi = JSON.parse(t.getAttribute('data-roi') || 'null'); } catch (e) { roi = null; }
          if (!roi || roi.length < 4) return;

          // Expect ROI in normalized [0,1] w.r.t. the ORIGINAL image.
          // Clamp defensively.
          let x = Number(roi[0] || 0);
          let y = Number(roi[1] || 0);
          let w = Number(roi[2] || 0.01);
          let h = Number(roi[3] || 0.01);
          if (!isFinite(x)) x = 0;
          if (!isFinite(y)) y = 0;
          if (!isFinite(w)) w = 0.01;
          if (!isFinite(h)) h = 0.01;
          w = Math.max(0.01, Math.min(1.0, w));
          h = Math.max(0.01, Math.min(1.0, h));
          x = Math.max(0.0, Math.min(1.0 - 1e-6, x));
          y = Math.max(0.0, Math.min(1.0 - 1e-6, y));
          if (x + w > 1.0) w = Math.max(0.01, 1.0 - x);
          if (y + h > 1.0) h = Math.max(0.01, 1.0 - y);

          // Set tile aspect ratio to match the crop region (stable in CSS grid).
          const natW = img.naturalWidth || 1;
          const natH = img.naturalHeight || 1;
          const roiAspect = (w * natW) / Math.max(1e-6, (h * natH));
          if (isFinite(roiAspect) && roiAspect > 0) {
            t.style.aspectRatio = String(roiAspect);
          }

          // ---- Robust crop (background-position approach) -------------------
          // This avoids transform-order bugs and stays correct under any layout sizing.
          // Scale background so that the ROI fills the tile.
          const bgSizeX = (100 / w);
          const bgSizeY = (100 / h);
          const bgPosX = (-x / w) * 100;
          const bgPosY = (-y / h) * 100;

          // Apply to tile as background.
          t.style.backgroundImage = `url("${img.currentSrc || img.src}")`;
          t.style.backgroundRepeat = 'no-repeat';
          t.style.backgroundSize = `${bgSizeX}% ${bgSizeY}%`;
          t.style.backgroundPosition = `${bgPosX}% ${bgPosY}%`;

          // Hide the img element; we keep it for preload/natural size.
          img.style.display = 'none';
          t.classList.add('is-ready');
        }

        function updateAll() { tiles.forEach(t => applyCrop(t)); }

        setActive(0);
        tiles.forEach(t => {
          const img = t.querySelector('img.roi-img');
          if (!img) return;
          if (img.complete && img.naturalWidth) applyCrop(t);
          else img.addEventListener('load', () => applyCrop(t), { once: true });
        });
        window.addEventListener('resize', () => setTimeout(updateAll, 50));
        try {
          if (typeof ResizeObserver !== 'undefined') {
            const ro = new ResizeObserver(() => setTimeout(updateAll, 0));
            ro.observe(wrap);
            tiles.forEach(t => ro.observe(t));
          }
        } catch (e) {}

        tiles.forEach((t, i) => {
          t.addEventListener('click', (e) => {
            e.stopPropagation();
            setActive(i);
          });
        });

        wrap.addEventListener('click', () => {
          if (clickTimer) clearTimeout(clickTimer);
          clickTimer = setTimeout(() => {
            clickTimer = null;
            setActive((idx + 1) % tiles.length);
          }, 220);
        });
        wrap.addEventListener('dblclick', () => {
          if (clickTimer) clearTimeout(clickTimer);
          clickTimer = null;
        });
      });
    }

    function initTableViz() {
      document.querySelectorAll('.echart[data-echart], .echart[data-echart-id]').forEach(el => {
        function showErr(msg) {
          try {
            const safe = String(msg || 'Table viz failed').slice(0, 240);
            el.innerHTML = `<div style="padding:12px 14px;font-family:var(--font-mono);font-size:12px;line-height:1.35;color:rgba(148,163,184,0.95);">${safe}</div>`;
            try { el.dataset.echartsReady = '0'; } catch (e) {}
          } catch (e) {}
        }

        function loadECharts() {
          try {
            if (window.echarts && typeof window.echarts.init === 'function') return Promise.resolve(window.echarts);
            if (window.__ds_echarts_promise) return window.__ds_echarts_promise;
            window.__ds_echarts_promise = new Promise((resolve, reject) => {
              const s = document.createElement('script');
              s.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js';
              s.async = true;
              s.onload = () => {
                if (window.echarts && typeof window.echarts.init === 'function') resolve(window.echarts);
                else reject(new Error('ECharts loaded but window.echarts.init missing'));
              };
              s.onerror = () => reject(new Error('Failed to load ECharts script'));
              document.head.appendChild(s);
            });
            return window.__ds_echarts_promise;
          } catch (e) {
            return Promise.reject(e);
          }
        }

        function readJsonFromId(id) {
          const node = id ? document.getElementById(id) : null;
          if (!node) return null;
          const raw = String(node.textContent || '').trim();
          if (!raw) return null;
          try { return JSON.parse(raw); } catch (e) { return null; }
        }

        function isEChartsOption(o) {
          if (!o || typeof o !== 'object') return false;
          const hasDataSystem = !!(o.dataset || o.xAxis || o.yAxis || o.polar || o.radar || o.geo || o.calendar || o.parallel);
          const s = o.series;
          if (!s) return false;
          if (Array.isArray(s)) return hasDataSystem && s.some(it => it && typeof it === 'object' && typeof it.type === 'string' && it.type);
          return hasDataSystem && typeof s === 'object' && typeof s.type === 'string' && s.type;
        }

        function legacyToOption(p, isDark) {
          if (!p || typeof p !== 'object') throw new Error('Table viz payload is empty');
          const kind = String(p.kind || '').toLowerCase();
          const x = Array.isArray(p.x) ? p.x : [];
          const y = Array.isArray(p.y) ? p.y : [];
          const metric = String(p.metric || '');
          const textMain = isDark ? 'rgba(255,255,255,0.85)' : 'rgba(15,23,42,0.85)';
          const grid = { left: 42, right: 20, top: 36, bottom: 42, containLabel: true };
          const axisLabel = { color: textMain };
          if (kind === 'bar') {
            const seriesIn = Array.isArray(p.series) ? p.series : [];
            const series = seriesIn.length
              ? seriesIn.map(s => ({ type: 'bar', name: String((s || {}).name || ''), data: Array.isArray((s || {}).data) ? (s || {}).data : [], barMaxWidth: 42, itemStyle: { borderRadius: 8 } }))
              : [{ type: 'bar', name: metric || 'series', data: Array.isArray(p.data) ? p.data : (Array.isArray(y) ? y : []), barMaxWidth: 42, itemStyle: { borderRadius: 8 } }];
            const yName = (Array.isArray(y) && y.length === 1 && typeof y[0] === 'string') ? String(y[0]) : '';
            return {
              grid,
              tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
              legend: series.length > 1 ? { top: 0, textStyle: { color: textMain, fontSize: 11 } } : undefined,
              xAxis: { type: 'category', data: x, axisLabel },
              yAxis: { type: 'value', name: yName || undefined, axisLabel, splitLine: { lineStyle: { opacity: 0.2 } } },
              series,
              title: metric ? { text: metric, left: 'center', top: 0, textStyle: { color: textMain, fontSize: 12, fontWeight: 600 } } : undefined,
            };
          }
          if (kind === 'line') {
            const seriesIn = Array.isArray(p.series) ? p.series : [];
            const series = seriesIn.length
              ? seriesIn.map(s => ({ type: 'line', showSymbol: false, smooth: true, name: String((s || {}).name || ''), data: Array.isArray((s || {}).data) ? (s || {}).data : [] }))
              : [{ type: 'line', showSymbol: false, smooth: true, name: metric || 'series', data: Array.isArray(p.data) ? p.data : (Array.isArray(y) ? y : []) }];
            return {
              grid,
              tooltip: { trigger: 'axis' },
              legend: series.length > 1 ? { top: 0, textStyle: { color: textMain, fontSize: 11 } } : undefined,
              xAxis: { type: 'category', data: x, axisLabel },
              yAxis: { type: 'value', axisLabel, splitLine: { lineStyle: { opacity: 0.2 } } },
              series,
            };
          }
          if (kind === 'heatmap') {
            const xh = Array.isArray(p.x) ? p.x : [];
            const yh = Array.isArray(p.y) ? p.y : [];
            const data = Array.isArray(p.data) ? p.data : [];
            const vmax = typeof p.max === 'number' ? p.max : (data.length ? Math.max.apply(null, data.map(d => Number((d || [0,0,0])[2]) || 0)) : 10);
            return {
              grid: { left: 70, right: 20, top: 30, bottom: 56 },
              tooltip: { position: 'top' },
              xAxis: { type: 'category', data: xh, splitArea: { show: true }, axisLabel },
              yAxis: { type: 'category', data: yh, splitArea: { show: true }, axisLabel },
              visualMap: { min: 0, max: vmax || 10, calculable: true, orient: 'horizontal', left: 'center', bottom: 8, textStyle: { color: textMain } },
              series: [{ type: 'heatmap', data, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.35)' } } }],
            };
          }
          throw new Error('Table viz payload is not supported');
        }

        let rawObj = null;
        const id = (el.getAttribute('data-echart-id') || '').trim();
        if (id) rawObj = readJsonFromId(id);
        if (!rawObj) {
          try { rawObj = JSON.parse(el.getAttribute('data-echart') || 'null'); } catch (e) { rawObj = null; }
        }
        if (!rawObj) {
          showErr('Table viz JSON parse failed');
          return;
        }

        const bodyTheme = (document.body.getAttribute('data-theme') || '').toLowerCase();
        const isDark = bodyTheme === 'dark';
        if ((el.clientHeight || 0) < 40) el.style.height = '420px';

        let renderer = 'auto';
        let height = 0;
        let option = null;
        try {
          if (rawObj && typeof rawObj === 'object' && String(rawObj.type || '').toLowerCase() === 'echarts' && rawObj.option && typeof rawObj.option === 'object') {
            option = rawObj.option;
            renderer = String(rawObj.renderer || 'auto').toLowerCase();
            height = Number(rawObj.height || 0) || 0;
          } else if (rawObj && typeof rawObj === 'object' && rawObj.spec && typeof rawObj.spec === 'object' && rawObj.spec.option && typeof rawObj.spec.option === 'object') {
            option = rawObj.spec.option;
            renderer = String(rawObj.spec.renderer || 'auto').toLowerCase();
            height = Number(rawObj.spec.height || 0) || 0;
          } else if (isEChartsOption(rawObj)) {
            option = rawObj;
          } else {
            option = legacyToOption(rawObj, isDark);
          }
        } catch (e) {
          showErr(e && e.message ? e.message : 'Table viz option invalid');
          return;
        }
        if (!option || typeof option !== 'object') {
          showErr('Table viz option is empty');
          return;
        }
        if (height > 100) {
          try { el.style.height = `${Math.round(height)}px`; } catch (e) {}
        }

        loadECharts()
          .then(echarts => {
            const initOpts = {};
            if (renderer === 'canvas' || renderer === 'svg') initOpts.renderer = renderer;
            let chart = null;
            try { chart = echarts.init(el, isDark ? 'dark' : undefined, initOpts); } catch (e) { chart = null; }
            if (!chart) throw new Error('ECharts init failed');
            try { chart.setOption(option, true); } catch (e) { throw e; }
            try { el.dataset.echartsReady = '1'; } catch (e) {}
            const onResize = () => { try { chart.resize(); } catch (e) {} };
            window.addEventListener('resize', onResize);
            try {
              if (typeof ResizeObserver !== 'undefined') {
                const ro = new ResizeObserver(() => onResize());
                ro.observe(el);
              }
            } catch (e) {}
            requestAnimationFrame(() => onResize());
          })
          .catch(e => showErr(e && e.message ? e.message : 'Table viz failed'));
      });
    }

    function autoHighlightData() {
      // Auto highlight numbers and percentages in text
      const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
      let node;
      const regex = /(\\b\\d+(?:\\.\\d+)?%?|\\b\\d+x\\b)/g;
      const nodesToReplace = [];
      while (node = walk.nextNode()) {
        if (node.parentElement.closest('script, style, .keynote-highlight, .echart')) continue;
        if (regex.test(node.nodeValue)) {
          nodesToReplace.push(node);
        }
      }
      nodesToReplace.forEach(node => {
        const span = document.createElement('span');
        span.innerHTML = node.nodeValue.replace(regex, '<span class="data-highlight">$1</span>');
        node.parentNode.replaceChild(span, node);
      });
    }

    function initFxFrames() {
      document.querySelectorAll('.fx-layer[data-fx="1"]').forEach(layer => {
        const cont = layer.querySelector('[data-fxframes="1"]');
        if (!cont) return;
        const frames = Array.from(cont.querySelectorAll('img.fx-frame'));
        if (!frames.length) return;
        const fps = Number(layer.getAttribute('data-fps') || '10');
        const frameMs = Number(layer.getAttribute('data-frame-ms') || '0');
        const interval = frameMs > 0
          ? Math.max(60, Math.floor(frameMs))
          : Math.max(60, Math.floor(1000 / Math.max(1, Math.min(30, fps))));
        let idx = 0;
        frames.forEach((el, i) => el.classList.toggle('is-on', i === 0));
        setInterval(() => {
          frames[idx].classList.remove('is-on');
          idx = (idx + 1) % frames.length;
          frames[idx].classList.add('is-on');
        }, interval);
      });
    }

    document.addEventListener('DOMContentLoaded', () => {
      initFocusControls();
      initFocusZoom();
      initRoiTiles();
      initTableViz();
      initFxFrames();
      if (!document.body.classList.contains('fx-keynote')) autoHighlightData();
    });
    """
