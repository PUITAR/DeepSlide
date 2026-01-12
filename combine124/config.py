from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _repo_root() -> Path:
    # combine124/config.py -> combine124/ -> repo root
    return Path(__file__).resolve().parent.parent


def resolve_env_path(env_path: Optional[str] = None) -> Optional[str]:
    """Resolve .env path with precedence:

    1) explicit env_path
    2) env var COMBINE124_ENV_PATH
    3) repo root ./.env
    4) repo root ./config/env/.env
    """

    candidates = []
    if env_path:
        candidates.append(Path(env_path))

    env_from_var = os.getenv("COMBINE124_ENV_PATH")
    if env_from_var:
        candidates.append(Path(env_from_var))

    root = _repo_root()
    candidates.append(root / ".env")
    candidates.append(root / "config" / "env" / ".env")
    # Backward-compatible with existing repo layout
    candidates.append(root / "deepslide" / "config" / "env" / ".env")

    for p in candidates:
        try:
            if p.is_file():
                return str(p)
        except Exception:
            continue
    return None


def load_env(env_path: Optional[str] = None, override: bool = False) -> Optional[str]:
    """Load dotenv into process env and return the path used (or None)."""

    resolved = resolve_env_path(env_path)
    if not resolved:
        return None

    load_dotenv(dotenv_path=resolved, override=override)
    return resolved


def getenv_required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val
