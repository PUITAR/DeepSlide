import os
import shutil
import uuid
import json
from datetime import datetime
from typing import Optional, Dict
from app.core.config import settings
from app.models.project import Project, ProjectCreate
import aiofiles

class ProjectService:
    def __init__(self):
        self.storage_dir = settings.PROJECT_STORAGE_DIR

    async def create_project(self, project_in: ProjectCreate) -> Project:
        project_id = str(uuid.uuid4())
        project_dir = os.path.join(self.storage_dir, project_id)
        os.makedirs(project_dir, exist_ok=True)

        # Create metadata file
        now = datetime.utcnow()
        project = Project(
            id=project_id,
            name=project_in.name,
            requirements=project_in.requirements,
            template=project_in.template,
            created_at=now,
            updated_at=now,
            files={}
        )
        
        await self._save_project_metadata(project)
        
        # Initialize basic files (mocking template copy for now)
        await self._init_project_files(project_dir, project_in.template)
        
        return project

    async def get_project(self, project_id: str) -> Optional[Project]:
        project_dir = os.path.join(self.storage_dir, project_id)
        metadata_path = os.path.join(project_dir, "metadata.json")
        
        if not os.path.exists(metadata_path):
            return None
            
        async with aiofiles.open(metadata_path, 'r') as f:
            content = await f.read()
            data = json.loads(content)
            # Convert ISO strings back to datetime
            data['created_at'] = datetime.fromisoformat(data['created_at'])
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
            return Project(**data)

    async def _save_project_metadata(self, project: Project):
        project_dir = os.path.join(self.storage_dir, project.id)
        metadata_path = os.path.join(project_dir, "metadata.json")
        
        data = project.model_dump()
        # Convert datetime to ISO strings for JSON
        data['created_at'] = data['created_at'].isoformat()
        data['updated_at'] = data['updated_at'].isoformat()
        
        async with aiofiles.open(metadata_path, 'w') as f:
            await f.write(json.dumps(data, indent=2))

    async def _init_project_files(self, project_dir: str, template: str):
        # Create standard files
        files = ["content.tex", "title.tex", "base.tex", "speech.txt"]
        for filename in files:
            path = os.path.join(project_dir, filename)
            async with aiofiles.open(path, 'w') as f:
                if filename == "content.tex":
                    await f.write("% Content goes here")
                elif filename == "title.tex":
                    name = os.path.basename(project_dir)
                    safe = (
                        name.replace('\\', r"\textbackslash{}")
                        .replace('{', r"\{")
                        .replace('}', r"\}")
                        .replace('_', r"\_")
                    )
                    await f.write(f"\\title{{{safe}}}\n\\author{{DeepSlide}}\n\\date{{\\today}}")
                elif filename == "base.tex":
                    await f.write("\\documentclass{beamer}\\begin{document}\\input{title.tex}\\input{content.tex}\\end{document}")
                else:
                    await f.write("")

project_service = ProjectService()
