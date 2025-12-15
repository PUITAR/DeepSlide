import re
import os

def extract_metadata(tex_content: str) -> str:
    """
    从 base.tex 内容中提取标题、作者、机构等元数据，
    组合成一段文本，作为演讲的“第0页”（封面页）内容。
    """
    metadata_text = "【封面页 (Cover Slide)】\n"
    
    # 提取标题 \title{...}
    title_match = re.search(r'\\title\{(.*?)\}', tex_content, re.DOTALL)
    if title_match:
        metadata_text += f"Title: {title_match.group(1).strip()}\n"
    
    # 提取副标题 \subtitle{...}
    subtitle_match = re.search(r'\\subtitle\{(.*?)\}', tex_content, re.DOTALL)
    if subtitle_match:
        metadata_text += f"Subtitle: {subtitle_match.group(1).strip()}\n"

    # 提取作者 \author{...} 或 \author[...]{...}
    # 兼容 \author{Name} 和 \author[Short]{Name}
    author_match = re.search(r'\\author(?:\[.*?\])?\{(.*?)\}', tex_content, re.DOTALL)
    if author_match:
        metadata_text += f"Author: {author_match.group(1).strip()}\n"

    # 提取机构 \institute{...}
    institute_match = re.search(r'\\institute(?:\[.*?\])?\{(.*?)\}', tex_content, re.DOTALL)
    if institute_match:
        metadata_text += f"Institute: {institute_match.group(1).strip()}\n"
        
    return metadata_text

def _clean_tex_text(raw_text: str) -> str:
    """内部辅助函数：清洗 LaTeX 命令，保留纯文本"""
    text = raw_text
    # 1. 提取标题 \frametitle{...}
    text = re.sub(r'\\frametitle\{(.*?)\}', r'【本页标题】: \1\n', text)
    # 2. 替换图片
    text = re.sub(r'\\includegraphics\[.*?\]\{.*?\}', r'[图片展示]', text)
    # 3. 替换引用
    text = re.sub(r'\\bibliography\{.*?\}', r'[参考文献列表]', text)
    # 4. 去除列表标签
    text = text.replace('\\begin{itemize}', '').replace('\\end{itemize}', '')
    text = text.replace('\\begin{enumerate}', '').replace('\\end{enumerate}', '')
    text = text.replace('\\item', '\n- ')
    # 5. 去除常用样式
    text = re.sub(r'\\[a-zA-Z]+\{(.*?)\}', r'\1', text) # \textbf{x} -> x
    text = re.sub(r'\\[a-zA-Z]+', '', text) # \centering -> ""
    # 6. 整理空行
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return "\n".join(lines)

def extract_frames(tex_content: str) -> list[str]:
    """从 TeX 内容中提取所有 \\begin{frame} ... \\end{frame}"""
    frame_pattern = re.compile(r'\\begin\{frame\}(.*?)\\end\{frame\}', re.DOTALL)
    raw_frames = frame_pattern.findall(tex_content)
    return [_clean_tex_text(f) for f in raw_frames]

def parse_presentation(base_file_path: str, content_file_path: str) -> list[str]:
    """
    综合解析 base.tex and content.tex
    返回一个列表，列表每个元素代表一页 Slide 的文本。
    顺序：[封面元数据] + [Content Frames] + [Base Frames(如Ref)]
    """
    slides = []

    # 1. 读取 base.tex
    if os.path.exists(base_file_path):
        with open(base_file_path, 'r', encoding='utf-8') as f:
            base_content = f.read()
        
        # --- 步骤 A: 提取封面信息作为第一页 ---
        cover_slide = extract_metadata(base_content)
        slides.append(cover_slide)
        
        # --- 步骤 B: 提取 base.tex 里的 Frames (通常是结尾的 References) ---
        # 注意：这里我们简单地把 base 里的 frame 放在最后。
        # 如果 base.tex 结构复杂，可能需要更精确的插入位置判断。
        # 参考文献是在 \input{content.tex} 之后的，所以放在最后没问题。
        base_frames = extract_frames(base_content)
        # 这里的 base_frames 包含 \titlepage，它是一个特殊的 frame，我们可以选择过滤掉或保留
        # 因为我们已经手动构建了 cover_slide，建议过滤掉内容为空或只包含 \titlepage 的 frame
        base_frames = [f for f in base_frames if "titlepage" not in f and f.strip()]
    else:
        print(f"[Utils] 警告: 未找到 base.tex: {base_file_path}")
        base_frames = []

    # 2. 读取 content.tex
    if os.path.exists(content_file_path):
        with open(content_file_path, 'r', encoding='utf-8') as f:
            content_content = f.read()
        content_frames = extract_frames(content_content)
    else:
        print(f"[Utils] 警告: 未找到 content.tex: {content_file_path}")
        content_frames = []

    # 3. 合并：封面 -> 正文 -> 结尾(Ref)
    slides.extend(content_frames)
    slides.extend(base_frames)

    return slides