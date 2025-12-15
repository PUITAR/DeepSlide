import os
import re
import json
import math
import hashlib
from typing import Dict, List, Tuple, Optional
import sys

from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent
from dotenv import load_dotenv

from colorama import Fore

# project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    print(f'Add {ROOT} to sys.path')
    sys.path.insert(0, ROOT)

class Templater:
    def __init__(self, config_dir: str, embdding_dir: str, template_dir: str):
        self.config_dir = config_dir
        env_path = os.path.join(config_dir, "env", ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)

        self.embedding_dir = embdding_dir
        self.template_dir = template_dir

        self.llm = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-chat",
            url="https://api.deepseek.com",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
        )

    def _create_agent(self, system_content: str) -> ChatAgent:
        sys_msg = BaseMessage.make_assistant_message(
            role_name="Templater Agent",
            content=system_content,
        )
        return ChatAgent(sys_msg, model=self.llm, tools=[])

    def _hash_embed(self, text: str, dim: int = 256) -> List[float]:
        tokens = re.findall(r"\b\w+\b", text.lower())
        v = [0.0] * dim
        for w in tokens:
            h = int(hashlib.sha1(w.encode("utf-8")).hexdigest(), 16)
            v[h % dim] += 1.0
        n = math.sqrt(sum(x * x for x in v))
        if n > 0:
            v = [x / n for x in v]
        return v


    def _embed_query_sentence(self, text: str) -> Optional[List[float]]:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(os.getenv("SENTENCE_MODEL", "template/rag/all-MiniLM-L6-v2"))
            vec = model.encode([text], normalize_embeddings=True)[0]
            return list(map(float, vec))
        except Exception:
            return None

    def _cosine(self, a: List[float], b: List[float]) -> float:
        num = sum(x * y for x, y in zip(a, b))
        da = math.sqrt(sum(x * x for x in a))
        db = math.sqrt(sum(y * y for y in b))
        if da == 0.0 or db == 0.0:
            return 0.0
        return num / (da * db)

    def _load_embeddings_path(self) -> Optional[str]:
        p = os.path.join(self.embedding_dir, "beamer_descriptions.tensordict.pt")
        return p if os.path.exists(p) else None

    def _load_embeddings(self) -> Tuple[Dict[str, List[float]], int]:
        p = self._load_embeddings_path()
        if p is None:
            base_dir = self.template_dir
            data = {}
            for name in os.listdir(base_dir):
                d = os.path.join(base_dir, name, "description.md")
                if os.path.exists(d):
                    try:
                        text = open(d, "r", encoding="utf-8").read().strip()
                        data[name] = text
                    except Exception:
                        pass
            vecs = {k: self._hash_embed(v) for k, v in data.items()}
            dim = len(next(iter(vecs.values()))) if vecs else 256
            return vecs, dim
        if p.endswith(".pt"):
            try:
                import torch
                td = torch.load(p)
                vecs = {k: list(map(float, v.tolist())) for k, v in td.items()}
                dim = len(next(iter(vecs.values()))) if vecs else 0
                return vecs, dim
            except Exception:
                return {}, 0
        return {}, 0

    def _load_template_descriptions(self, names: List[str]) -> Dict[str, str]:
        base_dir = self.template_dir
        result = {}
        for n in names:
            p = os.path.join(base_dir, n, "description.md")
            if os.path.exists(p):
                try:
                    result[n] = open(p, "r", encoding="utf-8").read().strip()
                except Exception:
                    result[n] = ""
            else:
                result[n] = ""
        return result

    def select(self, user_description: str, top_k: int = 3) -> str:
        agent = self._create_agent(
            "Rewrite the user template description into a single concise English paragraph. Return only the rewritten description without any extra markers."
        )
        usr_msg = BaseMessage.make_user_message(role_name="User", content=user_description)
        try:
            response = agent.step(usr_msg)
            rewritten = response.msg.content.strip()
        except Exception:
            rewritten = user_description.strip()
        vecs, dim = self._load_embeddings()
        candidates: List[str]
        if vecs and dim > 0:
            q = self._embed_query_sentence(rewritten)
            if q is None or len(q) != dim:
                q = self._hash_embed(rewritten, dim=dim)
            scores = [(name, self._cosine(q, vec)) for name, vec in vecs.items()]
            scores.sort(key=lambda x: x[1], reverse=True)
            candidates = [n for n, _ in scores[:max(1, top_k)]]
        else:
            candidates = []
        descs = self._load_template_descriptions(candidates)
        info = []
        for n in candidates:
            info.append(f"Name: {n}\n{descs.get(n, '')}")
        selection_prompt = (
            "You are selecting the most relevant beamer template. Here is the rewritten need:\n" + rewritten +
            "\n\nCandidates:\n" + "\n\n".join(info) +
            "\n\nReturn only the best template name."
        )
        agent2 = self._create_agent("Select the best matching template name from the provided candidates. Return only the name.")
        usr2 = BaseMessage.make_user_message(role_name="User", content=selection_prompt)
        try:
            res2 = agent2.step(usr2)
            name = res2.msg.content.strip()
        except Exception:
            name = candidates[0] if candidates else ""
        name = re.sub(r"[^\w\-]+", "", name)

        # print(f"Selected template: {name}")

        return name

    def modify(self, base_dir: str, user_need: str) -> Dict[str, str]:
        base_tex = os.path.join(base_dir, "base.tex")
        if not os.path.exists(base_tex):
            return {"success": "false", "message": "base.tex not found"}
        current = open(base_tex, "r", encoding="utf-8").read()
        sys = (
            "You are a LaTeX Beamer template stylist. Modify base.tex to meet the user style request. "
            "Keep document structure intact, preserve title/content/ref includes, and avoid removing existing essential settings unless required. "
            "Return the full updated base.tex wrapped in <base></base> tags."
        )
        agent = self._create_agent(sys)
        prompt = (
            "User need:\n" + user_need + "\n\nCurrent base.tex:\n" + current
        )
        usr = BaseMessage.make_user_message(role_name="User", content=prompt)
        try:
            res = agent.step(usr)
            content = res.msg.content
        except Exception:
            content = "<base>\n" + current + "\n</base>"

        print(Fore.YELLOW + f"Agent response: \n" + Fore.RESET, content)

        m = re.search(r"<base>([\s\S]*?)</base>", content)
        if not m:
            m = re.search(r"<base>([\s\S]*?)</base>", content)
        updated = m.group(1).strip() if m else current
        open(base_tex, "w", encoding="utf-8").write(updated)
        return {"success": "true", "message": "updated", "path": base_tex}
