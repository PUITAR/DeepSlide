from __future__ import annotations

from typing import Any, Dict, List, Optional

from .camel_client import CamelAIClient
from .utils import extract_json_from_response, validate_requirements


class PPTRequirementsCollector:
    """Multi-turn requirements collector.

    Stable output schema (top-level keys):
    - audience: str
    - duration: str
    - focus_sections: list[str] (optional)
    - style: str (optional)
    - special_notes: str (optional)

    Extra keys for traceability:
    - paper_info, conversation_history
    """

    def __init__(self, env_path: Optional[str] = None):
        self.camel_client = CamelAIClient(env_path)
        self.paper_file_name = ""
        self.paper_project_dir = ""
        self.paper_main_tex = ""
        self.paper_abstract = ""
        self.merged_main_path = ""

        self.conversation_history: List[Dict[str, str]] = []
        self._requirements: Dict[str, Any] = {
            "audience": "",
            "duration": "",
            "focus_sections": [],
            "style": "",
            "special_notes": "",
        }
        self.is_confirmed = False

    def set_paper_file(self, file_name: str) -> None:
        self.paper_file_name = file_name

    def set_paper_project(self, project_dir: str, main_tex_path: Optional[str] = None, merged_main_path: Optional[str] = None) -> None:
        self.paper_project_dir = project_dir or ""
        self.paper_main_tex = main_tex_path or ""
        self.merged_main_path = merged_main_path or ""

    def set_paper_abstract(self, abstract_text: str) -> None:
        self.paper_abstract = abstract_text or ""

    def prime_context(self) -> None:
        self.camel_client.set_context(
            {
                "file_name": self.paper_file_name,
                "project_dir": self.paper_project_dir,
                "main_tex": self.paper_main_tex,
                "merged_main": self.merged_main_path,
                "abstract": self.paper_abstract,
            }
        )

    def process_user_input(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})

        ai_response = self.camel_client.get_response(user_input)

        extracted = extract_json_from_response(ai_response)
        if extracted:
            # Merge extracted stable fields
            for k in ["audience", "duration", "focus_sections", "style", "special_notes"]:
                if k in extracted:
                    self._requirements[k] = extracted.get(k)

            ok, _ = validate_requirements(self._requirements)
            if ok:
                self.is_confirmed = True

        self.conversation_history.append({"role": "assistant", "content": ai_response})
        return ai_response

    def get_requirements(self) -> Dict[str, Any]:
        # Ensure stable keys exist
        out = {
            "audience": self._requirements.get("audience") or "",
            "duration": self._requirements.get("duration") or "",
            "focus_sections": self._requirements.get("focus_sections") or [],
            "style": self._requirements.get("style") or "",
            "special_notes": self._requirements.get("special_notes") or "",
            "paper_info": {
                "file_name": self.paper_file_name,
                "project_dir": self.paper_project_dir,
                "main_tex": self.paper_main_tex,
                "merged_main": self.merged_main_path,
                "abstract": self.paper_abstract,
            },
            "conversation_history": self.conversation_history,
        }
        return out

    def confirm_requirements(self) -> None:
        self.is_confirmed = True

    def reset(self) -> None:
        self.conversation_history = []
        self._requirements = {
            "audience": "",
            "duration": "",
            "focus_sections": [],
            "style": "",
            "special_notes": "",
        }
        self.is_confirmed = False
        self.paper_file_name = ""
        self.paper_project_dir = ""
        self.paper_main_tex = ""
        self.paper_abstract = ""
        self.merged_main_path = ""
        self.camel_client.clear_memory()


__all__ = ["PPTRequirementsCollector"]
