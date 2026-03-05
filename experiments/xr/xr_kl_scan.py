from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from deepslide_eval.io_utils import ensure_dir, write_jsonl
from deepslide_eval.manifest import DatasetInstance, OutputArtifact, dataset_instances_to_rows, output_artifacts_to_rows

from xr_kl_paths import XREvalPaths


_LK_RE = re.compile(r"l[\s_=-]*(\d+).*?k[\s_=-]*(\d+)", re.IGNORECASE)
_S_RE = re.compile(r"s[\s_=-]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _parse_lk_from_name(name: str) -> Optional[Tuple[int, int]]:
    m = _LK_RE.search(name or "")
    if not m:
        return None
    try:
        l = int(m.group(1))
        k = int(m.group(2))
        return l, k
    except Exception:
        return None


def _parse_s_from_name(name: str) -> Optional[float]:
    m = _S_RE.search(name or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _extract_title_hint_from_filename(pdf_path: Path) -> str:
    s = pdf_path.stem
    s = s.replace("_", " ")
    s = _norm_ws(s)
    s = re.sub(r"\bminipage\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bimages[_-]?\w+\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bL\s*\d+\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bK\s*\d+\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bS\s*[0-9]+(?:\.[0-9]+)?\b", " ", s, flags=re.IGNORECASE)
    s = _norm_ws(s)

    m = re.search(r"\b1\.0\b(.*)$", s)
    if m:
        tail = _norm_ws(m.group(1))
        if tail:
            return tail

    parts = s.split(" ")
    tail = " ".join(parts[-18:]) if len(parts) > 18 else s
    return _norm_ws(tail)


def _find_dataset_pdf_by_paper_id(dataset_cache_root: Path, paper_id: str) -> Optional[Path]:
    if not paper_id:
        return None
    for p in dataset_cache_root.rglob("paper.pdf"):
        if p.parent.name == paper_id:
            return p
    return None


def _find_dataset_pdf_by_title_hint(dataset_cache_root: Path, title_hint: str) -> Optional[Path]:
    title_hint = _norm_ws(title_hint).lower()
    if not title_hint:
        return None

    try:
        import fitz
    except Exception as e:
        raise RuntimeError(f"missing_pymupdf: {e}")

    tokens = re.findall(r"[a-z]{4,}", title_hint)
    tokens = [t for t in tokens if t not in {"with", "from", "that", "this", "into", "your", "their"}]
    seen = set()
    tokens = [t for t in tokens if not (t in seen or seen.add(t))]
    if not tokens:
        return None
    need = max(4, min(8, int(len(tokens) * 0.6)))

    best_p = None
    best_score = -1
    for p in dataset_cache_root.rglob("paper.pdf"):
        try:
            doc = fitz.open(str(p))
        except Exception:
            continue
        try:
            txt = ""
            for i in range(min(2, doc.page_count)):
                t = doc.load_page(i).get_text("text") or ""
                txt += "\n" + t
            hay = _norm_ws(txt).lower()
            score = sum(1 for t in tokens if t in hay)
            if score > best_score:
                best_score = score
                best_p = p
            if score >= max(need, len(tokens)):
                return p
        finally:
            doc.close()
    if best_p is not None and best_score >= need:
        return best_p
    return None


def scan_xr_kl(
    paths: XREvalPaths,
    source_pdf: Optional[str],
    paper_id: Optional[str],
) -> Tuple[List[DatasetInstance], List[OutputArtifact]]:
    ensure_dir(paths.manifests_dir)
    ensure_dir(paths.cache_dir)

    pdfs = sorted([p for p in paths.outputs_cache_root.rglob("*.pdf") if p.is_file()])
    if not pdfs:
        raise FileNotFoundError(f"no pdf artifacts under: {paths.outputs_cache_root}")

    src_pdf_path: Optional[Path] = Path(source_pdf) if source_pdf else None
    if src_pdf_path is None and paper_id:
        src_pdf_path = _find_dataset_pdf_by_paper_id(paths.dataset_cache_root, paper_id=str(paper_id))

    if src_pdf_path is None:
        title_hint = _extract_title_hint_from_filename(pdfs[0])
        src_pdf_path = _find_dataset_pdf_by_title_hint(paths.dataset_cache_root, title_hint=title_hint)

    if src_pdf_path is None or not src_pdf_path.exists():
        raise FileNotFoundError("missing source pdf: provide --source-pdf or --paper-id (auto-match failed)")

    if not paper_id:
        paper_id = str(src_pdf_path.parent.name)
    paper_id = str(paper_id)
    inst_id = f"xr/{paper_id}"

    instances = [
        DatasetInstance(
            instance_id=inst_id,
            domain="xr",
            subpath="",
            paper_id=paper_id,
            paper_pdf_path=str(src_pdf_path),
            source_tar_path=None,
        )
    ]

    artifacts: List[OutputArtifact] = []
    seen_sys = set()
    for p in pdfs:
        lk = _parse_lk_from_name(p.name)
        if lk is not None:
            l, k = lk
            system = f"L{l}_K{k}"
        else:
            sval = _parse_s_from_name(p.name)
            if sval is None:
                continue
            system = f"S{sval:g}"
        if system in seen_sys:
            continue
        seen_sys.add(system)
        artifacts.append(
            OutputArtifact(
                system=system,
                instance_id=inst_id,
                domain="xr",
                subpath="",
                paper_id=paper_id,
                artifact_path=str(p),
                artifact_type="pdf",
            )
        )

    if not artifacts:
        raise RuntimeError(f"no artifacts with parsable L/K or S in filenames under: {paths.outputs_cache_root}")

    write_jsonl(paths.manifests_dir / "dataset.jsonl", dataset_instances_to_rows(instances))
    write_jsonl(paths.manifests_dir / "outputs.jsonl", output_artifacts_to_rows(artifacts))
    return instances, artifacts
