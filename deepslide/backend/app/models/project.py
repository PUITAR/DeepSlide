from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid

class ProjectBase(BaseModel):
    name: str = "Untitled Project"
    requirements: Dict[str, Any] = {}
    template: str = "default"

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: str
    status: str = "created"
    created_at: datetime
    updated_at: datetime
    files: Dict[str, str] = {} # filename -> path

    class Config:
        from_attributes = True

class FileUpdate(BaseModel):
    content: str

class AIModificationRequest(BaseModel):
    instruction: str
    target_type: str # "content", "speech", "title"
    page_index: Optional[int] = None

class SpeechGenerationRequest(BaseModel):
    text: str
    page_index: int
    voice_id: Optional[str] = None
