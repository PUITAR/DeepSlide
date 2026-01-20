
import streamlit as st
import sys
import os
import json
import uuid
import html as _html
import streamlit.components.v1 as components

# Add current directory and parent to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, '../../..')) # For root imports if needed

from logic_chain_editor import LogicChainEditor, LogicChainUI
from data_types import LogicNode

st.set_page_config(layout="wide", page_title="Logic Chain Workbench")

# --- Small global polish for Streamlit UI (non-invasive) ---
st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
      div[data-testid="stHorizontalBlock"] { gap: 0.75rem; }
      .stButton > button { border-radius: 10px; }
      .stMarkdown p { margin-bottom: 0.35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

def _parse_duration_min(s: str, default_val: int = 5) -> int:
    import re
    try:
        m = re.search(r"(\d+)", str(s or ""))
        if m:
            return max(1, int(m.group(1)))
    except Exception:
        return default_val
    return default_val

# --- OVERRIDDEN RENDER FUNCTION FOR TESTING LAYOUT ---
def _render_logic_chain_board_html_test(
    nodes,
    edges,
    active_idx: int,
    node_count: int,
    ref_count: int,
    total_min: int,
):
    uid = f"ds_lc_{uuid.uuid4().hex}"

    safe_nodes = []
    for i, n in enumerate(nodes or []):
        dmin = _parse_duration_min(str(getattr(n, "duration", "")), 3)
        safe_nodes.append(
            {
                "i": int(i),
                "name": _html.escape(str(getattr(n, "name", ""))),
                "dmin": int(dmin),
            }
        )

    safe_refs = []
    for i, e in enumerate(edges or []):
        if str(e.get("type", "sequential")) != "reference":
            continue
        try:
            fi = int(e.get("from"))
            ti = int(e.get("to"))
        except Exception:
            continue
        if not (0 <= fi < len(safe_nodes) and 0 <= ti < len(safe_nodes)):
            continue
        safe_refs.append(
            {
                "from": fi,
                "to": ti,
                "reason": _html.escape(str(e.get("reason", ""))),
                "idx": i,
            }
        )

    refs_json = json.dumps(
        [{"from": r["from"], "to": r["to"], "reason": r.get("reason", ""), "idx": r["idx"]} for r in safe_refs],
        ensure_ascii=False,
    )

    node_html = "".join(
        [
            "<div class='ds-board-card" + (" is-active" if int(n["i"]) == int(active_idx) else "") + "' data-idx='"
            + str(n["i"])
            + "'>"
            + "<div class='ds-card-actions'>"
            + "<button class='ds-act-btn' data-act='edit' title='Edit node'>✎</button>"
            + "<button class='ds-act-btn is-accent' data-act='link' title='Add reference from this node'>🔗</button>"
            + "</div>"
            + "<div class='ds-board-top'>"
            + "<div class='ds-board-badge'>"
            + str(n["i"] + 1)
            + "</div>"
            + "<div class='ds-board-name'>"
            + n["name"]
            + "</div>"
            + "</div>"
            + "<div class='ds-board-meta'>"
            + "<button class='ds-dur-btn' data-delta='-1' title='-1 min'>−</button>"
            + "<span class='ds-dur-val'>"
            + str(int(n["dmin"]))
            + "</span>"
            + "<span class='ds-dur-unit'>min</span>"
            + "<button class='ds-dur-btn' data-delta='1' title='+1 min'>+</button>"
            + "</div>"
            + "</div>"
            for n in safe_nodes
        ]
    )

    # Slightly shorter iframe: all panning/scrolling happens inside the board.
    h = 720

    tpl = """
    <div class="ds-board" id="__DS_UID__">
      <div class="ds-board-head">
        <div>
          <div class="ds-board-title">Logic Chain Map</div>
          <div class="ds-board-sub">Drag cards to reorder • ✎ edit node • ⚙ edit reference</div>
        </div>
        <div class="ds-board-legend">
          <span class="ds-lg ds-lg-stat">__DS_NODE_COUNT__ nodes</span>
          <span class="ds-lg ds-lg-stat">__DS_REF_COUNT__ refs</span>
          <span class="ds-lg ds-lg-stat">~__DS_TOTAL_MIN__ min</span>
          <span class="ds-lg ds-lg-ref">Reference Flow</span>
        </div>
      </div>

      <div class="ds-board-wrap" aria-label="Logic chain canvas">
        <div class="ds-wrap-toolbar" aria-hidden="false">
          <button class="ds-tb-btn" data-act="left" title="Scroll left">⟵</button>
          <button class="ds-tb-btn" data-act="right" title="Scroll right">⟶</button>
          <button class="ds-tb-btn" data-act="fit" title="Center active">⤢</button>
        </div>

        <div class="ds-board-canvas">
          <svg class="ds-board-svg" aria-hidden="true"></svg>
          <div class="ds-board-row">__DS_NODE_HTML__</div>
        </div>

        <div class="ds-fade ds-fade-left" aria-hidden="true"></div>
        <div class="ds-fade ds-fade-right" aria-hidden="true"></div>
      </div>
    </div>

    <style>
      :root {
        --c-text: #0f172a;
        --c-muted: #64748b;
        --c-border: #e2e8f0;
        --c-card: rgba(255, 255, 255, 0.92);
        --c-accent: #6366f1;
        --c-accent-2: #ec4899;
        --c-accent-light: #e0e7ff;
        --c-bg: #f8fafc;
      }
      body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }
      .ds-board {
        border-radius: 22px;
        background: var(--c-bg);
        background-image: radial-gradient(#cbd5e1 1px, transparent 1px);
        background-size: 26px 26px;
        border: 1px solid var(--c-border);
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
        padding: 20px;
        height: 100%;
        display: flex;
        flex-direction: column;
        gap: 14px;
      }
      .ds-board-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
        padding: 0 4px;
      }
      .ds-board-title {
        font-size: 18px;
        font-weight: 800;
        color: var(--c-text);
        margin-bottom: 2px;
        letter-spacing: 0.2px;
      }
      .ds-board-sub {
        font-size: 12.5px;
        font-weight: 600;
        color: var(--c-muted);
      }
      .ds-board-legend {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: 8px;
      }
      .ds-lg {
        font-size: 12px;
        font-weight: 700;
        color: var(--c-muted);
        background: rgba(255,255,255,0.85);
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid var(--c-border);
        display: inline-flex;
        align-items: center;
        gap: 6px;
        backdrop-filter: blur(10px);
      }
      .ds-lg-ref::before {
        content: "";
        width: 12px;
        height: 3px;
        background: linear-gradient(90deg, var(--c-accent), var(--c-accent-2));
        border-radius: 4px;
      }
      .ds-board-wrap {
        position: relative;
        flex: 1;
        border-radius: 16px;
        border: 1px solid var(--c-border);
        background: rgba(255, 255, 255, 0.55);
        box-shadow: inset 0 1px 2px rgba(15,23,42,0.04);
        overflow: auto;
        overscroll-behavior: contain;
      }
      .ds-board-wrap.is-panning { cursor: grabbing; }
      .ds-wrap-toolbar {
        position: sticky;
        top: 10px;
        left: 10px;
        z-index: 80;
        display: inline-flex;
        gap: 6px;
        padding: 6px;
        background: rgba(255,255,255,0.75);
        border: 1px solid var(--c-border);
        border-radius: 999px;
        backdrop-filter: blur(10px);
        margin: 10px;
      }
      .ds-tb-btn {
        width: 34px;
        height: 34px;
        border: 1px solid var(--c-border);
        background: #fff;
        border-radius: 999px;
        cursor: pointer;
        font-weight: 800;
        color: var(--c-text);
        box-shadow: 0 1px 2px rgba(15,23,42,0.05);
        transition: transform 0.12s ease, box-shadow 0.12s ease;
      }
      .ds-tb-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 18px rgba(15,23,42,0.08);
      }
      .ds-board-canvas {
        position: relative;
        min-width: 100%;
        min-height: 100%;
      }
      .ds-board-svg {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        z-index: 10;
        pointer-events: auto;
      }
      .ds-board-row {
        position: relative;
        display: flex;
        gap: 26px;
        padding: 38px;
        width: fit-content;
        align-items: flex-start;
        z-index: 20;
        pointer-events: none; /* keep empty-space interactions for SVG + panning */
      }
      .ds-board-card {
        width: 280px;
        min-width: 280px;
        background: var(--c-card);
        border: 1px solid var(--c-border);
        border-radius: 16px;
        padding: 18px;
        box-shadow: 0 6px 14px rgba(15, 23, 42, 0.08);
        cursor: grab;
        transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
        position: relative;
        user-select: none;
        pointer-events: auto;
        z-index: 30;
        backdrop-filter: blur(12px);
      }
      .ds-board-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 18px 32px rgba(15, 23, 42, 0.14);
        border-color: rgba(99, 102, 241, 0.6);
      }
      .ds-board-card:active { cursor: grabbing; }
      .ds-board-card.is-active {
        border-color: var(--c-accent);
        box-shadow: 0 0 0 2px var(--c-accent-light), 0 18px 32px rgba(15, 23, 42, 0.14);
      }
      .ds-card-actions {
        position: absolute;
        top: 10px;
        right: 10px;
        display: flex;
        gap: 6px;
        opacity: 0;
        transform: translateY(-4px);
        transition: opacity 0.14s ease, transform 0.14s ease;
        z-index: 40;
      }
      .ds-board-card:hover .ds-card-actions {
        opacity: 1;
        transform: translateY(0);
      }
      .ds-act-btn {
        width: 30px;
        height: 30px;
        border-radius: 10px;
        border: 1px solid var(--c-border);
        background: rgba(255,255,255,0.92);
        color: var(--c-text);
        font-weight: 900;
        cursor: pointer;
        box-shadow: 0 1px 2px rgba(15,23,42,0.06);
      }
      .ds-act-btn.is-accent {
        border-color: rgba(99, 102, 241, 0.35);
      }
      .ds-act-btn:hover {
        border-color: rgba(99, 102, 241, 0.6);
      }
      .ds-board-top {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 12px;
        padding-right: 64px;
      }
      .ds-board-badge {
        width: 32px;
        height: 32px;
        border-radius: 10px;
        background: var(--c-accent-light);
        color: var(--c-accent);
        font-weight: 900;
        font-size: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }
      .ds-board-name {
        font-weight: 900;
        color: var(--c-text);
        font-size: 15px;
        line-height: 1.25;
      }
      .ds-board-meta {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: var(--c-muted);
        font-size: 12.5px;
        font-weight: 800;
        background: rgba(241,245,249,0.85);
        padding: 6px 10px;
        border-radius: 10px;
        width: fit-content;
      }
      .ds-dur-btn {
        width: 26px;
        height: 26px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 9px;
        border: 1px solid var(--c-border);
        background: #fff;
        color: var(--c-text);
        font-weight: 900;
        cursor: pointer;
        box-shadow: 0 1px 2px rgba(15,23,42,0.05);
      }
      .ds-dur-btn:hover {
        background: var(--c-accent);
        color: #fff;
        border-color: rgba(99,102,241,0.8);
      }
      .ds-edge-settings-btn {
        cursor: pointer;
        opacity: 0;
        transition: opacity 0.14s ease;
      }
      g:hover .ds-edge-settings-btn { opacity: 1; }
      .ds-fade {
        position: sticky;
        top: 0;
        bottom: 0;
        width: 26px;
        pointer-events: none;
        z-index: 70;
      }
      .ds-fade-left {
        left: 0;
        float: left;
        background: linear-gradient(90deg, rgba(248,250,252,0.95), rgba(248,250,252,0));
      }
      .ds-fade-right {
        right: 0;
        float: right;
        background: linear-gradient(270deg, rgba(248,250,252,0.95), rgba(248,250,252,0));
      }
    </style>

    <script>
      (() => {
        const root = document.getElementById(__DS_UID_JSON__);
        if (!root) return;
        const wrap = root.querySelector('.ds-board-wrap');
        const canvas = root.querySelector('.ds-board-canvas');
        const svg = root.querySelector('.ds-board-svg');
        const list = root.querySelector('.ds-board-row');
        const refs = __DS_REFS_JSON__;

        let dragging = null;
        let isDraggingFlag = false;
        let isPanning = false;
        let pan0 = { x: 0, y: 0, sl: 0, st: 0 };

        function setCmd(cmd, idx, val, order) {
          try {
            const url = new URL(window.parent.location.href);
            if (cmd) url.searchParams.set('lc_cmd', String(cmd));
            if (idx !== undefined && idx !== null) url.searchParams.set('lc_idx', String(idx));
            if (val !== undefined && val !== null) url.searchParams.set('lc_val', String(val));
            if (order) url.searchParams.set('lc_order', String(order));
            window.parent.location.href = url.toString();
          } catch (e) {
            console.error('Failed to set command', e);
          }
        }

        function clearSvg() {
          while (svg.firstChild) svg.removeChild(svg.firstChild);
        }

        function addDefs() {
          const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');

          const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
          marker.setAttribute('id', 'arrow');
          marker.setAttribute('viewBox', '0 0 10 10');
          marker.setAttribute('refX', '8');
          marker.setAttribute('refY', '5');
          marker.setAttribute('markerWidth', '6');
          marker.setAttribute('markerHeight', '6');
          marker.setAttribute('orient', 'auto-start-reverse');
          const mp = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          mp.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
          mp.setAttribute('fill', '#6366f1');
          marker.appendChild(mp);
          defs.appendChild(marker);

          const grad = document.createElementNS('http://www.w3.org/2000/svg', 'linearGradient');
          grad.setAttribute('id', 'refGrad');
          grad.setAttribute('x1', '0%');
          grad.setAttribute('y1', '0%');
          grad.setAttribute('x2', '100%');
          grad.setAttribute('y2', '0%');
          const s1 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
          s1.setAttribute('offset', '0%');
          s1.setAttribute('stop-color', '#6366f1');
          const s2 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
          s2.setAttribute('offset', '100%');
          s2.setAttribute('stop-color', '#ec4899');
          grad.appendChild(s1);
          grad.appendChild(s2);
          defs.appendChild(grad);

          svg.appendChild(defs);
        }

        function ensureCanvasSize(extraHeight) {
          const desiredW = Math.max(list.scrollWidth, wrap.clientWidth);
          const desiredH = Math.max(list.scrollHeight + (extraHeight || 0), wrap.clientHeight);
          canvas.style.width = desiredW + 'px';
          canvas.style.height = desiredH + 'px';
          svg.setAttribute('viewBox', '0 0 ' + desiredW + ' ' + desiredH);
        }

        function draw() {
          const nodes = Array.from(list.querySelectorAll('.ds-board-card'));
          if (!nodes.length) return;

          const pos = new Map();
          let maxBottom = 0;
          nodes.forEach(el => {
            const idx = Number(el.getAttribute('data-idx'));
            const left = el.offsetLeft;
            const top = el.offsetTop;
            const w = el.offsetWidth;
            const h = el.offsetHeight;
            const cx = left + w / 2;
            const bottom = top + h;
            maxBottom = Math.max(maxBottom, bottom);
            pos.set(idx, { cx, bottom, w, h, left, top });
          });

          // Lane packing to avoid overlaps.
          const sorted = refs.slice().sort((a, b) => {
            const sa = Math.abs(a.to - a.from);
            const sb = Math.abs(b.to - b.from);
            return sa - sb;
          });
          const lanes = [];
          const placements = [];
          const pad = 18;
          sorted.forEach(e => {
            const a = pos.get(Number(e.from));
            const b = pos.get(Number(e.to));
            if (!a || !b) return;
            const startX = Math.min(a.cx, b.cx);
            const endX = Math.max(a.cx, b.cx);

            let laneIdx = -1;
            for (let i = 0; i < lanes.length; i++) {
              let collision = false;
              for (const itv of lanes[i]) {
                if (startX < itv[1] + pad && endX > itv[0] - pad) { collision = true; break; }
              }
              if (!collision) {
                laneIdx = i;
                lanes[i].push([startX, endX]);
                break;
              }
            }
            if (laneIdx === -1) {
              laneIdx = lanes.length;
              lanes.push([[startX, endX]]);
            }
            placements.push({ e, laneIdx });
          });

          const laneGap = 26;
          const laneStart = maxBottom + 26;
          const extraHeight = (lanes.length ? (laneStart + lanes.length * laneGap + 42) : (maxBottom + 80)) - list.scrollHeight;
          ensureCanvasSize(Math.max(0, extraHeight));

          clearSvg();
          addDefs();

          placements.forEach(({ e, laneIdx }) => {
            const a = pos.get(Number(e.from));
            const b = pos.get(Number(e.to));
            if (!a || !b) return;

            const x1 = a.cx;
            const y1 = a.bottom;
            const x2 = b.cx;
            const y2 = b.bottom;
            const laneY = laneStart + laneIdx * laneGap;
            const r1 = 14;
            const dir = (x2 > x1) ? 1 : -1;

            let d = `M ${x1} ${y1} L ${x1} ${laneY - r1}`;
            d += ` Q ${x1} ${laneY} ${x1 + dir * r1} ${laneY}`;
            d += ` L ${x2 - dir * r1} ${laneY}`;
            d += ` Q ${x2} ${laneY} ${x2} ${laneY - r1}`;
            d += ` L ${x2} ${y2}`;

            const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            g.style.cursor = 'pointer';

            const hit = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            hit.setAttribute('d', d);
            hit.setAttribute('stroke', 'transparent');
            hit.setAttribute('stroke-width', '18');
            hit.setAttribute('fill', 'none');
            hit.setAttribute('class', 'ds-edge-hit');
            hit.style.pointerEvents = 'stroke';
            hit.addEventListener('click', (ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              setCmd('edit_edge', e.idx);
            });
            g.appendChild(hit);

            const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            p.setAttribute('d', d);
            p.setAttribute('fill', 'none');
            p.setAttribute('stroke', 'url(#refGrad)');
            p.setAttribute('stroke-width', '2.2');
            p.setAttribute('stroke-linecap', 'round');
            p.setAttribute('marker-end', 'url(#arrow)');
            p.style.pointerEvents = 'none';
            g.appendChild(p);

            // Edge settings button (show on hover)
            const settingsGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            settingsGroup.setAttribute('class', 'ds-edge-settings-btn');
            const sx = x1 + dir * 14;
            const sy = laneY - 16;
            const sc = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            sc.setAttribute('cx', sx);
            sc.setAttribute('cy', sy);
            sc.setAttribute('r', '10');
            sc.setAttribute('fill', '#fff');
            sc.setAttribute('stroke', '#cbd5e1');
            sc.setAttribute('stroke-width', '1');
            settingsGroup.appendChild(sc);
            const stxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            stxt.setAttribute('x', sx);
            stxt.setAttribute('y', sy + 4);
            stxt.setAttribute('text-anchor', 'middle');
            stxt.setAttribute('font-size', '12px');
            stxt.setAttribute('fill', '#64748b');
            stxt.textContent = '⚙';
            settingsGroup.appendChild(stxt);
            settingsGroup.style.pointerEvents = 'all';
            settingsGroup.addEventListener('click', (ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              setCmd('edit_edge', e.idx);
            });
            g.appendChild(settingsGroup);

            if (e.reason) {
              const t = document.createElementNS('http://www.w3.org/2000/svg', 'title');
              t.textContent = e.reason;
              g.appendChild(t);
            }
            svg.appendChild(g);
          });
        }

        // --- Toolbar actions ---
        root.querySelectorAll('.ds-tb-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const act = btn.getAttribute('data-act');
            const step = 360;
            if (act === 'left') wrap.scrollBy({ left: -step, top: 0, behavior: 'smooth' });
            if (act === 'right') wrap.scrollBy({ left: step, top: 0, behavior: 'smooth' });
            if (act === 'fit') {
              const active = list.querySelector('.ds-board-card.is-active') || list.querySelector('.ds-board-card');
              if (active) {
                const x = active.offsetLeft + active.offsetWidth / 2 - wrap.clientWidth / 2;
                wrap.scrollTo({ left: Math.max(0, x), top: 0, behavior: 'smooth' });
              }
            }
          });
        });

        // --- Drag-to-pan on empty space (wrap) ---
        wrap.addEventListener('mousedown', (ev) => {
          if (ev.button !== 0) return;
          if (isDraggingFlag) return;
          // Avoid starting pan when interacting with a card/button/edge
          const t = ev.target;
          if (t && (t.closest && (t.closest('.ds-board-card') || t.closest('.ds-wrap-toolbar')))) return;
          if (t && (t.classList && (t.classList.contains('ds-edge-hit') || t.classList.contains('ds-edge-settings-btn')))) return;
          if (t instanceof SVGElement) {
            // clicks on SVG background can pan; clicks on edge-hit are handled above.
          }
          isPanning = true;
          wrap.classList.add('is-panning');
          pan0 = { x: ev.clientX, y: ev.clientY, sl: wrap.scrollLeft, st: wrap.scrollTop };
          ev.preventDefault();
        });
        window.addEventListener('mousemove', (ev) => {
          if (!isPanning) return;
          const dx = ev.clientX - pan0.x;
          const dy = ev.clientY - pan0.y;
          wrap.scrollLeft = pan0.sl - dx;
          wrap.scrollTop = pan0.st - dy;
        }, { passive: true });
        window.addEventListener('mouseup', () => {
          if (!isPanning) return;
          isPanning = false;
          wrap.classList.remove('is-panning');
        });

        // --- Reorder support ---
        function applyReorderFromDom() {
          const ids = Array.from(list.querySelectorAll('.ds-board-card')).map(el => Number(el.getAttribute('data-idx')));
          setCmd('reorder', null, null, ids.join(','));
        }

        list.addEventListener('drop', (ev) => {
          ev.preventDefault();
          if (!dragging) return;
          applyReorderFromDom();
        });

        list.querySelectorAll('.ds-board-card').forEach(card => {
          card.setAttribute('draggable', 'true');

          // action buttons
          const editBtn = card.querySelector('[data-act="edit"]');
          if (editBtn) {
            editBtn.addEventListener('click', (ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              const idx = card.getAttribute('data-idx');
              setCmd('edit_node', idx);
            });
          }
          const linkBtn = card.querySelector('[data-act="link"]');
          if (linkBtn) {
            linkBtn.addEventListener('click', (ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              const idx = card.getAttribute('data-idx');
              setCmd('add_edge_prefill', idx);
            });
          }

          card.addEventListener('click', () => {
            list.querySelectorAll('.ds-board-card').forEach(x => x.classList.remove('is-active'));
            card.classList.add('is-active');
          });

          card.addEventListener('dblclick', (ev) => {
            if (isDraggingFlag) { isDraggingFlag = false; return; }
            if (ev.target.closest('.ds-dur-btn') || ev.target.closest('.ds-card-actions')) return;
            const idx = card.getAttribute('data-idx');
            setCmd('edit_node', idx);
          });

          card.addEventListener('dragstart', (ev) => {
            dragging = card;
            isDraggingFlag = true;
            try { ev.dataTransfer.setData('text/plain', card.getAttribute('data-idx') || ''); } catch (e) {}
          });

          card.addEventListener('dragend', () => {
            dragging = null;
            setTimeout(() => { isDraggingFlag = false; }, 120);
            draw();
          });

          card.addEventListener('dragover', (ev) => {
            ev.preventDefault();
            if (!dragging || dragging === card) return;
            const rect = card.getBoundingClientRect();
            const before = (ev.clientX - rect.left) < rect.width / 2;
            if (before) {
              if (card.previousSibling !== dragging) list.insertBefore(dragging, card);
            } else {
              if (card.nextSibling !== dragging) list.insertBefore(dragging, card.nextSibling);
            }
            draw();
          });

          card.addEventListener('drop', (ev) => {
            ev.preventDefault();
            if (!dragging) return;
            applyReorderFromDom();
          });

          card.querySelectorAll('.ds-dur-btn').forEach(btn => {
            btn.addEventListener('click', (ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              const idx = Number(card.getAttribute('data-idx'));
              const delta = Number(btn.getAttribute('data-delta') || '0');
              if (!Number.isFinite(delta) || delta === 0) return;
              setCmd('dur', idx, delta);
            });
          });
        });

        const ro = new ResizeObserver(() => draw());
        ro.observe(list);
        window.addEventListener('resize', draw);
        setTimeout(draw, 60);
      })();
    </script>
    """

    html_str = (
        tpl.replace("__DS_UID__", uid)
        .replace("__DS_NODE_HTML__", node_html)
        .replace("__DS_UID_JSON__", json.dumps(uid))
        .replace("__DS_REFS_JSON__", refs_json)
        .replace("__DS_NODE_COUNT__", str(int(node_count)))
        .replace("__DS_REF_COUNT__", str(int(ref_count)))
        .replace("__DS_TOTAL_MIN__", str(int(total_min)))
    )

    return html_str, h


from logic_chain_editor import LogicChainEditor, LogicChainUI, _dialog_edit_node, _dialog_edit_edge, _dialog_add_node, _dialog_add_edge

# ... imports ...

class TestLogicChainUI(LogicChainUI):
    # Local command handler (more reliable than the upstream one for this test bench)
    def _handle_commands_local(self) -> None:
        """Handle commands coming from the HTML canvas via URL query params.

        Supported:
          - lc_cmd=dur&lc_idx=<node_idx>&lc_val=<delta>
          - lc_cmd=reorder&lc_order=0,2,1,...
          - lc_cmd=edit_node&lc_idx=<node_idx>
          - lc_cmd=edit_edge&lc_idx=<edge_idx>
          - lc_cmd=add_edge_prefill&lc_idx=<node_idx>
        """

        def _qp_get(key: str):
            try:
                v = st.query_params.get(key)
                # Streamlit may return list-like values in some versions.
                if isinstance(v, (list, tuple)):
                    return v[0] if v else None
                return v
            except Exception:
                qp = st.experimental_get_query_params()
                v = qp.get(key, [None])
                return v[0] if isinstance(v, list) else v

        def _qp_clear():
            try:
                st.query_params.clear()
            except Exception:
                st.experimental_set_query_params()

        cmd = _qp_get("lc_cmd")
        if not cmd:
            return

        idx_raw = _qp_get("lc_idx")
        val_raw = _qp_get("lc_val")
        order_raw = _qp_get("lc_order")

        handled = False

        try:
            if cmd == "dur" and idx_raw is not None and val_raw is not None:
                idx = int(idx_raw)
                delta = int(val_raw)
                if 0 <= idx < len(self.editor.nodes or []):
                    cur = _parse_duration_min(getattr(self.editor.nodes[idx], "duration", ""), 3)
                    nxt = max(1, cur + delta)
                    self.editor.nodes[idx].duration = f"{nxt}min"
                handled = True

            elif cmd == "reorder" and order_raw:
                order = [int(x) for x in str(order_raw).split(",") if str(x).strip() != ""]
                n = len(self.editor.nodes or [])
                if len(order) == n and sorted(order) == list(range(n)):
                    # Prefer a native method if available.
                    if hasattr(self.editor, "reorder_nodes") and callable(getattr(self.editor, "reorder_nodes")):
                        self.editor.reorder_nodes(order)
                    else:
                        old_nodes = list(self.editor.nodes)
                        new_nodes = [old_nodes[i] for i in order]
                        mapping = {old_i: new_i for new_i, old_i in enumerate(order)}
                        self.editor.nodes = new_nodes
                        # Remap edges (both sequential & reference) if present.
                        new_edges = []
                        for e in (self.editor.edges or []):
                            try:
                                fi = int(e.get("from"))
                                ti = int(e.get("to"))
                            except Exception:
                                continue
                            if fi in mapping and ti in mapping:
                                e2 = dict(e)
                                e2["from"] = mapping[fi]
                                e2["to"] = mapping[ti]
                                new_edges.append(e2)
                        self.editor.edges = new_edges
                handled = True

            elif cmd == "edit_node" and idx_raw is not None:
                st.session_state.trigger_edit_node_idx = int(idx_raw)
                handled = True

            elif cmd == "edit_edge" and idx_raw is not None:
                st.session_state.trigger_edit_edge_idx = int(idx_raw)
                handled = True

            elif cmd == "add_edge_prefill" and idx_raw is not None:
                st.session_state.trigger_add_edge_from = int(idx_raw)
                handled = True
        finally:
            if handled:
                _qp_clear()
                st.rerun()

    def render(self) -> None:
        self._handle_commands_local()
        
        # Explicit rerun if command was handled to ensure clean state? 
        # Actually _handle_commands clears query params but doesn't rerun.
        # If we want the dialog to show immediately, we might rely on the fact that
        # st.dialog functions, when called, open the modal.
        
        st.markdown("### 🛠️ Logic Chain Editor")
        st.markdown("Use this workbench to verify interactions before deployment.")
        
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            with c1:
                if st.button("➕ Add Node", use_container_width=True):
                    _dialog_add_node(self.editor)
            with c2:
                if st.button("🔗 Add Link", use_container_width=True):
                    _dialog_add_edge(self.editor)
            with c3:
                if st.button("✨ Auto-Reference", use_container_width=True, help="Magic Links"):
                    self._recommend_edges()
        
        # Trigger Dialogs based on session state
        if "trigger_edit_node_idx" in st.session_state:
            idx = st.session_state.trigger_edit_node_idx
            del st.session_state.trigger_edit_node_idx
            _dialog_edit_node(self.editor, idx)
            
        if "trigger_edit_edge_idx" in st.session_state:
            idx = st.session_state.trigger_edit_edge_idx
            del st.session_state.trigger_edit_edge_idx
            _dialog_edit_edge(self.editor, idx)
            
        if "trigger_add_edge_from" in st.session_state:
            idx = st.session_state.trigger_add_edge_from
            del st.session_state.trigger_add_edge_from
            _dialog_add_edge(self.editor, default_from_idx=idx)

        # Render Map with LOCAL TEST RENDERER
        st.markdown('<div class="ds-lc-mapwrap-marker"></div>', unsafe_allow_html=True)
        total_min = sum(_parse_duration_min(n.duration, 3) for n in (self.editor.nodes or []))
        ref_count = sum(1 for e in (self.editor.edges or []) if str(e.get("type", "")) == "reference")
        
        # Calculate adaptive height
        # Estimate based on max lanes. This is rough but better than fixed.
        # Base height for cards ~ 200px
        # Plus space for lanes.
        # Let's use the JS-side estimated logic or just a large default.
        # Since we can't easily get JS calculation back to Python in same run, 
        # we'll use a generous default height.
        
        board_html, board_h = _render_logic_chain_board_html_test(
            self.editor.nodes,
            self.editor.edges,
            active_idx=-1, 
            node_count=len(self.editor.nodes or []),
            ref_count=int(ref_count),
            total_min=int(total_min),
        )
        components.html(board_html, height=board_h, scrolling=False)


# --- Mocking Infrastructure for "Magic Links" ---
class MockEdgesRecommender:
    def recommend(self, node_names, abstract, tools):
        # Simulate intelligent recommendation
        edges = []
        n = len(node_names)
        if n > 1:
            edges.append({"from": 0, "to": n-1, "reason": "Intro connects to Conclusion", "type": "reference"})
        if n > 2:
            edges.append({"from": 1, "to": 2, "reason": "Problem motivates Method", "type": "reference"})
        return edges

# Initialize Session State Mocks
if "edges_rec" not in st.session_state:
    st.session_state.edges_rec = MockEdgesRecommender()
if "content_tree_nodes" not in st.session_state:
    st.session_state.content_tree_nodes = [] # Mock empty tree
if "collector" not in st.session_state:
    class MockCollector:
        paper_abstract = "This is a mock abstract for testing."
    st.session_state.collector = MockCollector()

# --- Main Test App ---

# Initialize Editor State
if "test_editor" not in st.session_state:
    editor = LogicChainEditor()
    # Add some dummy nodes to start with
    editor.add_node("1. Introduction", "Background info and motivation", "2min")
    editor.add_node("2. Problem Statement", "Why existing solutions fail", "3min")
    editor.add_node("3. Methodology", "Our novel approach", "5min")
    editor.add_node("4. Experiments", "Performance evaluation", "4min")
    editor.add_node("5. Conclusion", "Summary and future work", "2min")
    
    # Add some dummy reference edges
    editor.set_edges([
        {"from": 0, "to": 2, "reason": "Background -> Method", "type": "reference"},
        {"from": 2, "to": 4, "reason": "Method -> Conclusion", "type": "reference"},
        {"from": 1, "to": 3, "reason": "Problem -> Experiments", "type": "reference"},
    ])
    
    st.session_state.test_editor = editor

editor = st.session_state.test_editor

# Render the UI Component with TEST OVERRIDE
ui = TestLogicChainUI(editor)
ui.render()

# --- Real-time State Inspector ---
with st.expander("🔍 Developer Tools & State Inspector", expanded=False):
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### Nodes (Ordered)")
        nodes_data = [
            {
                "Index": i, 
                "Name": n.name, 
                "Duration": n.duration, 
                "Description": n.description[:50] + "..." if len(n.description) > 50 else n.description
            } 
            for i, n in enumerate(editor.nodes)
        ]
        st.dataframe(nodes_data, use_container_width=True)

    with c2:
        st.markdown("#### Edges (References)")
        edges_data = [
            {
                "From": f"{e['from']} ({editor.nodes[e['from']].name})",
                "To": f"{e['to']} ({editor.nodes[e['to']].name})",
                "Reason": e.get("reason", "")
            }
            for e in editor.edges if e.get("type") == "reference" and 0 <= int(e['from']) < len(editor.nodes) and 0 <= int(e['to']) < len(editor.nodes)
        ]
        if edges_data:
            st.dataframe(edges_data, use_container_width=True)
        else:
            st.info("No reference edges defined.")

    st.caption("Note: Sequential edges are maintained automatically by the backend and are hidden from this view.")
