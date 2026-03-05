import html
import json
import os
import re
import urllib.parse
from xml.etree import ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from app.services.drawio_agent import generate_drawio_xml_from_spec


def diagram_kit_css() -> str:
    return """
.diagram-kit{width:100%;margin-top:12px;position:relative}
.drawio-kit{
  position:relative;
  width:100%;
  border-radius:var(--radius-md);
  background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.012));
  border: 1px solid var(--border-soft);
  box-shadow: var(--shadow-md);
  padding: 0;
  overflow:hidden;
  height: var(--drawio-h, 520px);
}
body[data-theme="light"] .drawio-kit{
  background: linear-gradient(180deg, rgba(255,255,255,0.72), rgba(255,255,255,0.62));
}
.diagram-canvas{
  position:relative;
  width:100%;
  height:100%;
  background-color: #ffffff;
  background-image:
    linear-gradient(to right, rgba(17,24,39,0.06) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(17,24,39,0.06) 1px, transparent 1px),
    linear-gradient(to right, rgba(17,24,39,0.03) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(17,24,39,0.03) 1px, transparent 1px);
  background-size: 64px 64px, 64px 64px, 16px 16px, 16px 16px;
  background-position: 0 0, 0 0, 0 0, 0 0;
  overflow:hidden;
  cursor: grab;
  user-select:none;
  touch-action: none;
}
.diagram-canvas.dragging{cursor: grabbing;}
.diagram-status{
  position:absolute;
  left:12px;
  top:10px;
  z-index:2;
  max-width:78%;
  padding:6px 10px;
  border-radius:10px;
  font-size:12px;
  line-height:1.1;
  color: rgba(17,24,39,0.72);
  background: rgba(255,255,255,0.82);
  border: 1px solid rgba(17,24,39,0.10);
  backdrop-filter: blur(8px);
  pointer-events:none;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.diagram-status.error{
  color: rgba(127,29,29,0.92);
  border-color: rgba(127,29,29,0.18);
  background: rgba(254,242,242,0.92);
}
.diagram-status.hidden{display:none;}
.diagram-svg{
  position:absolute;
  left:0;
  top:0;
  transform-origin: 0 0;
  will-change: transform;
}
.diagram-svg svg{display:block;}
.drawio-renderer{
  position:absolute;
  left:-99999px;
  top:-99999px;
  width:1px;
  height:1px;
  opacity:0;
  border:0;
  pointer-events:none;
}
"""


def render_auto_diagram(steps: List[str]) -> str:
    steps = [str(s).strip() for s in (steps or []) if str(s or "").strip()]
    steps = steps[:6]
    if len(steps) < 2:
        return ""
    spec = {
        "nodes": [{"id": f"n{i+1}", "phase": "Execution", "label": (s.split(":", 1)[0] if ":" in s else f"Stage {i+1}"), "detail": (s.split(":", 1)[1].strip() if ":" in s else s)} for i, s in enumerate(steps)],
        "edges": [{"from": f"n{i+1}", "to": f"n{i+2}", "label": ""} for i in range(len(steps) - 1)],
        "layout": {"direction": "LR"},
        "title": "",
    }
    return render_diagram_spec(spec)


