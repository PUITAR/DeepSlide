import os
import shutil
import uuid
import logging
import subprocess
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class AudioService:
    def __init__(self):
        self.root_dir = settings.BASE_DIR # deepslide-v3/backend
        # Assuming index-tts is at the same level as backend or configured path
        # The original code pointed to ROOT/index-tts/index-tts-main
        # ROOT was /home/ym/DeepSlide
        self.repo_root = os.path.dirname(os.path.dirname(os.path.dirname(self.root_dir))) # /home/ym/DeepSlide
        self.index_tts_dir = os.path.join(self.repo_root, "index-tts", "index-tts-main")

    def _log(self, msg: str):
        logger.info(msg)

    async def generate_speech(self, project_id: str, text: str, page_index: int, voice_id: str = 'examples/voice_03.wav') -> str:
        project_dir = os.path.join(settings.PROJECT_STORAGE_DIR, project_id)
        audio_dir = os.path.join(project_dir, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        
        output_filename = f"speech_{page_index}.wav"
        output_path = os.path.join(audio_dir, output_filename)
        
        # Temporary file for text
        temp_text_path = os.path.join(audio_dir, f"temp_text_{page_index}.txt")
        with open(temp_text_path, "w", encoding="utf-8") as f:
            f.write(text)

        # Call TTS logic
        # We can reuse the python script approach from original code
        
        python_logic = f"""
import os, sys, traceback
try:
    from indextts.infer_v2 import IndexTTS2
    from tqdm import tqdm
except ImportError:
    print("ImportError: Failed to import IndexTTS2 or tqdm")
    sys.exit(1)
os.environ['USE_MODELSCOPE'] = '1'
try:
    print("Initializing IndexTTS2...")
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
except Exception as e:
    print(f"Failed to init GPU IndexTTS2: {{e}}")
    try:
        print("Fallback to CPU IndexTTS2...")
        tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=False, use_cuda_kernel=False, use_deepspeed=False, device='cpu')
    except Exception as e2:
        print(f"Failed to init CPU IndexTTS2: {{e2}}")
        traceback.print_exc()
        sys.exit(1)

text = \"\"\"{text}\"\"\".strip().replace("<add>", "").strip()
if text:
    output_path = '{output_path}'
    print(f"Generating {{output_path}}...")
    try:
        tts.infer(spk_audio_prompt='{voice_id}', text=text, output_path=output_path, verbose=True)
    except Exception as e:
        print(f"Error generating {{output_path}}: {{e}}")
        traceback.print_exc()
        sys.exit(1)
"""
        
        # Locate uv
        uv_path = shutil.which("uv")
        if not uv_path:
             possible_paths = ["/home/ym/anaconda3/bin/uv", "/usr/local/bin/uv", "/usr/bin/uv"]
             for p in possible_paths:
                 if os.path.exists(p):
                     uv_path = p
                     break
        
        if not uv_path:
            logger.error("uv not found")
            return ""

        cmd = [uv_path, "run", "python", "-c", python_logic]
        
        env = os.environ.copy()
        if uv_path:
            uv_dir = os.path.dirname(uv_path)
            if uv_dir not in env.get("PATH", ""):
                env["PATH"] = f"{uv_dir}:{env.get('PATH', '')}"

        try:
            process = subprocess.Popen(
                cmd, 
                cwd=self.index_tts_dir, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                env=env
            )
            stdout, _ = process.communicate()
            logger.info(f"TTS Output: {stdout}")
            
            if process.returncode == 0 and os.path.exists(output_path):
                # Return relative path or URL
                return f"/api/project/{project_id}/files/audio/{output_filename}"
            else:
                logger.error(f"TTS Failed: {stdout}")
                return ""
                
        except Exception as e:
            logger.error(f"TTS Execution Error: {e}")
            return ""

audio_service = AudioService()
