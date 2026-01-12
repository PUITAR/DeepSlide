import os
import fitz  # PyMuPDF
import json
import logging
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

    def align(self, pdf_path: str, original_speeches: List[str]) -> List[str]:
        """
        Align original speeches with PDF pages, generating new speech for structural pages.
        Returns a list of speech strings, one for each page in the PDF.
        """
        if not self.llm_model:
            logger.error("LLM not initialized.")
            return original_speeches

        if not os.path.exists(pdf_path):
            logger.error(f"PDF not found: {pdf_path}")
            return original_speeches

        # 1. Extract text from PDF
        try:
            doc = fitz.open(pdf_path)
            pdf_pages_text = []
            for i, page in enumerate(doc):
                text = page.get_text("text")
                # Clean up text: remove excessive whitespace
                text = " ".join(text.split())
                # Truncate to avoid context window issues, but keep enough to identify content
                pdf_pages_text.append(f"Page {i+1}: {text[:800]}")
            doc.close()
        except Exception as e:
            logger.error(f"Error reading PDF: {e}")
            return original_speeches

        if not pdf_pages_text:
            return original_speeches

        # 2. Construct Prompt
        # Format original speeches
        formatted_speeches = []
        for i, s in enumerate(original_speeches):
            formatted_speeches.append(f"Script Fragment {i+1}: {str(s)[:500]}...")

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
   - **Constraint**: Ensure all generated speeches are complete sentences. Do not end with "..." or leave sentences unfinished.
   - For **References/End**: Generate `<add>` followed by a closing sentence.

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
                    # Fallback or padding?
                    # Let's trust the LLM mostly, but if short, pad with empty strings; if long, truncate.
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
