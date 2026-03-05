from fastapi import APIRouter, HTTPException
from app.models.project import AIModificationRequest
from app.services.ai_service import ai_service

router = APIRouter()

@router.post("/{project_id}/modify")
async def modify_slide(project_id: str, request: AIModificationRequest):
    result = await ai_service.modify_slide(
        project_id, 
        request.instruction, 
        request.target_type, 
        request.page_index
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result
