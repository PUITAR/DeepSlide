import os
# import fitz  # PyMuPDF -> Moved to subprocess to avoid segfaults
import json
import logging
import subprocess
import tempfile
import sys
import re
from typing import List, Tuple, Optional, Dict, Any
from dotenv import load_dotenv

from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent

logger = logging.getLogger(__name__)

class SpeechAligner:
    def __init__(self):
        self._init_llm()

    def _init_llm(self):
        # Load env similar to other agents
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../config/env/.env'))
        if os.path.exists(env_path):
            load_dotenv(env_path)
        
        api_key = os.getenv('DEFAULT_MODEL_API_KEY') or os.getenv('LLM_API_KEY')
        if not api_key:
            logger.warning("LLM API Key not found. SpeechAligner will not work properly.")
            self.llm_model = None
            return

        model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')
        base_url = os.getenv('DEFAULT_MODEL_API_URL', 'https://api.deepseek.com')
        
        self.llm_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=model_type,
            url=base_url,
            api_key=api_key,
            model_config_dict={
                "temperature": 0.1,  # Low temperature for stability
                "max_tokens": 4096
            }
        )

    def _extract_text(self, pdf_path: str) -> List[str]:
        """Extract text from PDF using a subprocess to avoid segfaults."""
        try:
            logger.info(f"Opening PDF in subprocess: {pdf_path}")
            
            # Script to run in subprocess
            script = """
import sys
import json
import fitz

def extract(path):
    try:
        doc = fitz.open(path)
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text("text")
            text = " ".join(text.split())
            # Truncate to avoid context window issues
            pages.append(f"Page {i+1}: {text[:min(800, len(text))]}")
        doc.close()
        print(json.dumps(pages))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    extract(sys.argv[1])
"""
            
            # Run the subprocess
            result = subprocess.run(
                [sys.executable, "-c", script, pdf_path],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                logger.error(f"Subprocess failed with code {result.returncode}: {result.stderr}")
                return []

            output = result.stdout.strip()
            if not output:
                logger.warning("Subprocess returned empty output")
                return []
                
            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON from subprocess: {output}")
                return []
            
            if isinstance(data, dict) and "error" in data:
                logger.error(f"Subprocess error: {data['error']}")
                return []
                
            if isinstance(data, list):
                logger.info(f"Extracted {len(data)} pages")
                return data
                
            return []

        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _parse_frames(self, content_tex: str) -> List[str]:
        """Extract LaTeX frames from content.tex"""
        matches = list(re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', content_tex, re.DOTALL))
        return [m.group(1) for m in matches]

    def align(self, pdf_path: str, original_speeches: List[str], content_tex: Optional[str] = None) -> Dict[str, Any]:
        """
        Align original speeches with PDF pages and LaTeX frames.
        
        Returns:
            Dict with keys:
            - 'speeches': List[str] (The full list of aligned speeches for PDF generation)
            - 'alignment': List[Tuple[str, str]] (List of (Latex_Frame, Speech) tuples for Graph Generation)
        """
        print("In align method")
        if not self.llm_model:
            logger.error("LLM not initialized.")
            return {"speeches": original_speeches, "alignment": []}

        if not os.path.exists(pdf_path):
            logger.error(f"PDF not found: {pdf_path}")
            return {"speeches": original_speeches, "alignment": []}

        print("start to extract text from pdf")

        # 1. Extract text from PDF
        pdf_pages_text = self._extract_text(pdf_path)
        print(f"Extracted PDF pages: {len(pdf_pages_text)}")

        if not pdf_pages_text:
            return {"speeches": original_speeches, "alignment": []}
            
        # 2. Extract Frames if content_tex provided
        frames = []
        if content_tex:
            frames = self._parse_frames(content_tex)
            print(f"Extracted LaTeX Frames: {len(frames)}")

        # 3. Construct Prompt
        formatted_speeches = []
        for i, s in enumerate(original_speeches):
            # NO TRUNCATION to avoid LLM returning truncated text
            formatted_speeches.append(f"Script Fragment {i+1}: {str(s)}")
            
        formatted_frames = []
        for i, f in enumerate(frames):
            # Frames can be truncated as they are reference for matching
            formatted_frames.append(f"Frame {i+1}: {str(f)[:min(500, len(f))]}...")

        pdf_context = "\n\n".join(pdf_pages_text)
        script_context = "\n\n".join(formatted_speeches)
        frame_context = "\n\n".join(formatted_frames) if frames else "No LaTeX frames provided."

        system_content = """You are a professional presentation speech editor and structural analyst.
Your task is to align a set of pre-written speech scripts with the actual slides of a generated PDF, AND match them to their source LaTeX code (if applicable).

Inputs:
1. Text extracted from each page of the PDF.
2. A list of pre-written speech fragments (Script Fragments).
3. A list of LaTeX Frame codes (Frames).

Instructions:
1. Analyze the PDF page content to identify its type:
   - **Cover/Title/TOC/Divider/End**: These are Structural Pages. They usually DO NOT have a corresponding "Script Fragment" or "Frame".
   - **Content Slide**: These correspond to the pre-written "Script Fragments" and "Frames".

2. Generate a JSON list where the N-th element corresponds EXACTLY to the N-th page of the PDF.
   Each element should be an object:
   {
     "pdf_page_index": <int>,
     "speech": "<string>",
     "matched_frame_index": <int or null> 
   }

   - **speech**: 
     - For Structural Pages (Cover, TOC, etc.): Generate a new speech starting with `<add>`.
     - For Content Slides: Use the content from the matching "Script Fragment".
   - **matched_frame_index**:
     - If this PDF page corresponds to one of the provided "Frames", put the index of that frame (1-based).
     - If it is a Structural Page (no LaTeX source frame), set to null.

3. Output Format:
   - Return ONLY the JSON list.
   - The length MUST match the number of PDF pages exactly.
"""

        user_content = f"""
Number of PDF Pages: {len(pdf_pages_text)}
Number of Script Fragments: {len(original_speeches)}
Number of Frames: {len(frames)}

--- PDF CONTENT ---
{pdf_context}

--- SCRIPT FRAGMENTS ---
{script_context}

--- LATEX FRAMES ---
{frame_context}

Please generate the alignment JSON.
"""

        # 4. Call LLM
        try:
            agent = ChatAgent(
                BaseMessage.make_assistant_message(role_name="Aligner", content=system_content),
                model=self.llm_model
            )
            
            user_msg = BaseMessage.make_user_message(role_name="User", content=user_content)
            response = agent.step(user_msg)
            content = response.msg.content
            
            # 5. Parse JSON
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                final_speeches = []
                final_alignment = [] # List of (Frame, Speech)
                
                # Ensure length matches PDF
                if len(data) != len(pdf_pages_text):
                    logger.warning("LLM returned wrong number of pages.")
                    # Padding logic...
                
                for i, item in enumerate(data):
                    sp = item.get("speech", "")
                    fr_idx = item.get("matched_frame_index")
                    
                    final_speeches.append(sp)
                    
                    # Construct alignment tuple if frame index is valid
                    if fr_idx is not None and isinstance(fr_idx, int):
                        # Adjust 1-based index to 0-based
                        zero_idx = fr_idx - 1
                        if 0 <= zero_idx < len(frames):
                            final_alignment.append((frames[zero_idx], sp))
                
                # Fallback padding for speeches if needed
                if len(final_speeches) < len(pdf_pages_text):
                    final_speeches.extend([""] * (len(pdf_pages_text) - len(final_speeches)))
                
                return {
                    "speeches": final_speeches[:len(pdf_pages_text)],
                    "alignment": final_alignment
                }
            else:
                logger.error("No JSON list found in LLM response.")
                return {"speeches": original_speeches, "alignment": []}

        except Exception as e:
            logger.error(f"Error during speech alignment: {e}")
            return {"speeches": original_speeches, "alignment": []}
