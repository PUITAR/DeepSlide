from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RoleEvalPaths:
    repo_root: Path

    @property
    def evaluation_root(self) -> Path:
        return self.repo_root / "experiments" / "role"

    @property
    def dataset_cache_root(self) -> Path:
        return self.repo_root / "dataset" / ".cache"

    @property
    def outputs_cache_root(self) -> Path:
        return self.repo_root / "experiments" / ".cache" / "role"

    @property
    def outputs_root(self) -> Path:
        return self.repo_root / "experiments" / "role" / "outputs"

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
