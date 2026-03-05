from __future__ import annotations

import re
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple

from deepslide_eval.io_utils import ensure_dir, sha1_bytes, write_jsonl
from deepslide_eval.manifest import DatasetInstance, OutputArtifact, dataset_instances_to_rows, output_artifacts_to_rows

from case3_paths import Case3EvalPaths


_PAPER_ID_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|\d{7})(?:v\d+)?$")


def _is_paper_id(s: str) -> bool:
    return _PAPER_ID_RE.match(s or "") is not None


def _find_dataset_pdf_by_paper_id(dataset_cache_root: Path, paper_id: str) -> Optional[Path]:
    if not paper_id:
        return None
    for p in dataset_cache_root.rglob("paper.pdf"):
        if p.parent.name == paper_id:
            return p
    return None


def _materialize_recipe_zip(zip_path: Path, cache_root: Path) -> Optional[Path]:
    try:
        st = zip_path.stat()
        sig = f"{str(zip_path)}|{st.st_size}|{st.st_mtime_ns}"
    except Exception:
        sig = str(zip_path)
    key = sha1_bytes(sig.encode("utf-8"))
    out_root = cache_root / "case3_unzipped" / key
    base_pdf = out_root / "recipe" / "base.pdf"
    speech_txt = out_root / "recipe" / "speech.txt"
    if base_pdf.exists() and speech_txt.exists():
        return base_pdf

    ensure_dir(out_root)
    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            names = [n for n in zf.namelist() if isinstance(n, str)]
            names_norm = [n.replace("\\", "/") for n in names]
            base_candidates = [n for n in names_norm if n.endswith("recipe/base.pdf")]
            if not base_candidates:
                return None
            chosen_norm = sorted(base_candidates, key=lambda s: (len(s), s))[0]
            prefix = chosen_norm[: -len("recipe/base.pdf")].rstrip("/")
            recipe_prefix = f"{prefix}/recipe/" if prefix else "recipe/"

            want = {"base.pdf", "speech.txt"}
            for n, n_norm in zip(names, names_norm):
                if not n_norm.startswith(recipe_prefix):
                    continue
                if n_norm.endswith("/"):
                    continue
                rel = n_norm[len(prefix) + 1 :] if prefix else n_norm
                dst = out_root / rel
                if dst.parent.name != "recipe":
                    continue
                if dst.name not in want:
                    continue
                ensure_dir(dst.parent)
                with zf.open(n, "r") as src, dst.open("wb") as f:
                    f.write(src.read())
    except Exception:
        return None

    return base_pdf if base_pdf.exists() else None


def scan_case3(paths: Case3EvalPaths, source_pdf: Optional[str], paper_id: Optional[str]) -> Tuple[List[DatasetInstance], List[OutputArtifact]]:
    ensure_dir(paths.manifests_dir)
    ensure_dir(paths.cache_dir)

    src_pdf_path: Optional[Path] = Path(source_pdf) if source_pdf else None
    if src_pdf_path is None and paper_id and _is_paper_id(paper_id):
        src_pdf_path = _find_dataset_pdf_by_paper_id(paths.dataset_cache_root, paper_id=paper_id)
    if src_pdf_path is None or not src_pdf_path.exists():
        raise FileNotFoundError("missing source pdf: provide --source-pdf or --paper-id")

    if not paper_id:
        paper_id = str(src_pdf_path.parent.name)
    paper_id = str(paper_id)

    inst_id = f"case3/{paper_id}"
    instances = [
        DatasetInstance(
            instance_id=inst_id,
            domain="case3",
            subpath="",
            paper_id=paper_id,
            paper_pdf_path=str(src_pdf_path),
            source_tar_path=None,
        )
    ]

    artifacts: List[OutputArtifact] = []

    deepslide_base_pdf = paths.outputs_cache_root / "deepslide" / "recipe" / "base.pdf"
    if deepslide_base_pdf.exists():
        artifacts.append(
            OutputArtifact(
                system="deepslide",
                instance_id=inst_id,
                domain="case3",
                subpath="",
                paper_id=paper_id,
                artifact_path=str(deepslide_base_pdf),
                artifact_type="pdf",
            )
        )

    zip_map = {
        "wo-bm25-retriever.zip": "wo-bm25-retriever",
        "wo-logicchain.zip": "wo-logicchain",
        "wo-logicchain-rec.zip": "wo-logicchain-rec",
    }
    for fname, system in zip_map.items():
        zp = paths.outputs_cache_root / fname
        if not zp.exists():
            continue
        base_pdf = _materialize_recipe_zip(zp, cache_root=paths.cache_dir)
        if base_pdf is None or not base_pdf.exists():
            continue
        artifacts.append(
            OutputArtifact(
                system=system,
                instance_id=inst_id,
                domain="case3",
                subpath="",
                paper_id=paper_id,
                artifact_path=str(base_pdf),
                artifact_type="pdf",
            )
        )

    instances.sort(key=lambda x: x.instance_id)
    artifacts.sort(key=lambda x: (x.system, x.instance_id, x.artifact_path))

    write_jsonl(paths.manifests_dir / "dataset.jsonl", dataset_instances_to_rows(instances))
    write_jsonl(paths.manifests_dir / "outputs.jsonl", output_artifacts_to_rows(artifacts))
    return instances, artifacts

