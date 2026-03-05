from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


DATASET_PDF_NAME = "paper.pdf"
DATASET_SOURCE_NAME = "source.tar.gz"


@dataclass(frozen=True)
class DatasetInstance:
    instance_id: str
    domain: str
    subpath: str
    paper_id: str
    paper_pdf_path: str
    source_tar_path: Optional[str]


@dataclass(frozen=True)
class OutputArtifact:
    system: str
    instance_id: str
    domain: str
    subpath: str
    paper_id: str
    artifact_path: str
    artifact_type: str


_PAPER_ID_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|\d{7})(?:v\d+)?$")


def _is_paper_id(s: str) -> bool:
    return _PAPER_ID_RE.match(s) is not None


def _instance_id(domain: str, subpath: str, paper_id: str) -> str:
    if subpath:
        return f"{domain}/{subpath}/{paper_id}"
    return f"{domain}/{paper_id}"


def scan_dataset_cache(dataset_cache_root: Path) -> List[DatasetInstance]:
    instances: List[DatasetInstance] = []
    if not dataset_cache_root.exists():
        return instances

    for pdf_path in dataset_cache_root.rglob(DATASET_PDF_NAME):
        rel = pdf_path.relative_to(dataset_cache_root)
        parts = rel.parts
        if len(parts) < 2:
            continue

        domain = parts[0]
        paper_id = parts[-2]
        if not _is_paper_id(paper_id):
            continue

        middle = parts[1:-2]
        subpath = "/".join(middle)
        inst_id = _instance_id(domain, subpath, paper_id)

        source_tar = pdf_path.parent / DATASET_SOURCE_NAME
        instances.append(
            DatasetInstance(
                instance_id=inst_id,
                domain=domain,
                subpath=subpath,
                paper_id=paper_id,
                paper_pdf_path=str(pdf_path),
                source_tar_path=str(source_tar) if source_tar.exists() else None,
            )
        )

    instances.sort(key=lambda x: x.instance_id)
    return instances


def _artifact_type_from_suffix(path: Path) -> Optional[str]:
    suf = path.suffix.lower()
    if suf in {".pptx", ".ppt"}:
        return "pptx" if suf == ".pptx" else "ppt"
    if suf == ".pdf":
        return "pdf"
    if suf in {".html", ".htm"}:
        return "html"
    if suf == ".json":
        return "json"
    if suf in {".txt", ".md"}:
        return "text"
    return None


def scan_outputs_cache(outputs_cache_root: Path) -> List[OutputArtifact]:
    artifacts: List[OutputArtifact] = []
    if not outputs_cache_root.exists():
        return artifacts

    deepslide_best: Dict[Tuple[str, str, str], Path] = {}
    for p in outputs_cache_root.rglob("*"):
        if not p.is_file():
            continue
        art_type = _artifact_type_from_suffix(p)
        if art_type is None:
            continue

        rel = p.relative_to(outputs_cache_root)
        parts = rel.parts
        if len(parts) < 3:
            continue

        system = parts[0]
        domain = parts[1]
        if system == "deepslide":
            continue
        paper_id = parts[-2]
        if not _is_paper_id(paper_id):
            continue

        subpath = "/".join(parts[2:-2])
        inst_id = _instance_id(domain, subpath, paper_id)

        artifacts.append(
            OutputArtifact(
                system=system,
                instance_id=inst_id,
                domain=domain,
                subpath=subpath,
                paper_id=paper_id,
                artifact_path=str(p),
                artifact_type=art_type,
            )
        )

    deepslide_root = outputs_cache_root / "deepslide"
    if deepslide_root.exists():
        for base_pdf in deepslide_root.rglob("recipe/base.pdf"):
            try:
                rel = base_pdf.relative_to(outputs_cache_root)
            except Exception:
                continue
            parts = rel.parts
            if len(parts) < 4:
                continue
            if parts[0] != "deepslide":
                continue
            domain = parts[1]
            paper_idx = None
            for i in range(2, len(parts)):
                if _is_paper_id(parts[i]):
                    paper_idx = i
                    break
            if paper_idx is None:
                continue
            paper_id = parts[paper_idx]
            subpath = "/".join(parts[2:paper_idx])
            key = (domain, subpath, paper_id)
            prev = deepslide_best.get(key)
            if prev is None:
                deepslide_best[key] = base_pdf
            else:
                prev_parts = prev.relative_to(outputs_cache_root).parts
                if len(parts) < len(prev_parts) or (len(parts) == len(prev_parts) and str(base_pdf) < str(prev)):
                    deepslide_best[key] = base_pdf

        for (domain, subpath, paper_id), base_pdf in deepslide_best.items():
            inst_id = _instance_id(domain, subpath, paper_id)
            artifacts.append(
                OutputArtifact(
                    system="deepslide",
                    instance_id=inst_id,
                    domain=domain,
                    subpath=subpath,
                    paper_id=paper_id,
                    artifact_path=str(base_pdf),
                    artifact_type="pdf",
                )
            )

    artifacts.sort(key=lambda x: (x.system, x.instance_id, x.artifact_path))
    return artifacts


def join_instances_with_artifacts(
    instances: Iterable[DatasetInstance],
    artifacts: Iterable[OutputArtifact],
) -> Dict[str, Dict[str, List[OutputArtifact]]]:
    inst_map: Dict[str, DatasetInstance] = {i.instance_id: i for i in instances}
    by_inst: Dict[str, Dict[str, List[OutputArtifact]]] = {k: {} for k in inst_map.keys()}
    for a in artifacts:
        if a.instance_id not in by_inst:
            continue
        by_sys = by_inst[a.instance_id]
        by_sys.setdefault(a.system, []).append(a)
    return by_inst


def dataset_instances_to_rows(instances: Iterable[DatasetInstance]) -> List[dict]:
    return [asdict(x) for x in instances]


def output_artifacts_to_rows(artifacts: Iterable[OutputArtifact]) -> List[dict]:
    return [asdict(x) for x in artifacts]
