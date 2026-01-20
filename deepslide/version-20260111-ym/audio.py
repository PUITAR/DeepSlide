import os
import sys
import subprocess
import streamlit as st
from core import _log, ROOT

def transcribe_audio(audio_path: str) -> str:
    try:
        import dashscope
        from dotenv import load_dotenv
        
        # Load env
        env_path = os.path.join(os.path.dirname(__file__), '../config/env/.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
            
        api_key = os.getenv("DEFAULT_ASR_API_KEY")
        if not api_key:
            _log("ASR Error: DASHSCOPE_API_KEY not found in env.")
            return ""

        _log(f"Starting ASR (API) for {audio_path}")
        
        # 1. Check file
        if not os.path.exists(audio_path):
             _log(f"ASR Error: File not found: {audio_path}")
             return ""
        size = os.path.getsize(audio_path)
        if size < 100:
             _log("ASR Warning: Audio file too small.")
             return ""

        # 2. Call DashScope API
        api_url = os.getenv("DEFAULT_ASR_API_URL")
        if not api_url:
            _log("ASR Error: DEFAULT_ASR_API_URL not found in env.")
            return ""
        dashscope.base_http_api_url = api_url
        
        # Use file:// protocol for local files
        local_file_url = f"file://{os.path.abspath(audio_path)}"
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"audio": local_file_url}
                ]
            }
        ]
        
        response = dashscope.MultiModalConversation.call(
            api_key=api_key,
            model="qwen3-asr-flash", # As requested
            messages=messages,
            result_format="message",
            asr_options={
                "enable_itn": False
            }
        )
        
        _log(f"ASR API Response: {response}")

        if response.status_code == 200:
            # Parse output
            try:
                if hasattr(response, 'output') and response.output.choices:
                    content = response.output.choices[0].message.content
                    # Content is a list of dicts for multimodal
                    if isinstance(content, list):
                        for item in content:
                            if "text" in item:
                                return item["text"]
                    # Fallback
                    return str(content)
            except Exception as parse_e:
                _log(f"ASR Parse Error: {parse_e}")
                return ""
        else:
            _log(f"ASR API Failed: {response.code} - {response.message}")
            return ""
            
    except Exception as e:
        _log(f"STT Error: {e}")
        import traceback
        _log(traceback.format_exc())
        return ""

def _stt_available() -> bool:
    try:
        import dashscope
        return True
    except ImportError:
        return False

def ensure_asr_model_ready() -> bool:
    # API based, just check if dashscope is installed and key exists
    if not _stt_available():
        _log("ASR Error: dashscope package not installed.")
        return False
    return True

def run_tts(speech_text: str, output_dir: str, voice_prompt: str = 'examples/voice_03.wav') -> bool:
    import shutil
    from dotenv import load_dotenv

    env_path = os.path.join(os.path.dirname(__file__), '../config/env/.env')
    load_dotenv(env_path)

    os.makedirs(output_dir, exist_ok=True)
    sample_file = os.path.join(output_dir, "speech_script.txt")
    with open(sample_file, "w", encoding="utf-8") as f:
        f.write(speech_text)
    index_tts_dir = os.path.join(ROOT, "index-tts/index-tts-main")
    
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

try:
    with open('{sample_file}', 'r', encoding='utf-8') as f:
        sample_text = f.read().split('<next>')
    print(f"Loaded {{len(sample_text)}} speech segments.")
except Exception as e:
    print(f"Failed to read sample file: {{e}}")
    sys.exit(1)

for i, text in tqdm(enumerate(sample_text)):
    text = text.strip().replace("<add>", "").strip()
    if not text: continue
    output_path = os.path.join('{output_dir}', f'{{i+1}}.wav')
    print(f"Generating {{output_path}}...")
    try:
        tts.infer(spk_audio_prompt='{voice_prompt}', text=text, output_path=output_path, verbose=True)
    except Exception as e:
        print(f"Error generating {{output_path}}: {{e}}")
        traceback.print_exc()
"""
    try:
        # Locate uv
        uv_path = shutil.which("uv")
        if not uv_path:
            # Fallback for common paths
            possible_paths = ["/home/ym/anaconda3/bin/uv", "/usr/local/bin/uv", "/usr/bin/uv"]
            for p in possible_paths:
                if os.path.exists(p):
                    uv_path = p
                    break
        
        if not uv_path:
            msg = "Error: 'uv' command not found. Please install uv or ensure it's in the PATH."
            _log(msg)
            st.error(msg)
            return False

        _log(f"Starting TTS generation in {index_tts_dir} using {uv_path}")
        st.write("Running TTS inference...")
        cmd = [uv_path, "run", "python", "-c", python_logic]
        
        # Prepare env with PATH
        env = os.environ.copy()
        
        # Add the directory containing 'uv' to PATH if it's not already there
        if uv_path:
            uv_dir = os.path.dirname(uv_path)
            if uv_dir not in env.get("PATH", ""):
                env["PATH"] = f"{uv_dir}:{env.get('PATH', '')}"

        # Stream output to log and UI
        process = subprocess.Popen(
            cmd, 
            cwd=index_tts_dir, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1,
            env=env
        )
        
        # Read output line by line
        for line in process.stdout:
            line = line.strip()
            if line:
                _log(f"TTS: {line}")
        
        process.wait()
        
        if process.returncode == 0:
            _log("TTS Generation completed.")
            st.write("TTS Generation completed.")
            return True
        else:
            _log(f"TTS Generation failed with code {process.returncode}")
            st.error(f"TTS Generation failed with code {process.returncode}")
            return False
            
    except Exception as e:
        _log(f"TTS Execution Error: {e}")
        st.error(f"TTS Execution Error: {e}")
        return False
