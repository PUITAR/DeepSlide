import sys
import os

# Fix import paths for local execution
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, "deeppresenter"))
sys.path.append(os.path.join(current_dir, "pptagent"))

# Fix Gradio permission error
os.environ["GRADIO_TEMP_DIR"] = os.path.join(current_dir, "gradio_temp")
os.makedirs(os.environ["GRADIO_TEMP_DIR"], exist_ok=True)

import time
import uuid
from datetime import datetime
from pathlib import Path

import gradio as gr
from deeppresenter.main import AgentLoop
from deeppresenter.utils.constants import WORKSPACE_BASE
from deeppresenter.utils.log import create_logger
from deeppresenter.utils.typings import ChatMessage, ConvertType, InputRequest, Role
from platformdirs import user_cache_dir

from pptagent import PPTAgentServer

timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
logger = create_logger(
    "DeepPresenterUI",
    log_file=user_cache_dir("deeppresenter") + f"/logs/{timestamp}.log",
)


ROLE_EMOJI = {
    Role.SYSTEM: "⚙️",
    Role.USER: "👤",
    Role.ASSISTANT: "🤖",
    Role.TOOL: "📝",
}

CONVERT_MAPPING = {
    "自由生成 (freeform)": ConvertType.DEEPPRESENTER,
    "模版 (templates)": ConvertType.PPTAGENT,
}


gradio_css = """
            .center-title {
                text-align: center;
                margin-bottom: 10px;
            }
            .center-subtitle {
                text-align: center;
                margin-bottom: 20px;
                opacity: 0.8;
            }
            .token-display {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                padding: 10px;
            }
            .token-display h2 {
                color: #2c3e50;
                font-size: 1.2em;
                margin-bottom: 15px;
            }
            .gradio-container {
                max-width: 100% !important;
                overflow-x: hidden !important;
            }
            .file-container .wrap {
                min-height: auto !important;
                height: auto !important;
            }

            .file-container .upload-container {
                display: none !important;  /* 隐藏大的拖拽区域 */
            }

            .file-container .file-list {
                min-height: 40px !important;
                padding: 8px !important;
            }

            footer {
                display: none !important;
            }

            .gradio-container .footer {
                display: none !important;
            }
            body {
                margin: 5px !important;
                padding: 0 !important;
            }
            .html-container {
                padding: 0 !important;
            }
"""


class UserSession:
    """简化的用户会话类"""

    def __init__(self):
        self.loop = AgentLoop(
            session_id=f"{datetime.now().strftime('%Y%m%d')}/{uuid.uuid4().hex[:8]}",
        )
        self.created_time = time.time()


