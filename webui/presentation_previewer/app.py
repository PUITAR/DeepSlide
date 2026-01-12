import streamlit as st
import fitz  # PyMuPDF
import base64
from pathlib import Path
import re

st.set_page_config(
    page_title="DeepSlide Viewer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
custom_css = """
<style>
/* 深色主题 */
.stApp {
    background-color: #1a1a1a;
    color: #ffffff;
}

/* 侧边栏样式 */
.css-1d391kg {
    background-color: #2d2d2d;
}

/* 文件上传区域 */
.stFileUploader {
    background-color: #2d2d2d;
    border: 2px dashed #4a4a4a;
    border-radius: 10px;
    padding: 20px;
}

.stFileUploader:hover {
    border-color: #0066cc;
}

/* 页面导航 */
.page-nav {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 20px;
    margin: 20px 0;
    padding: 15px;
    background-color: #2d2d2d;
    border-radius: 10px;
}

/* 内容区域 */
.content-container {
    display: flex;
    gap: 20px;
    height: 70vh;
}

.pdf-viewer {
    flex: 1;
    background-color: #2d2d2d;
    border-radius: 10px;
    padding: 20px;
    overflow: auto;
}

.speech-viewer {
    flex: 1;
    background-color: #2d2d2d;
    border-radius: 10px;
    padding: 20px;
    overflow: auto;
}

/* PDF页面 */
.pdf-page {
    background-color: white;
    margin: 0 auto 20px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    display: block;
}

/* 演讲稿样式 */
.speech-content {
    color: #ffffff;
    line-height: 1.6;
    font-size: 16px;
}

.speech-segment {
    margin-bottom: 15px;
    padding: 15px;
    background-color: #3d3d3d;
    border-radius: 8px;
    border-left: 4px solid #0066cc;
}

.speech-segment.active {
    background-color: #4a4a4a;
    border-left-color: #ff6600;
}

/* 按钮样式 */
.stButton > button {
    background-color: #0066cc;
    color: white;
    border: none;
    border-radius: 5px;
    padding: 8px 16px;
    font-weight: bold;
    transition: all 0.3s ease;
}

.stButton > button:hover {
    background-color: #0052a3;
    transform: translateY(-1px);
}

/* 滑块样式 */
.stSlider > div > div > div > div {
    background-color: #0066cc;
}

/* 标题样式 */
h1, h2, h3 {
    color: #ffffff;
}

/* 加载状态 */
.loading {
    text-align: center;
    padding: 40px;
    color: #888;
}
</style>
"""

st.markdown(custom_css, unsafe_allow_html=True)

# 初始化会话状态
if 'pdf_pages' not in st.session_state:
    st.session_state.pdf_pages = []
if 'speech_segments' not in st.session_state:
    st.session_state.speech_segments = []
if 'current_page' not in st.session_state:
    st.session_state.current_page = 0
if 'total_pages' not in st.session_state:
    st.session_state.total_pages = 0
if 'page_direction' not in st.session_state:
    st.session_state.page_direction = 'next'
if 'last_page' not in st.session_state:
    st.session_state.last_page = 0
if 'last_wheel_ts' not in st.session_state:
    st.session_state.last_wheel_ts = ''

def parse_speech_text(text_content):
    """解析演讲稿文本，按<next>标签分割"""
    if not text_content:
        return []
    
    # 按<next>标签分割
    segments = re.split(r'<next>', text_content, flags=re.IGNORECASE)
    
    # 清理每个段落
    cleaned_segments = []
    for segment in segments:
        # 移除多余的空白字符
        cleaned = segment.strip()
        if cleaned:
            cleaned_segments.append(cleaned)
    
    return cleaned_segments

def render_pdf_page(page_data, page_num):
    """渲染PDF页面"""
    page_bytes = None
    if isinstance(page_data, (bytes, bytearray)):
        page_bytes = page_data
    elif isinstance(page_data, str):
        try:
            page_bytes = base64.b64decode(page_data)
        except Exception:
            page_bytes = None

    if page_bytes:
        st.image(page_bytes, caption=f"第 {page_num + 1} 页", use_column_width=True)
    else:
        st.error(f"无法渲染第 {page_num + 1} 页")

def render_speech_segment(segment_text, segment_index, is_active=False):
    """渲染演讲稿段落"""
    segment_class = "speech-segment active" if is_active else "speech-segment"
    st.markdown(f'<div class="{segment_class}">{segment_text}</div>', unsafe_allow_html=True)

# 主界面
# st.title("📊 DeepSlide Viewer")

def _load_sample_if_needed():
    try:
        if not st.session_state.pdf_pages or not st.session_state.speech_segments:
            sample_pdf_path = Path("/home/ym/DeepSlide/webui/presentation_previewer/sample.pdf")
            sample_text_path = Path("/home/ym/DeepSlide/webui/presentation_previewer/sample.txt")
            if sample_pdf_path.exists() and sample_text_path.exists():
                pdf_document = fitz.open(str(sample_pdf_path))
                pages = []
                for page_num in range(pdf_document.page_count):
                    page = pdf_document.load_page(page_num)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_data = pix.tobytes("png")
                    pages.append(img_data)
                st.session_state.pdf_pages = pages
                st.session_state.total_pages = len(pages)
                pdf_document.close()
                with open(sample_text_path, 'r', encoding='utf-8') as f:
                    text_content = f.read()
                st.session_state.speech_segments = parse_speech_text(text_content)
                st.session_state.current_page = 0
                st.session_state.last_page = 0
                st.session_state.page_direction = 'next'
    except Exception as e:
        st.error(f"❌ 加载示例文件失败: {str(e)}")

_load_sample_if_needed()

# 鼠标滚轮翻页（全局监听）
params = st.query_params
wheel = params.get('wheel', '')
wheel_ts = params.get('t', '')
if wheel and wheel_ts and wheel_ts != st.session_state.last_wheel_ts:
    st.session_state.last_wheel_ts = wheel_ts
    if wheel == 'down' and st.session_state.current_page < len(st.session_state.pdf_pages) - 1:
        st.session_state.last_page = st.session_state.current_page
        st.session_state.current_page += 1
        st.session_state.page_direction = 'next'
    elif wheel == 'up' and st.session_state.current_page > 0:
        st.session_state.last_page = st.session_state.current_page
        st.session_state.current_page -= 1
        st.session_state.page_direction = 'prev'

# 主要内容区域
if st.session_state.pdf_pages and st.session_state.speech_segments:
    
    # 定义翻页回调函数
    def prev_page():
        st.session_state.last_page = st.session_state.current_page
        st.session_state.current_page -= 1
        st.session_state.page_direction = 'prev'

    def next_page():
        st.session_state.last_page = st.session_state.current_page
        st.session_state.current_page += 1
        st.session_state.page_direction = 'next'

    # 内容展示区域（扩大PDF区域，缩小演讲稿区域）
    col1, col2 = st.columns([5.8, 3], vertical_alignment="top")
    
    with col1:
        st.subheader("📄 PDF页面")
        with st.container(height=600):
            # 渲染当前PDF页面（安全夹取索引，避免越界）
            if st.session_state.total_pages != len(st.session_state.pdf_pages):
                st.session_state.total_pages = len(st.session_state.pdf_pages)
            if st.session_state.current_page < 0:
                st.session_state.current_page = 0
            if st.session_state.current_page >= len(st.session_state.pdf_pages):
                st.session_state.current_page = max(0, len(st.session_state.pdf_pages) - 1)
            page_idx = st.session_state.current_page
            page_data = st.session_state.pdf_pages[page_idx]
            render_pdf_page(page_data, page_idx)
    
    with col2:
        st.subheader("📝 演讲稿")
        with st.container(height=600):
            # 计算对应的演讲稿段落（仅展示当前页对应段落）
            if st.session_state.speech_segments:
                segment_index = min(
                    int(st.session_state.current_page * len(st.session_state.speech_segments) / st.session_state.total_pages),
                    len(st.session_state.speech_segments) - 1
                )
                render_speech_segment(
                    st.session_state.speech_segments[segment_index],
                    segment_index,
                    True
                )
            else:
                st.info("暂无演讲稿内容")

    # 页面导航
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        st.button("⬅️ 上一页", disabled=st.session_state.current_page <= 0, on_click=prev_page)
    
    with col2:
        # 页面滑块
        if 'slider_page' not in st.session_state:
            st.session_state.slider_page = st.session_state.current_page + 1
        st.session_state.slider_page = st.session_state.current_page + 1

        def on_slider_change():
            new_page_idx = st.session_state.slider_page - 1
            if new_page_idx != st.session_state.current_page:
                st.session_state.page_direction = 'next' if new_page_idx > st.session_state.current_page else 'prev'
                st.session_state.last_page = st.session_state.current_page
                st.session_state.current_page = new_page_idx

        st.slider(
            "页面导航",
            min_value=1,
            max_value=len(st.session_state.pdf_pages),
            key="slider_page",
            on_change=on_slider_change,
            label_visibility="collapsed"
        )
    
    with col3:
        st.button("下一页 ➡️", disabled=st.session_state.current_page >= len(st.session_state.pdf_pages) - 1, on_click=next_page)

else:
    # 欢迎界面
    st.markdown("""
    <div style="text-align: center; padding: 50px;">
        <h2>🎯 欢迎使用 DeepSlide Viewer</h2>
        <p style="font-size: 18px; color: #888;">
            示例文件未找到，请将 sample.pdf/sample.txt 放入 webui/presentation_previewer 目录
        </p>
    </div>
    """, unsafe_allow_html=True)

# 页脚（移除分割线与说明）

# 注入脚本：捕获滚轮事件并更新Query参数，触发翻页
from streamlit.components.v1 import html as st_html
st_html(
    """
    <script>
    (function(){
      document.addEventListener('wheel', function(e){
        const params = new URLSearchParams(window.location.search);
        params.set('wheel', e.deltaY > 0 ? 'down' : 'up');
        params.set('t', Date.now());
        window.location.search = params.toString();
      }, {passive: true});
    })();
    </script>
    """,
    height=0
)
