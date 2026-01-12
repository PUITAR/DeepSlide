import os
# import fitz  # PyMuPDF -> Moved to subprocess to avoid segfaults
import json
import logging
import subprocess
import sys
from typing import List
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

    def align(self, pdf_path: str, original_speeches: List[str]) -> List[str]:
        """
        Align original speeches with PDF pages, generating new speech for structural pages.
        Returns a list of speech strings, one for each page in the PDF.
        """
        print("In align method")
        if not self.llm_model:
            logger.error("LLM not initialized.")
            return original_speeches

        if not os.path.exists(pdf_path):
            logger.error(f"PDF not found: {pdf_path}")
            return original_speeches

        print("start to extract text from pdf")

        # 1. Extract text from PDF (using direct method)
        pdf_pages_text = self._extract_text(pdf_path)

        print(f"Extracted PDF pages: {pdf_pages_text}")

        if not pdf_pages_text:
            return original_speeches

        # 2. Construct Prompt
        # Format original speeches
        formatted_speeches = []
        for i, s in enumerate(original_speeches):
            formatted_speeches.append(
                f"Script Fragment {i+1}: {str(s)}"
            )

        pdf_context = "\n\n".join(pdf_pages_text)
        script_context = "\n\n".join(formatted_speeches)

        system_content = """You are a professional presentation speech editor.
Your task is to align a set of pre-written speech scripts with the actual slides of a generated PDF, and generate missing speeches for structural slides.

Inputs:
1. Text extracted from each page of the PDF.
2. A list of pre-written speech fragments (generated for the content slides).

Instructions:
1. Analyze the PDF page content to identify its type:
   - **Cover/Title Page**: Usually Page 1. content often includes title, author, date.
   - **Table of Contents**: Often titled "Outline" or "Table of Contents".
   - **Section Divider**: Pages containing just a large section title.
   - **Content Slide**: Pages with bullet points, figures, formulas. These correspond to the pre-written scripts.
   - **References/Bibliography**: Last few pages.
   - **Appendix/Acknowledgement/Thank You**: Final pages.

2. Generate a speech list where the N-th element corresponds EXACTLY to the N-th page of the PDF.
   - **IMPORTANT**: For any speech that you generate YOURSELF (e.g., Cover Page, Table of Contents, Section Divider, References) that was NOT present in the "Script Fragments", you MUST prefix the speech with the tag `<add>`.
   - For **Cover Page**: Generate `<add>` followed by a brief welcome and title introduction.
   - For **Table of Contents**: Generate `<add>` followed by a brief mention "Here is the outline of the presentation."
   - For **Section Divider**: Generate `<add>` followed by a transition sentence (e.g., "Now, let's move on to [Section Name].").
   - For **Content Slide**: Match it with the most relevant "Script Fragment". Use the original script content. **DO NOT add the `<add>` tag for these slides.** If a script fragment spans multiple slides or if multiple fragments fit one slide, adjust accordingly to make it coherent. **Priority is to preserve the information in Script Fragments.**
   - For **References/End**: Generate `<add>` followed by a closing sentence.
   - NOTE: Ensure all generated speeches are complete first-person sentences. Do not end with "..." or leave sentences unfinished.

3. Output Format:
   - Return ONLY a valid JSON list of strings.
   - The length of the list MUST match the number of PDF pages exactly.
   - No markdown formatting (like ```json), just the raw JSON string.
"""

        user_content = f"""
Number of PDF Pages: {len(pdf_pages_text)}
Number of Script Fragments: {len(original_speeches)}

--- PDF CONTENT ---
{pdf_context}

--- SCRIPT FRAGMENTS ---
{script_context}

Please generate the aligned speech list (JSON format).
"""

        # 3. Call LLM
        try:
            agent = ChatAgent(
                BaseMessage.make_assistant_message(role_name="Aligner", content=system_content),
                model=self.llm_model
            )
            
            user_msg = BaseMessage.make_user_message(role_name="User", content=user_content)
            response = agent.step(user_msg)
            content = response.msg.content
            
            # 4. Parse JSON
            # Try to find JSON list in the output
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                aligned_speeches = json.loads(json_str)
                
                if len(aligned_speeches) != len(pdf_pages_text):
                    logger.warning(f"Aligned speech count ({len(aligned_speeches)}) does not match PDF page count ({len(pdf_pages_text)}).")
                    if len(aligned_speeches) < len(pdf_pages_text):
                        aligned_speeches.extend([""] * (len(pdf_pages_text) - len(aligned_speeches)))
                    else:
                        aligned_speeches = aligned_speeches[:len(pdf_pages_text)]
                
                return aligned_speeches
            else:
                logger.error("No JSON list found in LLM response.")
                logger.debug(f"LLM Response: {content}")
                return original_speeches

        except Exception as e:
            logger.error(f"Error during speech alignment: {e}")
            return original_speeches
