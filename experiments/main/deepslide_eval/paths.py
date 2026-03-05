from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalPaths:
    repo_root: Path

    @property
    def evaluation_root(self) -> Path:
        return self.repo_root / "experiments" / "evaluation"

    @property
    def dataset_cache_root(self) -> Path:
        return self.repo_root / "dataset" / ".cache"

    @property
    def outputs_cache_root(self) -> Path:
        return self.repo_root / "experiments" / ".cache" / "main"

    @property
    def outputs_root(self) -> Path:
        return self.evaluation_root / "outputs"

    @property
    def manifests_dir(self) -> Path:
        return self.outputs_root / "manifests"

    @property
    def cache_dir(self) -> Path:
        return self.outputs_root / "caches"

    @property
    def scores_dir(self) -> Path:
        return self.outputs_root / "scores"

    @property
    def reports_dir(self) -> Path:
        return self.outputs_root / "reports"


def default_paths() -> EvalPaths:
    here = Path(__file__).resolve()
    repo_root = here
    for _ in range(8):
        if (repo_root / "experiments").exists() and (repo_root / "dataset").exists():
            return EvalPaths(repo_root=repo_root)
        repo_root = repo_root.parent
    return EvalPaths(repo_root=Path.cwd().resolve())

