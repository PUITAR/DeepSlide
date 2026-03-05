import json
import concurrent.futures
import logging
from typing import Any, Dict, List, Optional

from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent

from app.core.model_config import sanitize_model_config
from app.core.agent_model_env import resolve_text_llm_env

logger = logging.getLogger(__name__)


def select_templates_via_llm(
    all_template_ids: List[str],
    abstract_text: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> List[str]:
    pool = [str(x) for x in all_template_ids if isinstance(x, str)]
    if "pipeline" not in pool:
        pool = ["pipeline"] + pool

    context = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in (conversation_history or [])[-6:]])
    ctx = str(abstract_text or "")[:1200]

    system_prompt = (
        "You are a narrative template selector. "
        "You will receive paper abstract + user requirements + template ID list. "
        "Pick 4 template IDs for logic-chain generation:\n"
        "1) Must include pipeline and put it at chosen[0].\n"
        "2) Must include exactly one hook version (hook must be in chosen and must not be pipeline).\n"
        "3) Pick 2 additional distinct templates from the given pool.\n"
        "Return STRICT JSON ONLY:\n"
        "{\n  \"chosen\": [\"pipeline\", \"<hook>\", \"<other1>\", \"<other2>\"],\n  \"hook\": \"<hook>\",\n  \"reasons\": {\"template_id\": \"one-line reason\", ...}\n}"
    )

    user_prompt = json.dumps(
        {
            "abstract": ctx,
            "recent_messages": context,
            "template_pool": pool,
        },
        ensure_ascii=False,
    )

    cfg = resolve_text_llm_env("TEMPLATE_RECOMMENDER")
    api_key = cfg.api_key
    if not api_key:
        logger.warning("[template_recommender] missing API key; using fallback templates")
        fallback = ["pipeline", "in_medias_res", "pyramid_bluf", "faq_defense"]
        out = [x for x in fallback if x in pool]
        while len(out) < 4:
            for x in pool:
                if x not in out:
                    out.append(x)
                    break
        return out[:4]

    try:
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
            raise

        sys_msg = BaseMessage.make_assistant_message(role_name="System", content=system_prompt)
        user_msg = BaseMessage.make_user_message(role_name="User", content=user_prompt)
        agent = ChatAgent(system_message=sys_msg, model=client)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(agent.step, user_msg)
            response = fut.result(timeout=30.0)
        raw = response.msg.content
        import re

        m = re.search(r"\{[\s\S]*\}", str(raw or ""))
        if not m:
            raise RuntimeError("bad response")
        data = json.loads(m.group(0))
        chosen = data.get("chosen")
        if not isinstance(chosen, list):
            raise RuntimeError("bad chosen")
        chosen = [str(x) for x in chosen]
        chosen = [x for x in chosen if x in pool]
        if not chosen or chosen[0] != "pipeline":
            chosen = ["pipeline"] + [x for x in chosen if x != "pipeline"]
        chosen = chosen[:4]
        if len(set(chosen)) != len(chosen):
            dedup = []
            for x in chosen:
                if x not in dedup:
                    dedup.append(x)
            chosen = dedup
        while len(chosen) < 4:
            for x in pool:
                if x not in chosen:
                    chosen.append(x)
                    break
        logger.info(f"[template_recommender] llm chosen={chosen[:4]}")
        return chosen[:4]
    except Exception as e:
        logger.warning(f"[template_recommender] llm failed: {e}; using fallback templates")
        fallback = ["pipeline", "in_medias_res", "pyramid_bluf", "faq_defense"]
        out = [x for x in fallback if x in pool]
        while len(out) < 4:
            for x in pool:
                if x not in out:
                    out.append(x)
                    break
        return out[:4]
