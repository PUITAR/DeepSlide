import json
import html
import re
from core import _log
from ppt_core import _strip_latex_inline, _encode_png_data_uri

def _try_float(s: str):
    try:
        s2 = (s or "").replace(",", "").strip()
        return float(s2)
    except Exception:
        return None

def _html_attr_escape(s: str) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("'", "&#39;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def _build_focus_zoom_widget(slide_img_src: str, regions, interval_ms: int, scale: float):
    safe_regions = json.dumps(regions, ensure_ascii=False)
    safe_scale = float(scale) if scale else 1.4
    safe_interval = int(interval_ms) if interval_ms else 2000
    return (
        f"<div class=\"focus-zoom\" data-regions='{safe_regions}' data-interval=\"{safe_interval}\" data-scale=\"{safe_scale}\">"
        f"<img class=\"focus-zoom-base\" src=\"{slide_img_src}\" alt=\"\">"
        f"<div class=\"focus-zoom-layer\"></div>"
        f"</div>"
    )

def _extract_table_caption(latex_table_code: str) -> str:
    if not latex_table_code:
        return ""
    m = re.search(r"\\caption\{(.*?)\}", latex_table_code, flags=re.DOTALL)
    if not m:
        return ""
    cap = m.group(1).strip()
    cap = re.sub(r"\s+", " ", cap)
    return _strip_latex_inline(cap)

def _extract_frametitle(latex_frame: str) -> str:
    if not latex_frame:
        return ""
    m = re.search(r"\\frametitle\{(.*?)\}", latex_frame, flags=re.DOTALL)
    if not m:
        return ""
    t = m.group(1)
    t = re.sub(r"\s+", " ", t).strip()
    return _strip_latex_inline(t)

def _extract_itemize_items(latex_frame: str):
    if not latex_frame:
        return []
    m = re.search(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", latex_frame, flags=re.DOTALL)
    if not m:
        return []
    inner = m.group(1)
    inner = re.sub(r"%.*$", "", inner, flags=re.MULTILINE)
    raw_items = re.split(r"\\item", inner)
    out = []
    for it in raw_items:
        s = (it or "").strip()
        if not s:
            continue
        s = re.sub(r"\\\\(?:\[[^\]]*\])?", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        s = _strip_latex_inline(s)
        if s:
            out.append(s)
    return out

def _extract_plain_text_from_frame(latex_frame: str) -> str:
    if not latex_frame:
        return ""
    s = latex_frame
    s = re.sub(r"\\begin\{(tabular\*?|tabularx\*?|longtable\*?|table\*?)\}.*?\\end\{\1\}", " ", s, flags=re.DOTALL)
    s = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^\}]*\}", " ", s)
    s = re.sub(r"\\begin\{(figure\*?|tikzpicture)\}.*?\\end\{\1\}", " ", s, flags=re.DOTALL)
    s = re.sub(r"\\note\{.*?\}", " ", s, flags=re.DOTALL)
    s = re.sub(r"\\frametitle\{.*?\}", " ", s, flags=re.DOTALL)
    s = re.sub(r"\\begin\{itemize\}.*?\\end\{itemize\}", " ", s, flags=re.DOTALL)
    s = re.sub(r"\\begin\{enumerate\}.*?\\end\{enumerate\}", " ", s, flags=re.DOTALL)
    s = _strip_latex_inline(s)
    return s

def _build_html_slide_section(body_html: str, speech_text: str, slide_class: str = "beamerish", index: int = None):
    body_html = str(body_html or "")
    speech_text = str(speech_text or "")
    cls = html.escape(slide_class) if slide_class else ""
    class_attr = f" class=\"{cls}\"" if cls else ""
    slide_num_html = f"<div class=\"slide-number-overlay\">{index}</div>" if index is not None else ""
    return (
        f"<section{class_attr}>"
        f"{slide_num_html}"
        f"{body_html}"
        f"</section>"
    )

