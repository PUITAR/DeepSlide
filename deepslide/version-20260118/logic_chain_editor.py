import streamlit as st
from typing import List, Dict, Any, Optional
import os
import sys
import html as _html
import uuid
import streamlit.components.v1 as components
import json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if ROOT not in sys.path:
    sys.path.append(ROOT)

try:
    from .data_types import LogicNode, LogicFlow
except ImportError:
    try:
        from data_types import LogicNode, LogicFlow
    except ImportError:
        from data_types import LogicNode, LogicFlow

# Define the custom component
_component_func = components.declare_component(
    "logic_chain_editor",
    path=os.path.join(os.path.dirname(__file__), "logic_chain_component")
)

class LogicChainEditor:
    def __init__(self):
        self.nodes: List[LogicNode] = []
        self.logic_flow: Optional[LogicFlow] = None
        self.edges: List[Dict[str, Any]] = []

    def _parse_total_minutes(self, dur: Any) -> int:
        try:
            if isinstance(dur, (int, float)):
                val = float(dur)
                return max(1, int(round(val)))
            s = str(dur or "").lower().strip()
            import re
            m = re.search(r"(\d+(?:\.\d+)?)", s)
            val = float(m.group(1)) if m else 10.0
            if any(u in s for u in ["h", "小时"]):
                val = val * 60.0
            # 默认按分钟
            return max(1, int(round(val)))
        except Exception:
            return 10

    def create_from_requirements(self, req: Dict[str, Any]) -> LogicFlow:
        nodes: List[LogicNode] = []
        focus = req.get("focus_sections") or []
        total_minutes = self._parse_total_minutes(req.get("duration"))
        count = max(1, len(focus))
        per = max(1, int(round(total_minutes / count)))
        base = [
            ("Introduction", "Background & Motivation", "2min"),
            ("Method", "Core Technical Approach", "4min"),
            ("Experiments", "Design & Evaluation", "2min"),
            ("Results", "Key Findings & Comparison", "3min"),
            ("Conclusion", "Contributions & Future Work", "2min"),
        ]
        if isinstance(focus, list) and focus:
            for s in focus:
                nodes.append(LogicNode(name=str(s), description="Key Elaboration", duration=f"{per}min"))
        else:
            for n, d, t in base:
                nodes.append(LogicNode(name=n, description=d, duration=t))
        self.nodes = nodes
        self.logic_flow = LogicFlow(nodes=nodes)
        self._reset_sequential_edges()
        return self.logic_flow

    def set_from_chain_json(self, data: Dict[str, Any], total_minutes: int = 10) -> None:
        self.nodes = []
        nodes_raw = data.get("nodes") or []
        for n in nodes_raw:
            name = str(n.get("role") or "Node")
            text = str(n.get("text") or "")
            # Prefer 'description' field if available, otherwise use text or default
            desc = str(n.get("description") or text[:200] or "Key Elaboration")
            ratio = float(n.get("duration_ratio") or 0.2)
            minutes = max(1, int(round(ratio * total_minutes)))
            
            self.nodes.append(LogicNode(name=name, description=desc, duration=f"{minutes}min"))
        self.logic_flow = LogicFlow(nodes=self.nodes)
        self._reset_sequential_edges()

    def add_node(self, name: str, description: str, duration: str, position: Optional[int] = None) -> None:
        node = LogicNode(name=name, description=description, duration=duration)
        if position is None or position >= len(self.nodes):
            self.nodes.append(node)
        else:
            self.nodes.insert(position, node)
        self.logic_flow = LogicFlow(nodes=self.nodes)
        self._reset_sequential_edges()

    def remove_node(self, index: int) -> bool:
        if 0 <= index < len(self.nodes):
            self.nodes.pop(index)
            self.logic_flow = LogicFlow(nodes=self.nodes)
            self._reset_sequential_edges()
            # Also remove edges involving this node
            self.edges = [e for e in self.edges if int(e.get("from")) != index and int(e.get("to")) != index]
            self.edges = [e for e in self.edges if int(e.get("from")) < len(self.nodes) and int(e.get("to")) < len(self.nodes)]
            return True
        return False

    def move_node(self, from_index: int, to_index: int) -> bool:
        if 0 <= from_index < len(self.nodes) and 0 <= to_index < len(self.nodes):
            node = self.nodes.pop(from_index)
            self.nodes.insert(to_index, node)
            self.logic_flow = LogicFlow(nodes=self.nodes)
            self._reset_sequential_edges()
            return True
        return False

    def update_node(self, index: int, name: Optional[str] = None, description: Optional[str] = None, duration: Optional[str] = None) -> bool:
        if 0 <= index < len(self.nodes):
            node = self.nodes[index]
            if name is not None:
                node.name = name
            if description is not None:
                node.description = description
            if duration is not None:
                node.duration = duration
            self.logic_flow = LogicFlow(nodes=self.nodes)
            return True
        return False

    def duplicate_node(self, index: int, position: Optional[int] = None) -> bool:
        if not (0 <= index < len(self.nodes)):
            return False
        src = self.nodes[index]
        node = LogicNode(name=str(src.name), description=str(src.description), duration=str(src.duration))
        insert_at = index + 1 if position is None else int(position)
        insert_at = max(0, min(len(self.nodes), insert_at))
        self.nodes.insert(insert_at, node)
        self.logic_flow = LogicFlow(nodes=self.nodes)
        self._reset_sequential_edges()
        return True

    def clear_reference_edges(self) -> None:
        self.edges = [e for e in (self.edges or []) if str(e.get("type", "sequential")) == "sequential"]

    def reorder_nodes(self, order: List[int]) -> bool:
        if not self.nodes:
            return False
        try:
            order = [int(x) for x in order]
        except Exception:
            return False
        n = len(self.nodes)
        if len(order) != n:
            return False
        if sorted(order) != list(range(n)):
            return False

        old_nodes = list(self.nodes)
        old_refs = [e for e in (self.edges or []) if str(e.get("type", "sequential")) == "reference"]
        new_nodes = [old_nodes[i] for i in order]
        remap = {old_i: new_i for new_i, old_i in enumerate(order)}

        self.nodes = new_nodes
        self.logic_flow = LogicFlow(nodes=self.nodes)
        self._reset_sequential_edges()

        remapped_refs: List[Dict[str, Any]] = []
        for e in old_refs:
            try:
                fi = remap[int(e.get("from"))]
                ti = remap[int(e.get("to"))]
            except Exception:
                continue
            remapped_refs.append(
                {
                    "from": int(fi),
                    "to": int(ti),
                    "reason": str(e.get("reason", "")),
                    "type": "reference",
                }
            )
        if remapped_refs:
            self.set_edges(remapped_refs)
        return True

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        nodes: List[LogicNode] = []
        nodes_raw = (data or {}).get("nodes") or []
        for n in nodes_raw:
            name = str((n or {}).get("name", "")).strip() or "Node"
            description = str((n or {}).get("description", "")).strip() or "Key Elaboration"
            duration = str((n or {}).get("duration", "")).strip() or "3min"
            node = LogicNode(name=name, description=description, duration=duration)
            nodes.append(node)
        self.nodes = nodes
        self.logic_flow = LogicFlow(nodes=self.nodes)

        self._reset_sequential_edges()
        edges_raw = (data or {}).get("edges") or []
        refs: List[Dict[str, Any]] = []
        for e in edges_raw:
            if str((e or {}).get("type", "sequential")) != "reference":
                continue
            refs.append(
                {
                    "from": (e or {}).get("from"),
                    "to": (e or {}).get("to"),
                    "reason": (e or {}).get("reason", ""),
                    "type": "reference",
                }
            )
        if refs:
            self.set_edges(refs)

    def _reset_sequential_edges(self) -> None:
        new_edges = []
        for i in range(len(self.nodes) - 1):
            new_edges.append({"from": i, "to": i + 1, "reason": "", "type": "sequential"})
        
        self.edges = new_edges

    def set_edges(self, edges: List[Dict[str, Any]]) -> None:
        n = len(self.nodes)
        
        # Keep existing sequential edges
        base = [e for e in self.edges if e.get("type") == "sequential"]
        
        added: List[Dict[str, Any]] = []
        for e in edges:
            try:
                fi = int(e.get("from", -1))
                ti = int(e.get("to", -1))
            except Exception:
                continue
            rs = str(e.get("reason", ""))
            tp = str(e.get("type", "reference"))
            
            # Add if valid indices
            if 0 <= fi < n and 0 <= ti < n:
                # Check for duplicate
                if any((x.get("from") == fi and x.get("to") == ti and x.get("type") == tp) for x in base + added):
                    continue
                added.append({"from": fi, "to": ti, "reason": rs, "type": tp})
        
        if added:
            base.extend(added)
            self.edges = base

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [
                {"name": n.name, "description": n.description, "duration": n.duration}
                for n in self.nodes
            ],
            "edges": [
                {"from": e["from"], "to": e["to"], "reason": e.get("reason", ""), "type": e.get("type", "sequential")}
                for e in self.edges
            ],
        }


