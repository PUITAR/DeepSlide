import os
import subprocess

# 1. 配置路径
# 脚本所在目录 (webui/presentation_previewer_auto)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Index-TTS 根目录
INDEX_TTS_DIR = "/home/ym/DeepSlide/index-tts/index-tts-main"
# 采样文件和输出目录的绝对路径
SAMPLE_FILE = os.path.join(CURRENT_DIR, "sample.txt")
OUTPUT_DIR = os.path.join(CURRENT_DIR, "audio")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# 2. 构建要在 index-tts 目录下执行的 Python 代码
# 我们把逻辑写成一个字符串，通过 python -c 执行
python_logic = f"""
import os
from indextts.infer_v2 import IndexTTS2
from tqdm import tqdm

os.environ['USE_MODELSCOPE'] = '1'

tts = IndexTTS2(
    cfg_path='checkpoints/config.yaml', 
    model_dir='checkpoints', 
    use_fp16=False, 
    use_cuda_kernel=False, 
    use_deepspeed=False
)

with open('{SAMPLE_FILE}', 'r', encoding='utf-8') as f:
    sample_text = f.read().split('<next>')

for i, text in tqdm(enumerate(sample_text), desc="Generating audios"):
    text = text.strip()
    if not text: continue
    output_path = os.path.join('{OUTPUT_DIR}', f'{{i+1}}.wav')
    tts.infer(
        spk_audio_prompt='examples/voice_03.wav', 
        text=text, 
        output_path=output_path, 
        verbose=True
    )
"""

# 3. 使用 subprocess 调用 index-tts 目录下的 uv 环境运行
# 这样会自动使用 index-tts-main 目录下的 .venv 和依赖
print(f"Starting audio generation in {INDEX_TTS_DIR}...")

try:
    subprocess.run(
        ["uv", "run", "python", "-c", python_logic],
        cwd=INDEX_TTS_DIR,  # 关键：切换工作目录到 index-tts
        check=True
    )
    print(f"\nSuccess! Audios are saved in: {OUTPUT_DIR}")
except subprocess.CalledProcessError as e:
    print(f"\nError occurred while running Index-TTS: {e}")