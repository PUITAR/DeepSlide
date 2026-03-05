import os
import fitz
import logging
import base64
from typing import List, Dict, Any, Optional

from app.services.core.compiler.compiler import Compiler

logger = logging.getLogger(__name__)

class CompilerService:
    def __init__(self):
        self.compiler = Compiler()

    def compile_project(self, project_path: str) -> Dict[str, Any]:
        """
        Compiles the project using the core Compiler.
        """
        logger.info(f"Compiling project at {project_path}")
        result = self.compiler.run(project_path)
        
        if result.get("success"):
            # Generate preview images immediately after success
            # self.generate_preview_images(project_path) # Done in get_preview usually
            pass
            
        return result

    def generate_preview_images(self, project_path: str) -> List[str]:
        """
        Generates PNG images for each page of the compiled PDF and returns Base64 strings.
        """
        pdf_path = os.path.join(project_path, "base.pdf")
        
        if not os.path.exists(pdf_path):
            return []
        
        try:
            doc = fitz.open(pdf_path)
            images_base64 = []
            
            for pn in range(doc.page_count):
                page = doc.load_page(pn)
                # Matrix=2 for better quality
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")
                b64_str = base64.b64encode(img_data).decode("utf-8")
                images_base64.append(f"data:image/png;base64,{b64_str}")
                
            doc.close()
            return images_base64
        except Exception as e:
            logger.error(f"Error generating preview: {e}")
            return []

compiler_service = CompilerService()