# --- Dialogs ---

@st.dialog("Edit Logic Node")
def _dialog_edit_node(editor: LogicChainEditor, idx: int):
    if not (0 <= idx < len(editor.nodes)):
        st.error("Node not found")
        return

    node = editor.nodes[idx]
    
    with st.form(f"form_edit_node_{idx}"):
        name = st.text_input("Name", value=node.name)
        
        dmin = _parse_duration_min(str(node.duration), 5)
        new_d = st.number_input("Duration (min)", min_value=1, max_value=120, value=int(dmin))
        
        desc = st.text_area("Description", value=node.description, height=140)
        
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.form_submit_button("Save Changes", type="primary"):
                editor.update_node(idx, name=name, description=desc, duration=f"{int(new_d)}min")
                st.rerun()
        with c2:
            if st.form_submit_button("Delete Node"):
                editor.remove_node(idx)
                st.rerun()

@st.dialog("Edit Reference Edge")
def _dialog_edit_edge(editor: LogicChainEditor, edge_idx: int):
    if not (0 <= edge_idx < len(editor.edges)):
        st.error("Edge not found")
        return
        
    edge = editor.edges[edge_idx]
    f = int(edge.get("from", -1))
    t = int(edge.get("to", -1))
    fname = editor.nodes[f].name if 0 <= f < len(editor.nodes) else "?"
    tname = editor.nodes[t].name if 0 <= t < len(editor.nodes) else "?"
    
    st.write(f"**{fname}** → **{tname}**")
    
    with st.form(f"form_edit_edge_{edge_idx}"):
        reason = st.text_input("Relationship Reason", value=edge.get("reason", ""))
        
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.form_submit_button("Update", type="primary"):
                edge["reason"] = reason
                st.rerun()
        with c2:
            if st.form_submit_button("Delete Link"):
                editor.edges.pop(edge_idx)
                st.rerun()

