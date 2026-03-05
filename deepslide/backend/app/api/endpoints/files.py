from fastapi import APIRouter, HTTPException, Depends
from app.models.project import FileUpdate
from app.services.project_service import project_service
from app.core.config import settings
import os
import aiofiles

router = APIRouter()

@router.get("/{project_id}/files/{filename}")
async def get_file_content(project_id: str, filename: str):
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    file_path = os.path.join(settings.PROJECT_STORAGE_DIR, project_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    async with aiofiles.open(file_path, 'r') as f:
        content = await f.read()
    return {"content": content}

@router.put("/{project_id}/files/{filename}")
async def update_file_content(project_id: str, filename: str, file_update: FileUpdate):
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    file_path = os.path.join(settings.PROJECT_STORAGE_DIR, project_id, filename)
    
    async with aiofiles.open(file_path, 'w') as f:
        await f.write(file_update.content)
        
    return {"success": True, "message": "File updated"}