def render_diagram_spec(spec: Any) -> str:
    d = _coerce_spec_dict(spec)
    nodes = d.get("nodes") or []
    edges = d.get("edges") or []
    if len(nodes) < 2:
        return ""

    xml: Optional[str] = None
    err: Optional[str] = None
    try:
        xml, err = generate_drawio_xml_from_spec(d)
    except Exception as e:
        err = f"drawio agent failed: {e}"
        xml = None
    if not xml or "<mxCell" not in xml:
        err2 = str(err or "unknown error").strip()
        err2 = re.sub(r"\s+", " ", err2)
        if len(err2) > 260:
            err2 = err2[:260] + "…"
        print(f"[DrawioAI] failed: {err2}")
        return (
            "<div class=\"diagram-kit\">"
            "<div class=\"drawio-kit\" style=\"padding:16px;\">"
            "<div style=\"font-weight:800;font-size:13px;opacity:0.85;\">AI diagram generation failed</div>"
            f"<div style=\"margin-top:8px;font-size:12px;opacity:0.75;\">{_esc_html(err2)}</div>"
            "</div>"
            "</div>"
        )
    xml = _sanitize_drawio_mxfile(xml)
    try:
        ET.fromstring(xml)
    except Exception:
        xml = _escape_drawio_mxcell_values(xml)
        xml = _sanitize_drawio_mxfile(xml)
    embed_base = str(os.getenv("DRAWIO_EMBED_URL") or "https://embed.diagrams.net").rstrip("/")
    iframe_id = f"dsv_{abs(hash(xml)) % (10**9)}"
    canvas_id = f"dsc_{abs(hash(xml)) % (10**9)}"
    svg_id = f"dss_{abs(hash(xml)) % (10**9)}"
    status_id = f"dst_{abs(hash(xml)) % (10**9)}"
    src = (
        f"{embed_base}/?embed=1&ui=min&spin=0&proto=json&returnbounds=1"
        "&saveAndExit=0&noSaveBtn=1&noExitBtn=1"
        "&readOnly=1&toolbar=0&nav=0"
        "&format=0&libraries=0&hide-pages=1&pv=0"
        "&splash=0&plugins=0"
    )
    origin = urllib.parse.urlparse(embed_base).scheme + "://" + urllib.parse.urlparse(embed_base).netloc
    xml_js = json.dumps(xml, ensure_ascii=False)
    origin_js = json.dumps(origin, ensure_ascii=False)
    js = (
        "<script>"
        "(function(){"
        f"var xml={xml_js};"
        f"var origin={origin_js};"
        f"var iframeId='{iframe_id}';"
        f"var canvasId='{canvas_id}';"
        f"var svgId='{svg_id}';"
        f"var statusId='{status_id}';"
        "var debug=false;try{debug=!!(window.localStorage&&localStorage.getItem('deepslide_drawio_debug')==='1');}catch(e){}"
        "function log(){if(!debug)return;try{console.log.apply(console,arguments);}catch(e){}}"
        "function setStatus(text,isError){"
        "var el=document.getElementById(statusId);"
        "if(!el)return;"
        "var t=String(text||'').trim();"
        "if(!t){el.classList.add('hidden');el.classList.remove('error');el.textContent='';return;}"
        "el.classList.remove('hidden');"
        "if(isError){el.classList.add('error');}else{el.classList.remove('error');}"
        "el.textContent=t;"
        "}"
        "var loaded=false;"
        "var exported=false;"
        "var initTimer=setTimeout(function(){"
        "if(!loaded){setStatus('Embed not loaded (check network / iframe loading)',true);}"
        "},4500);"
        "function post(msg){"
        "var iframe=document.getElementById(iframeId);"
        "if(!iframe||!iframe.contentWindow)return;"
        "try{iframe.contentWindow.postMessage(JSON.stringify(msg),origin);}catch(e){log('postMessage failed',e);}"
        "}"
        "function b64ToUtf8(b64){"
        "try{"
        "var bin=atob(b64);"
        "try{"
        "var hex=[];"
        "for(var i=0;i<bin.length;i++){"
        "var h=bin.charCodeAt(i).toString(16);"
        "hex.push('%'+('00'+h).slice(-2));"
        "}"
        "return decodeURIComponent(hex.join(''));"
        "}catch(e){return bin;}"
        "}catch(e){return '';}"
        "}"
        "function decodeSvgData(data){"
        "var s=String(data||'');"
        "if(s.indexOf('data:image/svg+xml;base64,')===0){"
        "return b64ToUtf8(s.slice(26));"
        "}"
        "if(s.indexOf('data:image/svg+xml,')===0){"
        "var p=s.slice(19);"
        "try{return decodeURIComponent(p);}catch(e){return p;}"
        "}"
        "return s;"
        "}"
        "function extractSvg(text){"
        "var s=String(text||'').trim();"
        "var i=s.indexOf('<svg');"
        "var j=s.lastIndexOf('</svg>');"
        "if(i>=0&&j>=0){return s.slice(i,j+6);}"
        "return s;"
        "}"
        "function setSvg(svgText){"
        "var holder=document.getElementById(svgId);"
        "if(!holder)return;"
        "var raw=extractSvg(svgText||'');"
        "holder.innerHTML=raw;"
        "var svg=holder.querySelector('svg');"
        "if(svg){svg.setAttribute('preserveAspectRatio','xMidYMid meet');return true;}"
        "return false;"
        "}"
        "function initPanZoom(){"
        "var canvas=document.getElementById(canvasId);"
        "var holder=document.getElementById(svgId);"
        "if(!canvas||!holder||canvas.dataset.pz)return;"
        "canvas.dataset.pz='1';"
        "var scale=1,tx=0,ty=0;"
        "var dragging=false,sx=0,sy=0,stx=0,sty=0;"
        "function apply(){holder.style.transform='translate('+tx+'px,'+ty+'px) scale('+scale+')';}"
        "function clamp(){if(scale<0.2)scale=0.2;if(scale>6)scale=6;}"
        "function fitOnce(){"
        "if(canvas.dataset.fit)return true;"
        "var svg=holder.querySelector('svg');"
        "if(!svg)return false;"
        "var vb=null;"
        "try{"
        "if(svg.viewBox&&svg.viewBox.baseVal&&svg.viewBox.baseVal.width>0&&svg.viewBox.baseVal.height>0){"
        "vb={x:svg.viewBox.baseVal.x,y:svg.viewBox.baseVal.y,w:svg.viewBox.baseVal.width,h:svg.viewBox.baseVal.height};"
        "}"
        "}catch(e){}"
        "if(!vb){"
        "try{"
        "var bb=svg.getBBox();"
        "if(bb&&bb.width>0&&bb.height>0){"
        "vb={x:bb.x,y:bb.y,w:bb.width,h:bb.height};"
        "svg.setAttribute('viewBox',vb.x+' '+vb.y+' '+vb.w+' '+vb.h);"
        "}"
        "}catch(e){}"
        "}"
        "if(!vb||!vb.w||!vb.h)return false;"
        "var rect=canvas.getBoundingClientRect();"
        "var pad=24;"
        "var s=Math.min((rect.width-pad*2)/vb.w,(rect.height-pad*2)/vb.h);"
        "if(!isFinite(s)||s<=0)s=1;"
        "scale=s;clamp();"
        "tx=pad+(rect.width-pad*2-vb.w*scale)/2 - vb.x*scale;"
        "ty=pad+(rect.height-pad*2-vb.h*scale)/2 - vb.y*scale;"
        "apply();"
        "canvas.dataset.fit='1';"
        "return true;"
        "}"
        "canvas.addEventListener('mousedown',function(e){dragging=true;canvas.classList.add('dragging');sx=e.clientX;sy=e.clientY;stx=tx;sty=ty;});"
        "window.addEventListener('mousemove',function(e){if(!dragging)return;tx=stx+(e.clientX-sx);ty=sty+(e.clientY-sy);apply();});"
        "window.addEventListener('mouseup',function(){if(!dragging)return;dragging=false;canvas.classList.remove('dragging');});"
        "canvas.addEventListener('wheel',function(e){e.preventDefault();var rect=canvas.getBoundingClientRect();var cx=e.clientX-rect.left;var cy=e.clientY-rect.top;"
        "var k=(e.deltaY<0)?1.12:0.89;var ns=scale*k;"
        "var ox=(cx-tx)/scale;var oy=(cy-ty)/scale;scale=ns;clamp();tx=cx-ox*scale;ty=cy-oy*scale;apply();},{passive:false});"
        "apply();"
        "setTimeout(function(){fitOnce();},0);"
        "setTimeout(function(){fitOnce();},60);"
        "}"
        "window.addEventListener('message',function(ev){"
        "if(!ev||!ev.data)return;"
        "if(ev.origin&&origin&&ev.origin!==origin)return;"
        "var msg=null;try{msg=JSON.parse(ev.data);}catch(e){return;}"
        "if(!msg||!msg.event)return;"
        "log('drawio event',msg.event);"
        "if(msg.event==='init'&&!loaded){loaded=true;try{clearTimeout(initTimer);}catch(e){}setStatus('Loading diagram…',false);post({action:'load',xml:xml});return;}"
        "if(msg.event==='load'&&!exported){exported=true;setStatus('Rendering…',false);post({action:'export',format:'svg'});return;}"
        "if(msg.event==='export'){"
        "var fmt=String(msg.format||'');"
        "if(fmt&&fmt!=='svg'&&fmt!=='xmlsvg')return;"
        "var data=msg.data||'';"
        "log('export format',fmt,'len',String(data).length,'prefix',String(data).slice(0,40));"
        "if(!data||String(data).length<20){setStatus('Export failed: empty data',true);return;}"
        "var svgText=decodeSvgData(data);"
        "if(!svgText||String(svgText).length<20){setStatus('Export failed: decode error',true);return;}"
        "var ok=setSvg(svgText);"
        "if(!ok){setStatus('Export failed: invalid SVG',true);return;}"
        "setStatus('',false);"
        "initPanZoom();"
        "}"
        "},false);"
        "setStatus('Preparing…',false);"
        "})();"
        "</script>"
    )
    return (
        "<div class=\"diagram-kit\">"
        "<div class=\"drawio-kit\">"
        f"<div id=\"{_esc_attr(canvas_id)}\" class=\"diagram-canvas\">"
        f"<div id=\"{_esc_attr(status_id)}\" class=\"diagram-status\">Preparing…</div>"
        f"<div id=\"{_esc_attr(svg_id)}\" class=\"diagram-svg\"></div>"
        "</div>"
        f"<iframe id=\"{_esc_attr(iframe_id)}\" class=\"drawio-renderer\" src=\"{_esc_attr(src)}\" loading=\"eager\" referrerpolicy=\"no-referrer\"></iframe>"
        "</div>"
        "</div>"
        + js
    )


