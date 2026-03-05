from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XREvalPaths:
    repo_root: Path

    @property
    def evaluation_root(self) -> Path:
        return self.repo_root / "experiments" / "xr"

    @property
    def dataset_cache_root(self) -> Path:
        return self.repo_root / "dataset" / ".cache"

    @property
    def outputs_cache_root(self) -> Path:
        return self.repo_root / "experiments" / ".cache" / "xr"

    @property
    def outputs_root(self) -> Path:
        return self.repo_root / "experiments" / "xr" / "outputs"

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
