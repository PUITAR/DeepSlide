# app.py
import streamlit as st
import json
from ppt_requirements_collector import PPTRequirementsCollector

# ======================
# 页面配置
# ======================
st.set_page_config(page_title="论文转PPT助手", layout="wide")
st.title("📄 论文转PPT助手")

# ======================
if "collector" not in st.session_state:
    st.session_state.collector = PPTRequirementsCollector()

if "uploaded" not in st.session_state:
    st.session_state.uploaded = False

if "app_state" not in st.session_state:
    st.session_state.app_state = "UPLOAD"  # 可选值: UPLOAD, CONVERSATION, CONFIRMATION, COMPLETED

if "final_requirements" not in st.session_state:
    st.session_state.final_requirements = {}

# ======================
# 左侧：文件上传区
# ======================
with st.sidebar:
    st.header("📁 上传论文 (.tex)")
    uploaded_file = st.file_uploader("选择 .tex 文件", type=["tex"])

    if uploaded_file is not None and not st.session_state.uploaded:
        st.session_state.uploaded = True
        st.session_state.collector.set_paper_file(uploaded_file.name)
        # ✅ 触发AI开始对话
        st.session_state.collector.process_user_input("请开始收集PPT需求。")
        st.session_state.app_state = "CONVERSATION"  # 更新状态
        st.success(f"✅ 已上传：{uploaded_file.name}")
        st.rerun()

# ======================
# 主区域：对话界面 
# ======================
st.subheader("💬 PPT 需求对话")

# ✅ 状态1: 等待上传
if st.session_state.app_state == "UPLOAD":
    st.info("请先在左侧上传您的 .tex 论文文件。")

# ✅ 状态2: 已完成，显示下载
elif st.session_state.app_state == "COMPLETED":
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
        st.session_state.collector.reset()
        st.session_state.final_requirements = {}
        st.session_state.uploaded = False
        st.session_state.app_state = "UPLOAD"
        st.rerun()

# ✅ 状态3: 需要确认
elif st.session_state.app_state == "CONFIRMATION":
    st.success("✅ 请确认以下信息：")
    req_data = st.session_state.collector.conversation_requirements
    if req_data:
        st.json(req_data)
    else:
        st.warning("⚠️ 未能提取结构化数据，以下是对话摘要：")
        for msg in st.session_state.collector.conversation_history[-4:]:
            st.markdown(f"**{msg['role'].title()}**: {msg['content']}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ 确认并生成"):
            # ✅ 保存最终需求并更新状态
            st.session_state.final_requirements = st.session_state.collector.get_requirements()
            st.session_state.app_state = "COMPLETED"  # ✅ 关键：直接跳转到完成状态
            st.rerun()
    with col2:
        if st.button("🔄 继续补充"):
            st.session_state.app_state = "CONVERSATION"  # 返回对话状态
            st.rerun()

# ✅ 状态4: 正常对话
elif st.session_state.app_state == "CONVERSATION":
    # 显示对话历史
    for msg in st.session_state.collector.conversation_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # 自动显示输入框
    user_input = st.chat_input("请输入您的回答...")
    if user_input:
        st.session_state.collector.process_user_input(user_input)
        
        # ✅ 检查是否触发了确认状态
        if st.session_state.collector.is_confirmed:
            st.session_state.app_state = "CONFIRMATION"  # 跳转到确认状态
            st.rerun()
        else:
            st.rerun()