def _parse_first_tabular_to_matrix(latex_table_code: str):
    if not latex_table_code:
        return []

    m = re.search(
        r"\\begin\{(tabular\*?|tabularx\*?|longtable\*?)\}.*?\\end\{\1\}",
        latex_table_code,
        flags=re.DOTALL,
    )
    if not m:
        return []

    tab = m.group(0)
    env = m.group(1)

    inner_m = re.search(
        rf"\\begin\{{{re.escape(env)}\}}(?:\[[^\]]*\])?(?:\{{[^\}}]*\}})?(?:\{{[^\}}]*\}})?(.*?)\\end\{{{re.escape(env)}\}}",
        tab,
        flags=re.DOTALL,
    )
    inner = inner_m.group(1) if inner_m else tab

    inner = re.sub(r"%.*", "", inner)
    inner = re.sub(r"\\multicolumn\{\d+\}\{[^\}]*\}\{(.*?)\}", r"\1", inner, flags=re.DOTALL)
    inner = re.sub(r"\\multirow\{\d+\}\{[^\}]*\}\{(.*?)\}", r"\1", inner, flags=re.DOTALL)
    inner = re.sub(r"\\cellcolor\{[^\}]*\}", "", inner)
    inner = re.sub(r"\\(toprule|midrule|bottomrule)", r"\\hline", inner)
    inner = re.sub(r"\\\\(?:\[[^\]]*\])?", "\n", inner)
    lines = [ln.strip() for ln in inner.splitlines()]
    rows = []
    for ln in lines:
        if not ln:
            continue
        ln = ln.strip()
        if ln in {"\\hline", "\\cline", "\\cmidrule"} or ln.startswith("\\hline") or ln.startswith("\\cline") or ln.startswith("\\cmidrule"):
            continue
        if "&" not in ln:
            continue
        parts = [p.strip() for p in ln.split("&")]
        parts = [_strip_latex_inline(p) for p in parts]
        if any(parts):
            rows.append(parts)
    if not rows:
        return []
    max_len = max(len(r) for r in rows)
    norm = [r + [""] * (max_len - len(r)) for r in rows]
    return norm

def _build_table_viz_widget(latex_table_code: str):
    matrix = _parse_first_tabular_to_matrix(latex_table_code)
    if not matrix:
        return ""
    caption = _extract_table_caption(latex_table_code)
    viz_html = _matrix_to_interactive_viz_html(matrix)
    caption_html = f"<div class=\"table-viz-caption\">{html.escape(caption)}</div>" if caption else ""
    return (
        "<div class=\"table-viz\">"
        "<div class=\"table-viz-head\">"
        "<div class=\"table-viz-title\">Table</div>"
        "<input class=\"table-search\" type=\"search\" placeholder=\"Search…\" aria-label=\"Search table\">"
        "</div>"
        + caption_html
        + "<div class=\"table-viz-body\">"
        + viz_html
        + "</div>"
        "</div>"
    )

def _build_keynote_text_widget(latex_frame: str, speech_text: str = ""):
    title = _extract_frametitle(latex_frame) or "Key Message"
    items = _extract_itemize_items(latex_frame)
    if not items:
        plain = _extract_plain_text_from_frame(latex_frame)
        if plain:
            parts = re.split(r"[。！？.!?]\s+|\n+", plain)
            items = [p.strip() for p in parts if p.strip()]
            items = items[:6]

    subtitle = ""
    if speech_text:
        speech = _strip_latex_inline(speech_text)
        if speech and len(speech) > 16:
            subtitle = speech[:180] + ("…" if len(speech) > 180 else "")

    bullet_html = ""
    if items:
        lis = "".join([f"<li>{html.escape(x)}</li>" for x in items[:8]])
        bullet_html = f"<ul class=\"keynote-bullets\">{lis}</ul>"

    subtitle_html = f"<div class=\"keynote-subtitle\">{html.escape(subtitle)}</div>" if subtitle else ""
    return (
        "<div class=\"keynote\">"
        "<div class=\"keynote-shell\">"
        "<div class=\"keynote-badge\">Product Brief</div>"
        f"<div class=\"keynote-title\">{html.escape(title)}</div>"
        + subtitle_html
        + bullet_html
        + "</div>"
        + "</div>"
    )

