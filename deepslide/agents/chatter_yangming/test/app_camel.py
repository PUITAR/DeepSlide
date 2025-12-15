import streamlit as st
import json
import os
import re
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage

# ======================
# 加载 CAMEL-AI 配置
# ======================
ENV_PATH = '/home/ym/DeepSlide/deepslide/config/env/.env'
load_dotenv(dotenv_path=ENV_PATH)

api_key = os.getenv('DEEPSEEK_API_KEY')
platform_type = os.getenv('DEFAULT_MODEL_PLATFORM_TYPE', 'deepseek')
model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')

# 初始化 CAMEL-AI 模型
try:
    model = ModelFactory.create(
        model_platform=ModelPlatformType(platform_type),
        model_type=model_type,
        api_key=api_key,
    )
    CAMEL_AVAILABLE = True
except Exception as e:
    print(f"CAMEL-AI 模型初始化失败: {e}")
    CAMEL_AVAILABLE = False

# ======================
# 页面配置
# ======================
st.set_page_config(page_title="论文转PPT助手", layout="wide")
st.title("📄 论文转PPT助手")

# ======================
# 初始化会话状态
# ======================
if "uploaded" not in st.session_state:
    st.session_state.uploaded = False
    st.session_state.file_name = ""

if "camel_conversation" not in st.session_state:
    st.session_state.camel_conversation = []

if "camel_agent" not in st.session_state:
    st.session_state.camel_agent = None

if "requirements" not in st.session_state:
    st.session_state.requirements = {
        "paper_info": {"file_name": ""},
        "conversation_requirements": {},
        "conversation_history": []
    }

if "needs_confirmation" not in st.session_state:
    st.session_state.needs_confirmation = False

if "final_requirements" not in st.session_state:
    st.session_state.final_requirements = {}

if "awaiting_json_output" not in st.session_state:
    st.session_state.awaiting_json_output = False

# ======================
# 初始化 CAMEL-Agent
# ======================
def init_camel_agent():
    if st.session_state.camel_agent is None and CAMEL_AVAILABLE:
        sys_msg = BaseMessage.make_assistant_message(
            role_name="PPT需求助手",
            content="""
            你是PPT生成助手。你的任务是通过与用户对话，收集生成PPT所需的关键信息。
            需要询问的信息包括但不限于：目标受众、演讲时长、重点章节、风格偏好、特殊要求等。
            请逐步引导用户提供这些信息，每次只问一个问题，保持对话自然流畅。
            
            当你认为已经收集了足够信息后，或用户表达了“确认”、“完成”、“没有其他要求”等意思时，
            你必须执行以下操作：
            1. 输出一个包含以下字段的 JSON 结构（严格按照格式）：
            {
              "audience": "...",
              "duration": "...",
              "focus_sections": ["...", "..."],
              "style": "...",
              "special_notes": "..."
            }
            2. JSON 后面可以附加一句话总结：“以上是为您生成PPT的初步需求，是否确认？”
            3. 严禁继续提问，必须输出 JSON。
            """
        )
        st.session_state.camel_agent = ChatAgent(system_message=sys_msg, model=model)

# ======================
# CAMEL-AI 对话助手
# ======================
def get_camel_response(user_input=None):
    """获取 CAMEL-AI 的响应"""
    if not CAMEL_AVAILABLE:
        return "⚠️ CAMEL-AI 模型不可用，请检查配置。"

    init_camel_agent()

    if not user_input:
        initial_msg = BaseMessage.make_user_message(role_name="User", content="请开始收集PPT需求。")
        response = st.session_state.camel_agent.step(initial_msg)
    else:
        user_msg = BaseMessage.make_user_message(role_name="User", content=user_input)
        response = st.session_state.camel_agent.step(user_msg)

    if response.terminated:
        return f"[AI 终止] {response.info}"

    ai_response = response.msg.content.strip()

    # 检查是否包含 JSON 结构（提取结构化数据）
    json_match = re.search(r'\{[^}]*\}', ai_response, re.DOTALL)
    if json_match:
        try:
            json_str = json_match.group()
            extracted_data = json.loads(json_str)
            # 将提取的数据同步到 requirements
            for key, value in extracted_data.items():
                st.session_state.requirements["conversation_requirements"][key] = value
            # 标记为已确认（因为 AI 输出了 JSON）
            st.session_state.needs_confirmation = True
        except json.JSONDecodeError:
            pass  # 如果解析失败，忽略

    return ai_response

