import json
import os
import re
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.agent_model_env import resolve_text_llm_env


MAX_NODE_TEXT_CHARS = 44
MAX_EDGE_LABEL_CHARS = 0
MAX_TEXT_CELLS = 3

PAGE_WIDTH = 960
PAGE_HEIGHT = 540

DISPLAY_TOOL_NAMES = {"display_diagram", "create_new_diagram"}
APPEND_TOOL_NAMES = {"append_diagram"}

PHASE_CONTAINER_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;container=1;collapsible=0;"
    "fillColor=#e0f2fe;gradientColor=#bfdbfe;gradientDirection=180;"
    "strokeColor=#38bdf8;strokeWidth=1.3;dashed=0;"
    "shadow=1;fontFamily=Inter;fontSize=12;fontStyle=1;fontColor=#0f172a;"
    "align=left;verticalAlign=top;spacing=14;spacingTop=18;"
)
GROUP_CONTAINER_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;container=1;collapsible=0;"
    "fillColor=#f8fafc;gradientColor=#e2e8f0;gradientDirection=180;"
    "strokeColor=#cbd5e1;strokeWidth=1.1;dashed=0;"
    "shadow=0;fontFamily=Inter;fontSize=12;fontStyle=1;fontColor=#0f172a;"
    "align=left;verticalAlign=top;spacing=14;spacingTop=18;"
)
CARD_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;"
    "fillColor=#ecfdf3;gradientColor=#bbf7d0;gradientDirection=180;"
    "strokeColor=#22c55e;strokeWidth=1.1;"
    "shadow=1;fontFamily=Inter;fontSize=13;fontColor=#082f49;"
    "align=left;verticalAlign=middle;spacing=14;"
)
EDGE_PRIMARY_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
    "html=1;strokeColor=#38bdf8;strokeWidth=2;endArrow=classic;endFill=1;"
    "flowAnimation=1;"
)
EDGE_SECONDARY_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
    "html=1;strokeColor=#94a3b8;strokeWidth=1.5;endArrow=classic;endFill=1;"
    "dashed=1;dashPattern=4 4;opacity=60;flowAnimation=0;"
)

LIGHT_CONTAINER_PALETTES: List[Tuple[str, str, str]] = [
    ("P1", "#e0f2fe", "#bfdbfe"),
    ("P2", "#ede9fe", "#ddd6fe"),
    ("P3", "#ffe4e6", "#fecdd3"),
    ("P4", "#ffedd5", "#fed7aa"),
    ("P5", "#dcfce7", "#bbf7d0"),
    ("P6", "#cffafe", "#a5f3fc"),
]

LIGHT_CARD_PALETTES: List[Tuple[str, str, str]] = [
    ("C1", "#ecfeff", "#cffafe"),
    ("C2", "#eff6ff", "#dbeafe"),
    ("C3", "#f5f3ff", "#ede9fe"),
    ("C4", "#fdf2f8", "#fce7f3"),
    ("C5", "#ecfdf3", "#bbf7d0"),
    ("C6", "#fff7ed", "#ffedd5"),
]


def _stable_bucket(*parts: str, mod: int = 100) -> int:
    raw = "||".join([str(p or "") for p in parts]).encode("utf-8", errors="ignore")
    h = hashlib.md5(raw).hexdigest()
    return int(h[:8], 16) % int(mod or 100)


def _choose_template(*, title: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], phase_order: List[str]) -> str:
    n_nodes = len(list(nodes or []))
    n_edges = len(list(edges or []))
    seed = _stable_bucket(title, str(n_nodes), str(n_edges), ",".join(phase_order or []))
    try:
        jitter = int.from_bytes(os.urandom(2), "big") % 100
    except Exception:
        jitter = 0
    seed = (seed + jitter) % 100

    if n_nodes >= 6 and n_edges >= 4 and seed < 70:
        return "TEMPLATE_C"
    if n_nodes >= 5 and n_edges <= 3 and seed < 55:
        return "TEMPLATE_D"
    return "TEMPLATE_B"



