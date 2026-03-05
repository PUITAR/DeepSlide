import json
import re
import concurrent.futures
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, ValidationError
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent

from app.core.model_config import sanitize_model_config
from app.core.agent_model_env import resolve_text_llm_env


class DiagramMetric(BaseModel):
    label: str = ""
    value: str = ""


class DiagramNode(BaseModel):
    id: str
    phase: str = "Execution"
    label: str
    detail: str = ""
    metrics: List[DiagramMetric] = Field(default_factory=list)
    progress: Optional[float] = None


class DiagramEdge(BaseModel):
    frm: str = Field(alias="from")
    to: str
    label: str = ""


class DiagramLayout(BaseModel):
    direction: str = "LR"


class DiagramSpec(BaseModel):
    title: str = ""
    nodes: List[DiagramNode]
    edges: List[DiagramEdge] = Field(default_factory=list)
    layout: DiagramLayout = Field(default_factory=DiagramLayout)


def _extract_first_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _norm_phase(p: str) -> str:
    t = str(p or "").strip()
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    if len(t) > 24:
        t = t[:24].rstrip()
    return t


def _coerce_progress(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, str):
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", v)
            if not m:
                return None
            v = float(m.group(1))
        v = float(v)
    except Exception:
        return None
    if v > 1.0 and v <= 100.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _ensure_unique_ids(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for i, n in enumerate(nodes):
        nn = dict(n or {})
        nid = str(nn.get("id") or "").strip()
        if not nid:
            nid = f"n{i+1}"
        base = nid
        k = 1
        while nid in seen:
            k += 1
            nid = f"{base}_{k}"
        nn["id"] = nid
        seen.add(nid)
        out.append(nn)
    return out


def _sanitize_spec_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    title = str((d or {}).get("title") or "").strip()[:90]
    nodes = list((d or {}).get("nodes") or [])
    edges = list((d or {}).get("edges") or [])
    layout = dict((d or {}).get("layout") or {})

    nodes2 = []
    for n in nodes[:8]:
        if not isinstance(n, dict):
            continue
        nn = dict(n)
        nn["label"] = str(nn.get("label") or nn.get("title") or "").strip()[:56]
        nn["detail"] = str(nn.get("detail") or nn.get("desc") or "").strip()[:140]
        nn["phase"] = _norm_phase(nn.get("phase"))
        nn["progress"] = _coerce_progress(nn.get("progress"))
        mm = nn.get("metrics") or []
        metrics_out = []
        if isinstance(mm, list):
            for m in mm[:4]:
                if isinstance(m, dict):
                    lab = str(m.get("label") or "").strip()[:18]
                    val = str(m.get("value") or "").strip()[:18]
                    if lab and val:
                        metrics_out.append({"label": lab, "value": val})
                elif isinstance(m, str):
                    s = str(m).strip()
                    if ":" in s:
                        a, b = s.split(":", 1)
                        a = a.strip()[:18]
                        b = b.strip()[:18]
                        if a and b:
                            metrics_out.append({"label": a, "value": b})
        nn["metrics"] = metrics_out
        nodes2.append(nn)

    nodes2 = [n for n in nodes2 if str(n.get("label") or "").strip()]
    nodes2 = _ensure_unique_ids(nodes2)

    if len(nodes2) < 2:
        raise ValueError("diagram spec must include >=2 nodes")
    if len(nodes2) > 6:
        nodes2 = nodes2[:6]

    ids = {n["id"] for n in nodes2}
    edges2 = []
    for e in edges[:16]:
        if not isinstance(e, dict):
            continue
        frm = str(e.get("from") or e.get("frm") or "").strip()
        to = str(e.get("to") or "").strip()
        if not frm or not to:
            continue
        if frm not in ids or to not in ids or frm == to:
            continue
        lab = str(e.get("label") or "").strip()[:40]
        edges2.append({"from": frm, "to": to, "label": lab})

    if not edges2:
        for i in range(len(nodes2) - 1):
            edges2.append({"from": nodes2[i]["id"], "to": nodes2[i + 1]["id"], "label": ""})

    direction = str(layout.get("direction") or "LR").strip().upper()
    if direction not in {"LR", "TB"}:
        direction = "LR"

    return {
        "title": title,
        "nodes": nodes2,
        "edges": edges2,
        "layout": {"direction": direction},
    }


class DiagramSpecAgent:
    @staticmethod
    def generate(
        *,
        slide_no: int,
        theme: str,
        title: str,
        subtitle: str,
        core_message: str,
        bullets: List[str],
        speech: str,
        requirements_context: str,
        max_nodes: int = 6,
    ) -> DiagramSpec:
        cfg = resolve_text_llm_env("DIAGRAM_SPEC")
        api_key = cfg.api_key
        if not api_key:
            raise RuntimeError("LLM client not initialized for diagram spec")
        try:
            try:
                model_platform = ModelPlatformType(cfg.platform_type)
            except Exception:
                model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL
            create_kwargs = {
                "model_platform": model_platform,
                "model_type": cfg.model_type,
                "api_key": api_key,
                "model_config_dict": sanitize_model_config(cfg.model_type, {"temperature": 0.2}),
            }
            if cfg.api_url:
                create_kwargs["url"] = cfg.api_url
            client = ModelFactory.create(**create_kwargs)
        except Exception:
            raise RuntimeError("LLM client init failed for diagram spec")

        max_nodes = max(2, min(6, int(max_nodes or 6)))
        payload = {
            "slide_no": int(slide_no),
            "theme": str(theme or ""),
            "requirements_context": (requirements_context or "")[:1200],
            "content": {
                "title": str(title or "")[:160],
                "subtitle": str(subtitle or "")[:220],
                "core_message": str(core_message or "")[:220],
                "bullets": [str(x)[:220] for x in (bullets or [])][:8],
            },
            "speech_excerpt": str(speech or "")[:900],
            "constraints": {
                "max_nodes": max_nodes,
                "max_edges": 12,
                "layout_directions": ["LR", "TB"],
            },
        }

        sys_base = (
            "You are a product keynote diagram designer.\n"
            "Task: output ONE SINGLE JSON object describing a diagram (nodes+edges) for ONE slide.\n"
            "Primary goal: make the process visually clear AND aesthetically striking.\n"
            "Aesthetic: high-tech research keynote / futuristic system diagram.\n"
            "- Think in terms of modules, stages, gateways, traffic flows.\n"
            "- Each node should feel like a compact card in a tech dashboard.\n"
            "- Prefer short, punchy labels and vivid, concrete details.\n"
            "- Use wording that suggests rich visuals: lanes, clusters, control plane, data plane, scoring head, router, etc.\n\n"
            "Hard constraints:\n"
            "- Output JSON ONLY (no markdown, no explanations).\n"
            f"- Produce between 2 and {max_nodes} nodes.\n"
            "- Nodes must have: id, phase, label. detail/metrics/progress are optional.\n"
            "- phase should be a short lane/cluster name (1–3 words) that can be used as a column or swimlane title.\n"
            "- Edges must reference existing node ids.\n"
            "- If edges are unclear, output a simple left-to-right chain.\n"
            "- Keep label short (<= 6 words). detail can be a short sentence.\n"
            "- Prefer labels of the form 'Verb + object' (e.g., 'Route with ef1', 'Merge top-k results').\n"
            "- For detail, describe what visually happens on the card (e.g., 'select K partitions via routing vectors').\n\n"
            "Schema:\n"
            "{\n"
            "  \"title\": str,\n"
            "  \"nodes\": [\n"
            "    {\"id\": str, \"phase\": str, \"label\": str, \"detail\": str?, \"metrics\": [{\"label\":str,\"value\":str}, ...]?, \"progress\": number?},\n"
            "    ...\n"
            "  ],\n"
            "  \"edges\": [{\"from\": str, \"to\": str, \"label\": str?}, ...],\n"
            "  \"layout\": {\"direction\": \"LR|TB\"}\n"
            "}\n"
        )

        user = json.dumps(payload, ensure_ascii=False)
        last_err = ""
        last_raw = ""
        for attempt in range(5):
            sys = sys_base
            if attempt > 0:
                tail = str(last_err or "").strip()
                if len(tail) > 600:
                    tail = tail[:600] + "…"
                sys = (
                    sys_base
                    + "\nRetry:\n"
                    + "- Your previous output was INVALID.\n"
                    + "- Fix ALL issues and output ONE valid JSON object that matches the schema.\n"
                    + (f"- Error summary: {tail}\n" if tail else "")
                )

            sys_msg = BaseMessage.make_assistant_message(role_name="System", content=sys)
            user_msg = BaseMessage.make_user_message(role_name="User", content=user)
            agent = ChatAgent(system_message=sys_msg, model=client)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(agent.step, user_msg)
                response = fut.result(timeout=30.0)
            raw = response.msg.content
            last_raw = raw
            json_text = _extract_first_json_object(raw)
            if not json_text:
                last_err = "No JSON object found."
                continue
            try:
                obj = json.loads(json_text)
            except Exception as e:
                last_err = f"JSON parse failed: {e}"
                continue
            try:
                fixed = _sanitize_spec_dict(obj if isinstance(obj, dict) else {})
                spec = DiagramSpec.model_validate(fixed)
                return spec
            except (ValidationError, ValueError) as e:
                last_err = f"Validation failed: {e}"
                continue

        raise RuntimeError(f"DiagramSpec generation failed after retries. last_err={last_err} last_raw_head={(last_raw or '')[:260]!r}")