def _escape_drawio_mxcell_values(xml: str) -> str:
    raw = str(xml or "")
    if "<mxCell" not in raw or "value=" not in raw:
        return raw

    def repl(m: re.Match[str]) -> str:
        val = m.group(1)
        t = val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t = t.replace("&amp;lt;", "&lt;").replace("&amp;gt;", "&gt;")
        t = t.replace("&amp;quot;", "&quot;").replace("&amp;apos;", "&apos;").replace("&amp;amp;", "&amp;")
        return f'value="{t}"'

    return re.sub(r'value="([^"]*)"', repl, raw)


def _sanitize_drawio_mxfile(xml: str) -> str:
    raw = str(xml or "")
    if "<mxGraphModel" not in raw or "<root>" not in raw:
        return raw

    def _escape_attr_text(s: str) -> str:
        t = str(s or "")
        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t = t.replace("&amp;lt;", "&lt;").replace("&amp;gt;", "&gt;")
        t = t.replace("&amp;quot;", "&quot;").replace("&amp;apos;", "&apos;").replace("&amp;amp;", "&amp;")
        return t

    cell_re = re.compile(r"(<mxCell\b[^>]*\bvertex=\"1\"[^>]*\bparent=\"1\"[^>]*?(?:/>|>[\s\S]*?</mxCell>))")
    overlays: List[Tuple[int, int, str]] = []
    cleaned_cells: List[Tuple[int, int, str]] = []

    for m in cell_re.finditer(raw):
        chunk = m.group(1)
        vm = re.search(r"\bvalue=\"([^\"]*)\"", chunk)
        if vm:
            val = vm.group(1)
            safe_val = _escape_attr_text(val)
            if safe_val != val:
                chunk = chunk[: vm.start(1)] + safe_val + chunk[vm.end(1) :]
        cleaned_cells.append((m.start(1), m.end(1), chunk))

        # Legacy overlay cleanup logic (kept, now based on updated chunk)
        if not vm or vm.group(1) != "":
            continue
        sm = re.search(r"\bstyle=\"([^\"]*)\"", chunk)
        if not sm:
            continue
        style = sm.group(1)
        if "fillColor=#FFFFFF" not in style and "fillColor=#ffffff" not in style:
            continue
        gm = re.search(r"<mxGeometry[^>]*\bwidth=\"([0-9.]+)\"[^>]*\bheight=\"([0-9.]+)\"", chunk)
        if not gm:
            continue
        try:
            w = float(gm.group(1))
            h = float(gm.group(2))
        except Exception:
            continue
        if w * h < 100000 and w < 500 and h < 200:
            continue
        overlays.append((m.start(1), m.end(1), chunk))

    # Apply cleaned_cells replacements (value escaping) first
    if cleaned_cells:
        segments: List[str] = []
        last = 0
        for start, end, chunk in cleaned_cells:
            segments.append(raw[last:start])
            last = end
            segments.append(chunk)
        segments.append(raw[last:])
        raw = "".join(segments)

    if not overlays:
        return raw

    segments: List[str] = []
    last = 0
    moved = []
    for start, end, chunk in overlays:
        segments.append(raw[last:start])
        last = end
        moved.append(chunk)
    segments.append(raw[last:])
    cleaned = "".join(segments)

    anchor = cleaned.find('<mxCell id="1" parent="0"/>')
    if anchor == -1:
        am = re.search(r"<mxCell\b[^>]*\bid=\"1\"[^>]*\bparent=\"0\"[^>]*/>", cleaned)
        if not am:
            return raw
        insert_at = am.end(0)
    else:
        insert_at = anchor + len('<mxCell id="1" parent="0"/>')

    insert_block = "".join(moved)
    return cleaned[:insert_at] + insert_block + cleaned[insert_at:]