# ======================
# 左侧：文件上传区
# ======================
with st.sidebar:
    st.header("📁 上传论文 (.tex)")
    uploaded_file = st.file_uploader("选择 .tex 文件", type=["tex"])

    if uploaded_file is not None and not st.session_state.uploaded:
        st.session_state.uploaded = True
        st.session_state.file_name = uploaded_file.name
        st.session_state.requirements["paper_info"]["file_name"] = uploaded_file.name
        st.success(f"✅ 已上传：{uploaded_file.name}")
        initial_msg = f"用户上传了论文《{uploaded_file.name}》，请开始收集PPT生成需求。"
        ai_reply = get_camel_response(initial_msg)
        st.session_state.camel_conversation.append({"role": "assistant", "content": ai_reply})
        st.session_state.requirements["conversation_history"].append({"role": "assistant", "content": ai_reply})
        st.rerun()

# ======================
# 主区域：对话界面
# ======================
st.subheader("💬 PPT 需求对话")

if not st.session_state.uploaded:
    st.info("请先在左侧上传您的 .tex 论文文件。")
else:
    # 显示当前对话历史
    for msg in st.session_state.camel_conversation:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 如果需要确认（AI 输出了 JSON 或用户手动确认）
    if st.session_state.needs_confirmation:
        st.success("✅ 已收集需求，以下是结构化信息：")
        
        # 显示结构化数据
        req_data = st.session_state.requirements["conversation_requirements"]
        if req_data:
            st.json(req_data)
        else:
            st.warning("⚠️ 未能从对话中提取结构化数据，请手动确认。")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 确认并生成"):
                # 同步最终数据
                st.session_state.final_requirements = st.session_state.requirements.copy()
                st.rerun()
        with col2:
            if st.button("🔄 继续补充"):
                st.session_state.needs_confirmation = False
                st.rerun()

    # 如果已确认，展示下载
    elif st.session_state.final_requirements:
        st.balloons()
        st.success("🎉 需求收集完成！")
        st.json(st.session_state.final_requirements)
        st.download_button(
            label="📥 下载需求配置 (JSON)",
            data=json.dumps(st.session_state.final_requirements, indent=2, ensure_ascii=False),
            file_name="ppt_requirements.json",
            mime="application/json"
        )
        if st.button("🔄 重新开始"):
            # 重置所有状态
            st.session_state.camel_conversation = []
            st.session_state.final_requirements = {}
            st.session_state.needs_confirmation = False
            st.session_state.requirements = {
                "paper_info": {"file_name": st.session_state.file_name},
                "conversation_requirements": {},
                "conversation_history": []
            }
            if st.session_state.camel_agent:
                st.session_state.camel_agent.clear_memory()
            initial_msg = f"用户重新上传了论文《{st.session_state.file_name}》，请开始收集PPT生成需求。"
            ai_reply = get_camel_response(initial_msg)
            st.session_state.camel_conversation.append({"role": "assistant", "content": ai_reply})
            st.session_state.requirements["conversation_history"].append({"role": "assistant", "content": ai_reply})
            st.rerun()

    # 正常对话输入框
    else:
        # 添加一个“强制确认”按钮（当 AI 没输出 JSON 时）
        col1, col2 = st.columns([4, 1])
        with col1:
            user_input = st.chat_input("请输入您的回答...")
        with col2:
            if st.button("✅ 确认需求"):
                # 直接进入确认流程
                st.session_state.needs_confirmation = True
                st.rerun()

        if user_input:
            # 保存用户输入
            st.session_state.camel_conversation.append({"role": "user", "content": user_input})
            st.session_state.requirements["conversation_history"].append({"role": "user", "content": user_input})

            # 获取 AI 回复
            ai_reply = get_camel_response(user_input)
            st.session_state.camel_conversation.append({"role": "assistant", "content": ai_reply})
            st.session_state.requirements["conversation_history"].append({"role": "assistant", "content": ai_reply})

            st.rerun()