def generate_drawio_xml_from_spec(spec: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    url = str(os.getenv("NEXT_AI_DRAWIO_URL") or "http://127.0.0.1:6002").rstrip("/")
    api = f"{url}/api/chat"

    title = str(spec.get("title") or "").strip()
    nodes = list(spec.get("nodes") or [])
    edges = list(spec.get("edges") or [])
    layout = dict(spec.get("layout") or {})
    direction = str(layout.get("direction") or "LR").strip().upper()

    phase_order: List[str] = []
    for n in nodes:
        p = str(n.get("phase") or "").strip()
        if not p:
            continue
        if p not in phase_order:
            phase_order.append(p)
    if not phase_order:
        phase_order = ["Flow"]
    if len(phase_order) > 4:
        head = phase_order[:3]
        head.append("Other")
        phase_order = head
    chosen_template = _choose_template(title=title, nodes=nodes, edges=edges, phase_order=phase_order)

    parts: List[str] = []
    if title:
        parts.append(f"Title: {title}")
    parts.append(f"CHOSEN_TEMPLATE: {chosen_template}")
    parts.append("Rule: You MUST follow CHOSEN_TEMPLATE exactly. Do NOT use lanes/swimlanes unless CHOSEN_TEMPLATE is TEMPLATE_A.")
    parts.append("Goal: modern, compact, keynote-style diagram. Colorful, clean, readable at a glance.")
    parts.append("")
    parts.append("CANVAS (must follow):")
    parts.append(f"- Single 16:9 page. Page size: {PAGE_WIDTH}x{PAGE_HEIGHT}. Keep all shapes within the page with ~24px margins.")
    parts.append(f"- Flow direction: {'top-to-bottom' if direction=='TB' else 'left-to-right'}.")
    parts.append("")
    parts.append("STYLE SYSTEM (light pastel only):")
    parts.append("- Keep geometry/font/shadow tokens from the base styles. You may only vary fillColor/gradientColor using palettes below.")
    parts.append(f"- PHASE_CONTAINER_STYLE = {PHASE_CONTAINER_STYLE}")
    parts.append(f"- GROUP_CONTAINER_STYLE = {GROUP_CONTAINER_STYLE}")
    parts.append(f"- CARD_STYLE = {CARD_STYLE}")
    parts.append(f"- EDGE_PRIMARY_STYLE = {EDGE_PRIMARY_STYLE}")
    parts.append(f"- EDGE_SECONDARY_STYLE = {EDGE_SECONDARY_STYLE}")
    parts.append("")
    parts.append("COLOR PALETTES (choose 2–4 per diagram, apply via fillColor/gradientColor):")
    parts.append("- Containers:")
    for key, fill, grad in LIGHT_CONTAINER_PALETTES:
        parts.append(f"  - {key}: fillColor={fill} gradientColor={grad}")
    parts.append("- Cards:")
    for key, fill, grad in LIGHT_CARD_PALETTES:
        parts.append(f"  - {key}: fillColor={fill} gradientColor={grad}")
    parts.append("")
    parts.append("TEMPLATES (for reference; you must follow CHOSEN_TEMPLATE):")
    parts.append("TEMPLATE_A (Phase lanes board): DISABLED. Do not use swimlanes.")
    parts.append("TEMPLATE_B (Linear flowchart): cards only; no containers; connect steps in order.")
    parts.append("TEMPLATE_C (Clustered blocks): 2–4 group containers (NOT swimlanes) + cards inside each group.")
    parts.append("TEMPLATE_D (Hub-and-spoke): one central card + 3–6 satellite cards; no containers.")
    parts.append("Avoid crossing edges. Prefer orthogonal connectors and keep connectors short and tidy.")
    parts.append("")
    parts.append("Hard constraints (must follow):")
    parts.append("- Keep text minimal to avoid overlap.")
    parts.append(f"- Each visible step card must contain <= {MAX_NODE_TEXT_CHARS} characters total.")
    parts.append("- No bullet lists. No multi-line paragraphs. Avoid line breaks (no &#10;, no \\n).")
    parts.append("- You MAY use HTML inside mxCell value to create hierarchy, but then you MUST XML-ESCAPE it inside the value attribute.")
    parts.append("- This means you must NOT output raw '<' or '>' inside value=\"...\". Use '&lt;' and '&gt;'.")
    parts.append("- Example card value (copy structure, not content): &lt;div style=&quot;font-weight:800;font-size:13px&quot;&gt;Title&lt;/div&gt;&lt;div style=&quot;opacity:.7;font-size:11px&quot;&gt;Subtitle&lt;/div&gt;")
    parts.append("- Avoid separate text-only cells; keep text inside the cards.")
    parts.append(f"- Do not put labels on connectors (edge labels length must be <= {MAX_EDGE_LABEL_CHARS}).")
    parts.append(f"- Keep everything within one page viewport ({PAGE_WIDTH}x{PAGE_HEIGHT}) with comfortable spacing.")
    parts.append("Style requirements:")
    parts.append("- For TEMPLATE_A: lanes must be swimlanes (style contains 'swimlane'); lanes use PHASE_CONTAINER_STYLE.")
    parts.append("- For TEMPLATE_C: groups are containers (container=1) but NOT swimlanes; groups use GROUP_CONTAINER_STYLE.")
    parts.append("- Cards use CARD_STYLE (and may pick a card palette).")
    parts.append("- Apply EDGE_PRIMARY_STYLE to the main connectors. Use EDGE_SECONDARY_STYLE only for secondary relations.")
    parts.append("- Do not add large empty white background rectangles.")
    parts.append("- If you add any background panel, it must be behind everything (lowest z-order).")
    parts.append("")
    if chosen_template == "TEMPLATE_A":
        parts.append("Lane order (use as swimlanes): " + ", ".join(phase_order))
        for ph in phase_order:
            phase_nodes = [n for n in nodes if str(n.get("phase") or "").strip() == ph]
            labels = [str(n.get("label") or "").strip() for n in phase_nodes if str(n.get("label") or "").strip()]
            if labels:
                joined = " → ".join(labels[:4])
                parts.append(f"- Lane '{ph}': {joined}")
        parts.append("")
    parts.append("Nodes:")
    for n in nodes[:12]:
        nid = str(n.get("id") or "").strip()
        label = str(n.get("label") or "").strip()
        detail = str(n.get("detail") or "").strip()
        brief = _brief_text(detail, max_chars=26)
        if chosen_template == "TEMPLATE_A":
            phase = str(n.get("phase") or "").strip()
            parts.append(f"- {nid} [{phase}]: {label}" + (f" | hint: {brief}" if brief else ""))
        else:
            parts.append(f"- {nid}: {label}" + (f" | hint: {brief}" if brief else ""))
    parts.append("")
    parts.append("Edges:")
    for e in edges[:20]:
        frm = str(e.get("from") or e.get("frm") or "").strip()
        to = str(e.get("to") or "").strip()
        parts.append(f"- {frm} -> {to}")

    prompt = "\n".join(parts).strip()

    req_json = {
        "messages": [{"role": "user", "parts": [{"type": "text", "text": prompt}]}],
        "xml": "",
        "previousXml": "",
        "sessionId": "deepslide-auto-diagram",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    cfg = resolve_text_llm_env("DRAWIO")
    provider = str(cfg.platform_type or "openai").strip().lower()
    api_key = str(cfg.api_key or "").strip()
    base_url = str(cfg.api_url or "").strip()
    model_id = str(cfg.model_type or "").strip()

    if api_key:
        headers["x-ai-provider"] = provider
        headers["x-ai-api-key"] = api_key
    if base_url:
        headers["x-ai-base-url"] = base_url
    if model_id:
        headers["x-ai-model"] = model_id

    revision_note = ""
    last_err: Optional[str] = None
    for attempt in range(1, 4):
        req_json["messages"] = [
            {
                "role": "user",
                "parts": [
                    {
                        "type": "text",
                        "text": (prompt + revision_note).strip(),
                    }
                ],
            }
        ]
        try:
            with httpx.stream("POST", api, headers=headers, json=req_json, timeout=120.0) as r:
                if r.status_code != 200:
                    last_err = f"next-ai-draw-io /api/chat HTTP {r.status_code}"
                    continue
                tool_xml = _parse_ui_sse_for_display_xml(r)
                if not tool_xml:
                    last_err = "next-ai-draw-io stream did not contain diagram tool output"
                    continue
                mxfile = wrap_with_mxfile(tool_xml)
                mxfile = normalize_mxfile(mxfile)
        except Exception as e:
            last_err = f"next-ai-draw-io request failed: {e}"
            continue

        violations = _validate_compactness(mxfile)
        if not violations:
            return mxfile, None

        last_err = "AI diagram violates compactness constraints: " + ", ".join(violations[:6])
        revision_note = (
            "\n\nREVISION REQUIRED (fix previous output):\n"
            "- Reduce text drastically. Remove all bullets and line breaks.\n"
            "- Keep only a short card title and at most 3–5 words of subtitle.\n"
            "- Remove separate text-only cells; keep text inside cards.\n"
            "- Remove connector labels; keep connectors unlabeled.\n"
            "- Increase card sizes slightly and add spacing so no text overlaps.\n"
            "- If you include a background panel, it must be behind all other elements (lowest z-order).\n"
        )

    return None, last_err or "next-ai-draw-io agent failed"


def _parse_ui_sse_for_display_xml(resp: httpx.Response) -> Optional[str]:
    xml_parts: List[str] = []
    last_available: Optional[str] = None

    for line in resp.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="ignore")
        line = str(line).strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except Exception:
            continue

        t = obj.get("type")
        if t == "tool-input-available":
            tool_name = obj.get("toolName")
            inp = obj.get("input") or {}
            if tool_name in DISPLAY_TOOL_NAMES:
                x = inp.get("xml")
                if isinstance(x, str) and x.strip():
                    last_available = x.strip()
            if tool_name in APPEND_TOOL_NAMES:
                x = inp.get("xml")
                if isinstance(x, str) and x.strip():
                    xml_parts.append(x.strip())

    if last_available:
        if xml_parts and "<mxfile" not in last_available and "<mxGraphModel" not in last_available:
            return last_available + "\n" + "\n".join(xml_parts)
        return last_available

    if xml_parts:
        return "\n".join(xml_parts)
    return None


def _brief_text(text: str, max_chars: int) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    t = re.sub(r"[•·●▪-]\s*", "", t).strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def _validate_compactness(mxfile: str) -> List[str]:
    raw = str(mxfile or "")
    violations: List[str] = []

    if "&#10;" in raw or "\n" in raw:
        multi_line = len(re.findall(r"value=\"[^\"]*(?:&#10;|\n)[^\"]*\"", raw))
        if multi_line > 0:
            violations.append("multiline_text")

    if "•" in raw or "&#8226;" in raw:
        violations.append("bullets_present")

    edge_labels = re.findall(r"<mxCell[^>]*\bedge=\"1\"[^>]*\bvalue=\"([^\"]+)\"", raw)
    if any(v.strip() for v in edge_labels):
        violations.append("edge_labels_present")

    text_cells = re.findall(r"<mxCell[^>]*\bvertex=\"1\"[^>]*\bstyle=\"[^\"]*text;[^\"]*\"[^>]*\bvalue=\"", raw)
    if len(text_cells) > MAX_TEXT_CELLS:
        violations.append("too_many_text_cells")

    values = re.findall(r"<mxCell[^>]*\bvertex=\"1\"[^>]*\bvalue=\"([^\"]*)\"", raw)
    for v in values:
        if not v:
            continue
        vv = html_unescape(v)
        vv = re.sub(r"<[^>]+>", "", vv).strip()
        if len(vv) > MAX_NODE_TEXT_CHARS and vv.lower() not in ("preparation", "integration", "execution"):
            violations.append("node_text_too_long")
            break

    return violations


def html_unescape(s: str) -> str:
    t = str(s or "")
    t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"")
    t = t.replace("&#10;", "\n").replace("&#xa;", "\n")
    return t


