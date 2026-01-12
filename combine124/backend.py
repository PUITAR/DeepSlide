from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from .chatter import PPTRequirementsCollector
from .logicchain import LogicChainOptions, LogicChainAgent


@dataclass
class CombinedOutput:
    ppt_requirements: Dict[str, Any]
    logic_options: LogicChainOptions


class Combine124Backend:
    """End-to-end glue: requirements + tex -> 4 logic chains + speech ratios."""

    def __init__(
        self,
        env_path: Optional[str] = None,
        model_url: Optional[str] = None,
        model_type: Optional[str] = None,
    ) -> None:
        self.collector = PPTRequirementsCollector(env_path=env_path)
        self.logic_agent = LogicChainAgent(env_path=env_path, model_url=model_url, model_type=model_type)

    # -------------------------
    # IO
    # -------------------------

    def load_requirements(self, path_or_dict: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(path_or_dict, dict):
            return path_or_dict

        path = path_or_dict
        if not os.path.isfile(path):
            raise FileNotFoundError(f"requirements json not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_tex(self, path_or_bytes: Union[str, bytes]) -> str:
        if isinstance(path_or_bytes, bytes):
            return path_or_bytes.decode("utf-8", errors="ignore")

        path = path_or_bytes
        if not os.path.isfile(path):
            raise FileNotFoundError(f"tex/text not found: {path}")
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    # -------------------------
    # Mapping
    # -------------------------

    def build_audience_profile(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "audience": requirements.get("audience") or "",
            "duration": requirements.get("duration") or "",
            "focus_sections": requirements.get("focus_sections") or [],
            "style": requirements.get("style") or "",
            "constraints": requirements.get("special_notes") or "",
        }

    # -------------------------
    # Pipeline
    # -------------------------

    def run_pipeline(self, raw_text: str, requirements: Dict[str, Any]) -> CombinedOutput:
        if not raw_text.strip():
            raise RuntimeError("run_pipeline: raw_text is empty")

        audience_profile = self.build_audience_profile(requirements)
        options = self.logic_agent.generate_options(raw_text=raw_text, audience_profile=audience_profile)
        return CombinedOutput(
            ppt_requirements=requirements,
            logic_options=options,
        )

    def run_pipeline_from_files(self, tex_path: str, requirements_json_path: str) -> CombinedOutput:
        requirements = self.load_requirements(requirements_json_path)
        raw_text = self.read_tex(tex_path)
        return self.run_pipeline(raw_text=raw_text, requirements=requirements)


def _cli() -> None:
    import sys

    if len(sys.argv) != 3:
        print("Usage: python -m combine124.backend <tex_path> <requirements_json_path>")
        raise SystemExit(1)

    tex_path = sys.argv[1]
    req_path = sys.argv[2]

    backend = Combine124Backend()
    combined = backend.run_pipeline_from_files(tex_path, req_path)

    print("Chosen templates:", combined.logic_options.chosen_template_ids)
    print("Hook template:", combined.logic_options.hook_template_id)


if __name__ == "__main__":
    _cli()
