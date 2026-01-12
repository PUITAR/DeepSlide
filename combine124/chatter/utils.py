from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple


def extract_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from model response.

    The chatter prompt enforces a single JSON block when done.
    """

    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return None
    try:
        return json.loads(json_match.group(0))
    except Exception:
        return None


def validate_requirements(requirements: Dict[str, Any]) -> Tuple[bool, str]:
    required_fields = ["audience", "duration"]
    for field in required_fields:
        if not requirements.get(field):
            return False, f"Missing required field: {field}"

    focus = requirements.get("focus_sections")
    if focus is not None and not isinstance(focus, list):
        return False, "focus_sections must be a list"

    return True, "Validation passed"
