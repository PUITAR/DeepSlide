import streamlit as st
from typing import List, Dict, Any, Optional
import os
import sys

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

            print(f"name: {name}, desc: {desc}, ratio: {ratio}, minutes: {minutes}")
            
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
            return True
        return False

    def _reset_sequential_edges(self) -> None:
        # Only create sequential edges.
        # Clear existing edges but preserve user-added reference edges? 
        # Actually, if we reset, we usually mean to rebuild the backbone.
        # But per user request: "Initial state should have 0 reference edges. Sequential edges are n-1."
        # This method is called when nodes change structure, so rebuilding sequential backbone is correct.
        
        # Filter out existing reference edges if we want to preserve them?
        # The prompt says: "When clicking 'p' (Recommend Edges), ONLY THEN consider generating reference edges."
        # "Initial state reference edges should be 0."
        # So it's safe to just rebuild sequential edges here.
        
        new_edges = []
        for i in range(len(self.nodes) - 1):
            new_edges.append({"from": i, "to": i + 1, "reason": "", "type": "sequential"})
        
        # If we want to keep existing reference edges, we'd append them here.
        # But usually node changes invalidate indices, so clearing is safer.
        self.edges = new_edges

    def set_edges(self, edges: List[Dict[str, Any]]) -> None:
        # This method is used by the recommender to ADD reference edges.
        # It should NOT overwrite the sequential backbone.
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

class LogicChainUI:
    def __init__(self, editor: LogicChainEditor):
        self.editor = editor

    def render(self) -> None:
        st.subheader("Editor")
        for i, node in enumerate(self.editor.nodes):
            # Use node.id for stable keys across reorders/deletions
            # Fallback to index if id is missing (though it shouldn't be with new data_types)
            nid = getattr(node, "id", str(i))
            
            with st.expander(f"Node {i+1}: {node.name}"):
                with st.form(f"form_node_{nid}", clear_on_submit=False):
                    name = st.text_input("Name", node.name, key=f"name_{nid}")
                    desc = st.text_area("Description", node.description, key=f"desc_{nid}")
                    dur = st.text_input("Duration", node.duration, key=f"dur_{nid}")
                    submitted = st.form_submit_button("Save Changes")
                if submitted:
                    self.editor.update_node(i, name=name, description=desc, duration=dur)
                    st.success("Saved")
                    st.rerun()
                cols = st.columns(3)
                with cols[0]:
                    if st.button("Move Up", key=f"up_{nid}") and i > 0:
                        self.editor.move_node(i, i - 1)
                        st.rerun()
                with cols[1]:
                    if st.button("Move Down", key=f"down_{nid}") and i < len(self.editor.nodes) - 1:
                        self.editor.move_node(i, i + 1)
                        st.rerun()
                with cols[2]:
                    if st.button("Delete", key=f"del_{nid}"):
                        self.editor.remove_node(i)
                        st.rerun()
        # st.divider()
        with st.expander("Add Logic Node", expanded=False):
            with st.form("form_add_node", clear_on_submit=True):
                name = st.text_input("New Name", "")
                desc = st.text_area("New Description", "")
                dur = st.text_input("New Duration", "1min")
                add_ok = st.form_submit_button("Add Node")
            if add_ok and name.strip():
                self.editor.add_node(name=name.strip(), description=desc.strip(), duration=dur.strip())
                st.success("Added")
                st.rerun()
        # st.divider()
        with st.expander("Edit Reference Edges", expanded=False):
            # Display existing reference edges
            ref_edges = [e for e in self.editor.edges if e.get("type") == "reference"]
            if not ref_edges:
                st.info("No reference edges yet. Use 'Recommend Reference Edges' or add manually.")
            
            for j, e in enumerate(self.editor.edges):
                if e.get("type") != "reference":
                    continue
                
                # Generate a unique key for the edge based on its content to avoid index shifts
                # Fallback to j if needed, but combining from/to is better
                edge_key = f"edge_{e['from']}_{e['to']}_{j}"
                
                c1, c2, c3, c4 = st.columns([1, 1, 3, 1])
                with c1:
                    # from/to indices are tied to node list
                    # Use safe access in case index is out of bounds (though shouldn't happen with current logic)
                    fname = self.editor.nodes[int(e['from'])].name if 0 <= int(e['from']) < len(self.editor.nodes) else "Unknown"
                    st.text(f"From: {fname} ({e['from']})")
                with c2:
                    tname = self.editor.nodes[int(e['to'])].name if 0 <= int(e['to']) < len(self.editor.nodes) else "Unknown"
                    st.text(f"To: {tname} ({e['to']})")
                with c3:
                    reason = st.text_input(f"Reason", e.get("reason", ""), key=f"reason_{edge_key}", label_visibility="collapsed")
                with c4:
                    if st.button("Delete", key=f"del_{edge_key}"):
                        self.editor.edges.remove(e)
                        st.rerun()
                    elif reason != e.get("reason", ""):
                        e["reason"] = reason
                        st.success("Updated")
            
            st.markdown("---")
            st.caption("Manually Add Reference Edge")
            cadd1, cadd2, cadd3 = st.columns([2, 2, 3])
            with cadd1:
                # Selectbox for from node
                opts = [f"{i}. {n.name}" for i, n in enumerate(self.editor.nodes)]
                f_idx = st.selectbox("From Node", options=range(len(opts)), format_func=lambda x: opts[x], key="new_ref_from")
            with cadd2:
                t_idx = st.selectbox("To Node", options=range(len(opts)), format_func=lambda x: opts[x], key="new_ref_to")
            with cadd3:
                new_reason = st.text_input("Relation Reason", key="new_ref_reason")
            
            if st.button("Add Reference Edge"):
                if f_idx == t_idx:
                    st.error("Source and Target cannot be the same")
                else:
                    self.editor.set_edges([{"from": f_idx, "to": t_idx, "reason": new_reason, "type": "reference"}])
                    st.success("Added")
                    st.rerun()

        # st.divider()
        # Visualize with different styles for edges
        st.subheader("Visualization")
        dot = "digraph G {\nrankdir=LR;\nnode [shape=box, style=rounded];\n"
        for i, node in enumerate(self.editor.nodes):
            label = f"{node.name}\\n{node.duration}"
            dot += f"N{i} [label=\"{label}\"];\n"
        
        for e in self.editor.edges:
            fi = int(e["from"]) if str(e.get("from")).isdigit() else 0
            ti = int(e["to"]) if str(e.get("to")).isdigit() else 0
            etype = e.get("type", "sequential")
            
            style_attr = ""
            if etype == "reference":
                # Ensure dashed style for reference edges
                style_attr = " [style=dashed, color=gray, constraint=false]"
            else:
                style_attr = " [style=solid, color=black]"
                
            dot += f"N{fi} -> N{ti}{style_attr};\n"
            
        dot += "}\n"
        st.graphviz_chart(dot)
