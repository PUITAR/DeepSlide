from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case1EvalPaths:
    repo_root: Path

    @property
    def evaluation_root(self) -> Path:
        return self.repo_root / "experiments" / "main"

    @property
    def outputs_cache_root(self) -> Path:
        return self.repo_root / "experiments" / ".cache" / "case1"

    @property
    def outputs_root(self) -> Path:
        return self.repo_root / "experiments" / "case1" / "outputs"

    @property
    def cache_dir(self) -> Path:
        return self.outputs_root / "caches"

    @property
    def scores_dir(self) -> Path:
        return self.outputs_root / "scores"

    @property
    def reports_dir(self) -> Path:
        return self.outputs_root / "reports"