def _esc_attr(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def _esc_html(s: str) -> str:
    return html.escape(str(s or ""), quote=False)


def _diagram_spec_to_drawio_mxfile(d: Dict[str, Any]) -> str:
    title = str(d.get("title") or "").strip()
    nodes = list(d.get("nodes") or [])
    edges = list(d.get("edges") or [])

    phases = ["Preparation", "Integration", "Execution"]
    by_phase: Dict[str, List[Dict[str, Any]]] = {p: [] for p in phases}
    for n in nodes:
        p = str(n.get("phase") or "Execution").strip() or "Execution"
        if p not in by_phase:
            p = "Execution"
        by_phase[p].append(n)

    col_x = {"Preparation": 40, "Integration": 330, "Execution": 620}
    node_w, node_h = 220, 72
    gap_y = 92
    start_y = 70

    cells: List[str] = []
    next_id = 2
    id_map: Dict[str, str] = {}

    for p in phases:
        for i, n in enumerate(by_phase.get(p) or []):
            nid = str(n.get("id") or "").strip() or f"n{next_id}"
            cid = str(next_id)
            next_id += 1
            id_map[nid] = cid
            label = str(n.get("label") or "").strip()
            detail = str(n.get("detail") or "").strip()
            value = label
            if detail:
                value = value + "&#xa;" + detail
            value = _esc_attr(value).replace("&amp;#xa;", "&#xa;")
            x = col_x[p]
            y = start_y + i * gap_y
            style = "rounded=1;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#111827;strokeWidth=1;"
            cells.append(
                f"<mxCell id=\"{cid}\" value=\"{value}\" style=\"{style}\" vertex=\"1\" parent=\"1\">"
                f"<mxGeometry x=\"{x}\" y=\"{y}\" width=\"{node_w}\" height=\"{node_h}\" as=\"geometry\"/>"
                f"</mxCell>"
            )

    for e in edges:
        frm = str(e.get("from") or e.get("frm") or "").strip()
        to = str(e.get("to") or "").strip()
        if frm not in id_map or to not in id_map or frm == to:
            continue
        a = id_map[frm]
        b = id_map[to]
        lab = str(e.get("label") or "").strip()
        lab = _esc_attr(lab)
        eid = str(next_id)
        next_id += 1
        style = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=classic;"
        cells.append(
            f"<mxCell id=\"{eid}\" value=\"{lab}\" style=\"{style}\" edge=\"1\" parent=\"1\" source=\"{a}\" target=\"{b}\">"
            f"<mxGeometry relative=\"1\" as=\"geometry\"/>"
            f"</mxCell>"
        )

    root = "<mxCell id=\"0\"/><mxCell id=\"1\" parent=\"0\"/>" + "".join(cells)
    mx = f"<mxGraphModel><root>{root}</root></mxGraphModel>"
    return f"<mxfile><diagram name=\"Page-1\" id=\"page-1\">{mx}</diagram></mxfile>"


def _esc(s: str) -> str:
    t = str(s or "")
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return t


def _ring_svg(percent: float) -> str:
    p = max(0.0, min(100.0, float(percent or 0.0)))
    r = 22.0
    c = 2.0 * 3.1415926 * r
    dash = (p / 100.0) * c
    return (
        "<svg viewBox=\"0 0 56 56\" xmlns=\"http://www.w3.org/2000/svg\">"
        "<defs>"
        "<linearGradient id=\"dkg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">"
        "<stop offset=\"0\" stop-color=\"var(--accent-tertiary)\"/>"
        "<stop offset=\"0.55\" stop-color=\"var(--accent-primary)\"/>"
        "<stop offset=\"1\" stop-color=\"var(--accent-secondary)\"/>"
        "</linearGradient>"
        "</defs>"
        "<circle cx=\"28\" cy=\"28\" r=\"22\" fill=\"none\" stroke=\"rgba(255,255,255,0.12)\" stroke-width=\"6\"/>"
        f"<circle cx=\"28\" cy=\"28\" r=\"22\" fill=\"none\" stroke=\"url(#dkg)\" stroke-width=\"6\" stroke-linecap=\"round\" stroke-dasharray=\"{dash:.2f} {c:.2f}\" transform=\"rotate(-90 28 28)\"/>"
        "</svg>"
    )


def _edge_svg(label: str) -> str:
    lab = str(label or "").strip()
    lab_html = f"<div class=\"diagram-kit-edge-label\">{_esc(lab)}</div>" if lab else ""
    return (
        "<div class=\"diagram-kit-edge\" aria-hidden=\"true\">"
        "<div style=\"position:relative;\">"
        "<svg viewBox=\"0 0 120 40\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\">"
        "<defs>"
        "<linearGradient id=\"dke\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"0\">"
        "<stop offset=\"0\" stop-color=\"var(--accent-tertiary)\"/>"
        "<stop offset=\"0.55\" stop-color=\"var(--accent-primary)\"/>"
        "<stop offset=\"1\" stop-color=\"var(--accent-secondary)\"/>"
        "</linearGradient>"
        "</defs>"
        "<path d=\"M6 20 C 38 6, 82 6, 114 20\" stroke=\"url(#dke)\" stroke-width=\"3.5\" stroke-linecap=\"round\"/>"
        "<path d=\"M102 14 L114 20 L102 26\" stroke=\"url(#dke)\" stroke-width=\"3.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>"
        "</svg>"
        f"{lab_html}"
        "</div>"
        "</div>"
    )


def _coerce_progress(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, str):
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", v)
            if not m:
                return None
            v = float(m.group(1))
        v = float(v)
    except Exception:
        return None
    if v > 1.0 and v <= 100.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _coerce_spec_dict(spec: Any) -> Dict[str, Any]:
    if isinstance(spec, dict):
        d = spec
    else:
        d = {}
        try:
            d = {
                "title": getattr(spec, "title", ""),
                "nodes": getattr(spec, "nodes", []),
                "edges": getattr(spec, "edges", []),
                "layout": getattr(spec, "layout", {"direction": "LR"}),
            }
        except Exception:
            d = {}

    nodes = list(d.get("nodes") or [])
    edges = list(d.get("edges") or [])
    layout = dict(d.get("layout") or {})
    direction = str(layout.get("direction") or "LR").strip().upper()
    if direction not in {"LR", "TB"}:
        direction = "LR"

    nodes2 = []
    seen = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip() or f"n{i+1}"
        if nid in seen:
            nid = f"{nid}_{i+1}"
        seen.add(nid)
        phase = str(n.get("phase") or "Execution").strip() or "Execution"
        label = str(n.get("label") or "").strip()[:56]
        detail = str(n.get("detail") or "").strip()[:140]
        metrics = n.get("metrics") or []
        mm = []
        if isinstance(metrics, list):
            for m in metrics[:4]:
                if isinstance(m, dict):
                    lab = str(m.get("label") or "").strip()[:18]
                    val = str(m.get("value") or "").strip()[:18]
                    if lab and val:
                        mm.append({"label": lab, "value": val})
        nodes2.append({"id": nid, "phase": phase, "label": label or f"Stage {i+1}", "detail": detail, "metrics": mm, "progress": n.get("progress")})

    ids = {n["id"] for n in nodes2}
    edges2 = []
    for e in edges[:16]:
        if not isinstance(e, dict):
            continue
        frm = str(e.get("from") or e.get("frm") or "").strip()
        to = str(e.get("to") or "").strip()
        if not frm or not to:
            continue
        if frm not in ids or to not in ids or frm == to:
            continue
        lab = str(e.get("label") or "").strip()[:40]
        edges2.append({"from": frm, "to": to, "label": lab})

    if not edges2 and len(nodes2) >= 2:
        for i in range(len(nodes2) - 1):
            edges2.append({"from": nodes2[i]["id"], "to": nodes2[i + 1]["id"], "label": ""})

    return {"title": str(d.get("title") or "")[:90], "nodes": nodes2[:6], "edges": edges2, "layout": {"direction": direction}}


def _layout_lr(nodes: List[Dict[str, Any]], edges: List[Dict[str, str]], direction: str) -> Dict[str, Any]:
    ids = [n["id"] for n in nodes]
    idx_map = {nid: i for i, nid in enumerate(ids)}
    adj = {nid: [] for nid in ids}
    indeg = {nid: 0 for nid in ids}
    for e in edges:
        a = e["from"]
        b = e["to"]
        if a in adj and b in indeg:
            adj[a].append(b)
            indeg[b] += 1

    q = [nid for nid in ids if indeg[nid] == 0]
    topo = []
    while q:
        q.sort(key=lambda x: idx_map.get(x, 0))
        u = q.pop(0)
        topo.append(u)
        for v in adj.get(u, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    if len(topo) != len(ids):
        topo = ids[:]

    layer = {nid: 0 for nid in ids}
    for u in topo:
        for v in adj.get(u, []):
            layer[v] = max(layer[v], layer[u] + 1)

    max_layer = max(layer.values()) if layer else 0
    buckets: Dict[int, List[str]] = {}
    for nid in ids:
        buckets.setdefault(layer[nid], []).append(nid)
    for k in buckets:
        buckets[k].sort(key=lambda x: idx_map.get(x, 0))

    rows = max((len(v) for v in buckets.values()), default=1)
    cols = max_layer + 1

    node_w = 320.0
    node_h = 176.0
    gap_x = 170.0
    gap_y = 190.0
    pad_x = 72.0
    pad_y = 72.0
    if cols <= 0:
        cols = 1
    if rows <= 0:
        rows = 1
    step_x = node_w + gap_x
    step_y = node_h + gap_y
    content_w = (cols - 1) * step_x + node_w
    content_h = (rows - 1) * step_y + node_h
    W = max(1000.0, content_w + pad_x * 2.0)
    H = max(560.0, content_h + pad_y * 2.0)

    pos: Dict[str, Tuple[float, float]] = {}
    for c in range(cols):
        col_nodes = buckets.get(c, [])
        for r, nid in enumerate(col_nodes):
            x = pad_x + node_w / 2.0 + c * step_x
            y = pad_y + node_h / 2.0 + r * step_y
            if direction == "TB":
                pos[nid] = (y, x)
            else:
                pos[nid] = (x, y)

    return {"pos": pos, "width": int(W if direction != "TB" else H), "height": int(H if direction != "TB" else W)}


def _layout_phase_lanes(nodes: List[Dict[str, Any]], edges: List[Dict[str, str]], direction: str) -> Dict[str, Any]:
    ids = [n["id"] for n in nodes]
    idx_map = {nid: i for i, nid in enumerate(ids)}

    def _norm_phase(p: str) -> str:
        t = str(p or "").strip().lower()
        if not t:
            return "Execution"
        if t in {"prep", "preparation", "prepare", "init", "setup"}:
            return "Preparation"
        if t in {"integration", "integrate", "merge", "routing", "route"}:
            return "Integration"
        if t in {"execution", "execute", "run", "search", "query", "compute", "serving"}:
            return "Execution"
        if "prep" in t:
            return "Preparation"
        if "integr" in t or "merge" in t or "route" in t:
            return "Integration"
        return "Execution"

    phase_order = ["Preparation", "Integration", "Execution"]
    buckets: Dict[str, List[str]] = {p: [] for p in phase_order}
    for n in nodes:
        nid = n["id"]
        ph = _norm_phase(n.get("phase"))
        buckets.setdefault(ph, []).append(nid)
    for k in list(buckets.keys()):
        buckets[k].sort(key=lambda x: idx_map.get(x, 0))

    lanes = [p for p in phase_order if buckets.get(p)]
    if not lanes:
        lanes = ["Execution"]
        buckets["Execution"] = ids[:]

    lane_count = len(lanes)
    max_in_lane = max((len(buckets.get(p) or []) for p in lanes), default=1)

    node_w = 320.0
    node_h = 176.0
    gap_x = 170.0
    gap_y = 190.0
    pad_x = 72.0
    pad_y = 72.0
    step_x = node_w + gap_x
    step_y = node_h + gap_y

    if direction == "TB":
        cols = max(1, int(max_in_lane))
        rows = max(1, int(lane_count))
        content_w = (cols - 1) * step_x + node_w
        content_h = (rows - 1) * step_y + node_h
        W = max(1000.0, content_w + pad_x * 2.0)
        H = max(560.0, content_h + pad_y * 2.0)
        pos: Dict[str, Tuple[float, float]] = {}
        for li, ph in enumerate(lanes):
            row_nodes = buckets.get(ph) or []
            for ci, nid in enumerate(row_nodes):
                x = pad_x + node_w / 2.0 + ci * step_x
                y = pad_y + node_h / 2.0 + li * step_y
                pos[nid] = (x, y)
        return {"pos": pos, "width": int(W), "height": int(H)}

    cols = max(1, int(lane_count))
    rows = max(1, int(max_in_lane))
    content_w = (cols - 1) * step_x + node_w
    content_h = (rows - 1) * step_y + node_h
    W = max(1000.0, content_w + pad_x * 2.0)
    H = max(560.0, content_h + pad_y * 2.0)

    pos = {}
    for li, ph in enumerate(lanes):
        col_nodes = buckets.get(ph) or []
        for ri, nid in enumerate(col_nodes):
            x = pad_x + node_w / 2.0 + li * step_x
            y = pad_y + node_h / 2.0 + ri * step_y
            pos[nid] = (x, y)

    return {"pos": pos, "width": int(W), "height": int(H)}


def _layout_flow_grid(nodes: List[Dict[str, Any]], edges: List[Dict[str, str]], direction: str) -> Dict[str, Any]:
    ids = [n["id"] for n in nodes]
    idx_map = {nid: i for i, nid in enumerate(ids)}

    adj = {nid: [] for nid in ids}
    indeg = {nid: 0 for nid in ids}
    for e in edges:
        a = e.get("from")
        b = e.get("to")
        if a in adj and b in indeg:
            adj[a].append(b)
            indeg[b] += 1

    q = [nid for nid in ids if indeg[nid] == 0]
    topo = []
    while q:
        q.sort(key=lambda x: idx_map.get(x, 0))
        u = q.pop(0)
        topo.append(u)
        for v in adj.get(u, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(topo) != len(ids):
        topo = ids[:]

    n = len(topo)
    if n <= 0:
        return {"pos": {}, "width": 1000, "height": 560}

    node_w = 320.0
    node_h = 176.0
    gap_x = 140.0
    gap_y = 140.0
    pad_x = 64.0
    pad_y = 64.0
    step_x = node_w + gap_x
    step_y = node_h + gap_y

    if direction == "TB":
        cols = max(1, min(3, n))
        rows = int((n + cols - 1) / cols)
        content_w = (cols - 1) * step_x + node_w
        content_h = (rows - 1) * step_y + node_h
        W = max(1000.0, content_w + pad_x * 2.0)
        H = max(560.0, content_h + pad_y * 2.0)
        pos: Dict[str, Tuple[float, float]] = {}
        for i, nid in enumerate(topo):
            c = i % cols
            r = int(i / cols)
            x = pad_x + node_w / 2.0 + c * step_x
            y = pad_y + node_h / 2.0 + r * step_y
            pos[nid] = (x, y)
        return {"pos": pos, "width": int(W), "height": int(H)}

    cols = max(1, min(3, n))
    rows = int((n + cols - 1) / cols)
    content_w = (cols - 1) * step_x + node_w
    content_h = (rows - 1) * step_y + node_h
    W = max(1000.0, content_w + pad_x * 2.0)
    H = max(560.0, content_h + pad_y * 2.0)
    pos = {}
    for i, nid in enumerate(topo):
        c = i % cols
        r = int(i / cols)
        x = pad_x + node_w / 2.0 + c * step_x
        y = pad_y + node_h / 2.0 + r * step_y
        pos[nid] = (x, y)
    return {"pos": pos, "width": int(W), "height": int(H)}


def _edge_anchors(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float, float, float]:
    x1, y1 = a
    x2, y2 = b
    dx = x2 - x1
    dy = y2 - y1
    node_w = 320.0
    node_h = 176.0
    if abs(dx) >= abs(dy):
        sgn = 1.0 if dx >= 0 else -1.0
        return (x1 + sgn * node_w / 2.0, y1, x2 - sgn * node_w / 2.0, y2)
    sgn = 1.0 if dy >= 0 else -1.0
    return (x1, y1 + sgn * node_h / 2.0, x2, y2 - sgn * node_h / 2.0)


def _route_path(a: Tuple[float, float], b: Tuple[float, float], W: float, H: float) -> str:
    x1, y1 = a
    x2, y2 = b
    dx = x2 - x1
    dy = y2 - y1
    margin = 18.0

    def clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    if abs(dx) >= abs(dy):
        sgn = 1.0 if dx >= 0 else -1.0
        bend = min(160.0, max(90.0, abs(dx) * 0.35))
        c1x = clamp(x1 + sgn * bend, margin, float(W) - margin)
        c2x = clamp(x2 - sgn * bend, margin, float(W) - margin)
        return f"M{x1:.1f},{y1:.1f} C{c1x:.1f},{y1:.1f} {c2x:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"

    sgn = 1.0 if dy >= 0 else -1.0
    bend = min(160.0, max(90.0, abs(dy) * 0.35))
    c1y = clamp(y1 + sgn * bend, margin, float(H) - margin)
    c2y = clamp(y2 - sgn * bend, margin, float(H) - margin)
    return f"M{x1:.1f},{y1:.1f} C{x1:.1f},{c1y:.1f} {x2:.1f},{c2y:.1f} {x2:.1f},{y2:.1f}"