def _unescape_basic_entities(s: str) -> str:
    t = str(s or "")
    t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"")
    return t


def _get_attr(tag: str, name: str) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return str(m.group(1)) if m else ""


def _set_attr(tag: str, name: str, value: str) -> str:
    v = str(value or "")
    if re.search(rf'\b{name}="', tag):
        return re.sub(rf'\b{name}="[^"]*"', f'{name}="{v}"', tag, count=1)
    if tag.endswith("/>"):
        return tag[:-2] + f' {name}="{v}"/>'
    return tag[:-1] + f' {name}="{v}">'


def normalize_mxfile(mxfile: str) -> str:
    raw = str(mxfile or "")
    if "<mxCell" not in raw:
        return raw

    def _parse_style(style: str) -> Dict[str, str]:
        d: Dict[str, str] = {}
        for part in str(style or "").split(";"):
            p = part.strip()
            if not p:
                continue
            if "=" in p:
                k, v = p.split("=", 1)
                d[k.strip()] = v.strip()
            else:
                d[p] = ""
        return d

    def _format_style(d: Dict[str, str]) -> str:
        out: List[str] = []
        for k, v in d.items():
            if v == "":
                out.append(k)
            else:
                out.append(f"{k}={v}")
        return ";".join(out) + ";"

    def _is_light_hex(value: str) -> bool:
        v = str(value or "").strip()
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", v):
            return False
        if not v.startswith("#"):
            v = "#" + v
        r = int(v[1:3], 16) / 255.0
        g = int(v[3:5], 16) / 255.0
        b = int(v[5:7], 16) / 255.0
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return lum >= 0.62

    def _merge_style_keep_colors(current: str, base: str) -> str:
        cur = _parse_style(current)
        b = _parse_style(base)
        for k, v in b.items():
            cur[k] = v
        for k in ("fillColor", "gradientColor"):
            if k in cur and k in _parse_style(current):
                v = _parse_style(current).get(k) or ""
                if v and _is_light_hex(v):
                    cur[k] = v
        if "strokeColor" in _parse_style(current):
            v = _parse_style(current).get("strokeColor") or ""
            if v and re.fullmatch(r"#?[0-9a-fA-F]{6}", v):
                cur["strokeColor"] = v if v.startswith("#") else ("#" + v)
        return _format_style(cur)

    def norm_vertex(m: re.Match) -> str:
        tag = m.group(0)
        style = _get_attr(tag, "style")
        if not style:
            return tag
        if "text;" in style:
            return tag

        value_raw = _get_attr(tag, "value")
        if not value_raw and "container=1" not in style and "swimlane" not in style:
            return tag

        value_txt = re.sub(r"<[^>]+>", "", _unescape_basic_entities(value_raw)).strip()
        is_lane = ("swimlane" in style) or ("shape=swimlane" in style)
        is_container = ("container=1" in style) or is_lane

        if is_lane:
            merged = _merge_style_keep_colors(style, PHASE_CONTAINER_STYLE)
            return _set_attr(tag, "style", merged)
        if is_container:
            merged = _merge_style_keep_colors(style, GROUP_CONTAINER_STYLE)
            return _set_attr(tag, "style", merged)
        if value_txt:
            merged = _merge_style_keep_colors(style, CARD_STYLE)
            return _set_attr(tag, "style", merged)
        return tag

    def norm_edge(m: re.Match) -> str:
        tag = m.group(0)
        style = _get_attr(tag, "style")
        if not style:
            return tag
        is_secondary = ("dashed=1" in style) or ("dashPattern" in style) or ("opacity" in style and "opacity=60" in style)
        return _set_attr(tag, "style", EDGE_SECONDARY_STYLE if is_secondary else EDGE_PRIMARY_STYLE)

    raw = re.sub(r"<mxCell\b[^>]*\bvertex=\"1\"[^>]*>", norm_vertex, raw)
    raw = re.sub(r"<mxCell\b[^>]*\bedge=\"1\"[^>]*>", norm_edge, raw)
    return raw


