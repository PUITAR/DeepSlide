import os
import importlib.util
import sys
from typing import Any, Dict, List, Tuple


def load_lgcc_templates() -> Tuple[List[str], Dict[str, Any]]:
    path = os.path.join(os.path.dirname(__file__), "narrative_templates.py")
    spec = importlib.util.spec_from_file_location("narrative_templates", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load narrative templates")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    all_ids = list(getattr(mod, "ALL_TEMPLATE_IDS"))
    templates = dict(getattr(mod, "TEMPLATES"))
    return all_ids, templates
