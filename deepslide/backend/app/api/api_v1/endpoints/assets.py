import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/logo.jpg")
def get_logo():
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
    project_root = os.path.abspath(os.path.join(backend_root, ".."))
    candidates = [
        os.path.join(project_root, "frontend", "public", "assets", "logo.jpg"),
        os.path.join(project_root, "frontend", "dist", "assets", "logo.jpg"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Logo not found")
