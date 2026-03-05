from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import subprocess
import time
import uuid

from app.api.api_v1.endpoints.projects import projects_db
from app.services.asr_service import asr_service

router = APIRouter()


class GenerateTTSRequest(BaseModel):
    page_index: int


def _get_project(project_id: str):
    for p in projects_db:
        if p.get("project_id") == project_id:
            return p
    return None


def _run_tts_index(text: str, out_path: str, voice_prompt: str):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../.."))
    index_tts_dir = os.path.join(root, "index-tts", "index-tts-main")
    if not os.path.isdir(index_tts_dir):
        # Fallback to simple index-tts
        index_tts_dir = os.path.join(root, "index-tts")
        if not os.path.isdir(index_tts_dir):
            raise RuntimeError(f"index-tts not found at {index_tts_dir}")

    code = f"""
import os
import sys
try:
    from indextts.infer_v2 import IndexTTS2
except ImportError:
    sys.path.append(os.getcwd())
    try:
        from indextts.infer_v2 import IndexTTS2
    except ImportError:
        from indextts.infer import IndexTTS2

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['USE_MODELSCOPE'] = '1'

# Try v2 init
try:
    device = os.environ.get('INDEXTTS_DEVICE') or os.environ.get('DS_TTS_DEVICE')
    if not device:
        try:
            import torch
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        except Exception:
            device = 'cpu'

    use_fp16 = device.startswith('cuda')
    use_cuda_kernel = device.startswith('cuda')
    use_deepspeed = False

    try:
        tts = IndexTTS2(model_dir='checkpoints', cfg_path='checkpoints/config.yaml', use_fp16=use_fp16, use_cuda_kernel=use_cuda_kernel, use_deepspeed=use_deepspeed, device=device)
    except Exception:
        tts = IndexTTS2(model_dir='checkpoints', cfg_path='checkpoints/config.yaml', use_fp16=False, use_cuda_kernel=False, use_deepspeed=False, device='cpu')
except Exception:
    # Fallback to v1 init
    tts = IndexTTS2(model_dir='checkpoints', cfg_path='config.yaml')

tts.infer(
    text={text!r},
    output_path={out_path!r},
    prompt_speaker={None!r},
    spk_audio_prompt={voice_prompt!r},
    prompt_text='',
    prompt_language='auto',
    text_language='auto',
    temperature=0.8,
    top_p=0.8,
    top_k=30,
)
"""
    import shutil
    uv_path = shutil.which("uv")
    if not uv_path:
        for p in ["/home/ym/anaconda3/bin/uv", "/usr/local/bin/uv", "/usr/bin/uv"]:
             if os.path.exists(p):
                 uv_path = p
                 break
    
    cmd = [uv_path or "uv", "run", "--python", "3.10", "python", "-c", code]
    
    env = os.environ.copy()
    if uv_path:
        uv_dir = os.path.dirname(uv_path)
        if uv_dir not in env.get("PATH", ""):
             env["PATH"] = f"{uv_dir}:{env.get('PATH', '')}"

    started = time.time()
    proc = subprocess.run(cmd, cwd=index_tts_dir, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "tts failed")[:2000])
    if not os.path.exists(out_path):
        raise RuntimeError("tts output missing")


def _get_project_exists(project_id: str) -> bool:
    for p in projects_db:
        if p.get("project_id") == project_id:
            return True
    return False


@router.post("/{project_id}/tts/generate")
async def generate_tts(project_id: str, req: GenerateTTSRequest):
    p = _get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    recipe_dir = os.path.join(p["path"], "recipe")
    speech_path = os.path.join(recipe_dir, "speech.txt")
    if not os.path.exists(speech_path):
        raise HTTPException(status_code=404, detail="speech.txt not found")
    try:
        with open(speech_path, "r", encoding="utf-8", errors="ignore") as f:
            speech_txt = f.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read speech.txt")

    parts = [s.strip() for s in speech_txt.split("<next>")]
    page_index = int(req.page_index)
    if page_index < 0 or page_index >= len(parts):
        raise HTTPException(status_code=400, detail="Invalid page_index")
    text = parts[page_index]
    if not text:
        raise HTTPException(status_code=400, detail="Empty speech for this page")

    out_dir = os.path.join(recipe_dir, "audio")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{page_index + 1}.wav")

    voice_prompt = p.get("selected_voice_path") or p.get("voice_prompt_path") or "examples/voice_03.wav"
    if not os.path.isabs(voice_prompt):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
        alt = os.path.join(root, "index-tts", voice_prompt)
        if os.path.exists(alt):
            voice_prompt = alt

    if not os.path.exists(out_path):
        _run_tts_index(text, out_path, voice_prompt)

    return {"success": True, "url": f"/api/v1/projects/{project_id}/tts/{page_index}"}


@router.get("/{project_id}/tts/{page_index}")
async def get_tts_audio(project_id: str, page_index: int):
    p = _get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    recipe_dir = os.path.join(p["path"], "recipe")
    out_path = os.path.join(recipe_dir, "audio", f"{int(page_index) + 1}.wav")
    if not os.path.exists(out_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(out_path, media_type="audio/wav", filename=os.path.basename(out_path))


@router.post("/{project_id}/audio/transcribe")
async def transcribe(
    project_id: str, 
    audio: UploadFile = File(...), 
    lang: str = Form("zh"),
    save_voice: bool = Form(False)
):
    if not _get_project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    tmp_dir = os.path.join("storage", "asr_uploads", project_id)
    os.makedirs(tmp_dir, exist_ok=True)

    ext = os.path.splitext(audio.filename or "")[1] or ".webm"
    file_path = os.path.join(tmp_dir, f"asr_{uuid.uuid4().hex}{ext}")
    content = await audio.read()
    if not content or len(content) < 100:
        raise HTTPException(status_code=400, detail="Empty audio")
    with open(file_path, "wb") as f:
        f.write(content)

    text = await asr_service.transcribe_file(file_path, lang=lang)
    if not text:
        raise HTTPException(status_code=500, detail="Transcription failed")
        
    result = {"text": text}
    
    if save_voice:
        # Save as voice clone sample
        voice_dir = os.path.join("storage", "voice_clones", project_id)
        os.makedirs(voice_dir, exist_ok=True)
        # We convert to wav or just keep original format?
        # Ideally we should convert to wav for TTS, but for now we just save the file.
        # Let's save as voice_prompt.wav (assuming downstream can handle it or we rename)
        # But audio.filename extension might be webm. 
        # For simplicity, we just copy the uploaded file to voice_prompt{ext}
        # And update project metadata (mock db)
        
        voice_path = os.path.join(voice_dir, f"voice_prompt{ext}")
        import shutil
        shutil.copy2(file_path, voice_path)
        
        # Update project in db
        for p in projects_db:
            if p["project_id"] == project_id:
                p["voice_prompt_path"] = voice_path
                break
                
        result["voice_cloned"] = True
        result["voice_path"] = voice_path
        
    return result
