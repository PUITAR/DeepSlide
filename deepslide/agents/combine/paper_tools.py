import os
import re
from typing import List

def _safe_read(path: str, max_chars: int = 4000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        return txt[:max_chars]
    except Exception:
        return ""

def make_paper_tools(project_dir: str, merged_main: str):
    def search_text(query: str = "", limit: int = 10, **kwargs) -> str:
        """Search for LaTeX text snippets containing the query terms within the paper project directory and return summaries.
        Args: query is the search keyword, limit is the maximum number of entries to return.
        Returns: A list string of "file_path: snippet" joined by newlines.
        """
        q = (kwargs.get("q") or kwargs.get("query_text") or query or "")
        try:
            limit = int(kwargs.get("limit", limit))
        except Exception:
            pass
        terms = [t.lower() for t in re.split(r"\s+", q.strip()) if t.strip()]
        hits: List[str] = []
        for dirpath, _, filenames in os.walk(project_dir):
            for fn in filenames:
                if not fn.lower().endswith(".tex"):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    low = content.lower()
                    score = sum(1 for t in terms if t in low)
                    if score:
                        hits.append(f"{full}: {content[:300].replace('\n',' ')}")
                        if len(hits) >= limit:
                            break
                except Exception:
                    continue
            if len(hits) >= limit:
                break
        if not hits:
            return "No matches"
        return "\n".join(hits)

    def list_sections(**kwargs) -> str:
        """List sections and subsection titles in the merged main file for quick navigation of the paper structure.
        Args: None.
        Returns: A string containing Sections/Subsections titles.
        """
        txt = _safe_read(merged_main, max_chars=80000)
        secs = re.findall(r"\\section\*?\{([^}]+)\}", txt)
        subs = re.findall(r"\\subsection\*?\{([^}]+)\}", txt)
        out = []
        if secs:
            out.append("Sections:")
            out.extend([f"- {s}" for s in secs])
        if subs:
            out.append("Subsections:")
            out.extend([f"- {s}" for s in subs])
        return "\n".join(out) if out else "No sections"

    def read_main_excerpt(start: int = 0, length: int = 2000, **kwargs) -> str:
        """Read a segment of content from the merged main file starting at 'start' with a specified 'length' for preview and reference.
        Args: start is the starting offset, length is the number of characters to read.
        Returns: The main file segment string.
        """
        start_key = kwargs.get("offset") or kwargs.get("begin") or start
        length_key = kwargs.get("len") or kwargs.get("size") or length
        txt = _safe_read(merged_main, max_chars=200000)
        try:
            start_val = max(0, int(start_key))
        except Exception:
            start_val = 0
        try:
            len_val = max(1, int(length_key))
        except Exception:
            len_val = 2000
        end = min(len(txt), start_val + len_val)
        return txt[start_val:end]

    def read_file(relpath: str = "", max_chars: int = 4000, **kwargs) -> str:
        """Read file content by relative path within the project for in-depth viewing of the original text.
        Args: relpath is the relative path, max_chars is the maximum number of characters to read.
        Returns: File content snippet string.
        """
        rp = kwargs.get("path") or kwargs.get("file") or kwargs.get("file_path") or relpath
        try:
            max_chars = int(kwargs.get("max_chars", max_chars))
        except Exception:
            pass
        full = os.path.join(project_dir, rp)
        return _safe_read(full, max_chars=max_chars)

    return [search_text, list_sections, read_main_excerpt, read_file]
