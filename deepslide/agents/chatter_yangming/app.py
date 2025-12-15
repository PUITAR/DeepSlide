# app.py
import streamlit as st
import json
import urllib.parse
from ppt_requirements_collector import PPTRequirementsCollector
import os
from project_analyzer import save_uploaded_file, extract_archive, find_main_tex, merge_project_to_main, extract_abstract_from_dir

# ======================
# 页面配置
# ======================
st.set_page_config(page_title="DeepSlide", page_icon="📄", layout="wide")

_css = """
<style>
  html, body { background: linear-gradient(135deg, #0f172a 0%, #111827 100%); color: #e5e7eb; }
  .stApp { background: transparent; }
  header { visibility: hidden; }
  .stSidebar { background: rgba(17,24,39,0.95); backdrop-filter: blur(8px); border-right: 1px solid #374151; }
  section.main { background: rgba(31,41,55,0.6); }
  .css-1dp5vir, .stFileUploader, .stTextInput, .stButton > button { border-radius: 12px !important; }
  .stTextInput > div > div > input, textarea { background: #0b1220 !important; color: #e5e7eb !important; border: 1px solid #1f2937 !important; }
  .stFileUploader { background: #0b1220; border: 1px dashed #334155; color: #cbd5e1; }
  .stButton > button { background: #7c3aed; color: #fff; border: none; box-shadow: 0 6px 14px rgba(124,58,237,0.35); }
  .stButton > button:hover { background: #6d28d9; }
  .card { border: 1px solid #1f2937; border-radius: 16px; background: rgba(31,41,55,0.7); box-shadow: 0 8px 24px rgba(2,6,23,0.5); padding: 12px 16px; }
  .card h4 { display:inline-block; margin: 0 0 8px; padding: 6px 10px; border-radius: 10px; background: #1f2937; color: #c4b5fd; font-size: 16px; line-height: 1.25; }
  .titlebar { display:flex; align-items:center; justify-content:space-between; padding: 12px 20px; border-radius: 16px; background: rgba(31,41,55,0.6); box-shadow: 0 4px 16px rgba(2,6,23,0.4); margin-bottom: 12px; }
  .brand { font-weight: 600; color: #e5e7eb; }
  .brand-text { font-weight: 700; letter-spacing: 0.2px; font-size: 18px; }
  .brand-text .deep { color: #1e3a8a; }
  .brand-text .slide { color: #c2410c; }
  .muted { color: #9ca3af; }
  .pill { display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius:999px; background:#312e81; color:#c7d2fe; font-size:12px; }
  .chat-card { border: 1px solid #1f2937; border-radius: 16px; background: rgba(17,24,39,0.8); box-shadow: 0 8px 24px rgba(2,6,23,0.5); padding: 16px; }
  .stChatMessage[data-testid="stChatMessage"] { border-radius: 14px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(2,6,23,0.4); background: #0b1220; }
  .stChatMessage[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] p { line-height: 1.6; color: #e5e7eb; }
  .stChatMessage [data-testid="stChatMessageAvatar"]:not(:has(img)) { display: none !important; }
  p { color: #e5e7eb; }
  .stButton > button p { color: #e5e7eb !important; }
  a { color: #93c5fd; }
  .chat-row { display:flex; align-items:flex-start; gap:10px; margin:8px 0; }
  .chat-row.user { justify-content:flex-end; }
  .chat-row.assistant { justify-content:flex-start; }
  .bubble { max-width:70%; padding:10px 14px; border-radius:14px; box-shadow: 0 4px 12px rgba(2,6,23,0.4); }
  .bubble.user { background:#1f2937; color:#e5e7eb; border:1px solid #334155; right:0; }
  .bubble.assistant { background:#0b1220; color:#e5e7eb; border:1px solid #1f2937; left:0; }
  .avatar { width:28px; height:28px; border-radius:8px; border:1px solid #334155; background:#0b1220; flex-shrink:0; }
</style>
"""

st.markdown(_css, unsafe_allow_html=True)

# assistant avatar
_avatar_data_uri = None
try:
    import base64
    with open("deepslide/assets/logo.png", "rb") as _f:
        _avatar_data_uri = "data:image/png;base64," + base64.b64encode(_f.read()).decode()
except Exception:
    _avatar_data_uri = None

# user avatar removed

