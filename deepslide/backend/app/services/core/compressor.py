import os
import logging
import math
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional, Callable
import requests
import sys
from unittest.mock import MagicMock

# Hack to bypass missing 'unstructured' dependency in camel
sys.modules["unstructured"] = MagicMock()
sys.modules["unstructured.documents"] = MagicMock()
sys.modules["unstructured.documents.elements"] = MagicMock()

from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool
from app.core.model_config import build_model_config
from app.core.agent_model_env import resolve_text_llm_env

from .content import Content
from .frame import Frame
from .section import Section
from .spection import Spection
from .chapter_node import ChapterNode
from .data_types import LogicNode, LogicFlow

import re

logger = logging.getLogger(__name__)


def _preview_text(value: Any, limit: int = 200) -> str:
    try:
        s = str(value)
    except Exception:
        return "<unprintable>"
    return s if len(s) <= limit else s[:limit] + "..."

def _strip_tex_commands(s: str) -> str:
    t = str(s or "")
    t = re.sub(r"%.*$", " ", t, flags=re.MULTILINE)
    t = re.sub(r"\\begin\{[^\}]+\}(\[[^\]]*\])?", " ", t)
    t = re.sub(r"\\end\{[^\}]+\}", " ", t)
    t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?(\{[^\}]*\})?", " ", t)
    t = re.sub(r"[\{\}]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _extract_media_blocks(tex: str, limit: int = 12) -> List[Dict[str, Any]]:
    s = str(tex or "")
    blocks: List[Dict[str, Any]] = []
    occupied: List[Tuple[int, int]] = []

    def _in_occupied(pos: int) -> bool:
        for a, b in occupied:
            if a <= pos < b:
                return True
        return False

    def _add(kind: str, latex: str):
        if not latex or not latex.strip():
            return
        caption = ""
        label = ""
        m = re.search(r"\\caption\{([\s\S]*?)\}", latex)
        if m:
            caption = _strip_tex_commands(m.group(1))[:180]
        m2 = re.search(r"\\label\{([\s\S]*?)\}", latex)
        if m2:
            label = _strip_tex_commands(m2.group(1))[:120]
        imgs = re.findall(r"\\includegraphics\*?(?:\[[^\]]*\])?\{([^\}]+)\}", latex)
        imgs = [str(x).strip() for x in imgs if str(x).strip()]
        blocks.append(
            {
                "kind": kind,
                "caption": caption,
                "label": label,
                "images": imgs[:4],
                "latex": latex.strip()[:min(len(latex), 4000)],
            }
        )

    for m in re.finditer(r"\\begin\{figure\*?\}[\s\S]*?\\end\{figure\*?\}", s, flags=re.IGNORECASE):
        occupied.append((m.start(), m.end()))
        _add("figure", m.group(0))
        if len(blocks) >= limit:
            return blocks[:limit]

    for m in re.finditer(r"\\begin\{table\*?\}[\s\S]*?\\end\{table\*?\}", s, flags=re.IGNORECASE):
        occupied.append((m.start(), m.end()))
        _add("table", m.group(0))
        if len(blocks) >= limit:
            return blocks[:limit]

    for m in re.finditer(r"\\begin\{tabular\*?\}[\s\S]*?\\end\{tabular\*?\}", s, flags=re.IGNORECASE):
        if _in_occupied(m.start()):
            continue
        _add("tabular", m.group(0))
        if len(blocks) >= limit:
            return blocks[:limit]

    for m in re.finditer(r"\\includegraphics\*?(?:\[[^\]]*\])?\{[^\}]+\}", s):
        if _in_occupied(m.start()):
            continue
        _add("includegraphics", m.group(0))
        if len(blocks) >= limit:
            return blocks[:limit]

    return blocks[:limit]

def _normalize_path_like(p: str) -> str:
    s = str(p or "").strip().strip('"').strip("'")
    s = s.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    if s.startswith("/"):
        s = s[1:]
    s = re.sub(r"/{2,}", "/", s)
    return s

def _split_basename_noext(p: str) -> Tuple[str, str]:
    bn = os.path.basename(str(p or ""))
    root, ext = os.path.splitext(bn)
    return root.lower(), ext.lower()

def _resolve_image_ref(ref: str, image_list: List[str]) -> Tuple[str, List[str]]:
    """
    Resolve an \\includegraphics{...} ref to a path existing in image_list.
    Returns (chosen_path_or_empty, candidates).
    """
    norm_ref = _normalize_path_like(ref)
    if not norm_ref or norm_ref.startswith(("http://", "https://", "data:")):
        return "", []

    norm_images = [(_normalize_path_like(p), p) for p in (image_list or [])]
    norm_to_orig = {}
    for n, o in norm_images:
        norm_to_orig.setdefault(n, o)

    if norm_ref in norm_to_orig:
        return norm_to_orig[norm_ref], [norm_to_orig[norm_ref]]

    cand = []
    for n, o in norm_images:
        if n.endswith("/" + norm_ref) or n == norm_ref:
            cand.append(o)
    if len(cand) == 1:
        return cand[0], cand

    ref_root, ref_ext = _split_basename_noext(norm_ref)
    if ref_root:
        for n, o in norm_images:
            bn_root, bn_ext = _split_basename_noext(n)
            if bn_root != ref_root:
                continue
            if ref_ext and bn_ext and bn_ext != ref_ext:
                continue
            cand.append(o)

    cand = [c for c in cand if c]
    if not cand:
        return "", []
    cand = sorted(set(cand))
    if len(cand) == 1:
        return cand[0], cand

    ref_norm = norm_ref
    ref_base = os.path.basename(ref_norm)
    ref_dir = os.path.dirname(ref_norm).strip("/")
    ref_root, _ = _split_basename_noext(ref_norm)
    ref_dir_parts = [p for p in ref_dir.split("/") if p]

    scored: List[Tuple[int, int, str]] = []
    for c in cand:
        c_norm = _normalize_path_like(c)
        c_base = os.path.basename(c_norm)
        c_root, _ = _split_basename_noext(c_norm)
        score = 0
        if c_norm == ref_norm:
            score += 1000
        if c_norm.endswith("/" + ref_norm) or (ref_dir and c_norm.endswith(ref_dir + "/" + c_base)):
            score += 300
        if ref_dir and ("/" + ref_dir + "/") in ("/" + c_norm + "/"):
            score += 120
        for part in ref_dir_parts:
            if part and ("/" + part + "/") in ("/" + c_norm + "/"):
                score += 15
        if c_base == ref_base and ref_base:
            score += 40
        if ref_root and c_root == ref_root:
            score += 30
        scored.append((score, len(c_norm), c))

    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    chosen = scored[0][2]
    return chosen, cand

def _rewrite_includegraphics_paths(latex: str, image_list: List[str]) -> Tuple[str, List[Tuple[str, str]]]:
    s = str(latex or "")
    changes: List[Tuple[str, str]] = []

    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        path = m.group(2) or ""
        suffix = m.group(3)
        chosen, _ = _resolve_image_ref(path, image_list)
        if chosen and chosen != path:
            changes.append((path, chosen))
            return prefix + chosen + suffix
        return m.group(0)

    out = re.sub(r"(\\includegraphics\*?(?:\[[^\]]*\])?\{)([^\}]+)(\})", repl, s)
    return out, changes


def _normalize_graphics_sizing(latex: str) -> str:
    s = str(latex or "")

    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        opts = m.group(2) or ""
        path = m.group(3) or ""
        if not opts:
            return prefix + "[width=0.9\\linewidth]" + "{" + path + "}"
        if "width" in opts:
            m_width = re.search(r"width\s*=\s*([0-9.]+)\\linewidth", opts)
            if m_width:
                try:
                    val = float(m_width.group(1))
                except Exception:
                    val = 1.0
                if val > 0.98:
                    new_opts = re.sub(r"width\s*=\s*[0-9.]+\\linewidth", "width=0.95\\linewidth", opts)
                    return prefix + new_opts + "{" + path + "}"
            elif re.search(r"width\s*=\s*\\linewidth", opts):
                new_opts = re.sub(r"width\s*=\s*\\linewidth", "width=0.95\\linewidth", opts)
                return prefix + new_opts + "{" + path + "}"
        else:
            opts_clean = opts.rstrip("]")
            opts_clean += ("," if opts_clean.strip() else "") + "width=0.9\\linewidth"
            return prefix + opts_clean + "]" + "{" + path + "}"
        return m.group(0)

    out = re.sub(r"(\\includegraphics\*?)(\[[^\]]*\])?\{([^\}]+)\}", repl, s)
    return out


class _BM25TreeRetriever:
    def __init__(self, nodes: List[ChapterNode]):
        self.nodes = list(nodes or [])
        self.node_ids: List[str] = []
        self.docs_tokens: List[List[str]] = []
        self.doc_lens: List[int] = []
        self.term_df: Dict[str, int] = {}
        self.parent: Dict[str, Optional[str]] = {}
        self.children: Dict[str, List[str]] = {}
        self.depth: Dict[str, int] = {}
        self.k1 = 1.5
        self.b = 0.75
        self._build_tree()
        self._build_corpus()


    def _build_tree(self) -> None:
        for n in self.nodes:
            nid = n.node_id
            pid = n.parent_id
            self.parent[nid] = pid
            if pid:
                self.children.setdefault(pid, []).append(nid)
            if nid not in self.children:
                self.children[nid] = []
        roots = [n.node_id for n in self.nodes if not self.parent.get(n.node_id)]
        queue: List[Tuple[str, int]] = []
        if roots:
            for rid in roots:
                queue.append((rid, 0))
        else:
            for n in self.nodes:
                queue.append((n.node_id, 0))
        while queue:
            nid, d = queue.pop(0)
            if nid in self.depth and self.depth[nid] <= d:
                continue
            self.depth[nid] = d
            for cid in self.children.get(nid, []):
                queue.append((cid, d + 1))
                

    def _tokenize(self, text: str) -> List[str]:
        s = _strip_tex_commands(text or "").lower()
        tokens: List[str] = []
        for ch in s:
            if "\u4e00" <= ch <= "\u9fff":
                tokens.append(ch)
        words = re.findall(r"[A-Za-z0-9_]+", s)
        tokens.extend(words)
        return tokens

    def _build_corpus(self) -> None:
        docs: List[List[str]] = []
        node_ids: List[str] = []
        for n in self.nodes:
            parts = [n.title or "", n.summary or ""]
            content = getattr(n, "content", "") or ""
            if content:
                if len(content) > 8192:
                    content = content[:8192]
                parts.append(content)
            text = "\n".join(parts)
            tokens = self._tokenize(text)
            if not tokens:
                continue
            docs.append(tokens)
            node_ids.append(n.node_id)
        self.docs_tokens = docs
        self.node_ids = node_ids
        self.doc_lens = [len(toks) for toks in self.docs_tokens]
        if not self.docs_tokens:
            return
        df: Dict[str, int] = {}
        for toks in self.docs_tokens:
            seen = set(toks)
            for term in seen:
                df[term] = df.get(term, 0) + 1
        self.term_df = df

    def _infer_mode(self, query: str) -> str:
        toks = self._tokenize(query)
        if not toks:
            return "default"
        if len(toks) <= 4:
            return "overview"
        return "detail"

    def search(self, query: str, limit: int = 5) -> List[Tuple[ChapterNode, float]]:
        if not self.docs_tokens or not self.node_ids:
            return []
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []
        mode = self._infer_mode(query)
        n_docs = len(self.docs_tokens)
        avgdl = sum(self.doc_lens) / float(n_docs) if n_docs > 0 else 0.0
        id_to_index: Dict[str, int] = {nid: i for i, nid in enumerate(self.node_ids)}
        base_scores: List[float] = [0.0] * n_docs
        for i, toks in enumerate(self.docs_tokens):
            tf = Counter(toks)
            doc_len = self.doc_lens[i]
            score = 0.0
            for term in q_tokens:
                df = self.term_df.get(term)
                if not df:
                    continue
                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                denom = freq + self.k1 * (1.0 - self.b + self.b * (doc_len / (avgdl or 1.0)))
                score += idf * freq * (self.k1 + 1.0) / denom
            base_scores[i] = score
        child_sum: Dict[str, float] = {}
        for nid, children in self.children.items():
            s = 0.0
            for cid in children:
                idx = id_to_index.get(cid)
                if idx is None:
                    continue
                s += base_scores[idx]
            child_sum[nid] = s
        alpha = 0.4
        beta = 0.2
        results: List[Tuple[ChapterNode, float]] = []
        node_by_id: Dict[str, ChapterNode] = {n.node_id: n for n in self.nodes}
        for nid in self.node_ids:
            idx = id_to_index[nid]
            score = base_scores[idx]
            parent_id = self.parent.get(nid)
            parent_score = 0.0
            if parent_id:
                p_idx = id_to_index.get(parent_id)
                if p_idx is not None:
                    parent_score = base_scores[p_idx]
            score += alpha * child_sum.get(nid, 0.0) + beta * parent_score
            depth = self.depth.get(nid, 0)
            if mode == "overview":
                bias = 1.0 / (1.0 + 0.25 * depth)
            elif mode == "detail":
                bias = 1.0 + 0.1 * depth
            else:
                bias = 1.0
            score *= bias
            if score <= 0.0:
                continue
            node = node_by_id.get(nid)
            if not node:
                continue
            results.append((node, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[: max(1, int(limit or 5))]

class Compressor:
    def __init__(self):
        self._init_llm()
        self.node_map: Dict[str, ChapterNode] = {}
        self.image_list = []
        self.output_dir = None
        self._force_termination = False
        self.speech_speed = float(os.getenv('SPEECH_SPEED', 6.0))
        self._retriever: Optional[_BM25TreeRetriever] = None
        
        # State for current logic node processing
        self.generated_content = Content()
        self.generated_speech: List[Spection] = []
        self.current_duration = 0.0
        self.target_duration_sec = 60.0

        # Track generated titles to avoid duplication
        self.generated_titles: List[str] = []

    def _init_llm(self):
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../.env'))
        if os.path.exists(env_path):
            load_dotenv(env_path)
        
        cfg = resolve_text_llm_env("COMPRESSOR")
        api_key = cfg.api_key
        if not api_key:
            logger.warning("LLM API Key not found. Compressor will not work properly.")
            self.llm_model = None
            return

        platform_type = cfg.platform_type
        model_type = cfg.model_type
        base_url = cfg.api_url

        try:
            model_platform = ModelPlatformType(platform_type)
        except Exception:
            model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL

        create_kwargs = {
            "model_platform": model_platform,
            "model_type": model_type,
            "api_key": api_key,
            "model_config_dict": build_model_config(
                model_type=model_type,
                temperature=0.2,
                max_tokens=8 * 1024,
            ),
        }
        if base_url:
            create_kwargs["url"] = base_url

        self.llm_model = ModelFactory.create(**create_kwargs)

    def list_available_images(self) -> str:
        """List all available image filenames that can be used in slides."""
        if not self.image_list: return "No images available."
        return "\n".join(self.image_list)

    def search_web(self, query: str) -> str:
        """
        Search the web for the given query using Bing (CN accessible).
        Returns a summary of results including titles, links, and snippets.
        """
        try:
            url = "https://cn.bing.com/search"
            params = {'q': query}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            }
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                return f"Search failed with status code {resp.status_code}"
                
            results = []
            items = re.findall(r'<li class="b_algo"(.*?)</li>', resp.text, re.DOTALL)
            
            for i, item in enumerate(items):
                if i >= 5: break
                
                link_match = re.search(r'<h2.*?><a[^>]*href="(.*?)"[^>]*>(.*?)</a></h2>', item, re.DOTALL)
                if not link_match: continue
                    
                link = link_match.group(1)
                title = re.sub(r'<.*?>', '', link_match.group(2)).strip()
                
                snippet_match = re.search(r'<div class="[^"]*b_caption[^"]*">.*?<p[^>]*>(.*?)</p>', item, re.DOTALL)
                if not snippet_match:
                    snippet_match = re.search(r'<p class="b_lineclamp.*?">(.*?)</p>', item, re.DOTALL)
                
                snippet = ""
                if snippet_match:
                    snippet = re.sub(r'<.*?>', '', snippet_match.group(1)).strip()
                
                results.append(f"[{i+1}] Title: {title}\n    Link: {link}\n    Snippet: {snippet}")
                
            if not results:
                return "No search results found."
                
            return "\n\n".join(results)
            
        except Exception as e:
            return f"Error during web search: {e}"

    def _build_retriever(self, nodes: List[ChapterNode]) -> None:
        '''Build a BM25 retriever for the given nodes.'''
        try:
            self._retriever = _BM25TreeRetriever(nodes)
        except Exception as e:
            logger.error("Failed to build BM25 retriever: %s", e)
            self._retriever = None

    def _fallback_search_nodes(self, query: str, limit: int) -> List[ChapterNode]:
        '''Fallback search for content nodes relevant to a query using fuzzy matching.'''
        content_limit = 8192
        query_terms = query.lower().split()
        scored_nodes = []
        for node in self.node_map.values():
            parts = [(node.title or ""), (node.summary or "")]
            content = getattr(node, "content", "") or ""
            if content and len(content) <= content_limit:
                parts.append(content)
            text = " ".join(parts)
            text_lower = text.lower()
            score = 0
            for term in query_terms:
                if term in text_lower:
                    score += 1
            if score > 0:
                scored_nodes.append((score, node))
        scored_nodes.sort(key=lambda x: x[0], reverse=True)
        top_nodes = [n for _, n in scored_nodes[: max(1, int(limit or 5))]]
        return top_nodes

    def search_relevant_nodes(self, query: str, limit: int = 5) -> str:
        '''Search for content nodes relevant to a query using fuzzy matching.'''
        nodes: List[ChapterNode] = []
        if self._retriever and query:
            try:
                retrieved = self._retriever.search(query, limit)
                nodes = [n for n, _ in retrieved]
            except Exception as e:
                logger.error("BM25 retrieval failed: %s", e)
                nodes = []
        if not nodes and query:
            nodes = self._fallback_search_nodes(query, limit)
        if not nodes:
            return "No relevant nodes found."
        lines = []
        for node in nodes:
            lines.append(f"ID: {node.node_id} | Title: {node.title} | Summary: {_preview_text(node.summary or '')}")
        return "\n".join(lines)

    def get_node_details(self, node_id: str) -> str:
        """Get details of a specific node, including children titles and summary."""
        node = self.node_map.get(node_id)
        if not node: return "Node not found."
        media = _extract_media_blocks(node.content or "", limit=8)
        children_info = []
        if node.children_ids:
            for cid in node.children_ids:
                child = self.node_map.get(cid)
                if child: children_info.append(f"- {child.title} (ID: {child.node_id})")
        children_str = "\n".join(children_info) if children_info else "None"
        has_academic = bool((node.metadata or {}).get("has_academic_content"))
        return (
            f"ID: {node.node_id}\nTitle: {node.title}\nType: {node.node_type}\nHasAcademic: {has_academic}\n"
            f"MediaCount: {len(media)}\nChildren:\n{children_str}\n\nSummary: {node.summary}\n\nContent Preview:\n{node.content[:500]}..."
        )

    def get_node_content(self, node_id: str) -> str:
        """Get the full content of a node."""
        node = self.node_map.get(node_id)
        if not node: return "Node not found."
        return f"Title: {node.title}\nContent:\n{node.content}"

    def get_node_media(self, node_id: str, limit: int = 10) -> str:
        """Get figure/table blocks extracted from a node content."""
        node = self.node_map.get(node_id)
        if not node:
            return "Node not found."
        lim = max(1, min(20, int(limit or 10)))
        media = _extract_media_blocks(node.content or "", limit=lim)
        if not media:
            return "No media blocks found."
        out = []
        for i, it in enumerate(media, 1):
            out.append(
                f"[{i}] kind={it.get('kind')} images={it.get('images') or []} caption={_preview_text(it.get('caption') or '', 120)} label={_preview_text(it.get('label') or '', 80)}\n"
                f"{it.get('latex')}\n"
            )
        return "\n".join(out).strip()

    def estimate_speech_duration(self, speech_script: str) -> str:
        """Estimate the duration of a speech script in seconds."""
        cjk_count = len(re.findall(r'[\u4e00-\u9fff]', speech_script))
        non_cjk_text = re.sub(r'[\u4e00-\u9fff]', ' ', speech_script)
        word_count = len(non_cjk_text.split())
        total_units = cjk_count + word_count
        duration = total_units / self.speech_speed
        return f"{duration:.1f}"

    def add_slide(self, latex_body: str, speech_script: str) -> str:
        """Create a Beamer slide with LaTeX content and speech script."""
        def _extract_title_only(body: str) -> str:
            s = "\n".join([ln.strip() for ln in str(body or "").splitlines() if ln.strip()])
            if not re.search(r"\\(?:Large|LARGE|huge|Huge)\b", s):
                return ""
            if re.search(r"\\begin\{|\\item\b|\\includegraphics\b|\\begin\{(tabular|table|figure|tikzpicture)\}", s):
                return ""
            m = re.search(
                r"^(?:\\centering\s*)?(?:\\Large|\\LARGE|\\huge|\\Huge)\s*(?:\\textbf\{([^}]*)\}|\{([^}]*)\}|([^\\]+))\s*$",
                s,
            )
            if not m:
                return ""
            title = m.group(1) or m.group(2) or m.group(3) or ""
            title = re.sub(r"\\textbf\{([^}]*)\}", r"\1", title)
            title = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", title)
            title = re.sub(r"\s+", " ", title).strip()
            return title

        title_only = _extract_title_only(latex_body)
        if title_only:
            self.add_section(f"\\section{{{title_only}}}")
            return "Converted title-only slide to section."

        body_str = str(latex_body or "")
        has_figure = bool(re.search(r"\\begin\{figure\*?\}|\\includegraphics\b", body_str))
        has_table = bool(re.search(r"\\begin\{table\*?\}|\\begin\{tabular\*?\}", body_str))
        if has_figure and has_table:
            return "Error: Slide contains both figure and table. Split into separate slides."
        if has_figure or has_table:
            item_count = len(re.findall(r"\\item\b", body_str))
            plain_len = len(_strip_tex_commands(body_str))
            if item_count > 3 or plain_len > 260:
                return "Error: Slide contains figure/table; keep text minimal (<=3 bullets) or move text to next slide / speech."

        # --- Check for duplication ---
        # Extract frametitle to check against history
        ft_match = re.search(r'\\frametitle\{([^}]+)\}', latex_body)
        current_title = ft_match.group(1).strip() if ft_match else ""

        if current_title:
            # Normalize for check
            norm_title = current_title.lower().strip()
            for existing in self.generated_titles:
                if existing.lower().strip() == norm_title:
                    return f"Error: A slide with title '{current_title}' has already been generated. Please generate different content."
        # -----------------------------

        duration = float(self.estimate_speech_duration(speech_script))
        self.current_duration += duration
        
        latex_body = re.sub(r'\\begin{frame}\n*', '', latex_body)
        latex_body = re.sub(r'\n*\\end{frame}', '', latex_body).strip()

        latex_body, img_changes = _rewrite_includegraphics_paths(latex_body, self.image_list or [])
        latex_body = _normalize_graphics_sizing(latex_body)
        full_latex = f"\\begin{{frame}}\n{latex_body}\n\\end{{frame}}"

        self.generated_content.append(Frame(full_latex))
        self.generated_speech.append(Spection(speech_script))
        
        # Record title if successfully added
        if current_title:
            self.generated_titles.append(current_title)
        
        msg = f"Slide added. Duration: {duration:.1f}s. Total: {self.current_duration:.1f}s / {self.target_duration_sec}s."
        if img_changes:
            msg += f" ImagePathsFixed: {len(img_changes)}."
        if self.current_duration > self.target_duration_sec * 2.0:
            self._force_termination = True
            return msg + " CRITICAL: Time budget exceeded. Terminating."
        return msg

    def add_section(self, latex_cmd: str) -> str:
        """Add a section or subsection divider."""
        if "&" in latex_cmd and "\\&" not in latex_cmd:
            latex_cmd = latex_cmd.replace("&", "\\&")
        self.generated_content.append(Section(latex_cmd))
        return "Section added."

    def add_citation(self, citation_key: str, bibtex_entry: str) -> str:
        """Add a citation to the bibliography."""
        if not self.output_dir: return "Error: Output directory not set."
        ref_path = os.path.join(self.output_dir, "ref.bib")
        try:
            if os.path.exists(ref_path):
                with open(ref_path, "r", encoding="utf-8") as f:
                    if citation_key in f.read(): return f"Citation {citation_key} exists."
            with open(ref_path, "a", encoding="utf-8") as f:
                f.write("\n" + bibtex_entry + "\n")
            return f"Citation {citation_key} added."
        except Exception as e:
            return f"Error: {e}"

    def compress(self, logic_flow: LogicFlow, nodes: List[ChapterNode], image_list: List[str] = None, output_dir: str = None, global_instructions: str = "", progress_cb: Optional[Callable[[int, int, str], None]] = None) -> Tuple[Content, List[Spection]]:
        if not self.llm_model:
            logger.error("LLM not initialized.")
            return Content(), []

        self.node_map = {n.node_id: n for n in nodes}
        self.image_list = image_list or []
        self.output_dir = output_dir
        self._build_retriever(nodes)
        
        # Reset generated titles for new compression task
        self.generated_titles = []
        
        full_content = Content()
        full_speech: List[Spection] = []
        
        roots = [n for n in nodes if not n.parent_id]
        
        print("=== Begin Compression ===")

        # Use natural order of nodes, ignoring edges for generation order
        ordered_indices = list(range(len(logic_flow.nodes or [])))

        total = len(ordered_indices)
        for i, node_idx in enumerate(ordered_indices):
            logic_node = logic_flow.nodes[node_idx]
            try:
                if progress_cb:
                    progress_cb(i, total, str(getattr(logic_node, 'name', '') or ''))
            except Exception:
                pass
            print(f"\nProcessing Logic Node {i+1}/{total}: {logic_node.name}")
            
            section_cmd = f"\\section{{{logic_node.name}}}"
            full_content.append(Section(section_cmd))
            
            node_content, node_speech = self._process_logic_node(logic_node, roots, global_instructions)
            
            if node_content:
                full_content.extend(node_content)
                full_speech.extend(node_speech)
            else:
                print(f"No content generated for {logic_node.name}")

        return full_content, full_speech

    def _process_logic_node(self, logic_node: LogicNode, roots: List[ChapterNode], global_instructions: str = "") -> Tuple[Content, List[Spection]]:
        # Reset state for this node
        self.generated_content = Content()
        self.generated_speech = []
        self.current_duration = 0.0
        self._force_termination = False
        
        self.target_duration_sec = 60.0
        try:
            d_str = logic_node.duration.lower()
            if 'min' in d_str:
                self.target_duration_sec = float(re.search(r'(\d+(\.\d+)?)', d_str).group(1)) * 60
            elif 'sec' in d_str:
                self.target_duration_sec = float(re.search(r'(\d+(\.\d+)?)', d_str).group(1))
            else:
                self.target_duration_sec = float(re.search(r'(\d+(\.\d+)?)', d_str).group(1)) * 60
        except:
            pass
        
        print(f"Target Duration: {self.target_duration_sec}s")
        
        # Prepare context about already generated slides
        generated_context = ""
        if self.generated_titles:
            titles_list = "\n".join([f"- {t}" for t in self.generated_titles])
            generated_context = f"\nContext - Previously generated slides (DO NOT REPEAT content/titles):\n{titles_list}\n"
        
        tools = [
            FunctionTool(self.list_available_images),
            FunctionTool(self.search_relevant_nodes),
            FunctionTool(self.get_node_details),
            FunctionTool(self.get_node_content),
            FunctionTool(self.get_node_media),
            FunctionTool(self.estimate_speech_duration),
            FunctionTool(self.add_slide),
            FunctionTool(self.add_section),
            FunctionTool(self.add_citation)
        ]
        
        sys_msg = BaseMessage.make_assistant_message(
            role_name="Compressor",
            content=f"""You are an expert presentation creator.
Target Node: {logic_node.name}
Description: {logic_node.description}
Duration: {self.target_duration_sec}s
{generated_context}

Goal: Create Beamer slides for this topic.
1. Search content using tools.
2. Use `add_section(latex_cmd)` for titles/structure. Prefer `\\section{{...}}` (or `\\subsection{{...}}`) instead of making a title-only slide.
3. Use `add_slide(latex_body, speech_script)` to create content slides. Ensure content is NOT a duplicate of previous slides.
4. Use `add_citation` if needed.
5. Keep within time limit.
6. Reply DONE when finished.

Style Requirements (Clean, Concise, Modern Beamer):
- Layout: Use standard `itemize` or `enumerate` environments. Keep slides un-cluttered.
- Content: KEY POINTS ONLY. Use bullet points. Avoid long paragraphs or walls of text.
- Titles: ALWAYS use `\\frametitle{{...}}` for every slide.
- Figures/Tables: If a slide contains a figure or table, do not add dense text alongside it.
- Typography: Do NOT use `\\Large` or `\\huge` for body text. Let Beamer handle font sizes.

Note:
1. ALWAYS locate the most relevant source nodes with `search_relevant_nodes`, then call `get_node_content` for the key node(s).
2. If the source node content contains figures/tables (or `HasAcademic: True`), you MUST call `get_node_media(node_id)` and include at least one representative figure/table in the generated slides for this logic node, unless there is a strong reason (e.g., time budget). Prefer preserving the original LaTeX block returned by `get_node_media`.
3. For slides containing a figure or table: keep the slide minimal (title + at most 1-3 short bullets, or even no bullets). Put detailed explanation into `speech_script`, or create a separate text slide before/after.
4. If both a figure and a table are relevant, create separate slides for them (do NOT place both in one slide).
5. If you cannot fit the figure/table into a slide, mention it in the `speech_script` explicitly and optionally cite it.
6. DO NOT create a "big title" inside the slide by using `\\Large/\\huge` text; instead use `add_section('\\section{{...}}')`.
"""
        )
        
        agent = ChatAgent(system_message=sys_msg, model=self.llm_model, tools=tools)
        user_msg = BaseMessage.make_user_message(role_name="User", content="Start generating.")
        
        for _ in range(15):
            try:
                response = agent.step(user_msg)
                content = response.msg.content
                if content and "DONE" in content: break
                if response.terminated: break
                if self._force_termination: break
                if self.current_duration > self.target_duration_sec * 1.5: break
                
                user_msg = BaseMessage.make_user_message(role_name="User", content=f"Current Duration: {self.current_duration:.1f}s. Continue.")
            except Exception as e:
                logger.error(f"Agent error: {e}")
                break
                
        return self.generated_content, self.generated_speech
