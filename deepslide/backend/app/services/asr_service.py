import os
from dotenv import load_dotenv

from app.core.agent_model_env import resolve_asr_env


class AsrService:
    def __init__(self):
        env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
        if os.path.exists(env_path):
            load_dotenv(env_path)

    async def transcribe_file(self, audio_path: str, lang: str = "zh") -> str:
        cfg = resolve_asr_env("ASR")
        api_key = cfg.api_key
        api_url = cfg.api_url
        model = cfg.model_type or "qwen3-asr-flash"
        platform = cfg.platform_type or "aliyun"

        if not api_key or not api_url:
            return ""

        if platform.lower() == "aliyun":
            try:
                import dashscope
            except Exception:
                return ""

            dashscope.base_http_api_url = api_url
            local_file_url = f"file://{os.path.abspath(audio_path)}"
            messages = [
                {
                    "role": "user",
                    "content": [{"audio": local_file_url}],
                }
            ]

            try:
                response = dashscope.MultiModalConversation.call(
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    result_format="message",
                    asr_options={"enable_itn": False},
                )
            except Exception:
                return ""

            try:
                if getattr(response, "status_code", None) != 200:
                    return ""
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            return str(item["text"]).strip()
                return str(content).strip()
            except Exception:
                return ""

        return ""


asr_service = AsrService()
