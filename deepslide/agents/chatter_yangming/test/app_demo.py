import streamlit as st
import json
from datetime import datetime

# streamlit run /home/ym/DeepSlide/deepslide/agents/Chatter/app.py
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

if "current_step" not in st.session_state:
    st.session_state.current_step = -1  # -1: 未开始；0,1,...: 问答步骤；"confirmed": 已确认

if "requirements" not in st.session_state:
    st.session_state.requirements = {
        "paper_info": {"file_name": ""},
        "conversation_requirements": {},
        "conversation_history": []
    }

# ======================
# 问答流程定义（MVP：2个问题）
# ======================
QUESTIONS = [
    {
        "key": "audience",
        "text": "您的演讲面向什么受众？",
        "options": ["本科生", "研究生", "学术同行", "工业界专家", "公众", "其他"]
    },
    {
        "key": "duration",
        "text": "演讲时长预计是多少分钟？",
        "type": "number",
        "min_value": 1,
        "max_value": 120
    }
]

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
        st.info("现在可以开始对话了！")

# ======================
# 主区域：对话界面
# ======================
st.subheader("💬 PPT 需求对话")

# 如果未上传文件，提示上传
if not st.session_state.uploaded:
    st.info("请先在左侧上传您的 .tex 论文文件。")
else:
    # 显示聊天历史（可选）
    for msg in st.session_state.requirements["conversation_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 已完成确认
    if st.session_state.current_step == "confirmed":
        st.success("✅ 您的需求已确认！")
        req = st.session_state.requirements
        st.json({
            "论文文件": req["paper_info"]["file_name"],
            "受众": req["conversation_requirements"].get("audience", "未设置"),
            "时长（分钟）": req["conversation_requirements"].get("duration", "未设置")
        })
        # 提供下载
        st.download_button(
            label="📥 下载需求配置 (JSON)",
            data=json.dumps(req, indent=2, ensure_ascii=False),
            file_name="ppt_requirements.json",
            mime="application/json"
        )
        if st.button("🔄 重新开始"):
            st.session_state.current_step = -1
            st.session_state.requirements["conversation_requirements"] = {}
            st.session_state.requirements["conversation_history"] = []
            st.rerun()

    # 正在进行问答
    elif st.session_state.current_step < len(QUESTIONS):
        step = st.session_state.current_step

        # 助手提问（仅当尚未提问时）
        if step >= 0 and (len(st.session_state.requirements["conversation_history"]) <= step * 2):
            q = QUESTIONS[step]
            with st.chat_message("assistant"):
                st.markdown(q["text"])
            st.session_state.requirements["conversation_history"].append({
                "role": "assistant",
                "content": q["text"]
            })

        # 用户输入
        if step == -1:
            # 开始对话按钮
            if st.button("▶️ 开始需求对话"):
                st.session_state.current_step = 0
                st.rerun()
        else:
            q = QUESTIONS[step]
            user_input = None

            with st.chat_message("user"):
                if "options" in q:
                    user_input = st.selectbox(
                        "请选择：",
                        options=q["options"],
                        key=f"input_{step}",
                        label_visibility="collapsed"
                    )
                elif q.get("type") == "number":
                    user_input = st.number_input(
                        "请输入分钟数：",
                        min_value=q.get("min_value", 1),
                        max_value=q.get("max_value", 60),
                        step=1,
                        key=f"input_{step}",
                        label_visibility="collapsed"
                    )

            # 提交按钮（仅在用户有输入后显示）
            if user_input is not None:
                if st.button("→ 下一步", key=f"next_{step}"):
                    # 保存用户回答
                    st.session_state.requirements["conversation_requirements"][q["key"]] = user_input
                    st.session_state.requirements["conversation_history"].append({
                        "role": "user",
                        "content": str(user_input)
                    })
                    # 推进到下一步
                    if step + 1 >= len(QUESTIONS):
                        # 进入确认阶段
                        st.session_state.current_step = "confirmed"
                    else:
                        st.session_state.current_step += 1
                    st.rerun()