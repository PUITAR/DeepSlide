from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
from pathlib import Path
import time
import uuid

app = FastAPI(title="DeepSlide WebUI Stub API", version="0.1.0")

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

sessions = {}

def stage_status(elapsed: float):
    stages = {"rag": "pending", "summary": "pending", "plan": "pending", "generate": "pending"}
    if elapsed < 1.5:
        stages["rag"] = "running"
    elif elapsed < 3.0:
        stages["rag"] = "completed"
        stages["summary"] = "running"
    elif elapsed < 4.5:
        stages["rag"] = "completed"
        stages["summary"] = "completed"
        stages["plan"] = "running"
    elif elapsed < 6.0:
        stages["rag"] = "completed"
        stages["summary"] = "completed"
        stages["plan"] = "completed"
        stages["generate"] = "running"
    else:
        for k in stages:
            stages[k] = "completed"
    return stages

@app.get("/")
async def root():
    return {"message": "Stub API running"}

@app.post("/api/chat")
async def chat(
    message: str = Form(""),
    content: str = Form("paper"),
    output_type: str = Form("slides"),
    style: str = Form("academic"),
    length: Optional[str] = Form(None),
    density: Optional[str] = Form(None),
    fast_mode: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    files: List[UploadFile] = File([]),
):
    sid = session_id or str(uuid.uuid4())
    session_dir = UPLOAD_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        dest = session_dir / f.filename
        with dest.open("wb") as w:
            w.write(await f.read())
        saved.append({"name": f.filename, "url": f"/uploads/{sid}/{f.filename}"})
    sessions[sid] = {
        "start": time.time(),
        "cancelled": False,
        "output_type": output_type,
        "content": content,
        "style": style,
        "length": length,
        "density": density,
    }
    return {"message": "Accepted", "session_id": sid, "uploaded_files": saved}

@app.post("/api/cancel/{session_id}")
async def cancel(session_id: str):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    s["cancelled"] = True
    return {"message": "Cancelled", "cancelled": True}

@app.get("/api/status/{session_id}")
async def status(session_id: str):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.get("cancelled"):
        st = {"rag": "failed", "summary": "failed", "plan": "failed", "generate": "failed"}
        return {"stages": st, "error": "Cancelled"}
    elapsed = time.time() - s["start"]
    st = stage_status(elapsed)
    return {"stages": st}

@app.get("/api/result/{session_id}")
async def result(session_id: str):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.get("cancelled"):
        raise HTTPException(status_code=400, detail="Cancelled")
    elapsed = time.time() - s["start"]
    if elapsed < 6.0:
        return JSONResponse(status_code=202, content={"status": "processing"})
    out = {"message": "", "slides": [{"index": i} for i in range(1, 6)]}
    img = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='800' height='450'><rect width='100%25' height='100%25' fill='%23f5f3ff'/><text x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='36' fill='%23634ca6'>DeepSlide Stub Output</text></svg>"
    if s.get("output_type") == "slides":
        out["ppt_url"] = img
    else:
        out["poster_url"] = img
    return out