@st.dialog("Add Reference Edge")
def _dialog_add_edge(editor: LogicChainEditor, default_from_idx: Optional[int] = None):
    nodes = editor.nodes
    if len(nodes) < 2:
        st.info("Need at least 2 nodes to add an edge.")
        return

    opts = [f"{i}. {n.name}" for i, n in enumerate(nodes)]
    
    # Determine default indices
    def_f = 0
    def_t = 1
    if default_from_idx is not None and 0 <= default_from_idx < len(nodes):
        def_f = default_from_idx
        def_t = (def_f + 1) % len(nodes)
        
    with st.form("form_add_edge"):
        c1, c2 = st.columns(2)
        with c1:
            f_idx = st.selectbox("From", options=range(len(nodes)), format_func=lambda x: opts[x], index=def_f, key="add_edge_from")
        with c2:
            t_idx = st.selectbox("To", options=range(len(nodes)), format_func=lambda x: opts[x], index=def_t, key="add_edge_to")
            
        reason = st.text_input("Relationship Reason")
        
        if st.form_submit_button("Add Connection", type="primary"):
            if f_idx == t_idx:
                st.error("Cannot connect node to itself")
            else:
                editor.set_edges([{"from": f_idx, "to": t_idx, "reason": reason, "type": "reference"}])
                st.rerun()

@st.dialog("Add Node")
def _dialog_add_node(editor: LogicChainEditor):
    with st.form("form_add_new_node"):
        name = st.text_input("Name")
        desc = st.text_area("Description")
        dur = st.number_input("Duration (min)", min_value=1, value=5)
        
        if st.form_submit_button("Add Node", type="primary"):
            if name.strip():
                editor.add_node(name.strip(), desc.strip(), f"{dur}min")
                st.rerun()
            else:
                st.error("Name is required")

