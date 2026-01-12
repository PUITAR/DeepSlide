from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from typing import Tuple

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from dotenv import dotenv_values

from .narrative_templates import ALL_TEMPLATE_IDS, TEMPLATES, NarrativeTemplate


# =========================
# Data structures
# =========================

@dataclass
class LogicNode:
    index: int
    role: str
    provenance: str  # "paper" | "bridge" | "rhetorical"
    text: str
    evidence: List[str]
    # 新增：每个节点的建议演讲时长占比（0~1 之间的小数，sum ≈ 1）
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
    """4 narrative variants for the same PDF."""
    chosen_template_ids: List[str]            # length = 4
    hook_template_id: str                     # the most eye-catching one
    reasons: Dict[str, str]                   # template_id -> reason
    chains: Dict[str, LogicChain]             # template_id -> chain


# =========================
# Agent
# =========================

class LogicChainAgent:
    def __init__(
        self,
        model_url: Optional[str] = None,
        model_type: Optional[str] = None,
        api_key_env: str = "DEFAULT_MODEL_API_KEY",
    ) -> None:
        """
        优先走 DEFAULT_MODEL_* 这一套环境变量：
        - DEFAULT_MODEL_API_URL
        - DEFAULT_MODEL_TYPE
        - DEFAULT_MODEL_API_KEY

        同时兼容旧字段：
        - LLM_BASE_URL
        - LLM_API_KEY
        - DEEPSEEK_API_KEY
        """
        # 仅从项目内 .env 读取配置，而不依赖外部环境变量
        # 路径固定为 deepslide/config/env/.env
        env_config: Dict[str, str] = {}
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            deepslide_root = os.path.dirname(os.path.dirname(here))  # .../deepslide
            env_path = os.path.join(deepslide_root, "config", "env", ".env")
            if os.path.isfile(env_path):
                env_config = dotenv_values(env_path)  # type: ignore[assignment]
        except Exception:
            env_config = {}

        # 1) URL：参数 > DEFAULT_MODEL_API_URL > 默认值
        self.model_url = (
            model_url
            or env_config.get("DEFAULT_MODEL_API_URL")
            or "https://api.deepseek.com"
        )

        # 2) model_type：参数 > DEFAULT_MODEL_TYPE > 默认值
        effective_model_type = (
            model_type
            or env_config.get("DEFAULT_MODEL_TYPE")
            or "deepseek-chat"
        )

        # 3) API Key：优先用传进来的 key 名，其次 DEFAULT_MODEL_API_KEY，再退回 DEEPSEEK_API_KEY
        api_key = env_config.get(api_key_env) \
            or env_config.get("DEFAULT_MODEL_API_KEY") \
            or env_config.get("DEEPSEEK_API_KEY")

        if not api_key:
            raise RuntimeError(
                "LogicChainAgent: 未找到 API Key，"
                "请在环境变量中设置 DEFAULT_MODEL_API_KEY / LLM_API_KEY / DEEPSEEK_API_KEY。"
            )

        # Generator model
        gen_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=effective_model_type,
            url=self.model_url,
            api_key=api_key,
            model_config_dict={"temperature": 0.3},
        )

        # Selector model
        sel_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=effective_model_type,
            url=self.model_url,
            api_key=api_key,
            model_config_dict={"temperature": 0.0},
        )

        # -------- Agent 对象保持不变，下面只是 prompt 增加 duration_ratio 说明 --------
        chain_sys = (
            "你是一个学术论文/技术报告的“结构化叙述 + 证据约束”专家。\n"
            "给你原文纯文本 + 叙述模板，请生成逻辑链 nodes + edges。\n\n"
            "【核心原则】\n"
            "A) 允许为了讲好故事加入 bridge/rhetorical 节点（背景解释、类比、矛盾制造、设问等）。\n"
            "B) 但凡涉及 paper 的事实/方法/实验/结论，必须标为 provenance=\"paper\"，并提供可检索的 evidence。\n"
            "C) 绝对禁止把“补充叙述”伪装成“paper 结论”：\n"
            "   - bridge/rhetorical 节点禁止写具体实验数值、具体提升倍数、具体 baseline/dataset 名称，\n"
            "     除非该信息确实在原文中出现，并且你把该节点标为 paper + evidence。\n\n"
            "【输出格式：只返回严格 JSON】\n"
            "顶层：{\"nodes\": [...], \"edges\": [...]}。\n"
            "nodes: 数组，每个元素必须包含：\n"
            "  {\"index\": int, \"role\": str, \"provenance\": \"paper\"|\"bridge\"|\"rhetorical\", "
            "\"text\": str, \"evidence\": [str, ...], \"duration_ratio\": float}\n"
            "约束：\n"
            "1) index 必须从 0 开始连续递增（不能跳号）。\n"
            "2) role 必须从模板允许的角色集合里选（允许重复；必要时可用 \"Extra\"）。\n"
            "3) provenance=\"paper\" 时：evidence 必须非空，并且每条 evidence 必须是原文中可直接找到的短片段/关键词串。\n"
            "   - evidence 不是解释，而是“能在原文里检索到的字面片段”。\n"
            "4) provenance=\"bridge\" 或 \"rhetorical\" 时：\n"
            "   - 禁止使用“本文/论文证明/实验证明/we show/we prove”这类强断言措辞。\n"
            "   - 禁止引入原文不存在的数字/指标/数据集/算法名；若必须提及则改为 provenance=\"paper\" 并给 evidence。\n"
            "5) text 要适合做 PPT 页面标题+要点（简洁、信息密度高）。\n"
            "6) 每个节点必须提供 \"duration_ratio\" 字段，取值为 0~1 之间的小数，"
            "表示该节点在整场演讲中建议占用的时间比例；所有节点的 duration_ratio 之和应接近 1.0 "
            "（例如在 0.95~1.05 之间）。\n\n"
            "edges: 数组，每个元素：\n"
            "  {\"from_index\": int, \"to_index\": int, \"reason\": str}\n"
            "reason 用一句话说明逻辑关系（因果/递进/对比/举例/总结/证据支撑等）。\n"
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
            "你是一个“叙述模板选择”专家。\n"
            "你将看到：原文纯文本、受众信息、以及12种模板ID。\n"
            "任务：选择 4 个模板ID 生成 4 种版本：\n"
            "1) 必须包含 pipeline（贴原文顺序的基准版），且必须放在 chosen[0]\n"
            "2) 必须包含 1 个最抓人眼球版本 hook（你自己判断，不能是 pipeline）\n"
            "3) 另外再选 2 个你认为最适合该受众与内容的模板\n\n"
            "只返回严格 JSON：\n"
            "{\n"
            "  \"chosen\": [\"pipeline\", \"<hook>\", \"<other1>\", \"<other2>\"],\n"
            "  \"hook\": \"<hook>\",\n"
            "  \"reasons\": {\"template_id\": \"一句话理由\", ...}\n"
            "}\n"
            "要求：chosen 长度=4，互不重复，全部来自给定模板集合；hook 必须在 chosen 且 != pipeline。\n"
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
    
    # =========================
    # Public APIs
    # =========================

    def extract_from_pdf(self, pdf_path: str) -> LogicChain:
        """兼容旧接口：默认用 pipeline 模板生成一条贴原文的链（带 provenance+evidence）。"""
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        raw_text = self._extract_text_from_pdf(pdf_path)
        if not raw_text.strip():
            raise RuntimeError("从 PDF 中未能提取到有效文本。")

        template = TEMPLATES["pipeline"]
        data = self._generate_with_validation(raw_text, template, audience_profile=None)
        return self._parse_logic_chain(data)

    def extract_options_from_pdf(
        self,
        pdf_path: str,
        audience_profile_path: Optional[str] = None,
    ) -> LogicChainOptions:
        """主入口：pipeline + hook + 2 others，共 4 种版本（均带 provenance+evidence + 自动校验修复）。"""
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        audience_profile = self._load_audience_profile(audience_profile_path)

        raw_text = self._extract_text_from_pdf(pdf_path)
        if not raw_text.strip():
            raise RuntimeError("从 PDF 中未能提取到有效文本。")

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

    # =========================
    # Audience profile
    # =========================

    def _load_audience_profile(self, audience_profile_path: Optional[str]) -> Optional[Dict[str, Any]]:
        if not audience_profile_path:
            return None
        import json
        if not os.path.isfile(audience_profile_path):
            raise FileNotFoundError(f"Audience profile JSON not found: {audience_profile_path}")
        with open(audience_profile_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                raise RuntimeError("无法解析受众配置 JSON 文件")

    def _audience_text(self, audience_profile: Optional[Dict[str, Any]]) -> str:
        import json
        if audience_profile is None:
            return "{\"audience_background\":\"普通公众（几乎无专业知识）\",\"scenario\":\"一般科普/分享演讲\"}"
        try:
            return json.dumps(audience_profile, ensure_ascii=False)
        except Exception:
            return str(audience_profile)

    # =========================
    # PDF text extraction
    # =========================

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        try:
            import PyPDF2  # type: ignore
        except Exception:
            raise RuntimeError(
                "_extract_text_from_pdf: 目前未安装 PyPDF2，"
                "请在环境中安装或自行替换为其他 PDF 解析实现。"
            )

        parts: List[str] = []
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
        return "\n".join(parts)

    # =========================
    # Template selection
    # =========================

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
        except Exception as e:
            # Fallback: never crash template selection
            print("[WARN] TemplateSelector JSON parse failed:", repr(e))
            print("[WARN] Raw output head:", content[:800])
            return self._fallback_selection()

        chosen = data.get("chosen")
        hook = data.get("hook")
        reasons = data.get("reasons") or {}

        if not isinstance(chosen, list):
            return self._fallback_selection()

        chosen = [str(x).strip() for x in chosen if str(x).strip()]
        hook = str(hook).strip() if hook else ""

        chosen = [x for x in chosen if x in TEMPLATES]
        chosen = self._dedup_keep_order(chosen)

        if "pipeline" not in chosen:
            chosen = ["pipeline"] + chosen
        if chosen and chosen[0] != "pipeline":
            chosen = ["pipeline"] + [x for x in chosen if x != "pipeline"]

        if (not hook) or hook not in TEMPLATES or hook == "pipeline":
            hook = next((x for x in chosen if x != "pipeline"), "in_medias_res")

        if hook not in chosen:
            chosen.insert(1, hook)

        chosen = self._dedup_keep_order(chosen)
        if len(chosen) > 4:
            chosen = chosen[:4]
        if len(chosen) < 4:
            defaults = ["in_medias_res", "myth_fact", "faq_defense", "case_study", "design_review", "pyramid_bluf", "imrad"]
            for d in defaults:
                if len(chosen) >= 4:
                    break
                if d not in chosen and d in TEMPLATES:
                    chosen.append(d)

        norm_reasons: Dict[str, str] = {}
        if isinstance(reasons, dict):
            for k, v in reasons.items():
                kk = str(k).strip()
                if kk in TEMPLATES:
                    norm_reasons[kk] = str(v).strip()

        norm_reasons.setdefault("pipeline", "基准版：最大程度贴合原文顺序，便于对照与复核。")
        norm_reasons.setdefault(hook, "抓眼球版：优先制造悬念/张力/强对比，以吸引听众注意力。")
        return chosen, hook, norm_reasons

    def _fallback_selection(self) -> Tuple[List[str], str, Dict[str, str]]:
        chosen = ["pipeline", "in_medias_res", "myth_fact", "case_study"]
        hook = "in_medias_res"
        reasons = {
            "pipeline": "基准版：最大程度贴合原文顺序，便于对照复核。",
            "in_medias_res": "抓眼球版：先抛最亮眼结果制造悬念，再倒叙解释。",
            "myth_fact": "纠偏版：从常见误解切入，用证据推翻并建立正确模型。",
            "case_study": "案例版：用一个具体任务流程串起来，便于非专业受众理解。",
        }
        return chosen, hook, reasons

    # =========================
    # Generation + Validation + Repair (points 1-5)
    # =========================

    def _generate_with_validation(
        self,
        raw_text: str,
        template: NarrativeTemplate,
        audience_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate ONCE, validate, print issues, and always return (no auto-repair, no crash)."""
        audience_txt = self._audience_text(audience_profile)
        src_for_llm = self._truncate_text(raw_text, max_chars=45000)

        data = self._call_llm_generate_chain_with_template(
            source_text=src_for_llm,
            template=template,
            audience_txt=audience_txt,
        )

        issues = self._validate_chain_data(data, template, source_text=src_for_llm)
        ok = (len(issues) == 0)

        # Attach validation metadata (won't break downstream parsing)
        data["_validation"] = {
            "ok": ok,
            "issue_count": len(issues),
            "issues": issues,
        }

        # Print validation summary
        if ok:
            print(f"\n[VALIDATION OK] template={template.template_id}")
        else:
            print(f"\n[VALIDATION FAILED] template={template.template_id} issues={len(issues)}")
            for it in issues[:30]:
                print(" -", it)
            if len(issues) > 30:
                print(f" ... ({len(issues) - 30} more)")

            # Optional preview: first 2 nodes for quick inspection
            try:
                nodes = data.get("nodes", [])
                print("[OUTPUT PREVIEW] first 2 nodes:")
                for n in nodes[:2]:
                    print(" ", n)
            except Exception:
                pass

        return data

    def _call_llm_generate_chain_with_template(
        self,
        source_text: str,
        template: NarrativeTemplate,
        audience_txt: str,
    ) -> Dict[str, Any]:
        user_content = (
            "请严格按下述“叙述模板定义”生成逻辑链（nodes+edges）。\n\n"
            "叙述模板定义如下：\n"
            f"{template.prompt_block()}\n"
            "受众与场景配置（JSON）：\n"
            f"{audience_txt}\n\n"
            "重要提醒：\n"
            "- 你可以为了讲好故事加入 bridge/rhetorical 节点（冲突、类比、设问等）。\n"
            "- 但任何 provenance=\"paper\" 的节点都必须给 evidence，并且 evidence 必须能在原文中直接找到。\n"
            "- bridge/rhetorical 节点不能冒充论文结论（不要写‘实验证明/本文表明’等措辞，也不要塞具体提升数字）。\n\n"
            "原文（截断后的纯文本）：\n"
            "【原文开始】\n"
            f"{source_text}\n"
            "【原文结束】\n"
        )

        user_message = BaseMessage.make_user_message(role_name="User", content=user_content)
        resp = self.chain_agent.step(user_message)
        self._record_and_print_usage(resp, label=f"generate_chain:{template.template_id}")
        content = (resp.msg.content or "").strip()
        data = self._safe_json_loads(content, err_prefix=f"ChainGen[{template.template_id}]")

        if not isinstance(data, dict):
            raise RuntimeError("LogicChainAgent: 模型返回不是 JSON 对象。")
        data.setdefault("nodes", [])
        data.setdefault("edges", [])
        return data

    def _call_llm_repair_chain(
        self,
        source_text: str,
        template: NarrativeTemplate,
        audience_txt: str,
        bad_json: Dict[str, Any],
        issues: List[str],
        attempt: int,
    ) -> Dict[str, Any]:
        import json

        issues_txt = "\n".join([f"- {x}" for x in issues[:30]])
        bad_txt = json.dumps(bad_json, ensure_ascii=False)

        user_content = (
            f"你刚才生成的 JSON 未通过校验（第 {attempt} 次修复）。请根据问题列表修复，返回新的严格 JSON。\n\n"
            "【问题列表】\n"
            f"{issues_txt}\n\n"
            "【必须遵守】\n"
            "1) provenance=\"paper\" 的节点必须带 evidence，且 evidence 必须是原文中能直接找到的字面片段/关键词串。\n"
            "2) 若某句话无法在原文中找到支撑，请将该节点改为 provenance=\"bridge\" 或 \"rhetorical\"，并移除强断言措辞。\n"
            "3) role 必须来自模板允许集合（或使用 Extra）。index 必须从0连续递增。\n"
            "4) 必须满足模板的结构 requirements（first_roles / role_min_counts / order_constraints）。\n\n"
            "【叙述模板定义】\n"
            f"{template.prompt_block()}\n"
            "【受众与场景配置（JSON）】\n"
            f"{audience_txt}\n\n"
            "【你之前的错误 JSON】\n"
            f"{bad_txt}\n\n"
            "【原文（截断后的纯文本）】\n"
            "【原文开始】\n"
            f"{source_text}\n"
            "【原文结束】\n"
        )

        user_message = BaseMessage.make_user_message(role_name="User", content=user_content)
        resp = self.chain_agent.step(user_message)
        content = (resp.msg.content or "").strip()
        data = self._safe_json_loads(content, err_prefix=f"Repair[{template.template_id}]")

        if not isinstance(data, dict):
            raise RuntimeError("LogicChainAgent: 修复返回不是 JSON 对象。")
        data.setdefault("nodes", [])
        data.setdefault("edges", [])
        return data

    # =========================
    # Validation rules (points 1-4)
    # =========================

    _ALLOWED_PROVENANCE = {"paper", "bridge", "rhetorical"}

    # Strong-claim phrases that are NOT allowed in bridge/rhetorical nodes
    _FORBIDDEN_NONPAPER_PHRASES = [
        "实验证明", "实验表明", "论文证明", "本文证明", "本文表明", "论文表明", "我们证明", "我们表明",
        "we prove", "we show", "experiments show", "our experiments show", "the paper shows",
        "the paper proves", "this paper proves", "this paper shows", "results demonstrate",
    ]

    # If a non-paper node contains both digits and metric-ish tokens, treat it as suspicious fabrication
    _METRICISH_TOKENS = [
        "qps", "recall", "准确率", "召回", "提升", "倍", "%", "ms", "延迟", "吞吐", "speedup",
        "sift", "deep1m", "hnsw", "nsg", "ivf", "faiss",
    ]

    def _validate_chain_data(self, data: Dict[str, Any], template: NarrativeTemplate, source_text: str) -> List[str]:
        issues: List[str] = []

        nodes = data.get("nodes")
        edges = data.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return ["顶层必须包含 nodes(list) 与 edges(list)。"]

        # Validate nodes basic schema and index continuity
        expected_idx = 0
        role_counts: Dict[str, int] = {}
        first_role: Optional[str] = None

        source_lower = source_text.lower()
        ratio_sum: float = 0.0
        has_ratio = False

        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                issues.append(f"nodes[{i}] 不是对象(dict)。")
                continue

            idx = n.get("index")
            role = str(n.get("role", "")).strip()
            prov = str(n.get("provenance", "")).strip()
            text = str(n.get("text", "")).strip()
            evid = n.get("evidence")
            dur_raw = n.get("duration_ratio")

            if idx is None:
                issues.append(f"nodes[{i}] 缺少 index。")
                continue
            try:
                idx_int = int(idx)
            except Exception:
                issues.append(f"nodes[{i}].index 不是整数：{idx!r}")
                continue

            if idx_int != expected_idx:
                issues.append(f"index 必须从0连续递增：期望 {expected_idx}，实际 {idx_int}。")
                expected_idx = idx_int + 1
            else:
                expected_idx += 1

            if i == 0:
                first_role = role

            allowed_roles = set(template.roles) | {"Extra"}
            if role not in allowed_roles:
                issues.append(
                    f"nodes[{i}].role={role!r} 不在允许集合中（必须从模板角色或 Extra 选择）。"
                )

            if prov not in self._ALLOWED_PROVENANCE:
                issues.append(
                    f"nodes[{i}].provenance={prov!r} 非法（必须是 paper/bridge/rhetorical）。"
                )

            if not text:
                issues.append(f"nodes[{i}].text 为空。")

            # evidence must be list[str]
            ev_list: List[str] = []
            if isinstance(evid, list):
                ev_list = [str(x) for x in evid if str(x).strip()]
            elif evid is None:
                ev_list = []
            else:
                issues.append(f"nodes[{i}].evidence 必须是数组(list)或缺省。")

            # paper evidence constraints
            if prov == "paper":
                if not ev_list:
                    issues.append(f"nodes[{i}] provenance=paper 但 evidence 为空（必须提供可检索片段）。")
                else:
                    # At least one evidence snippet should be found in source_text
                    found_any = False
                    for ev in ev_list:
                        ev_s = ev.strip()
                        if len(ev_s) < 3:
                            continue
                        if ev_s.lower() in source_lower:
                            found_any = True
                            break
                    if not found_any:
                        issues.append(
                            f"nodes[{i}] paper 节点 evidence 在原文中找不到（请改用原文短片段/关键词串）。"
                        )

            # Non-paper forbidden zones (do not fabricate paper claims)
            if prov in {"bridge", "rhetorical"}:
                low = text.lower()

                for p in self._FORBIDDEN_NONPAPER_PHRASES:
                    if p.lower() in low:
                        issues.append(
                            f"nodes[{i}] 非paper节点包含强断言措辞 {p!r}（禁止冒充论文结论）。"
                        )
                        break

                has_digit = bool(re.search(r"\d", text))
                has_metricish = any(t in low for t in self._METRICISH_TOKENS)
                if has_digit and has_metricish:
                    issues.append(
                        f"nodes[{i}] 非paper节点包含数字+指标/术语（可能捏造具体结果）；如需数字请改为 paper 并给 evidence。"
                    )

            # count roles
            if role:
                role_counts[role] = role_counts.get(role, 0) + 1

            # duration_ratio 校验（可缺省，但强烈建议提供）
            if dur_raw is not None:
                try:
                    dur_val = float(dur_raw)
                    if dur_val < 0:
                        issues.append(
                            f"nodes[{i}].duration_ratio={dur_raw!r} 为负数，应为 0~1 之间的小数。"
                        )
                    else:
                        ratio_sum += dur_val
                        has_ratio = True
                except Exception:
                    issues.append(
                        f"nodes[{i}].duration_ratio={dur_raw!r} 不是数字，请使用 0~1 之间的小数。"
                    )
            else:
                issues.append(f"nodes[{i}] 缺少 duration_ratio 字段。")

        # Validate template requirements: first role
        if first_role is None:
            issues.append("nodes 为空。")
        else:
            if first_role not in template.requirements.first_roles:
                issues.append(
                    f"首节点 role={first_role!r} 不符合模板 first_roles 要求：{template.requirements.first_roles}"
                )

        # Validate minimal role counts
        for role, min_cnt in template.requirements.role_min_counts.items():
            if role_counts.get(role, 0) < min_cnt:
                issues.append(f"模板要求 min({role})>={min_cnt}，实际为 {role_counts.get(role, 0)}。")

        # Validate order constraints (first occurrence order)
        role_first_pos: Dict[str, int] = {}
        for j, n in enumerate(nodes):
            if isinstance(n, dict):
                r = str(n.get("role", "")).strip()
                if r and r not in role_first_pos:
                    role_first_pos[r] = j
        for a, b in template.requirements.order_constraints:
            if a in role_first_pos and b in role_first_pos:
                if role_first_pos[a] > role_first_pos[b]:
                    issues.append(f"模板顺序要求：{a} 必须在 {b} 之前（当前不满足）。")
            # if missing roles, already covered by min counts in most cases

        # duration_ratio 总和检查
        if has_ratio:
            if ratio_sum <= 0:
                issues.append("所有节点的 duration_ratio 之和 <= 0，必须大于 0。")
            elif not (0.9 <= ratio_sum <= 1.1):
                issues.append(
                    f"所有节点的 duration_ratio 之和为 {ratio_sum:.3f}，"
                    "建议接近 1.0（例如在 0.95~1.05 之间）。"
                )

        # Edges: basic sanity (indices range)
        n_nodes = len(nodes)
        for k, e in enumerate(edges):
            if not isinstance(e, dict):
                issues.append(f"edges[{k}] 不是对象(dict)。")
                continue
            try:
                fi = int(e.get("from_index"))
                ti = int(e.get("to_index"))
            except Exception:
                issues.append(f"edges[{k}] from_index/to_index 必须是整数。")
                continue
            if fi < 0 or fi >= n_nodes or ti < 0 or ti >= n_nodes:
                issues.append(f"edges[{k}] 边指向越界：{fi}->{ti}（nodes={n_nodes}）。")
            reason = str(e.get("reason", "")).strip()
            if not reason:
                issues.append(f"edges[{k}].reason 为空。")

        return issues

    # =========================
    # Parsing
    # =========================

    def _parse_logic_chain(self, data: Dict[str, Any]) -> LogicChain:
        nodes_raw = data.get("nodes") or []
        edges_raw = data.get("edges") or []

        nodes: List[LogicNode] = []
        for item in nodes_raw:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index"))
                role = str(item.get("role", "")).strip()
                prov = str(item.get("provenance", "")).strip()
                text = str(item.get("text", "")).strip()
                evid = item.get("evidence", [])
                if not isinstance(evid, list):
                    evid_list = []
                else:
                    evid_list = [str(x).strip() for x in evid if str(x).strip()]

                dur_raw = item.get("duration_ratio", None)
                try:
                    dur_val: Optional[float] = (
                        float(dur_raw) if dur_raw is not None else None
                    )
                except Exception:
                    dur_val = None
            except Exception:
                continue
            if text and role and prov:
                nodes.append(
                    LogicNode(
                        index=idx,
                        role=role,
                        provenance=prov,
                        text=text,
                        evidence=evid_list,
                        duration_ratio=dur_val,
                    )
                )

        edges: List[LogicEdge] = []
        for item in edges_raw:
            if not isinstance(item, dict):
                continue
            try:
                fi = int(item.get("from_index"))
                ti = int(item.get("to_index"))
                reason = str(item.get("reason", "")).strip()
            except Exception:
                continue
            if reason:
                edges.append(LogicEdge(from_index=fi, to_index=ti, reason=reason))

        nodes.sort(key=lambda n: n.index)
        return LogicChain(nodes=nodes, edges=edges)

    # =========================
    # Utils
    # =========================

    def _safe_json_loads(self, content: str, err_prefix: str) -> Any:
        """Robust JSON loader: strips code fences, extracts outermost object, fixes trailing commas,
        and falls back to python-literal dict when needed.
        """
        content = content.replace("```json", "").replace("```", "").strip()
        import json
        import ast

        try:
            return json.loads(content)
        except Exception:
            pass

        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            raise RuntimeError(f"{err_prefix}: 无法找到 JSON 对象：{content[:200]}...")

        s = m.group(0)

        # remove trailing commas
        s2 = re.sub(r",\s*([}\]])", r"\1", s)
        try:
            return json.loads(s2)
        except Exception:
            pass

        # python literal fallback (safer than eval)
        try:
            return ast.literal_eval(s2)
        except Exception as e:
            raise RuntimeError(f"{err_prefix}: 无法解析 JSON：{s2[:300]}...") from e
    
    def _record_and_print_usage(self, resp, label: str) -> Dict[str, int]:
        """
        从 CAMEL ChatAgentResponse 里提取本次调用的 token 用量，并打印。
        兼容不同 backend 可能的字段命名差异。
        """
        info = getattr(resp, "info", {}) or {}

        usage = {}
        if isinstance(info, dict):
            usage = info.get("usage_dict") or info.get("usage") or {}

        def _to_int(x) -> int:
            try:
                return int(x)
            except Exception:
                return 0

        prompt = _to_int(usage.get("prompt_tokens") or usage.get("prompt") or usage.get("input_tokens"))
        completion = _to_int(usage.get("completion_tokens") or usage.get("completion") or usage.get("output_tokens"))
        total = _to_int(usage.get("total_tokens") or usage.get("total") or (prompt + completion))

        # 记录本次
        self.last_call_usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

        # 汇总（如果你希望跑完整个流程后看总消耗）
        if not hasattr(self, "usage_summary") or not isinstance(getattr(self, "usage_summary"), dict):
            self.usage_summary = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.usage_summary["prompt_tokens"] += prompt
        self.usage_summary["completion_tokens"] += completion
        self.usage_summary["total_tokens"] += total

        # 打印（你说“生成完后打印校验信息再输出结果”，这里就顺手打印出来）
        rid = info.get("response_id") if isinstance(info, dict) else None
        rid_str = f" response_id={rid}" if rid else ""
        print(f"[TOKEN_USAGE] {label}: prompt={prompt}, completion={completion}, total={total}{rid_str}")

        return self.last_call_usage    

    def _truncate_text(self, raw_text: str, max_chars: int = 45000) -> str:
        if len(raw_text) <= max_chars:
            return raw_text
        return raw_text[:max_chars] + "\n[...TRUNCATED...]"

    def _dedup_keep_order(self, xs: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out


# =========================
# CLI demo
# =========================

def demo(pdf_path: str, audience_profile_path: Optional[str] = None) -> None:
    agent = LogicChainAgent()

    if audience_profile_path:
        options = agent.extract_options_from_pdf(pdf_path, audience_profile_path)

        print("==== TEMPLATE CHOSEN (4) ====")
        for tid in options.chosen_template_ids:
            title = TEMPLATES[tid].title_cn if tid in TEMPLATES else tid
            tag = " (HOOK)" if tid == options.hook_template_id else ""
            reason = options.reasons.get(tid, "")
            print(f"- {tid}: {title}{tag} | {reason}")

        for tid in options.chosen_template_ids:
            chain = options.chains.get(tid)
            if not chain:
                continue
            title = TEMPLATES[tid].title_cn
            print(f"\n==== {tid} :: {title} ====")
            print("---- Nodes ----")
            for n in chain.nodes:
                ev = ""
                if n.provenance == "paper" and n.evidence:
                    ev = f" | evidence: {n.evidence[:2]}"
                ratio_str = ""
                if getattr(n, "duration_ratio", None) is not None:
                    ratio_str = f" | time_ratio: {n.duration_ratio * 100:.1f}%"
                print(f"[{n.index}] [{n.role}] ({n.provenance}) {n.text}{ev}{ratio_str}")
            print("---- Edges ----")
            for e in chain.edges:
                print(f"{e.from_index} -> {e.to_index}: {e.reason}")

    else:
        chain = agent.extract_from_pdf(pdf_path)
        print("==== PIPELINE (source-aligned) ====")
        print("---- Nodes ----")
        for n in chain.nodes:
            ev = ""
            if n.provenance == "paper" and n.evidence:
                ev = f" | evidence: {n.evidence[:2]}"
            ratio_str = ""
            if getattr(n, "duration_ratio", None) is not None:
                ratio_str = f" | time_ratio: {n.duration_ratio * 100:.1f}%"
            print(f"[{n.index}] [{n.role}] ({n.provenance}) {n.text}{ev}{ratio_str}")
        print("---- Edges ----")
        for e in chain.edges:
            print(f"{e.from_index} -> {e.to_index}: {e.reason}")

    if hasattr(agent, "usage_summary"):
        s = agent.usage_summary
        print("\n==== TOKEN SUMMARY ====")
        print(f"prompt={s.get('prompt_tokens', 0)}, completion={s.get('completion_tokens', 0)}, total={s.get('total_tokens', 0)}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  # 只生成 pipeline（贴原文）")
        print("  python -m deepslide.agents.logicchain_zhiwei.logicchain path/to/file.pdf")
        print("")
        print("  # 生成 4 种叙述模板版本（pipeline + hook + 2 others）")
        print("  python -m deepslide.agents.logicchain_zhiwei.logicchain path/to/file.pdf path/to/audience.json")
        raise SystemExit(1)

    pdf_path = sys.argv[1]
    audience_path = sys.argv[2] if len(sys.argv) >= 3 else None
    demo(pdf_path, audience_path)
