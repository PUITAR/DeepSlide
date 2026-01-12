from __future__ import annotations

import json
import os
from pathlib import Path

from combine124.backend import Combine124Backend
from combine124.config import load_env


def _root() -> Path:
    return Path(__file__).resolve().parent


def main() -> None:
    samples = _root() / "samples"
    tex_path = samples / "sample.tex"
    req_path = samples / "requirements.json"

    if not tex_path.is_file() or not req_path.is_file():
        raise SystemExit("Missing sample files under combine124/samples/")

    # Load .env (end-to-end requires a working LLM backend).
    load_env()
    if not (os.getenv("DEFAULT_MODEL_API_KEY") or os.getenv("DEEPSEEK_API_KEY")):
        print("[WARN] No API key found in current env.")
        print("       Please create .env (repo root) or set COMBINE124_ENV_PATH.")
        print("       Then rerun: python -m combine124.smoke_test")
        raise SystemExit(2)

    backend = Combine124Backend()

    with open(req_path, "r", encoding="utf-8") as f:
        requirements = json.load(f)

    raw_text = tex_path.read_text(encoding="utf-8", errors="ignore")
    out = backend.run_pipeline(raw_text=raw_text, requirements=requirements)

    assert len(out.logic_options.chains) == 4, "Expected 4 chains"
    for tid in out.logic_options.chosen_template_ids:
        chain = out.logic_options.chains.get(tid)
        assert chain is not None, f"Missing chain: {tid}"
        assert len(chain.nodes) >= 1, f"Chain {tid} has no nodes"

    print("[OK] smoke_test passed")
    print("Chosen:", out.logic_options.chosen_template_ids)


if __name__ == "__main__":
    main()