def _matrix_to_interactive_viz_html(matrix):
    if not matrix or not isinstance(matrix, list) or not isinstance(matrix[0], list):
        return "<div class='error'>Visualization Failed</div>"

    header = matrix[0]
    body = matrix[1:] if len(matrix) > 1 else []

    def looks_like_header(row, rest):
        if not row or not rest:
            return False
        numeric_counts = 0
        for r in rest[:5]:
            if len(r) >= 2 and _try_float(r[1]) is not None:
                numeric_counts += 1
        return numeric_counts >= max(1, min(3, len(rest)))

    has_header = looks_like_header(header, body)
    if not has_header:
        header = [f"Col {i+1}" for i in range(len(matrix[0]))]
        body = matrix

    chart_html = ""
    chart_cfg = None
    labels = []
    if len(body) >= 2 and len(header) >= 2:
        labels = [str(r[0]) for r in body if len(r) >= 1]

    def build_dataset(col_idx: int, label: str, color_idx: int):
        vals = []
        ok = 0
        for r in body:
            if len(r) <= col_idx:
                vals.append(None)
                continue
            v = _try_float(r[col_idx])
            if v is None:
                vals.append(None)
            else:
                ok += 1
                vals.append(v)
        if ok < 2:
            return None
        palette = [
            ("rgba(0,152,121,0.55)", "rgba(0,152,121,1)"),
            ("rgba(54,162,235,0.55)", "rgba(54,162,235,1)"),
            ("rgba(255,99,132,0.55)", "rgba(255,99,132,1)"),
            ("rgba(255,159,64,0.55)", "rgba(255,159,64,1)"),
            ("rgba(153,102,255,0.55)", "rgba(153,102,255,1)"),
        ]
        bg, bd = palette[color_idx % len(palette)]
        return {
            "label": label,
            "data": vals,
            "backgroundColor": bg,
            "borderColor": bd,
            "borderWidth": 1,
            "spanGaps": True,
        }

    datasets = []
    for j in range(1, len(header)):
        ds = build_dataset(j, _strip_latex_inline(header[j]), j - 1)
        if ds:
            datasets.append(ds)

    if labels and datasets:
        chart_type = "bar" if len(datasets) == 1 else "line"
        if chart_type == "line":
            for ds in datasets:
                ds["fill"] = False
                ds["tension"] = 0.25

        chart_cfg = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": datasets,
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {"legend": {"display": True}},
                "scales": {"y": {"beginAtZero": True}},
                "animation": False,
            },
        }

    if chart_cfg:
        chart_json = _html_attr_escape(json.dumps(chart_cfg, ensure_ascii=False))
        chart_html = (
            "<div class=\"chart-container\" style=\"position: relative; height:45vh; width:92%; margin: 0 auto;\">"
            f"<canvas class=\"auto-chart\" data-chart='{chart_json}'></canvas>"
            "</div>"
        )

    thead = "".join([f"<th>{_strip_latex_inline(h)}</th>" for h in header])
    tbody_rows = []
    for r in body:
        tds = "".join([f"<td>{_strip_latex_inline(c)}</td>" for c in r])
        tbody_rows.append(f"<tr>{tds}</tr>")
    table_html = (
        "<table class=\"interactive-table\">"
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(tbody_rows)}</tbody>"
        "</table>"
    )

    if chart_html:
        return chart_html + table_html
    return table_html

def _iou(a: dict, b: dict) -> float:
    ax1, ay1 = float(a.get("x", 0.0)), float(a.get("y", 0.0))
    ax2, ay2 = ax1 + float(a.get("w", 0.0)), ay1 + float(a.get("h", 0.0))
    bx1, by1 = float(b.get("x", 0.0)), float(b.get("y", 0.0))
    bx2, by2 = bx1 + float(b.get("w", 0.0)), by1 + float(b.get("h", 0.0))
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = area_a + area_b - inter
    if denom <= 0:
        return 0.0
    return inter / denom

def _nms_regions(regions, iou_thr: float = 0.28, max_regions: int = 5):
    if not isinstance(regions, list):
        return []
    kept = []
    for r in regions:
        if not isinstance(r, dict):
            continue
        ok = True
        for k in kept:
            if _iou(r, k) >= iou_thr:
                ok = False
                break
        if ok:
            kept.append(r)
        if len(kept) >= max_regions:
            break
    return kept

def _normalize_focus_regions(regions, max_regions: int):
    if not isinstance(regions, list):
        return []
    out = []
    for r in regions:
        if not isinstance(r, dict):
            continue
        try:
            x = float(r.get("x"))
            y = float(r.get("y"))
            w = float(r.get("w"))
            h = float(r.get("h"))
        except Exception:
            continue
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        w = max(0.01, min(1.0, w))
        h = max(0.01, min(1.0, h))
        if x + w > 1.0:
            w = max(0.01, 1.0 - x)
        if y + h > 1.0:
            h = max(0.01, 1.0 - y)
        out.append({
            "x": round(x, 6),
            "y": round(y, 6),
            "w": round(w, 6),
            "h": round(h, 6),
            "label": str(r.get("label", ""))[:80]
        })
        if len(out) >= max_regions:
            break
    return out

