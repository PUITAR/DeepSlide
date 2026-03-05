from fastapi import APIRouter, HTTPException, Depends
from app.models.project import Project, ProjectCreate
from app.services.project_service import project_service
from app.services.compiler_service import compiler_service
from app.core.config import settings
import os

router = APIRouter()

@router.post("/create", response_model=Project)
async def create_project(project_in: ProjectCreate):
    try:
        return await project_service.create_project(project_in)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.post("/{project_id}/compile")
async def compile_project(project_id: str):
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project_dir = os.path.join(settings.PROJECT_STORAGE_DIR, project_id)
    result = await compiler_service.compile_project(project_dir)
    return result
