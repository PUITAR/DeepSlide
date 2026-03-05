from fastapi import APIRouter, HTTPException
from app.models.project import SpeechGenerationRequest
from app.services.audio_service import audio_service

router = APIRouter()

@router.post("/{project_id}/generate")
async def generate_speech(project_id: str, request: SpeechGenerationRequest):
    audio_url = await audio_service.generate_speech(
        project_id, 
        request.text, 
        request.page_index, 
        request.voice_id
    )
    
    if not audio_url:
        raise HTTPException(status_code=500, detail="Speech generation failed")
        
    return {"audio_url": audio_url, "duration": 0} # Duration calculation to be added