def inject_reveal_slide_control(html_content, page_idx):
    """Inject JavaScript to jump to specific slide index."""
    injection = f"""
    <script>
        // Wait for Reveal to be ready or just try to call it
        // Check if Reveal is defined
        if (typeof Reveal !== 'undefined') {{
            if (Reveal.isReady()) {{
                Reveal.slide({page_idx});
            }} else {{
                Reveal.addEventListener('ready', event => {{
                    Reveal.slide({page_idx});
                }});
            }}
        }}
    </script>
    </body>
    """
    
    if "</body>" in html_content:
        return html_content.replace("</body>", injection)
    else:
        return html_content + injection

def _render_vis_network(res, pdf_pages, files, show_sequential=True):
    import base64
    from PIL import Image
    import io
    import glob
    import os

    # 1. Prepare Images Map
    images_map = {}
    if pdf_pages:
        for i, p in enumerate(pdf_pages):
            if os.path.exists(p):
                try:
                    with Image.open(p) as img:
                        img.thumbnail((320, 240))
                        bio = io.BytesIO()
                        img.save(bio, format="PNG")
                        b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
                        images_map[i] = f"data:image/png;base64,{b64}"
                except: pass

    if not images_map and "pdf" in files:
        try:
            output_dir = os.path.dirname(files["pdf"])
            preview_dir = os.path.join(output_dir, "preview_cache")
            if os.path.exists(preview_dir):
                found_files = glob.glob(os.path.join(preview_dir, "page_*.png"))
                def extract_pn(fname):
                    base = os.path.basename(fname)
                    parts = base.split("_")
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1])
                    return 9999
                found_files.sort(key=extract_pn)
                for fpath in found_files:
                    pn = extract_pn(fpath)
                    if pn not in images_map:
                        try:
                            with Image.open(fpath) as img:
                                img.thumbnail((320, 240))
                                bio = io.BytesIO()
                                img.save(bio, format="PNG")
                                b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
                                images_map[pn] = f"data:image/png;base64,{b64}"
                        except: pass
        except Exception as e:
            print(f"Error loading from preview_cache: {e}")

    # 2. Build Nodes and Edges Data for JS
    max_res_id = max([int(n['id']) for n in res.get('nodes', [])]) if res.get('nodes') else -1
    total_slides = max(len(images_map), max_res_id + 1)
    
    nodes_data = []
    graph_node_info = {int(n['id']): n for n in res.get('nodes', [])}
    
    for i in range(total_slides):
        node_data = graph_node_info.get(i, {})
        nodes_data.append({
            "id": i,
            "label": f"SLIDE {i+1}",
            "section": node_data.get('section', 'Slide Content'),
            "img": images_map.get(i, "")
        })
        
    edges_data = res.get("edges", [])
    clean_edges = []
    
    for i in range(total_slides - 1):
        if show_sequential:
            clean_edges.append({"from": i, "to": i+1, "label": "", "type": "sequential"})
            
    for e in edges_data:
        try:
            src = int(e["from"])
            dst = int(e["to"])
            if 0 <= src < total_slides and 0 <= dst < total_slides:
                 clean_edges.append({"from": src, "to": dst, "label": e.get("label", ""), "type": "reference"})
        except: pass

    cards_html = ""
    for node in nodes_data:
        img_html = f'<img src="{node["img"]}" class="panel-thumb" alt="{node["label"]}">' if node["img"] else '<div class="panel-no-preview">No Preview</div>'
        card = f"""
        <div class="panel-card" id="card-{node['id']}">
            <div class="panel-header">
                <span>{node['label']}</span>
            </div>
            <div class="panel-sub">{node['section']}</div>
            <div class="panel-body">
                {img_html}
            </div>
        </div>
        """
        cards_html += card

    json_nodes = json.dumps(nodes_data)
    json_edges = json.dumps(clean_edges)

    VIZ_HEIGHT = 600
    
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #ffffff; overflow: hidden; }}
        .scroll-wrapper {{ position: relative; width: 100%; height: {VIZ_HEIGHT}px; display: flex; align-items: center; background: #f8fafc; }}
        .viz-container {{ position: relative; display: flex; flex-direction: row; gap: 60px; overflow-x: auto; overflow-y: visible; padding: 200px 60px 200px; align-items: center; height: 100%; width: 100%; scroll-behavior: smooth; }}
        #arrow-layer {{ position: absolute; top: 0; left: 0; width: 1px; height: 100%; pointer-events: none; z-index: 0; }}
        .scroll-btn {{ position: fixed; z-index: 200; background: rgba(255, 255, 255, 0.9); border: 1px solid #cbd5e1; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1); color: #334155; font-size: 1.2rem; top: 50%; transform: translateY(-50%); transition: all 0.2s; }}
        .scroll-btn:hover {{ background: #fff; transform: translateY(-50%) scale(1.1); color: #0f172a; }}
        .scroll-btn.left {{ left: 10px; }}
        .scroll-btn.right {{ right: 10px; }}
        .panel-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); min-width: 220px; max-width: 220px; flex-shrink: 0; display: flex; flex-direction: column; position: relative; z-index: 10; transition: transform 0.2s; }}
        .panel-card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); border-color: #94a3b8; }}
        .panel-header {{ background-color: #0f172a; color: white; padding: 10px 14px; font-size: 0.85rem; font-weight: 700; border-top-left-radius: 8px; border-top-right-radius: 8px; display: flex; justify-content: space-between; }}
        .panel-sub {{ color: #64748b; font-size: 0.7rem; text-transform: uppercase; font-weight: 600; padding: 10px 14px 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .panel-body {{ padding: 10px 14px 14px; display: flex; flex-direction: column; align-items: center; }}
        .panel-thumb {{ width: 100%; height: auto; border: 1px solid #cbd5e1; border-radius: 4px; }}
        .panel-no-preview {{ width: 100%; height: 100px; background: #f1f5f9; color: #94a3b8; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; }}
        .viz-container::-webkit-scrollbar {{ height: 8px; }}
        .viz-container::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}
      </style>
    </head>
    <body>
        <div class="scroll-wrapper">
            <div class="scroll-btn left" onclick="scrollViz(-1)">❮</div>
            <div class="viz-container" id="scroller">
                <svg id="arrow-layer"></svg>
                {cards_html}
            </div>
            <div class="scroll-btn right" onclick="scrollViz(1)">❯</div>
        </div>
        <script>
            const nodes = {json_nodes};
            const edges = {json_edges};
            function scrollViz(dir) {{ document.getElementById('scroller').scrollBy({{ left: dir * 300, behavior: 'smooth' }}); }}
            function drawArrows() {{
                const container = document.getElementById('scroller');
                const svg = document.getElementById('arrow-layer');
                svg.style.width = container.scrollWidth + 'px';
                while (svg.lastChild) {{ svg.removeChild(svg.lastChild); }}
                function getCardPos(id) {{
                    const card = document.getElementById('card-' + id);
                    if (!card) return null;
                    return {{ x: card.offsetLeft + card.offsetWidth / 2, y: card.offsetTop, h: card.offsetHeight, w: card.offsetWidth }};
                }}
                const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
                const markerBlue = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                markerBlue.setAttribute("id", "arrowhead-blue"); markerBlue.setAttribute("markerWidth", "10"); markerBlue.setAttribute("markerHeight", "7"); markerBlue.setAttribute("refX", "9"); markerBlue.setAttribute("refY", "3.5"); markerBlue.setAttribute("orient", "auto");
                const polyBlue = document.createElementNS("http://www.w3.org/2000/svg", "polygon"); polyBlue.setAttribute("points", "0 0, 10 3.5, 0 7"); polyBlue.setAttribute("fill", "#3b82f6"); markerBlue.appendChild(polyBlue); defs.appendChild(markerBlue);
                const markerRed = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                markerRed.setAttribute("id", "arrowhead-red"); markerRed.setAttribute("markerWidth", "10"); markerRed.setAttribute("markerHeight", "7"); markerRed.setAttribute("refX", "9"); markerRed.setAttribute("refY", "3.5"); markerRed.setAttribute("orient", "auto");
                const polyRed = document.createElementNS("http://www.w3.org/2000/svg", "polygon"); polyRed.setAttribute("points", "0 0, 10 3.5, 0 7"); polyRed.setAttribute("fill", "#ef4444"); markerRed.appendChild(polyRed); defs.appendChild(markerRed);
                const markerGray = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                markerGray.setAttribute("id", "arrowhead-gray"); markerGray.setAttribute("markerWidth", "10"); markerGray.setAttribute("markerHeight", "7"); markerGray.setAttribute("refX", "9"); markerGray.setAttribute("refY", "3.5"); markerGray.setAttribute("orient", "auto");
                const polyGray = document.createElementNS("http://www.w3.org/2000/svg", "polygon"); polyGray.setAttribute("points", "0 0, 10 3.5, 0 7"); polyGray.setAttribute("fill", "#94a3b8"); markerGray.appendChild(polyGray); defs.appendChild(markerGray);
                svg.appendChild(defs);
                edges.forEach(e => {{
                    const src = getCardPos(e.from);
                    const dst = getCardPos(e.to);
                    if (!src || !dst) return;
                    const isNext = (e.to === e.from + 1);
                    const isBack = e.to < e.from;
                    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                    path.setAttribute("fill", "none");
                    path.setAttribute("stroke-width", "2");
                    let d = "";
                    if (e.type === 'sequential') {{
                        const x1 = src.x + src.w/2; const y1 = src.y + src.h/2;
                        const x2 = dst.x - dst.w/2; const y2 = dst.y + dst.h/2;
                        d = `M ${{x1}} ${{y1}} C ${{x1+30}} ${{y1}}, ${{x2-30}} ${{y2}}, ${{x2}} ${{y2}}`;
                        path.setAttribute("stroke", "#94a3b8"); path.setAttribute("stroke-width", "1.5"); path.setAttribute("marker-end", "url(#arrowhead-gray)");
                    }} else {{
                        const offset = 40;
                        if (isBack) {{
                            const x1 = src.x - offset; const y1 = src.y;
                            const x2 = dst.x + offset; const y2 = dst.y;
                            const dist = Math.abs(x2 - x1); const h = 30 + Math.log(dist + 1) * 20;
                            d = `M ${{x1}} ${{y1}} C ${{x1}} ${{y1-h}}, ${{x2}} ${{y2-h}}, ${{x2}} ${{y2}}`;
                            path.setAttribute("stroke", "#ef4444"); path.setAttribute("stroke-dasharray", "4"); path.setAttribute("marker-end", "url(#arrowhead-red)");
                        }} else {{
                            const x1 = src.x + offset; const y1_b = src.y + src.h;
                            const x2 = dst.x - offset; const y2_b = dst.y + dst.h;
                            const dist = Math.abs(x2 - x1); const h = 30 + Math.log(dist + 1) * 20;
                            d = `M ${{x1}} ${{y1_b}} C ${{x1}} ${{y1_b+h}}, ${{x2}} ${{y2_b+h}}, ${{x2}} ${{y2_b}}`;
                            path.setAttribute("stroke", "#3b82f6"); path.setAttribute("marker-end", "url(#arrowhead-blue)");
                        }}
                        path.setAttribute("stroke-width", "3"); path.setAttribute("stroke-opacity", "0.8");
                    }}
                    path.setAttribute("d", d);
                    svg.appendChild(path);
                }});
            }}
            window.onload = drawArrows; window.onresize = drawArrows; setTimeout(drawArrows, 500); setTimeout(drawArrows, 1500);
        </script>
    </body>
    </html>
    """
    return html_code, VIZ_HEIGHT

def get_slide_card_html(image_path_or_bytes, page_index=None, total_pages=None):
    b64 = _encode_png_data_uri(image_path_or_bytes)
    
    overlay_html = ""
    if page_index is not None and total_pages is not None:
        overlay_html = f"""
        <div style="
            position: absolute;
            top: 20px;
            right: 25px;
            background: rgba(0,0,0,0.4);
            color: white;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 12px;
            font-family: sans-serif;
            pointer-events: none;
            backdrop-filter: blur(4px);
            z-index: 10;
        ">
            {page_index + 1} / {total_pages}
        </div>
        """

    return f"""
    <div style="
        display: flex; 
        justify-content: center; 
        align-items: center; 
        height: 100%; 
        width: 100%;
        background-color: #f8fafc;
        padding: 20px;
        box-sizing: border-box;
    ">
      <div style="
        position: relative;
        width: 100%;
        max-width: 960px; 
        aspect-ratio: 16/9;
        background: white;
        border-radius: 12px;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        overflow: hidden;
        display: flex;
        justify-content: center;
        align-items: center;
        border: 1px solid #e2e8f0;
      ">
        <img src="{b64}" style="width: 100%; height: 100%; object-fit: contain;">
        {overlay_html}
      </div>
    </div>
    """