st.markdown(
    """
    <div class="titlebar">
      <div class="brand"><span class="brand-text"><span class="deep">Deep</span><span class="slide">Slide</span></span></div>
      <div class="pill">v0.1</div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
    # st.markdown("<div class='card'><h4>Upload Paper Project (Archive)</h4>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Select archive file", type=["zip", "tar", "gz", "bz2", "xz"])

    if uploaded_file is not None and not st.session_state.uploaded:
        tmp_base = "/home/ym/DeepSlide/deepslide/tmp_uploads"
        archive_path = save_uploaded_file(uploaded_file, tmp_base)
        with st.spinner("Analyzing project archive..."):
            extract_dir = os.path.join(tmp_base, os.path.splitext(os.path.basename(archive_path))[0])
            extract_archive(archive_path, extract_dir)
            main_tex = find_main_tex(extract_dir)
            merged_path = ""
            if main_tex:
                merged_path = merge_project_to_main(os.path.dirname(main_tex), main_tex, "merged_main.tex")
            abstract_text = extract_abstract_from_dir(extract_dir) or ""
        st.session_state.uploaded = True
        st.session_state.collector.set_paper_file(uploaded_file.name)
        st.session_state.collector.set_paper_project(extract_dir, main_tex, merged_path)
        st.session_state.collector.set_paper_abstract(abstract_text)
        st.session_state.collector.prime_context()
        if abstract_text:
            st.session_state.collector.conversation_history.append({"role": "assistant", "content": f"Detected paper abstract:\n{abstract_text}"})
        preface = "Please start collecting PPT requirements."
        if abstract_text:
            preface = "Please start collecting PPT requirements based on the above abstract."
        st.session_state.collector.process_user_input(preface)
        st.session_state.app_state = "CONVERSATION"
        st.success(f"Uploaded and analyzed: {uploaded_file.name}")
    st.markdown("</div>", unsafe_allow_html=True)

# ======================
# 主区域：对话界面 
# ======================
# st.markdown("<div class='card'><h4>PPT Requirements Conversation</h4>", unsafe_allow_html=True)

# ✅ 状态1: 等待上传
if st.session_state.app_state == "UPLOAD":
    st.info("Please upload your paper project archive in the sidebar.")

# ✅ 状态2: 已完成，显示下载
elif st.session_state.app_state == "COMPLETED":
    st.success("PPT Requirements Collection Completed")
    st.json(st.session_state.final_requirements)
    st.download_button(
        label="Download Requirements Config (JSON)", 
        data=json.dumps(st.session_state.final_requirements, indent=2, ensure_ascii=False),
        file_name="ppt_requirements.json",
        mime="application/json"
    )
    if st.button("Reset Collection"):
        st.session_state.collector.reset()
        st.session_state.final_requirements = {}
        st.session_state.uploaded = False
        st.session_state.app_state = "UPLOAD"
        st.rerun()

# ✅ 状态3: 需要确认
elif st.session_state.app_state == "CONFIRMATION":
    st.success("Please confirm the following requirements:")
    req_data = st.session_state.collector.conversation_requirements
    if req_data:
        st.json(req_data)
    else:
        st.warning("Failed to extract structured requirements. Here is the conversation summary:")
        for msg in st.session_state.collector.conversation_history[-4:]:
            st.markdown(f"**{msg['role'].title()}**: {msg['content']}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Confirm and Generate"):
            st.session_state.final_requirements = st.session_state.collector.get_requirements()
            st.session_state.app_state = "COMPLETED"
            st.rerun()
    with col2:
        if st.button("Continue Supplying"):
            st.session_state.app_state = "CONVERSATION"
            st.rerun()

# ✅ 状态4: 正常对话
elif st.session_state.app_state == "CONVERSATION":
    # 使用 Streamlit 原生聊天组件以支持 Markdown 渲染；隐藏头像，左/右对齐使用默认布局
    for msg in st.session_state.collector.conversation_history:
        role = (msg.get("role") or "assistant").lower()
        content_md = msg.get("content") or ""
        if role == "assistant":
            with st.chat_message("assistant", avatar=_avatar_data_uri if _avatar_data_uri else None):
                st.markdown(content_md)
        else:
            with st.chat_message("user", avatar=None):
                st.markdown(content_md)

    # 自动显示输入框
    user_input = st.chat_input("Enter your response...")
    if user_input:
        st.session_state.collector.process_user_input(user_input)
        
        # ✅ 检查是否触发了确认状态
        if st.session_state.collector.is_confirmed:
            st.session_state.app_state = "CONFIRMATION"  # 跳转到确认状态
            st.rerun()
        else:
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)