class LogicChainUI:
    def __init__(self, editor: LogicChainEditor):
        self.editor = editor

    def render(self) -> None:
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

        if "trigger_add_node" in st.session_state:
            del st.session_state.trigger_add_node
            _dialog_add_node(self.editor)

        if "trigger_add_edge" in st.session_state:
            del st.session_state.trigger_add_edge
            _dialog_add_edge(self.editor)

        # Prepare Data
        total_min = sum(_parse_duration_min(n.duration, 3) for n in (self.editor.nodes or []))
        ref_count = sum(1 for e in (self.editor.edges or []) if str(e.get("type", "")) == "reference")
        
        data = _prepare_board_data(
            self.editor.nodes,
            self.editor.edges,
            active_idx=-1, 
            node_count=len(self.editor.nodes or []),
            ref_count=int(ref_count),
            total_min=int(total_min),
        )
        
        # Render Component
        event = _component_func(key="logic_chain_board", default=None, **data)
        
        # Handle Event
        if event:
            self._handle_event(event)
            
    def _handle_event(self, event: Dict[str, Any]) -> None:
        nonce = event.get("nonce")
        if st.session_state.get("last_lc_nonce") == nonce:
            return
        st.session_state["last_lc_nonce"] = nonce

        cmd = event.get("cmd")
        idx_raw = event.get("idx")
        val_raw = event.get("val")
        order_raw = event.get("order")

        if not cmd:
            return

        handled = False
        try:
            if cmd == "dur" and idx_raw is not None and val_raw is not None:
                idx = int(idx_raw)
                delta = int(val_raw)
                if 0 <= idx < len(self.editor.nodes or []):
                    cur = _parse_duration_min(getattr(self.editor.nodes[idx], "duration", ""), 3)
                    nxt = max(1, cur + delta)
                    self.editor.update_node(idx, duration=f"{nxt}min")
                    st.toast(f"Duration updated to {nxt}min")
                handled = True

            elif cmd == "reorder" and order_raw:
                order = [int(x) for x in str(order_raw).split(",") if str(x).strip() != ""]
                if self.editor.reorder_nodes(order):
                    handled = True

            elif cmd == "edit_node" and idx_raw is not None:
                st.session_state.trigger_edit_node_idx = int(idx_raw)
                handled = True

            elif cmd == "edit_edge" and idx_raw is not None:
                st.session_state.trigger_edit_edge_idx = int(idx_raw)
                handled = True

            elif cmd == "delete_edge" and idx_raw is not None:
                idx = int(idx_raw)
                if 0 <= idx < len(self.editor.edges):
                    self.editor.edges.pop(idx)
                    st.toast("Edge deleted")
                handled = True

            elif cmd == "add_edge_prefill" and idx_raw is not None:
                st.session_state.trigger_add_edge_from = int(idx_raw)
                handled = True

            elif cmd == "add_node":
                st.session_state.trigger_add_node = True
                handled = True
            
            elif cmd == "add_edge":
                st.session_state.trigger_add_edge = True
                handled = True
            
            elif cmd == "auto_connect":
                self._recommend_edges()
                handled = True
        except Exception as e:
            st.error(f"Interaction error: {e}")
        finally:
            if handled:
                st.rerun()

    def _recommend_edges(self):
        try:
            from content_tree_builder import make_tree_tools
            from core import _wrap_tools

            tools = make_tree_tools(st.session_state.get("content_tree_nodes", []))
            edges_rec = st.session_state.get("edges_rec")
            edges = []
            if edges_rec and getattr(edges_rec, "model", None) is not None:
                edges = edges_rec.recommend(
                    [n.name for n in self.editor.nodes],
                    st.session_state.collector.paper_abstract,
                    _wrap_tools(tools),
                ) or []
            
            if not edges:
                # Fallback
                n = len(self.editor.nodes)
                if n >= 3:
                     edges = [{"from": i, "to": i+2, "reason": "Related"} for i in range(n-2)]

            self.editor.clear_reference_edges()
            if edges:
                self.editor.set_edges(edges)
                st.toast(f"Added {len(edges)} reference edges")
            else:
                st.toast("No recommendations found")
            st.rerun()
        except Exception as e:
            st.error(f"Recommend failed: {e}")


def _parse_duration_min(s: str, default_val: int = 5) -> int:
    import re
    try:
        m = re.search(r"(\d+)", str(s or ""))
        if m:
            return max(1, int(m.group(1)))
    except Exception:
        return default_val
    return default_val


def _prepare_board_data(
    nodes,
    edges,
    active_idx: int,
    node_count: int,
    ref_count: int,
    total_min: int,
):
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
            + "<button class='ds-act-btn ds-settings-btn' title='Settings'>⚙</button>"
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

    return {
        "node_html": node_html,
        "refs_json": refs_json,
        "node_count": node_count,
        "ref_count": ref_count,
        "total_min": total_min,
    }
