from fastapi import APIRouter
from app.api.api_v1.endpoints import projects, editor, audio, assets, preview_insights

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(editor.router, prefix="/projects", tags=["editor"])
api_router.include_router(audio.router, prefix="/projects", tags=["audio"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(preview_insights.router, prefix="/projects", tags=["preview"])
