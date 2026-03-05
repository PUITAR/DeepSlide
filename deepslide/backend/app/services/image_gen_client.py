from __future__ import annotations

import base64
import logging
import os
import re
import time
import urllib.request
from typing import List, Optional, Tuple

from app.core.agent_model_env import resolve_img_env

logger = logging.getLogger(__name__)


class ImageGenClient:
    def __init__(self, agent: str = "VFX_IMG"):
        self.agent = str(agent or "VFX_IMG")
        self.cfg = resolve_img_env(self.agent)
        self.last_error: str = ""

    def is_enabled(self) -> bool:
        return bool(str(self.cfg.api_key or "").strip())

    def generate(self, *, prompt: str, size: Tuple[int, int], fmt: str = "png", n: int = 1) -> List[bytes]:
        self.last_error = ""
        if not self.is_enabled():
            return []
        platform = str(self.cfg.platform_type or "").strip().lower() or "openai"
        if platform not in {"openai", "openai_compatible", "openai-compatible"}:
            try:
                logger.warning(f"[img_gen] unsupported platform agent={self.agent} platform={platform!r}")
            except Exception:
                pass
            return []
        try:
            from openai import OpenAI
        except Exception as e:
            try:
                logger.warning(f"[img_gen] openai sdk missing agent={self.agent}: {e}")
            except Exception:
                pass
            return []

        w, h = int(size[0]), int(size[1])
        w = max(64, min(2048, w))
        h = max(64, min(2048, h))
        nn = max(1, min(6, int(n or 1)))

        def _preferred_size_str(ww: int, hh: int, supported: Optional[List[str]] = None) -> str:
            if supported:
                supp = [str(x).strip().strip("'").strip('"') for x in supported if str(x or "").strip()]
                if "auto" in supp:
                    return "auto"
                ar = float(ww) / float(hh or 1)
                best = None
                best_score = 1e9
                for s in supp:
                    m = re.match(r"^(\d+)x(\d+)$", s)
                    if not m:
                        continue
                    sw, sh = int(m.group(1)), int(m.group(2))
                    sar = float(sw) / float(sh or 1)
                    score = abs(sar - ar) + abs(sw - ww) / 4096.0 + abs(sh - hh) / 4096.0
                    if score < best_score:
                        best_score = score
                        best = s
                if best:
                    return best
            if ww >= hh * 1.1:
                return "1536x1024"
            if hh >= ww * 1.1:
                return "1024x1536"
            return "1024x1024"

        def _download(url: str) -> bytes:
            u = str(url or "").strip()
            if not u:
                return b""
            req = urllib.request.Request(u, headers={"User-Agent": "DeepSlide/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read() or b""

        def _decode(resp_obj) -> List[bytes]:
            data = getattr(resp_obj, "data", None) or []
            out: List[bytes] = []
            for it in data:
                b64 = getattr(it, "b64_json", None) or ""
                if b64:
                    try:
                        out.append(base64.b64decode(b64))
                        continue
                    except Exception:
                        pass
                url = getattr(it, "url", None) or ""
                if url:
                    try:
                        out.append(_download(url))
                        continue
                    except Exception:
                        pass
            return [b for b in out if b]

        client = OpenAI(api_key=self.cfg.api_key, base_url=self.cfg.api_url or None)
        model = str(self.cfg.model_type or "gpt-image-1")
        force_no_resp_format = str(os.getenv("DS_IMG_NO_RESPONSE_FORMAT") or "").strip() in {"1", "true", "yes"}
        size_str = _preferred_size_str(w, h)

        def _call(use_response_format: bool, size_override: Optional[str] = None):
            kwargs = {
                "model": model,
                "prompt": str(prompt or ""),
                "size": str(size_override or size_str),
                "n": nn,
            }
            if use_response_format:
                kwargs["response_format"] = "b64_json"
            return client.images.generate(**kwargs)

        def _parse_supported_sizes(err_text: str) -> List[str]:
            return re.findall(r"'(\d+x\d+|auto)'", str(err_text or ""))

        def _is_rate_limited(err_text: str) -> bool:
            t = str(err_text or "")
            return (" 429 " in f" {t} " or "Error code: 429" in t or "rate limit" in t.lower() or "限流" in t)

        try:
            resp = _call(use_response_format=not force_no_resp_format)
            out = _decode(resp)
            if out:
                return out
            try:
                logger.warning(f"[img_gen] empty result agent={self.agent} model={model!r} size={size_str} n={nn}")
            except Exception:
                pass
            return []
        except Exception as e:
            msg = str(e)
            should_retry = (not force_no_resp_format) and ("response_format" in msg and "Unknown parameter" in msg)
            if should_retry:
                try:
                    logger.warning(f"[img_gen] retry without response_format agent={self.agent} model={model!r}")
                except Exception:
                    pass
                try:
                    try:
                        resp2 = _call(use_response_format=False)
                        out2 = _decode(resp2)
                        if out2:
                            return out2
                    except Exception as e2_first:
                        msg2_first = str(e2_first)
                        supported = _parse_supported_sizes(msg2_first)
                        if supported:
                            size2 = _preferred_size_str(w, h, supported)
                            resp2b = _call(use_response_format=False, size_override=size2)
                            out2b = _decode(resp2b)
                            if out2b:
                                return out2b
                        if _is_rate_limited(msg2_first):
                            for delay in (1.5, 3.0):
                                time.sleep(delay)
                                resp2c = _call(use_response_format=False)
                                out2c = _decode(resp2c)
                                if out2c:
                                    return out2c
                        raise e2_first
                    try:
                        logger.warning(f"[img_gen] empty result after retry agent={self.agent} model={model!r} size={size_str} n={nn}")
                    except Exception:
                        pass
                    return []
                except Exception as e2:
                    try:
                        logger.warning(f"[img_gen] retry failed agent={self.agent} model={model!r} size={size_str} n={nn}: {e2}")
                    except Exception:
                        pass
                    self.last_error = str(e2)[:800]
                    return []
            supported = _parse_supported_sizes(msg)
            if supported:
                size2 = _preferred_size_str(w, h, supported)
                try:
                    resp3 = _call(use_response_format=False, size_override=size2)
                    out3 = _decode(resp3)
                    if out3:
                        return out3
                except Exception as e3:
                    try:
                        logger.warning(f"[img_gen] size-adjust retry failed agent={self.agent} model={model!r} size={size2} n={nn}: {e3}")
                    except Exception:
                        pass
                    self.last_error = str(e3)[:800]
                    return []
            if _is_rate_limited(msg):
                for delay in (1.5, 3.0):
                    time.sleep(delay)
                    try:
                        resp4 = _call(use_response_format=False)
                        out4 = _decode(resp4)
                        if out4:
                            return out4
                    except Exception as e4:
                        self.last_error = str(e4)[:800]
                        continue
            try:
                logger.warning(f"[img_gen] generate failed agent={self.agent} model={model!r} size={size_str} n={nn}: {e}")
            except Exception:
                pass
            self.last_error = str(e)[:800]
            return []
