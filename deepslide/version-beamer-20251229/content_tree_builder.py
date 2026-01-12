import re
import os
from typing import List, Dict, Any, Optional
from chapter_node import ChapterNode
from camel.toolkits import FunctionTool

def make_tree_tools(nodes: List[ChapterNode]):
    """
    Generate tools based on pre-parsed ChapterNode tree.
    """
    
    # Create a map for quick access
    node_map = {n.node_id: n for n in nodes}
    
    # Build a simplified outline structure compatible with existing tools
    # We focus on Level 1 sections as the main indexable units
    section_nodes = [n for n in nodes if n.level == 1]
    
    # If no level 1 sections found (e.g. article class without sections), fallback to level 1 logic on whatever top nodes exist
    if not section_nodes and nodes:
        # Find root nodes
        section_nodes = [n for n in nodes if not n.parent_id]

    outline = []
    for i, node in enumerate(section_nodes):
        subs = []
        # Collect level 2 subsection titles
        for child_id in node.children_ids:
            child = node_map.get(child_id)
            if child and child.level == node.level + 1:
                subs.append(child.title)
        
        outline.append({
            "index": i,
            "title": node.title,
            "subsections": subs,
            "node": node,
            "children_ids": node.children_ids
        })

    def list_outline(**kwargs) -> str:
        """List the section and subsection structure of the paper (content tree summary). Use this to understand the overall structure."""
        lines = []
        for sec in outline:
            lines.append(f"- {sec['index']}: {sec['title']}")
            for sub in sec.get("subsections", [])[:8]:
                lines.append(f"  · {sub}")
        return "\n".join(lines) if lines else "No outline"

    def search_nodes(query: str = "", limit: int = 8, **kwargs) -> str:
        """Search for nodes in the content tree by matching title, subsections AND content. Returns matching entries."""
        q = (kwargs.get("q") or kwargs.get("query_text") or query or "").lower().strip()
        try:
            limit = int(kwargs.get("limit", limit))
        except Exception:
            pass
            
        hits = []
        for sec in outline:
            node = sec["node"]
            score = 0
            
            # Title match (High weight)
            if q in sec["title"].lower():
                score += 10
            
            # Subsection title match (Medium weight)
            for sub in sec["subsections"]:
                if q in sub.lower():
                    score += 5
            
            # Content match (Low weight, but helps find topics hidden in text)
            # Check node content
            if q in node.content.lower():
                score += 3
            
            # Check children content (Level 2)
            for child_id in sec["children_ids"]:
                child = node_map.get(child_id)
                if child and q in child.content.lower():
                    score += 2
                
            if score > 0:
                hits.append((score, f"section[{sec['index']}] {sec['title']}"))
        
        # Sort by score desc
        hits.sort(key=lambda x: x[0], reverse=True)
        
        return "\n".join([h[1] for h in hits[:limit]]) if hits else "No matches"

    def get_node(idx: int = None, **kwargs) -> str:
        """Get the title and a list of subsections for a specific section index."""
        idx_key = kwargs.get("section_index") or kwargs.get("index") or kwargs.get("idx")
        if idx is None and idx_key is not None:
            try: idx = int(idx_key)
            except: idx = None
            
        for sec in outline:
            if sec["index"] == idx:
                subs_txt = "\n".join([f"- {s}" for s in sec["subsections"][:12]])
                return f"Section[{sec['index']}] {sec['title']}\n{subs_txt}"
        return "Not found"

    def get_node_content_by_index(idx: int = None, max_chars: int = 1200, **kwargs) -> str:
        """Get the actual text content of a section by its index. Useful for reading specific parts of the paper."""
        try:
            if idx is None:
                idx = int(kwargs.get("index") or kwargs.get("idx") or -1)
            mc = int(kwargs.get("max_chars", max_chars))
        except:
            mc = max_chars
            
        for sec in outline:
            if sec["index"] == idx:
                node = sec["node"]
                # Construct content from node and its children to give a full picture
                # Since LatexParser separates content, node.content is just the intro.
                # We should probably aggregate a bit if it's short.
                
                full_txt = node.content
                if len(full_txt) < mc:
                    for child_id in node.children_ids:
                        if len(full_txt) >= mc: break
                        child = node_map.get(child_id)
                        if child:
                            full_txt += f"\n\n--- {child.title} ---\n{child.content}"
                            
                return full_txt[:mc]
        return ""

    def find_best_index(query: str = "", **kwargs) -> str:
        """Find the best matching section index for a given query string (searches titles, subsections, and content)."""
        q = (kwargs.get("q") or query or "").lower().strip()
        if not q: return ""
        
        best = None
        best_score = 0
        
        keywords = re.split(r"[\s,;，；]+", q)
        keywords = [k for k in keywords if k]
        
        for sec in outline:
            score = 0
            node = sec["node"]
            title_lower = sec["title"].lower()
            
            # Pre-fetch children content to avoid repeated lookups
            children_nodes = [node_map[cid] for cid in sec["children_ids"] if cid in node_map]
            
            for k in keywords:
                # Title
                if k in title_lower:
                    score += 10
                # Subsections
                for sub in sec["subsections"]:
                    if k in sub.lower():
                        score += 5
                # Content
                if k in node.content.lower():
                    score += 3
                # Children Content
                for child in children_nodes:
                    if k in child.content.lower():
                        score += 2
            
            if score > best_score:
                best_score = score
                best = sec
                
        return str(best["index"]) if best else ""

    return [list_outline, search_nodes, get_node, get_node_content_by_index, find_best_index]
