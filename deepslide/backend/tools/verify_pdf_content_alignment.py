import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import fitz


def _strip_tex(s: str) -> str:
    t = str(s or "")
    t = re.sub(r"%.*$", " ", t, flags=re.MULTILINE)
    t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
    t = re.sub(r"\{([^\}]*)\}", r"\1", t)
    t = re.sub(r"\$[^$]*\$", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _tokenize(s: str) -> set[str]:
    toks = re.findall(r"[A-Za-z0-9]{3,}", str(s or ""))
    return set([t.lower() for t in toks])


def _expand_inputs(tex: str, base_dir: str) -> str:
    visited: set[str] = set()
    base_abs = os.path.abspath(base_dir)

    def _read(rel: str, cur_dir: str) -> str:
        r = str(rel or "").strip().replace("\\", "/")
        if not r or "\x00" in r or ".." in r:
            return ""
        if not os.path.splitext(r)[1]:
            r = r + ".tex"

        candidate_dirs = [os.path.abspath(cur_dir), base_abs]
        abs_path = ""
        for d in candidate_dirs:
            p = os.path.abspath(os.path.join(d, r))
            if p.startswith(base_abs + os.sep) and os.path.exists(p) and os.path.isfile(p):
                abs_path = p
                break
        if not abs_path or abs_path in visited:
            return ""
        visited.add(abs_path)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except Exception:
            return ""
        return _expand(raw, os.path.dirname(abs_path))

    def _expand(t: str, cur_dir: str) -> str:
        out = str(t or "")
        for _ in range(10):
            changed = False

            def _repl(m: re.Match) -> str:
                nonlocal changed
                changed = True
                return _read(m.group(1), cur_dir)

            out2 = re.sub(r"\\(?:input|include)\{([^}]+)\}", _repl, out)
            out = out2
            if not changed:
                break
        return out

    return _expand(tex, base_dir)


def _normalize_frames(tex: str) -> str:
    s = str(tex or "")
    out: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        m = re.search(r"\\frame\s*(\[[^\]]*\])?\s*\{", s[i:])
        if not m:
            out.append(s[i:])
            break
        start = i + m.start()
        out.append(s[i:start])
        opt = m.group(1) or ""
        j = i + m.end() - 1
        depth = 0
        k = j
        while k < n:
            ch = s[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body = s[j + 1 : k]
                    out.append("\\begin{frame}" + opt + "\n" + body + "\n\\end{frame}")
                    k += 1
                    break
            k += 1
        i = k
    return "".join(out)


def _extract_frames(tex: str) -> List[str]:
    return [m.group(1) for m in re.finditer(r"(\\begin\{frame\}.*?\\end\{frame\})", tex, re.DOTALL)]


def _frame_signature(frame_tex: str) -> Dict[str, Any]:
    t = str(frame_tex or "")
    m = re.search(r"\\frametitle\{([^}]*)\}", t)
    title = _strip_tex(m.group(1)) if m else ""
    plain = _strip_tex(t)
    tokens = _tokenize(title + " " + plain)
    return {"title": title, "plain": plain, "tokens": tokens}


def _page_signature(doc: fitz.Document, page_index: int) -> Dict[str, Any]:
    try:
        page = doc.load_page(int(page_index))
        txt = page.get_text("text") or ""
    except Exception:
        txt = ""
    clean = " ".join(str(txt).split())
    return {"text": clean, "tokens": _tokenize(clean)}


def _align_pages_to_frames(
    pdf_path: str,
    frames: List[str],
    speeches: List[str],
) -> Tuple[List[Optional[int]], List[Optional[int]]]:
    doc = fitz.open(pdf_path)
    P = doc.page_count
    page_sigs = [_page_signature(doc, i) for i in range(P)]
    doc.close()
    frame_sigs = [_frame_signature(fr) for fr in frames]
    F = len(frame_sigs)

    neg = -10**9
    dp = [[neg] * (F + 1) for _ in range(P + 1)]
    bt: List[List[tuple[int, int, int]]] = [[(0, 0, 0)] * (F + 1) for _ in range(P + 1)]
    dp[0][0] = 0

    def sim(pi: int, fi: int) -> int:
        p = page_sigs[pi]
        f = frame_sigs[fi]
        pt = p["tokens"]
        ft = f["tokens"]
        if not pt or not ft:
            base = 0.0
        else:
            inter = len(pt & ft)
            denom = max(1, min(len(pt), len(ft)))
            base = inter / float(denom)
        title = str(f.get("title") or "").strip()
        title_hit = False
        if title and title.lower() in str(p.get("text") or "").lower():
            base += 0.35
            title_hit = True
        if len(pt) >= 10 and len(ft) >= 10 and not title_hit and base < 0.08:
            return -700
        return int(base * 1000)

    for i in range(P + 1):
        for j in range(F + 1):
            cur = dp[i][j]
            if cur <= neg // 2:
                continue

            if i < P:
                sp = speeches[i] if len(speeches) == P and i < len(speeches) else ""
                skip_cost = 0 if "<add>" in str(sp) else -650
                v = cur + skip_cost
                if v > dp[i + 1][j]:
                    dp[i + 1][j] = v
                    bt[i + 1][j] = (i, j, 1)

            if j < F:
                v = cur - 900
                if v > dp[i][j + 1]:
                    dp[i][j + 1] = v
                    bt[i][j + 1] = (i, j, 2)

            if i < P and j < F:
                sp = speeches[i] if len(speeches) == P and i < len(speeches) else ""
                if "<add>" not in str(sp):
                    v = cur + sim(i, j)
                    if v > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = v
                        bt[i + 1][j + 1] = (i, j, 3)

    mapping: List[Optional[int]] = [None] * P
    scores: List[Optional[int]] = [None] * P
    i, j = P, F
    while i > 0 or j > 0:
        pi, pj, act = bt[i][j]
        if act == 3:
            mapping[pi] = pj
            scores[pi] = sim(pi, pj)
        i, j = pi, pj
        if i == 0 and j == 0:
            break
    return mapping, scores


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="Project directory path (contains recipe/)")
    ap.add_argument("--json", action="store_true", help="Output JSON report")
    ap.add_argument("--show", type=int, default=30, help="Show first N pages")
    args = ap.parse_args()

    project_path = os.path.abspath(args.project)
    recipe_dir = os.path.join(project_path, "recipe")
    pdf_path = os.path.join(recipe_dir, "base.pdf")
    content_path = os.path.join(recipe_dir, "content.tex")
    speech_path = os.path.join(recipe_dir, "speech.txt")

    if not os.path.exists(pdf_path):
        raise SystemExit(f"missing {pdf_path}")
    if not os.path.exists(content_path):
        raise SystemExit(f"missing {content_path}")

    with open(content_path, "r", encoding="utf-8", errors="ignore") as f:
        full_tex = f.read()
    tex = _normalize_frames(_expand_inputs(full_tex, recipe_dir))
    frames = _extract_frames(tex)

    speeches: List[str] = []
    if os.path.exists(speech_path):
        try:
            with open(speech_path, "r", encoding="utf-8", errors="ignore") as f:
                speeches = (f.read() or "").split("<next>")
        except Exception:
            speeches = []

    mapping, scores = _align_pages_to_frames(pdf_path, frames, speeches)
    doc = fitz.open(pdf_path)
    pages_count = doc.page_count
    doc.close()

    bad: List[int] = []
    for i in range(pages_count):
        fi = mapping[i]
        sc = scores[i]
        if fi is None:
            bad.append(i)
            continue
        if sc is not None and sc < 0:
            bad.append(i)

    report = {
        "project": project_path,
        "pages": pages_count,
        "frames": len(frames),
        "speeches": len(speeches),
        "mapped": sum(1 for x in mapping if isinstance(x, int)),
        "unmapped_pages": bad,
        "page_to_frame": mapping,
        "scores": scores,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"pages={pages_count} frames={len(frames)} speeches={len(speeches)} mapped={report['mapped']}")
    if bad:
        print(f"unmapped_or_low_score_pages={len(bad)} first={bad[: min(20, len(bad))]}")
    print("page -> frame (score)")
    for i in range(min(pages_count, int(args.show))):
        fi = mapping[i]
        sc = scores[i]
        print(f"{i:03d} -> {fi if fi is not None else 'None'} ({sc if sc is not None else ''})")


if __name__ == "__main__":
    main()