def _ensure_mxgraphmodel_page_attrs(mx_graph_model_xml: str) -> str:
    raw = str(mx_graph_model_xml or "")

    def repl(m: re.Match) -> str:
        attrs = str(m.group(1) or "")
        add: List[str] = []
        if "page=" not in attrs:
            add.append('page="1"')
        if "pageScale=" not in attrs:
            add.append('pageScale="1"')
        if "pageWidth=" not in attrs:
            add.append(f'pageWidth="{int(PAGE_WIDTH)}"')
        if "pageHeight=" not in attrs:
            add.append(f'pageHeight="{int(PAGE_HEIGHT)}"')
        if "grid=" not in attrs:
            add.append('grid="1"')
        if "gridSize=" not in attrs:
            add.append('gridSize="10"')
        if "guides=" not in attrs:
            add.append('guides="1"')
        if "tooltips=" not in attrs:
            add.append('tooltips="1"')
        if "connect=" not in attrs:
            add.append('connect="1"')
        if "arrows=" not in attrs:
            add.append('arrows="1"')
        if "fold=" not in attrs:
            add.append('fold="1"')
        if "shadow=" not in attrs:
            add.append('shadow="0"')
        if "math=" not in attrs:
            add.append('math="0"')
        if not add:
            return m.group(0)
        suffix = (" " + " ".join(add)) if add else ""
        return f"<mxGraphModel{attrs}{suffix}>"

    return re.sub(r"<mxGraphModel\b([^>]*)>", repl, raw, count=1)