class ChatDemo:
    def create_interface(self):
        """创建 Gradio 界面"""
        with gr.Blocks(
            title="DeepPresenter",
            theme=gr.themes.Soft(),
            css=gradio_css,
        ) as demo:
            gr.Markdown(
                "# DeepPresenter",
                elem_classes=["center-title"],
            )

            with gr.Row():
                with gr.Column():
                    chatbot = gr.Chatbot(
                        value=[],
                        height=300,
                        show_label=False,
                        type="messages",
                        render_markdown=True,
                        elem_classes=["chat-container"],
                    )

                    with gr.Accordion("📊 Token 使用统计", open=False):
                        token_display = gr.Markdown(
                            value="暂无数据",
                            elem_classes=["token-display"],
                        )
                    with gr.Row():
                        pages_dd = gr.Dropdown(
                            label="幻灯片页数 (#pages)",
                            choices=["auto"] + [str(i) for i in range(1, 31)],
                            value="auto",
                            scale=1,
                        )
                        convert_type_dd = gr.Dropdown(
                            label="输出类型 (output type)",
                            choices=list(CONVERT_MAPPING),
                            value=list(CONVERT_MAPPING)[0],
                            scale=1,
                        )
                        template_choices = PPTAgentServer.list_templates()
                        template_dd = gr.Dropdown(
                            label="选择模板 (template)",
                            choices=template_choices + ["auto"],
                            value="auto",
                            scale=2,
                            visible=False,
                        )

                    def _toggle_template_visibility(v: str):
                        return gr.update(visible=("模版" in v))

                    convert_type_dd.change(
                        _toggle_template_visibility,
                        inputs=[convert_type_dd],
                        outputs=[template_dd],
                    )

                    with gr.Row():
                        msg_input = gr.Textbox(
                            placeholder="You instruction here",
                            scale=4,
                            container=False,
                        )

                        send_btn = gr.Button("发送", scale=1, variant="primary")
                        download_btn = gr.DownloadButton(
                            "📥 下载文件",
                            scale=1,
                            variant="secondary",
                        )

                    attachments_input = gr.File(
                        file_count="multiple",
                        type="filepath",
                        elem_classes=["file-container"],
                    )

            def collect_token_stats(loop: AgentLoop) -> str:
                """收集所有 agents 的 token 统计并生成显示文本"""
                all_agent_costs = {}

                if hasattr(loop, "research_agent") and loop.research_agent:
                    all_agent_costs["Research Agent"] = {
                        "prompt": getattr(loop.research_agent.cost, "prompt", 0),
                        "completion": getattr(
                            loop.research_agent.cost, "completion", 0
                        ),
                        "total": getattr(loop.research_agent.cost, "total", 0),
                        "model": loop.config.research_agent.model_name,
                    }

                if hasattr(loop, "designagent") and loop.designagent:
                    all_agent_costs["Design Agent"] = {
                        "prompt": getattr(loop.designagent.cost, "prompt", 0),
                        "completion": getattr(loop.designagent.cost, "completion", 0),
                        "total": getattr(loop.designagent.cost, "total", 0),
                        "model": loop.config.design_agent.model_name,
                    }
                elif hasattr(loop, "pptagent") and loop.pptagent:
                    all_agent_costs["PPT Agent"] = {
                        "prompt": getattr(loop.pptagent.cost, "prompt", 0),
                        "completion": getattr(loop.pptagent.cost, "completion", 0),
                        "total": getattr(loop.pptagent.cost, "total", 0),
                        "model": loop.config.research_agent.model_name,
                    }

                token_lines = ["## Token 使用统计\n"]
                total_prompt = 0
                total_completion = 0
                total_all = 0

                for agent_name, cost_info in all_agent_costs.items():
                    prompt = cost_info.get("prompt", 0)
                    completion = cost_info.get("completion", 0)
                    total = cost_info.get("total", 0)
                    model = cost_info.get("model", "N/A")
                    total_prompt += prompt
                    total_completion += completion
                    total_all += total

                    token_lines.append(
                        f"**{agent_name}** (Model: `{model}`)  \n"
                        f"- 输入: {prompt:,} tokens  \n"
                        f"- 输出: {completion:,} tokens  \n"
                        f"- 小计: {total:,} tokens  \n"
                    )

                if total_all > 0:
                    token_lines.append("\n---\n")
                    token_lines.append(
                        f"**总计**  \n"
                        f"- 输入: {total_prompt:,} tokens  \n"
                        f"- 输出: {total_completion:,} tokens  \n"
                        f"- **总计: {total_all:,} tokens**"
                    )

                return "\n".join(token_lines) if total_all > 0 else "暂无 token 数据"

            async def send_message(
                message,
                history,
                attachments,
                convert_type_value,
                template_value,
                num_pages_value,
                request: gr.Request,
            ):
                user_session = UserSession()

                has_message = bool(message and message.strip())
                has_attachments = bool(attachments)
                if not has_message and not has_attachments:
                    yield (
                        history,
                        message,
                        gr.update(value=None),
                        gr.update(),
                        gr.update(),
                    )
                    return

                history.append(
                    {"role": "user", "content": message or "请根据上传的附件制作 PPT"}
                )

                aggregated_parts: list[str] = []
                history.append({"role": "assistant", "content": ""})

                loop = user_session.loop

                selected_convert_type = CONVERT_MAPPING[convert_type_value]
                selected_num_pages = (
                    None if num_pages_value == "auto" else int(num_pages_value)
                )
                if template_value == "auto":
                    template_value = None

                async for yield_msg in loop.run(
                    InputRequest(
                        instruction=message or "请根据上传的附件制作 PPT",
                        template=template_value,
                        attachments=attachments or [],
                        num_pages=str(selected_num_pages),
                        convert_type=selected_convert_type,
                    )
                ):
                    if isinstance(yield_msg, (str, Path)):
                        file_content = "📄 幻灯片生成完成，点击下方按钮下载文件"
                        aggregated_parts.append(file_content)
                        aggregated_text = "\n\n".join(aggregated_parts).strip()
                        history[-1]["content"] = aggregated_text

                        token_text = collect_token_stats(loop)

                        yield (
                            history,
                            "",
                            gr.update(value=None),
                            gr.update(value=str(yield_msg)),
                            gr.update(value=token_text),
                        )

                    elif isinstance(yield_msg, ChatMessage):
                        role_msg = f"{ROLE_EMOJI[yield_msg.role]} **{str(yield_msg.role).title()} Message**"
                        if yield_msg.text:
                            aggregated_parts.append(role_msg)

                        if yield_msg.text is not None and yield_msg.text.strip():
                            if yield_msg.role == Role.TOOL:
                                aggregated_parts.append(
                                    "```json\n"
                                    + yield_msg.text.replace("\\n", "\n")
                                    + "\n```"
                                )
                            else:
                                aggregated_parts.append(yield_msg.text)

                        if yield_msg.tool_calls:
                            for tool_call in yield_msg.tool_calls:
                                tool_msg = f"{ROLE_EMOJI.get(yield_msg.role, '💬')} **Tool Call: {tool_call.function.name}**"
                                aggregated_parts.append(tool_msg)

                                if hasattr(tool_call.function, "arguments"):
                                    args_str = tool_call.function.arguments
                                    args_msg = f"```json\n{args_str}\n```"
                                    aggregated_parts.append(args_msg)

                        aggregated_text = "\n\n".join(aggregated_parts).strip()
                        history[-1]["content"] = aggregated_text

                        token_text = collect_token_stats(loop)

                        yield (
                            history,
                            message,
                            gr.update(value=None),
                            gr.update(),
                            gr.update(value=token_text),
                        )

                    else:
                        raise ValueError(
                            f"Unsupported response message type: {type(yield_msg)}"
                        )

            msg_input.submit(
                send_message,
                inputs=[
                    msg_input,
                    chatbot,
                    attachments_input,
                    convert_type_dd,
                    template_dd,
                    pages_dd,
                ],
                outputs=[
                    chatbot,
                    msg_input,
                    attachments_input,
                    download_btn,
                    token_display,
                ],
                concurrency_limit=None,
            )

            send_btn.click(
                send_message,
                inputs=[
                    msg_input,
                    chatbot,
                    attachments_input,
                    convert_type_dd,
                    template_dd,
                    pages_dd,
                ],
                outputs=[
                    chatbot,
                    msg_input,
                    attachments_input,
                    download_btn,
                    token_display,
                ],
                concurrency_limit=None,
            )

        return demo


if __name__ == "__main__":
    import warnings

    chat_demo = ChatDemo()
    demo = chat_demo.create_interface()

    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module="websockets.legacy"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module="uvicorn.protocols.websockets"
    )

    serve_url = "localhost" if len(sys.argv) == 1 else sys.argv[1]
    print("Please visit http://localhost:7862")
    demo.launch(
        debug=True,
        server_name=serve_url,
        server_port=7862,
        share=False,
        max_threads=16,
        allowed_paths=[WORKSPACE_BASE],
    )
