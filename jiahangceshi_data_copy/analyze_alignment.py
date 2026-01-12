import os
import sys
import json
import requests
import re
import argparse
from typing import List, Tuple, Union

# 为了在 Python 3.8 环境下运行，我们在本地定义相关类，避免引入项目中的 Python 3.10+ 语法 (例如 Type | Type)
# To ensure compatibility with Python 3.8, we define classes locally to avoid Python 3.10+ syntax used in the project.

class Section(str):
    def __new__(cls, content: str):
        return super().__new__(cls, (content or ""))

    def is_valid(self) -> bool:
        s = str(self)
        if not s:
            return False
        if ("\\section" not in s) and ("\\subsection" not in s) and ("\\subsubsection" not in s):
            return False
        if s.count("{") != s.count("}"):
            return False
        return True

class Frame(str):
    def __new__(cls, content: str):
        return super().__new__(cls, (content or ""))

    def is_valid(self) -> bool:
        text = str(self)
        if not text:
            return False
        if "\\begin{frame}" not in text or "\\end{frame}" not in text:
            return False
        if text.count("\\begin{frame}") != 1 or text.count("\\end{frame}") != 1:
            return False
        return True

class Content(list):
    def from_file(self, file_path: str) -> None:
        self.clear()
        if not os.path.exists(file_path):
            print(f"Error: File not found - {file_path}")
            return
            
        with open(file_path, "r", encoding="utf-8") as f:
            inside_frame = False
            frame_lines = []
            for line in f:
                if inside_frame:
                    frame_lines.append(line)
                    if "\\end{frame}" in line:
                        self.append(Frame("".join(frame_lines)))
                        inside_frame = False
                        frame_lines = []
                    continue
                if "\\begin{frame}" in line:
                    inside_frame = True
                    frame_lines = [line]
                    continue
                if "\\section" in line or "\\subsection" in line or "\\subsubsection" in line:
                    self.append(Section(line))

def parse_arguments():
    parser = argparse.ArgumentParser(description="DeepSlide Content-Speech Alignment Tool")
    
    # 默认路径配置
    default_base_dir = "/home/ym/DeepSlide/jiahangceshi_data_copy"
    
    parser.add_argument("--content", type=str, default=os.path.join(default_base_dir, "content.tex"),
                        help="Path to the Latex content file (content.tex)")
    parser.add_argument("--speech", type=str, default=os.path.join(default_base_dir, "speech_script.txt"),
                        help="Path to the speech script file (speech_script.txt)")
    parser.add_argument("--output_dir", type=str, default=default_base_dir,
                        help="Directory to save the output files (alignment.json)")
    parser.add_argument("--api_key", type=str, default="sk-6286dc11a31e45649dbf55081b8aef20",
                        help="DeepSeek API Key")
    
    return parser.parse_args()

def align_process(content_file, speech_file, output_dir, api_key):
    print(f"Starting alignment process...")
    print(f"Content File: {content_file}")
    print(f"Speech File:  {speech_file}")
    
    if not os.path.exists(content_file) or not os.path.exists(speech_file):
        print("Error: Input files do not exist.")
        return

    # 1. 解析 Content (Parse Content)
    c = Content()
    c.from_file(content_file)
    frames = [item for item in c if isinstance(item, Frame)]
    print(f"Found {len(frames)} frames in content.")
    
    # 2. 解析 Speech (Parse Speech)
    with open(speech_file, "r", encoding="utf-8") as f:
        full_text = f.read()
        
    # 按 <next> 分割
    raw_segments = full_text.split('<next>')
    segments = [s.strip() for s in raw_segments]
    print(f"Found {len(segments)} speech segments.")
    
    # 3. 构建 Prompt (Construct Prompt)
    prompt_slides = ""
    for i, frame in enumerate(frames):
        content = str(frame).strip()[:2000] # Limit length
        prompt_slides += f"--- SLIDE {i} ---\n{content}\n\n"
        
    prompt_speech = ""
    for i, seg in enumerate(segments):
        if not seg: continue
        content = seg[:2000] # Limit length
        prompt_speech += f"--- SPEECH {i} ---\n{content}\n\n"
        
    system_prompt = """You are an intelligent presentation assistant.
You have a list of SLIDES (Latex Frames) and a list of SPEECH SEGMENTS.
Your task is to align them.

Constraint:
- The speech segments are sequential.
- The slides are sequential.
- Usually, one speech segment corresponds to one slide.
- However, some speech segments are "extra" (e.g., Intro, Outro, Transitions) and do not have a matching slide.
- Identify the matching pairs.

Return JSON format:
{
  "matches": [
    {"slide_index": 0, "speech_index": 1},
    {"slide_index": 1, "speech_index": 2}
  ]
}

Rules:
1. Every SLIDE must be matched to exactly one SPEECH segment. Pick the best fit.
2. If a speech segment is an intro/outro/transition that doesn't correspond to the slide's specific visual content, do NOT match it.
3. Return only the JSON.
"""

    user_prompt = f"SLIDES:\n{prompt_slides}\n\nSPEECH SEGMENTS:\n{prompt_speech}"
    
    # 4. 调用 DeepSeek API (Call DeepSeek)
    print("Sending request to DeepSeek...")
    url = "https://api.deepseek.com/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content']
        print("Received response from DeepSeek.")
        
        if "```" in content:
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```', '', content)
            
        data = json.loads(content)
        matches = data.get("matches", [])
        
    except Exception as e:
        print(f"Error communicating with DeepSeek: {e}")
        return

    print(f"Received {len(matches)} matches.")
    
    # 5. 处理结果 (Process Results)
    slide_to_speech = {m['slide_index']: m['speech_index'] for m in matches}
    matched_speech_indices = set(m['speech_index'] for m in matches)
    
    alignment_output = []
    
    for i, frame in enumerate(frames):
        if i in slide_to_speech:
            speech_idx = slide_to_speech[i]
            if 0 <= speech_idx < len(segments):
                alignment_output.append((str(frame), segments[speech_idx]))
            else:
                print(f"Warning: Invalid speech index {speech_idx} for slide {i}")
        else:
            print(f"Warning: Slide {i} has no matching speech.")
            
    output_json_path = os.path.join(output_dir, "alignment.json")
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(alignment_output, f, ensure_ascii=False, indent=2)
    print(f"Alignment saved to {output_json_path}")
    
    # 6. 更新 Speech 文件 (Update Speech File)
    # 我们不直接覆盖原始文件，而是保留原始逻辑：对 unmatched 的添加 <add> 标签
    # We reconstruct the segments to verify logic, but we write back to the speech file as requested.
    
    new_segments = []
    for i, seg in enumerate(segments):
        if i not in matched_speech_indices and seg:
            # 如果尚未添加 <add> 标签，则添加
            if not seg.startswith("<add>"):
                new_segments.append("<add>" + seg)
            else:
                new_segments.append(seg)
        else:
            new_segments.append(seg)
            
    new_content = "\n<next>\n".join(new_segments)
    
    with open(speech_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"Speech script updated at {speech_file}")

if __name__ == "__main__":
    args = parse_arguments()
    align_process(args.content, args.speech, args.output_dir, args.api_key)