def wrap_with_mxfile(xml: str) -> str:
    root_cells = '<mxCell id="0"/><mxCell id="1" parent="0"/>'
    content = str(xml or "").strip()
    if not content:
        gm = _ensure_mxgraphmodel_page_attrs("<mxGraphModel><root></root></mxGraphModel>")
        gm = gm.replace("<root></root>", f"<root>{root_cells}</root>")
        return f'<mxfile><diagram name="Page-1" id="page-1">{gm}</diagram></mxfile>'

    if "<mxfile" in content:
        return content
    if "<mxGraphModel" in content:
        content2 = _ensure_mxgraphmodel_page_attrs(content)
        return f'<mxfile><diagram name="Page-1" id="page-1">{content2}</diagram></mxfile>'

    if "<root>" in content:
        content = re.sub(r"</?root>", "", content).strip()

    last_self = content.rfind("/>")
    last_close = content.rfind("</mxCell>")
    last_end = max(last_self, last_close)
    if last_end != -1:
        end_offset = 9 if last_close > last_self else 2
        suffix = content[last_end + end_offset :]
        if re.fullmatch(r"(\s*</[^>]+>)*\s*", suffix or ""):
            content = content[: last_end + end_offset]

    content = re.sub(r"<mxCell[^>]*\bid=[\"']0[\"'][^>]*(?:/>|></mxCell>)", "", content)
    content = re.sub(r"<mxCell[^>]*\bid=[\"']1[\"'][^>]*(?:/>|></mxCell>)", "", content)
    content = content.strip()

    gm = _ensure_mxgraphmodel_page_attrs("<mxGraphModel><root></root></mxGraphModel>")
    gm = gm.replace("<root></root>", f"<root>{root_cells}{content}</root>")
    return f'<mxfile><diagram name="Page-1" id="page-1">{gm}</diagram></mxfile>'
