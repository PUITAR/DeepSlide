import re
from typing import List, Dict, Any

def _minutes_from_text(dur: Any) -> int:
    try:
        s = str(dur or "").lower().strip()
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        val = float(m.group(1)) if m else 10.0
        if any(u in s for u in ["h", "小时"]):
            val = val * 60.0
        return max(1, int(round(val)))
    except Exception:
        return 10

def build_chain_from_tree(tools: List, focus_sections: List[str], duration_text: str) -> Dict[str, Any]:
    try:
        from app import _log
    except ImportError:
        def _log(msg): pass

    by_name = {getattr(t, "__name__", f"t{i}"): t for i, t in enumerate(tools)}
    list_outline = None
    find_best_index = None
    get_node_content_by_index = None
    get_node = None
    for name, fn in by_name.items():
        if name == "list_outline":
            list_outline = fn
        elif name == "find_best_index":
            find_best_index = fn
        elif name == "get_node_content_by_index":
            get_node_content_by_index = fn
        elif name == "get_node":
            get_node = fn
    
    _log(f"TreeBuilder: focus={focus_sections}, has_tools={list(by_name.keys())}")

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    total = _minutes_from_text(duration_text)
    count = max(1, len(focus_sections or []))
    per = max(1, int(round(total / count)))
    
    missed_count = 0
    for i, sec_name in enumerate(focus_sections or []):
        idx_text = ""
        if find_best_index:
            try:
                idx_text = str(find_best_index(q=str(sec_name)))
            except Exception as e:
                _log(f"TreeBuilder: find_best_index error {e}")
                idx_text = ""
        
        idx_val = None
        try:
            if idx_text.strip():
                idx_val = int(idx_text)
        except Exception:
            idx_val = None
            
        _log(f"TreeBuilder: sec='{sec_name}' -> idx={idx_val}")

        preview = ""
        if idx_val is not None and get_node_content_by_index:
            try:
                preview = str(get_node_content_by_index(index=idx_val, max_chars=800))
            except Exception:
                preview = ""
        
        desc = ""
        if preview:
            sents = re.split(r"[\n\.。！？!?]", preview)
            sents = [x.strip() for x in sents if x.strip()]
            desc = "；".join(sents[:3])
        
        if not desc and idx_val is not None and get_node:
            try:
                info = str(get_node(index=idx_val))
                lines = [ln.strip("- ") for ln in info.split("\n") if ln.startswith("-")]
                if lines:
                    desc = "；".join(lines[:3])
            except Exception:
                pass
        
        # Fallback description if content not found
        if not desc:
            missed_count += 1
            desc = f"展示 {sec_name} 章节的核心内容"

        nodes.append({"name": str(sec_name), "description": desc, "duration": f"{per}min"})
        if i < count - 1:
            edges.append({"from": i, "to": i + 1, "reason": "", "type": "sequential"})
    
    if not nodes:
        _log("TreeBuilder: No nodes generated!")
        return None
    
    # If more than half of the sections were not matched, consider this a failure
    # and let the AI agent handle it (which has better semantic understanding).
    if missed_count > len(nodes) * 0.5:
        _log(f"TreeBuilder: Too many missed sections ({missed_count}/{len(nodes)}), falling back to AI.")
        return None
        
    return {"nodes": nodes, "edges": edges}
