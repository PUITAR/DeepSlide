from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from dotenv import dotenv_values

from .narrative_templates import ALL_TEMPLATE_IDS, TEMPLATES, NarrativeTemplate


# -------------------------
# Data structures
# -------------------------


@dataclass
class LogicNode:
    index: int
    role: str
    provenance: str  # "paper" | "bridge" | "rhetorical"
    text: str
    evidence: List[str]
    duration_ratio: Optional[float] = None


@dataclass
class LogicEdge:
    from_index: int
    to_index: int
    reason: str


@dataclass
class LogicChain:
    nodes: List[LogicNode]
    edges: List[LogicEdge]


@dataclass
class LogicChainOptions:
    chosen_template_ids: List[str]
    hook_template_id: str
    reasons: Dict[str, str]
    chains: Dict[str, LogicChain]


# -------------------------
# Agent
# -------------------------


class LogicChainAgent:
    """Local copy of logicchain_zhiwei, adapted to accept plain text instead of PDF."""

    def __init__(
        self,
        model_url: Optional[str] = None,
        model_type: Optional[str] = None,
        api_key_env: str = "DEFAULT_MODEL_API_KEY",
    ) -> None:
        env_config: Dict[str, str] = {}
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            deepslide_root = os.path.dirname(os.path.dirname(here))
            env_path = os.path.join(deepslide_root, "config", "env", ".env")
            if os.path.isfile(env_path):
                env_config = dotenv_values(env_path)  # type: ignore[assignment]
        except Exception:
            env_config = {}

        self.model_url = (
            model_url
            or env_config.get("DEFAULT_MODEL_API_URL")
            or "https://api.deepseek.com"
        )
        effective_model_type = (
            model_type
            or env_config.get("DEFAULT_MODEL_TYPE")
            or "deepseek-chat"
        )
        api_key = (
            env_config.get(api_key_env)
            or env_config.get("DEFAULT_MODEL_API_KEY")
            or env_config.get("DEEPSEEK_API_KEY")
        )
        if not api_key:
            raise RuntimeError(
                "LogicChainAgent: 未找到 API Key，请在 .env 中配置 DEFAULT_MODEL_API_KEY 或 DEEPSEEK_API_KEY。"
            )

        gen_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=effective_model_type,
            url=self.model_url,
            api_key=api_key,
            model_config_dict={"temperature": 0.3},
        )
        sel_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=effective_model_type,
            url=self.model_url,
            api_key=api_key,
            model_config_dict={"temperature": 0.0},
        )

        chain_sys = (
            "你是一个学术论文/技术报告的‘结构化叙述 + 证据约束’专家。\n"
            "给你原文纯文本 + 叙述模板，请生成逻辑链 nodes + edges。\n\n"
            "【核心原则】\n"
            "A) 允许为了讲好故事加入 bridge/rhetorical 节点。\n"
            "B) paper 事实必须标 provenance=\"paper\" 且给 evidence。\n"
            "C) 禁止把补充叙述伪装成 paper 结论。\n\n"
            "【输出格式】严格 JSON: {\"nodes\": [...], \"edges\": [...]}。\n"
            "nodes: {index, role, provenance, text, evidence, duration_ratio}。\n"
            "edges: {from_index, to_index, reason}。\n"
        )
        chain_system_message = BaseMessage.make_assistant_message(
            role_name="LogicChainGenerator",
            content=chain_sys,
        )
        self.chain_agent = ChatAgent(
            system_message=chain_system_message,
            model=gen_model,
            message_window_size=10,
        )

        selector_sys = (
            "你是一个‘叙述模板选择’专家。\n"
            "你将看到：原文纯文本、受众信息、以及12种模板ID。\n"
            "选择4个：包含 pipeline（放在第一个）、1个 hook、再选2个合适的。\n"
            "只返回 JSON: {\"chosen\": [...], \"hook\": \"...\", \"reasons\": {...}}。"
        )
        selector_system_message = BaseMessage.make_assistant_message(
            role_name="NarrativeTemplateSelector",
            content=selector_sys,
        )
        self.selector_agent = ChatAgent(
            system_message=selector_system_message,
            model=sel_model,
            message_window_size=10,
        )

    # -------------------------
    # Public APIs (text-based)
    # -------------------------

    def extract_from_text(self, text_path: str) -> LogicChain:
        if not os.path.isfile(text_path):
            raise FileNotFoundError(f"Text file not found: {text_path}")
        raw_text = self._load_text_source(text_path)
        if not raw_text.strip():
            raise RuntimeError("未能从文本文件读取到有效内容。")
        template = TEMPLATES["pipeline"]
        data = self._generate_with_validation(raw_text, template, audience_profile=None)
        return self._parse_logic_chain(data)

    def extract_options_from_text(
        self,
        text_path: str,
        audience_profile: Optional[Dict[str, Any]] = None,
    ) -> LogicChainOptions:
        if not os.path.isfile(text_path):
            raise FileNotFoundError(f"Text file not found: {text_path}")
        raw_text = self._load_text_source(text_path)
        if not raw_text.strip():
            raise RuntimeError("未能从文本文件读取到有效内容。")
        chosen, hook, reasons = self._call_llm_select_templates(raw_text, audience_profile)
        chains: Dict[str, LogicChain] = {}
        for tid in chosen:
            tmpl = TEMPLATES.get(tid)
            if not tmpl:
                continue
            data = self._generate_with_validation(raw_text, tmpl, audience_profile)
            chains[tid] = self._parse_logic_chain(data)
        return LogicChainOptions(
            chosen_template_ids=chosen,
            hook_template_id=hook,
            reasons=reasons,
            chains=chains,
        )

    # -------------------------
    # Audience helpers
    # -------------------------

    def _audience_text(self, audience_profile: Optional[Dict[str, Any]]) -> str:
        import json
        if audience_profile is None:
            return "{\"audience_background\":\"普通公众（几乎无专业知识）\",\"scenario\":\"一般科普/分享演讲\"}"
        try:
            return json.dumps(audience_profile, ensure_ascii=False)
        except Exception:
            return str(audience_profile)

    # -------------------------
    # Text loading (instead of PDF)
    # -------------------------

    def _load_text_source(self, text_path: str) -> str:
        with open(text_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    # -------------------------
    # Template selection
    # -------------------------

    def _call_llm_select_templates(
        self,
        raw_text: str,
        audience_profile: Optional[Dict[str, Any]],
    ) -> Tuple[List[str], str, Dict[str, str]]:
        template_briefs = []
        for tid in ALL_TEMPLATE_IDS:
            t = TEMPLATES[tid]
            template_briefs.append(f"- {t.template_id}: {t.title_cn} | {t.one_liner}")
        template_briefs_txt = "\n".join(template_briefs)

        audience_txt = self._audience_text(audience_profile)
        src_for_llm = self._truncate_text(raw_text, max_chars=45000)

        user_content = (
            "请选择 4 个叙述模板用于生成 4 种版本。\n\n"
            f"受众与场景(audience profile JSON):\n{audience_txt}\n\n"
            "可选模板列表（ID不可拼错）：\n"
            f"{template_briefs_txt}\n\n"
            "原文（截断后的纯文本）：\n"
            "【原文开始】\n"
            f"{src_for_llm}\n"
            "【原文结束】\n"
        )

        user_message = BaseMessage.make_user_message(role_name="User", content=user_content)
        resp = self.selector_agent.step(user_message)
        self._record_and_print_usage(resp, label="select_templates")
        content = (resp.msg.content or "").strip()

        try:
            data = self._safe_json_loads(content, err_prefix="TemplateSelector")
        except Exception:
            return self._fallback_selection()

        chosen = data.get("chosen")
        hook = data.get("hook")
        reasons = data.get("reasons") or {}

        return self._normalize_selection(chosen, hook, reasons)

    def _fallback_selection(self) -> Tuple[List[str], str, Dict[str, str]]:
        chosen = ["pipeline", "storytelling", "pyramid_bluf", "monroe"]
        hook = "storytelling"
        reasons = {
            "pipeline": "贴合原文顺序的基准版",
            "storytelling": "更抓人、能当 hook",
            "pyramid_bluf": "结论先行、适合决策类",
            "monroe": "说服动员、适合演讲",
        }
        return chosen, hook, reasons

    def _normalize_selection(
        self,
        chosen: Any,
        hook: Any,
        reasons: Dict[str, str],
    ) -> Tuple[List[str], str, Dict[str, str]]:
        if not isinstance(chosen, list):
            return self._fallback_selection()
        chosen_ids: List[str] = []
        for tid in chosen:
            if isinstance(tid, str) and tid in ALL_TEMPLATE_IDS and tid not in chosen_ids:
                chosen_ids.append(tid)
        if "pipeline" not in chosen_ids:
            chosen_ids = ["pipeline"] + chosen_ids
        chosen_ids = chosen_ids[:4]
        while len(chosen_ids) < 4:
            for cand in ALL_TEMPLATE_IDS:
                if cand not in chosen_ids:
                    chosen_ids.append(cand)
                if len(chosen_ids) == 4:
                    break
        hook_id = hook if isinstance(hook, str) and hook in chosen_ids and hook != "pipeline" else None
        if not hook_id:
            for tid in chosen_ids:
                if tid != "pipeline":
                    hook_id = tid
                    break
        if not hook_id:
            hook_id = "storytelling" if "storytelling" in chosen_ids else chosen_ids[0]
        for tid in chosen_ids:
            if tid not in reasons:
                reasons[tid] = "自动补全：模板被选中。"
        return chosen_ids, hook_id, reasons

    # -------------------------
    # Generation + validation
    # -------------------------

    def _generate_with_validation(
        self,
        raw_text: str,
        template: NarrativeTemplate,
        audience_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        user_content = self._build_generation_prompt(raw_text, template, audience_profile)
        user_message = BaseMessage.make_user_message(role_name="User", content=user_content)
        resp = self.chain_agent.step(user_message)
        self._record_and_print_usage(resp, label=f"gen_{template.template_id}")
        content = (resp.msg.content or "").strip()
        data = self._safe_json_loads(content, err_prefix="LogicChainGen")
        issues = self._validate_chain_data(data, raw_text, template)
        if not issues:
            return data
        repair_prompt = self._build_repair_prompt(content, issues, template)
        repair_msg = BaseMessage.make_user_message(role_name="User", content=repair_prompt)
        repair_resp = self.chain_agent.step(repair_msg)
        self._record_and_print_usage(repair_resp, label=f"repair_{template.template_id}")
        repaired = self._safe_json_loads((repair_resp.msg.content or "").strip(), err_prefix="LogicChainRepair")
        repair_issues = self._validate_chain_data(repaired, raw_text, template)
        return repaired if not repair_issues else data

    def _build_generation_prompt(
        self,
        raw_text: str,
        template: NarrativeTemplate,
        audience_profile: Optional[Dict[str, Any]],
    ) -> str:
        audience_txt = self._audience_text(audience_profile)
        tmpl_block = template.prompt_block()
        src = self._truncate_text(raw_text, max_chars=45000)
        return (
            "请按给定模板生成带 provenance+evidence 的逻辑链。\n\n"
            f"受众与场景(JSON): {audience_txt}\n\n"
            f"模板定义:\n{tmpl_block}\n"
            "输出严格 JSON，顶层 {\"nodes\": [...], \"edges\": [...]}。不要有 markdown。\n\n"
            "原文（截断）:\n"
            "【开始】\n"
            f"{src}\n"
            "【结束】\n"
        )

    def _build_repair_prompt(self, bad_json: str, issues: List[str], template: NarrativeTemplate) -> str:
        issue_txt = "\n".join([f"- {it}" for it in issues])
        return (
            "上一次生成未通过校验，请修复。\n"
            "问题列表:\n"
            f"{issue_txt}\n\n"
            "请输出修复后的严格 JSON（不要 markdown）。原输出如下：\n"
            f"{bad_json}\n"
        )

    # -------------------------
    # Validation
    # -------------------------

    def _validate_chain_data(
        self,
        data: Dict[str, Any],
        raw_text: str,
        template: NarrativeTemplate,
    ) -> List[str]:
        issues: List[str] = []
        nodes = data.get("nodes") if isinstance(data, dict) else None
        edges = data.get("edges") if isinstance(data, dict) else None
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return ["顶层必须包含 nodes(list) 和 edges(list)"]

        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                issues.append(f"nodes[{i}] 不是对象")
                continue
            if n.get("index") != i:
                issues.append(f"nodes[{i}] index 非连续")
            role = n.get("role")
            if role not in template.roles + ["Extra"]:
                issues.append(f"nodes[{i}] role 非模板允许值: {role}")
            prov = n.get("provenance")
            if prov not in ("paper", "bridge", "rhetorical"):
                issues.append(f"nodes[{i}] provenance 非法: {prov}")
            evid = n.get("evidence")
            if prov == "paper" and (not isinstance(evid, list) or not evid):
                issues.append(f"nodes[{i}] paper 缺少 evidence")
            if prov in ("bridge", "rhetorical"):
                txt = (n.get("text") or "").lower()
                if re.search(r"(we show|we prove|实验证明|本文证明)", txt):
                    issues.append(f"nodes[{i}] bridge/rhetorical 含强断言")
            dur = n.get("duration_ratio")
            if dur is None or not isinstance(dur, (int, float)):
                issues.append(f"nodes[{i}] 缺少 duration_ratio")

        try:
            total = sum([float(n.get("duration_ratio") or 0) for n in nodes])
            if not 0.8 <= total <= 1.2:
                issues.append(f"duration_ratio 总和异常: {total:.2f}")
        except Exception:
            issues.append("duration_ratio 计算失败")

        roles_seen = [n.get("role") for n in nodes if isinstance(n, dict)]
        if roles_seen:
            first_role = roles_seen[0]
            if template.requirements.first_roles and first_role not in template.requirements.first_roles:
                issues.append(f"首节点角色不满足: {first_role}")
        for role, min_cnt in template.requirements.role_min_counts.items():
            if roles_seen.count(role) < min_cnt:
                issues.append(f"角色 {role} 计数不足 {min_cnt}")
        for a, b in template.requirements.order_constraints:
            try:
                if roles_seen.index(a) > roles_seen.index(b):
                    issues.append(f"顺序要求失败: {a} 应在 {b} 之前")
            except ValueError:
                issues.append(f"顺序要求角色缺失: {a} 或 {b}")

        node_count = len(nodes)
        for i, e in enumerate(edges):
            if not isinstance(e, dict):
                issues.append(f"edges[{i}] 不是对象")
                continue
            fi = e.get("from_index")
            ti = e.get("to_index")
            if not isinstance(fi, int) or not isinstance(ti, int):
                issues.append(f"edges[{i}] index 非整数")
            else:
                if fi < 0 or fi >= node_count or ti < 0 or ti >= node_count:
                    issues.append(f"edges[{i}] index 越界")
            if not e.get("reason"):
                issues.append(f"edges[{i}] 缺少 reason")

        return issues

    # -------------------------
    # Parsing
    # -------------------------

    def _parse_logic_chain(self, data: Dict[str, Any]) -> LogicChain:
        nodes_raw = data.get("nodes") or []
        edges_raw = data.get("edges") or []
        nodes: List[LogicNode] = []
        edges: List[LogicEdge] = []
        for n in nodes_raw:
            nodes.append(
                LogicNode(
                    index=int(n.get("index", 0)),
                    role=str(n.get("role", "")),
                    provenance=str(n.get("provenance", "")),
                    text=str(n.get("text", "")),
                    evidence=[str(x) for x in n.get("evidence", [])],
                    duration_ratio=float(n.get("duration_ratio", 0.0)),
                )
            )
        for e in edges_raw:
            edges.append(
                LogicEdge(
                    from_index=int(e.get("from_index", 0)),
                    to_index=int(e.get("to_index", 0)),
                    reason=str(e.get("reason", "")),
                )
            )
        return LogicChain(nodes=nodes, edges=edges)

    # -------------------------
    # Utils
    # -------------------------

    def _safe_json_loads(self, content: str, err_prefix: str) -> Dict[str, Any]:
        import json
        cleaned = content.strip()
        cleaned = re.sub(r"^```json", "", cleaned)
        cleaned = re.sub(r"^```", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except Exception as e:
            raise ValueError(f"{err_prefix}: JSON 解析失败: {e}")

    def _truncate_text(self, text: str, max_chars: int) -> str:
        return text if len(text) <= max_chars else text[:max_chars]

    def _record_and_print_usage(self, resp, label: str) -> None:
        usage = getattr(resp, "usage", None)
        if not usage:
            return
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        total = getattr(usage, "total_tokens", None)
        print(f"[TOKEN_USAGE][{label}] prompt={prompt} completion={completion} total={total}")


__all__ = [
    "LogicNode",
    "LogicEdge",
    "LogicChain",
    "LogicChainOptions",
    "LogicChainAgent",
    "TEMPLATES",
    "ALL_TEMPLATE_IDS",
]
