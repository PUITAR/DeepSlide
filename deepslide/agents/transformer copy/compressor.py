import os
import logging
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool

from deepslide.utils.content import Content
from deepslide.utils.frame import Frame
from deepslide.utils.section import Section
from deepslide.utils.spection import Spection
from .chapter_node import ChapterNode
from .data_types import LogicNode, LogicFlow

# 正则表达式包
import re


logger = logging.getLogger(__name__)

class Compressor:
    def __init__(self):
        self._init_llm()
        self.node_map: Dict[str, ChapterNode] = {}
        self.trace = True
        # Speech speed in units per second (default 6.0, approx 90 chars/15s)
        self.speech_speed = float(os.getenv('SPEECH_SPEED', 6.0))
        
    def _init_llm(self):
        env_path = os.path.join(os.path.dirname(__file__), '../../config/env/.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
        
        api_key = os.getenv('DEFAULT_MODEL_API_KEY') or os.getenv('LLM_API_KEY')
        if not api_key:
            logger.warning("LLM API Key not found. Compressor will not work properly.")
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
                "temperature": 0.2, "timeout": 1000, 
                # "max_tokens": 16 * 1024
                "max_tokens": 8 * 1024
            }
        )

    def compress(self, logic_flow: LogicFlow, nodes: List[ChapterNode]) -> Tuple[Content, List[Spection]]:
        """
        Generate slides and speech for the given logic flow and content tree.
        Combines filtering and compression by letting the agent navigate and select content.
        """
        if not self.llm_model:
            logger.error("LLM not initialized.")
            return Content(), []

        # Build map for O(1) access
        self.node_map = {n.node_id: n for n in nodes}
        
        full_content = Content()
        full_speech: List[Spection] = []
        
        roots = [n for n in nodes if not n.parent_id]
        
        print("=== Begin Compression ===")

        for i, logic_node in enumerate(logic_flow.nodes):
            print(f"\nProcessing Logic Node {i+1}/{len(logic_flow.nodes)}: {logic_node.name}")
            
            # Add a section for the logic node
            section_cmd = f"\\section{{{logic_node.name}}}"
            full_content.append(Section(section_cmd))
            
            # Generate content for this logic node
            node_content, node_speech = self._process_logic_node(logic_node, roots)
            
            if node_content:
                full_content.extend(node_content)
                full_speech.extend(node_speech)
            else:
                print(f"No content generated for {logic_node.name}")

        return full_content, full_speech

    def _process_logic_node(self, logic_node: LogicNode, roots: List[ChapterNode]) -> Tuple[Content, List[Spection]]:
        generated_content = Content()
        generated_speech: List[Spection] = []
        
        # Track duration
        self.current_duration = 0.0
        
        # Parse target duration (e.g., "1 min" -> 60.0)
        target_duration_sec = 60.0 # default
        try:
            d_str = logic_node.duration.lower()
            if 'min' in d_str:
                target_duration_sec = float(re.search(r'(\d+(\.\d+)?)', d_str).group(1)) * 60
            elif 'sec' in d_str:
                target_duration_sec = float(re.search(r'(\d+(\.\d+)?)', d_str).group(1))
            else:
                # Assume minutes if no unit
                target_duration_sec = float(re.search(r'(\d+(\.\d+)?)', d_str).group(1)) * 60
        except:
            pass
        
        print(f"Target Duration: {target_duration_sec}s")
        
        # Define Tools
        
        def search_relevant_nodes(query: str, limit: int = 5) -> str:
            """
            Search for nodes relevant to a query using fuzzy matching on title and summary.
            Returns a list of node IDs and summaries.
            """
            print(f"[Tool:search_relevant_nodes] Query: '{query}'")
            query_terms = query.lower().split()
            scored_nodes = []
            
            for node in self.node_map.values():
                text = (node.title or "") + " " + (node.summary or "")
                text_lower = text.lower()
                score = 0
                for term in query_terms:
                    if term in text_lower:
                        score += 1
                if score > 0:
                    scored_nodes.append((score, node))
            
            scored_nodes.sort(key=lambda x: x[0], reverse=True)
            top_nodes = scored_nodes[:limit]
            
            if not top_nodes:
                return "No relevant nodes found."
                
            lines = []
            for _, node in top_nodes:
                 lines.append(f"ID: {node.node_id} | Title: {node.title} | Summary: {(node.summary or '')[:200]}")
            return "\n".join(lines)

        def get_node_details(node_id: str) -> str:
            """
            Get details of a specific node, including its children's titles and a preview of its content.
            """
            print(f"[Tool:get_node_details] Called for {node_id}")
            node = self.node_map.get(node_id)
            if not node:
                return "Node not found."
            
            children_info = []
            if node.children_ids:
                for cid in node.children_ids:
                    child = self.node_map.get(cid)
                    if child:
                        children_info.append(f"- {child.title} (ID: {child.node_id})")
            
            children_str = "\n".join(children_info) if children_info else "None"
            
            return f"""
ID: {node.node_id}
Title: {node.title}
Type: {node.node_type}
Children:
{children_str}

Summary: {node.summary}

Content Preview (first 500 chars):
{node.content[:500]}...
"""

        def get_node_content(node_id: str) -> str:
            """Get the full content of a node. Use this only when necessary."""
            node = self.node_map.get(node_id)
            if not node:
                return "Node not found."
            print(f"[Tool:get_node_content] Reading {node_id} ({len(node.content)} chars)")
            return f"Title: {node.title}\nContent:\n{node.content}"

        def estimate_speech_duration(speech_script: str) -> str:
            """
            Estimate the duration of a speech script in seconds based on current speech speed settings.
            Counts words for English/mixed text, or characters for CJK text.
            """
            # Improved counting logic
            # Count Chinese characters
            cjk_count = len(re.findall(r'[\u4e00-\u9fff]', speech_script))
            # Count non-CJK words (approximate by splitting on whitespace after removing CJK)
            non_cjk_text = re.sub(r'[\u4e00-\u9fff]', ' ', speech_script)
            word_count = len(non_cjk_text.split())
            
            # Total units
            total_units = cjk_count + word_count
            
            duration = total_units / self.speech_speed
            return f"{duration:.1f}"

        def add_slide(latex_body: str, speech_script: str):
            """
            Create a Beamer slide and corresponding speech.
            latex_body: The content inside \\begin{frame} ... \\end{frame}.
            speech_script: First-person speech script for this slide.
            """
            duration = float(estimate_speech_duration(speech_script))
            self.current_duration += duration
            
            print(f"[Tool:add_slide] Adding slide. Speech: {len(speech_script)} chars, {duration:.1f}s. Total: {self.current_duration:.1f}s / {target_duration_sec}s")
            
            # Clean latex
            latex_body = re.sub(r'\\begin{frame}\n*', '', latex_body)
            latex_body = re.sub(r'\n*\\end{frame}', '', latex_body).strip()
            full_latex = f"\\begin{{frame}}\n{latex_body}\n\\end{{frame}}"

            generated_content.append(Frame(full_latex))
            generated_speech.append(Spection(speech_script))
            
            return f"Slide added. Duration: {duration:.1f}s. Total Accumulated: {self.current_duration:.1f}s (Target: {target_duration_sec}s)."

        def add_section(latex_cmd: str):
            """Add a section/subsection divider."""
            print(f"[Tool:add_section] Adding section: {latex_cmd}")
            generated_content.append(Section(latex_cmd))
            return "Section added."

        tools = [
            FunctionTool(search_relevant_nodes),
            FunctionTool(get_node_details),
            FunctionTool(get_node_content),
            FunctionTool(estimate_speech_duration),
            FunctionTool(add_slide),
            FunctionTool(add_section)
        ]
        
        sys_msg_content = f"""You are an expert presentation creator.
Your task is to create a set of Beamer slides for a specific part of a presentation.

Target Logic Node:
Name: {logic_node.name}
Description: {logic_node.description}
Target Duration: {logic_node.duration} (approx {target_duration_sec} seconds)

Instructions:
1. **Search & Inspect**: Use `search_relevant_nodes` and `get_node_details` to find content.
2. **Read Content**: Use `get_node_content` sparingly to get exact details.
3. **Generate Slides**: Use `add_slide` to create slides.
   - **Content & Flow Priority**:
     - **Constraint**: Each slide MUST contain relevant information extracted from the source content. Do NOT fabricate content just to fill time.
     - **Constraint**: Ensure a logical flow between slides. The story should be coherent.
     - **Constraint**: Each slide must have 3-5 main bullet points. NOT too empty, NOT too crowded.
     - **Constraint**: Speech script should be engaging and concise.
   - **Duration Awareness**:
     - Use `estimate_speech_duration` to check if your planned speech meets the pacing.
     - Aim for the total duration ({target_duration_sec}s) as a guide, but **Quality and Coherence** are more important than exact timing.
     - If you have covered all key points and are slightly under time, that is acceptable. Do not add fluff.
     - If you are over time, prioritize the most critical information and summarize.
4. **Correspondence**: `add_slide` adds one frame and one speech script. Do NOT add frames without speech or vice versa.
5. **Structure**: Use `add_section` for logical separation if needed.

Finish by replying "DONE" when you have covered the topic and met the duration target.
"""
        
        sys_msg = BaseMessage.make_assistant_message(
            role_name="Compressor",
            content=sys_msg_content
        )
        
        agent = ChatAgent(system_message=sys_msg, model=self.llm_model, tools=tools)
        agent.step_timeout = 600
        
        user_msg = BaseMessage.make_user_message(role_name="User", content="Please start generating slides for this logic node.")
        
        max_steps = 15 # Increased slightly to allow for duration adjustments
        step = 0
        
        while step < max_steps:
            try:
                retry_count = 0
                max_retries = 3
                response = None
                
                while retry_count < max_retries:
                    try:
                        response = agent.step(user_msg)
                        break
                    except Exception as e:
                        retry_count += 1
                        logger.warning(f"Agent step failed: {e}")
                        import time
                        time.sleep(2)
                
                if response is None:
                    break

                content = response.msg.content
                if content and "DONE" in content:
                    break
                
                if response.terminated:
                    break
                    
                user_msg = BaseMessage.make_user_message(
                    role_name="User", 
                    content=f"Current Total Duration: {self.current_duration:.1f}s / {target_duration_sec}s. Continue. If finished, say DONE.")
                step += 1
                
            except Exception as e:
                logger.error(f"Error in agent loop: {e}")
                break
                
        return generated_content, generated_speech
