from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .chatter.ppt_requirements_collector import PPTRequirementsCollector
from .logicchain.logicchain import LogicChainAgent, LogicChainOptions, TEMPLATES


@dataclass
class CombinedOutput:
    """End-to-end result of the combined pipeline.

    - `ppt_requirements`: structured PPT config collected in part 1
    - `logic_options`: 4 narrative variants generated in part 2
    """

    ppt_requirements: Dict[str, Any]
    logic_options: LogicChainOptions


class Combine124Backend:
    """Glue layer between PPT requirements chat and logic-chain generator.

    The design assumes the following workflow:

    1. Use chatter_yangming (Streamlit UI) to talk with the user and finally
       obtain a `ppt_requirements.json` file.
    2. Prepare a textual source of the paper, e.g. a merged LaTeX main file
       produced by `project_analyzer.merge_project_to_main`.
    3. Call this backend with:
       - path to the merged LaTeX file (or any plain-text source)
       - path to the PPT requirements JSON
    4. It will:
       - convert PPT requirements → audience profile for logicchain
       - reuse LogicChainAgent (logicchain_zhiwei) to generate 4 narrative
         logic chains directly from the text, without requiring a PDF.
    """

    def __init__(
        self,
        env_path: Optional[str] = None,
        model_url: Optional[str] = None,
        model_type: Optional[str] = None,
    ) -> None:
        # Part 1: requirements collector (for potential future use inside this
        # backend; for now we mainly reuse its output JSON schema).
        self.collector = PPTRequirementsCollector(env_path=env_path)

        # Part 2: logic-chain generator (reuses central .env config).
        self.logic_agent = LogicChainAgent(
            model_url=model_url,
            model_type=model_type,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_ppt_requirements(self, json_path: str) -> Dict[str, Any]:
        """Load `ppt_requirements.json` produced by chatter_yangming.

        This is expected to be exactly the structure returned by
        `PPTRequirementsCollector.get_requirements()`.
        """

        if not os.path.isfile(json_path):
            raise FileNotFoundError(f"PPT requirements JSON not found: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    def build_audience_profile(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Map PPT requirements JSON → audience profile dict for logicchain.

        LogicChainAgent itself does not enforce a strict schema for the
        audience profile; it simply stringifies this dict and feeds it into
        the prompt. Here we perform a lightweight projection so that the
        semantics are explicit.
        """

        conv_req = requirements.get("conversation_requirements", {}) or {}

        audience_desc = conv_req.get("audience") or ""
        duration = conv_req.get("duration") or ""
        focus_sections = conv_req.get("focus_sections") or []
        style = conv_req.get("style") or ""
        special_notes = conv_req.get("special_notes") or ""

        paper_info = requirements.get("paper_info", {}) or {}

        profile: Dict[str, Any] = {
            "audience_description": audience_desc,
            "duration": duration,
            "focus_sections": focus_sections,
            "presentation_style": style,
            "special_notes": special_notes,
            # Additional context from the paper itself (if available).
            "paper_file_name": paper_info.get("file_name"),
            "paper_abstract": paper_info.get("abstract"),
        }

        # Remove keys whose value is falsy/empty to keep the prompt concise.
        return {k: v for k, v in profile.items() if v}

    def generate_logic_from_text(
        self,
        text_path: str,
        requirements: Dict[str, Any],
    ) -> CombinedOutput:
        """Core backend: plain text (e.g. merged_main.tex) → 4 logic chains.

        Parameters
        ----------
        text_path:
            Path to a text source of the paper. This can be a merged LaTeX
            main file or any UTF-8 plain-text file. The file content will be
            used as `raw_text` for the logicchain generator.
        requirements:
            Full JSON structure returned by `PPTRequirementsCollector`.
        """

        if not os.path.isfile(text_path):
            raise FileNotFoundError(f"Text source not found: {text_path}")

        with open(text_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        if not raw_text.strip():
            raise RuntimeError("generate_logic_from_text: input text is empty.")

        audience_profile = self.build_audience_profile(requirements)

        # We directly reuse LogicChainAgent's internal selection and generation
        # helpers, but feed `raw_text` instead of extracting from a PDF.
        chosen, hook, reasons = self.logic_agent._call_llm_select_templates(  # type: ignore[attr-defined]
            raw_text,
            audience_profile,
        )

        chains = {}
        for tid in chosen:
            tmpl = TEMPLATES.get(tid)
            if not tmpl:
                continue
            data = self.logic_agent._generate_with_validation(  # type: ignore[attr-defined]
                raw_text,
                tmpl,
                audience_profile,
            )
            chain = self.logic_agent._parse_logic_chain(data)  # type: ignore[attr-defined]
            chains[tid] = chain

        logic_options = LogicChainOptions(
            chosen_template_ids=chosen,
            hook_template_id=hook,
            reasons=reasons,
            chains=chains,
        )

        return CombinedOutput(
            ppt_requirements=requirements,
            logic_options=logic_options,
        )


def demo_cli() -> None:
    """Simple CLI demo for the combined backend.

    Usage (inside the repo root, e.g. via run_in_docker.sh):

        python -m deepslide.agents.combine124.backend \
            /app/path/to/merged_main.tex \
            /app/path/to/ppt_requirements.json
    """

    import sys

    if len(sys.argv) != 3:
        print(
            "Usage: python -m deepslide.agents.combine124.backend "
            "<merged_main.tex> <ppt_requirements.json>",
        )
        sys.exit(1)

    text_path = sys.argv[1]
    req_path = sys.argv[2]

    backend = Combine124Backend()
    requirements = backend.load_ppt_requirements(req_path)
    combined = backend.generate_logic_from_text(text_path, requirements)

    print("Chosen templates:", combined.logic_options.chosen_template_ids)
    print("Hook template:", combined.logic_options.hook_template_id)
    print("Reasons:")
    for tid, reason in combined.logic_options.reasons.items():
        print(f"  - {tid}: {reason}")

    # Just preview first few nodes of the hook chain for sanity.
    hook_chain = combined.logic_options.chains.get(
        combined.logic_options.hook_template_id,
    )
    if hook_chain:
        print("\n[Hook chain] First 3 nodes:")
        for node in hook_chain.nodes[:3]:
            print(f"[{node.index}] ({node.role}, {node.provenance}) {node.text}")


if __name__ == "__main__":
    demo_cli()
