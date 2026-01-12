import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
import uuid
from dotenv import load_dotenv
from tqdm import tqdm
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage

# Import from local modules (copied from divider_haoseng)
from .chapter_node import ChapterNode, NodeType
from .rough_divider import RoughDivider

logger = logging.getLogger(__name__)

class Divider:
    def __init__(self, max_try: int = 2):
        # max_try is kept for compatibility but might not be used if we rely on RoughDivider
        self.max_try = max_try
        self.rough_divider = RoughDivider()
        self.llm_agent = None
        self._init_llm()
        
        # Patterns for knowledge objects
        self.object_patterns = {
            "equation": {
                "pattern": r'(\$\$[\s\S]*?\$\$|\\begin\{(equation|align|gather|split)\}[\s\S]*?\\end\{\2\})',
                "type": NodeType.CUSTOM # Use CUSTOM for equations as there isn't a dedicated FORMULA type yet, or map to CODE? Let's use CUSTOM.
            },
            "figure": {
                "pattern": r'(\\begin\{figure\*?\}(?:[^{}]|{[^{}]*})*?\\end\{figure\*?\}|\\includegraphics(?:\[[^\]]*\])?\{[^}]*\})',
                "type": NodeType.CUSTOM
            },
            "table": {
                "pattern": r'(\\begin\{table\*?\}(?:[^{}]|{[^{}]*})*?\\end\{table\*?\}|\\begin\{tabular\}(?:[^{}]|{[^{}]*})*?\\end\{tabular\})',
                "type": NodeType.CUSTOM
            },
            "theorem": {
                "pattern": r'(\\begin\{(theorem|lemma|corollary|proposition|definition|example)\}(?:[^{}]|{[^{}]*})*?\\end\{\2\})',
                "type": NodeType.CUSTOM # Using QUOTE or CUSTOM for theorems
            }
        }

    def _init_llm(self):
        """Initialize LLM agent for summarization."""
        # env_path = 'deepslide/config/env/.env'
        env_path = os.path.join(os.path.dirname(__file__), '../config/.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
        
        api_key = os.getenv('DEFAULT_MODEL_API_KEY')
        if not api_key:
            logger.warning("LLM API Key not found. Summarization will use title only.")
            return

        try:
            # Use DEEPSEEK as default or check env
            model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')
            base_url = os.getenv('DEFAULT_MODEL_API_URL', 'https://api.deepseek.com')
            
            self.llm_model = ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
                model_type=model_type,
                url=base_url,
                api_key=api_key,
                model_config_dict={"temperature": 0.0}
            )
            
            sys_msg = BaseMessage.make_assistant_message(
                role_name="Summarizer",
                content="""
You are a precise summarizer. Your task is to generate a one-sentence summary of the provided text.
                """
            )
            
            self.llm_agent = ChatAgent(system_message=sys_msg, model=self.llm_model)
            logger.info("LLM Agent initialized for summarization.")
        except Exception as e:
            logger.error(f"Failed to init LLM: {e}")
            self.llm_agent = None

    def _get_llm_summary(self, content: str, context: str, is_leaf: bool, cutoff: int = 4096) -> str:
        """Generate summary using LLM."""
        if not self.llm_agent:
            return ""
            
        if is_leaf:
            prompt = f"""
Please summarize the following content into a single, concise sentence.
Context (Section Title): {context}

Content:
{content[:cutoff]} 

Summary:
"""
        else:
             prompt = f"""
The following are summaries of sub-sections. Please provide a single sentence summary that covers these points, taking into account the section title.
Section Title: {context}

Sub-summaries:
{content[:cutoff]}

Summary:
"""

        try:
            user_msg = BaseMessage.make_user_message(role_name="User", content=prompt.strip())
            # Reset memory to avoid context pollution between nodes? 
            # ChatAgent is stateful. We should reset or use a fresh agent?
            # Or just clear memory.
            self.llm_agent.clear_memory() 
            
            response = self.llm_agent.step(user_msg)
            if response.terminated:
                return ""
            return response.msg.content.strip()
        except Exception as e:
            logger.error(f"LLM error during summarization: {e}")
            return ""

    def divide(self, tex_path: str, schema: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Divide LaTeX content into a tree of sections and knowledge objects.
        """
        try:
            with open(tex_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read file {tex_path}: {e}")
            return []

        # 1. Use RoughDivider to get the structural tree
        # Configured for maximum extraction/granularity:
        # - High max_section_depth to keep deep structure
        # - High max_sections to avoid merging tail sections
        # - Low merge_short_threshold (0) to prevent merging short sections
        # - Minimal skip_keywords to avoid skipping appendices/refs
        planner_instructions = {
            "max_section_depth": 10,
            "max_sections": 200,
            "merge_short_threshold": 0,
            # Pass schema as focus keywords if provided
            "focus_keywords": schema if schema else [],
            "skip_keywords": [], # Don't skip anything
            "debug_mode": False
        }

        logger.info("Running RoughDivider...")
        nodes, feedback = self.rough_divider.divide(content, planner_instructions)

        # 2. Extract knowledge objects for each node
        logger.info("Extracting knowledge objects...")
        self._extract_knowledge_objects_for_nodes(nodes)

        # 3. Generate summaries with LLM
        if self.llm_agent:
            logger.info("Generating summaries with LLM (this may take a while)...")
            node_map = {n.node_id: n for n in nodes}
            # Find root nodes again as structure might have changed (though extract_objects only adds children)
            # Actually extract_objects updates nodes list with new children, but root nodes remain same
            root_nodes = [n for n in nodes if not n.parent_id]
            
            # Count total nodes for progress bar (excluding trivial object nodes if we skip them)
            # We summarize everything except maybe pure structural containers without content?
            # Let's just count all nodes for simplicity or recursive count
            
            # Initialize progress bar
            total_nodes = len(nodes)
            pbar = tqdm(total=total_nodes, desc="Summarizing", unit="node")
            
            for root in root_nodes:
                self._generate_summary_recursive(root, node_map, pbar)
                
            pbar.close()
        else:
            logger.info("Skipping LLM summarization (Agent not initialized).")

        # 4. Convert to dict tree structure for output
        # Find root nodes
        root_nodes = [n for n in nodes if not n.parent_id]
        
        # Build a map for easy access if needed, though nodes already have children_ids
        node_map = {n.node_id: n for n in nodes}

        # Recursive function to build the dict tree
        result_tree = [self._node_to_dict_recursive(root, node_map) for root in root_nodes]
        
        return result_tree

    def _generate_summary_recursive(self, node: ChapterNode, node_map: Dict[str, ChapterNode], pbar: Optional[tqdm] = None):
        """
        Recursively generate summaries.
        Bottom-up approach: Summarize children first, then parent.
        """
        # 1. Process children first
        child_summaries = []
        for child_id in node.children_ids:
            if child_id in node_map:
                child = node_map[child_id]
                self._generate_summary_recursive(child, node_map, pbar)
                
                # Collect child summary (prefer summary, fallback to title)
                s = child.summary if child.summary else child.title
                if s:
                    child_summaries.append(s)
        
        # 2. Generate summary for current node
        
        # Logic update per user request:
        # If leaf node (no children): Summarize 'content' AND 'title'
        # If parent node (has children): Summarize 'child_summaries' AND 'title' (ignore own content if it duplicates children)
        
        # Determine if leaf (ignoring empty children list)
        is_leaf = not bool(node.children_ids)
        
        if is_leaf:
            # Leaf node: Summarize content + title
            content_to_summarize = node.content.strip()
            
            # Skip empty content
            if not content_to_summarize:
                node.summary = node.title
            # If content is too short, just use title/content
            elif len(content_to_summarize) < 50 and node.title:
                 node.summary = node.title
            else:
                # Use LLM to summarize content
                # Use title as context
                # Pass both content and title to the prompt
                summary = self._get_llm_summary(content_to_summarize, node.title, is_leaf=True)
                node.summary = summary
        else:
            # Parent node: Summarize based on children's summaries + title
            if child_summaries:
                combined_summaries = "\n".join(f"- {s}" for s in child_summaries)
                # Pass both children summaries and title to the prompt
                summary = self._get_llm_summary(combined_summaries, node.title, is_leaf=False)
                node.summary = summary
            else:
                # Has children IDs but no valid summaries? Fallback to title
                node.summary = node.title

        # Update progress bar
        if pbar:
            pbar.update(1)

    def _extract_knowledge_objects_for_nodes(self, nodes: List[ChapterNode]):
        """
        Iterate through nodes and extract objects from their content.
        Add extracted objects as child nodes.
        """
        # We iterate over a copy or index because we might append new nodes to the list if we were maintaining a flat list.
        # But here we just need to update the relationships in the objects.
        # Note: 'nodes' list in divide() is the flat list returned by RoughDivider. 
        # New child nodes we create here won't be in that 'nodes' list unless we add them, 
        # but they will be linked via children_ids.
        
        # Use a map to check for existing IDs to avoid duplicates if any
        existing_ids = {n.node_id for n in nodes}
        new_nodes = []

        for node in nodes:
            # Only extract from content-bearing nodes (SECTION, SUBSECTION, CONTENT)
            # RoughDivider produces SECTION/SUBSECTION/CONTENT.
            if not node.content:
                continue

            # Check for each object type
            for obj_type_name, config in self.object_patterns.items():
                pattern = config["pattern"]
                node_type = config["type"]
                
                # Find all matches
                for match in re.finditer(pattern, node.content, re.DOTALL):
                    obj_content = match.group(0)
                    
                    # Create a new child node for this object
                    obj_node = ChapterNode(
                        title=f"{obj_type_name.capitalize()}", # Simple title
                        content=obj_content,
                        level=node.level + 1,
                        node_type=node_type,
                        parent_id=node.node_id
                    )
                    
                    # Add metadata
                    obj_node.metadata["object_type"] = obj_type_name
                    obj_node.metadata["original_text"] = obj_content
                    
                    # Add to parent
                    node.add_child(obj_node)
                    new_nodes.append(obj_node)
                    
                    # Log or track if needed
                    # logger.info(f"Extracted {obj_type_name} in {node.title}")
        
        # Add new nodes to the main list so they can be looked up
        nodes.extend(new_nodes)

    def _node_to_dict_recursive(self, node: ChapterNode, node_map: Dict[str, ChapterNode]) -> Dict[str, Any]:
        """
        Convert node to dict recursively, including children.
        This matches the structure expected by the transformer/downstream, 
        or provides a standard tree structure.
        """
        # Resolve children
        children_dicts = []
        for child_id in node.children_ids:
            if child_id in node_map:
                child_node = node_map[child_id]
                children_dicts.append(self._node_to_dict_recursive(child_node, node_map))
            else:
                logger.warning(f"Child node {child_id} not found in map for parent {node.node_id}")
        
        # Construct the filtered dictionary
        # 1. 节点ID 
        # 2. 节点内容概要（可以用LLM生成） - using title as summary for now
        # 3. 节点类型 
        # 4. 节点文本（content），纯文本保存，尽量不丢失信息 
        # 5. 子节点列表
        
        # Ensure node_type is a string
        node_type_val = node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type)
        
        node_dict = {
            "node_id": node.node_id,
            "summary": node.title, # Placeholder for LLM summary
            "node_type": node_type_val,
            "content": node.content,
            "children": children_dicts,
            "used": node.used
        }
        
        return node_dict

    def evaluate_coverage(self, tree: List[Dict[str, Any]], file_path: str) -> float:
        """
        Calculate and print the text coverage ratio of the extracted tree vs original file.
        
        Args:
            tree: The extracted node tree (List[Dict])
            file_path: Path to the original file
            
        Returns:
            float: The coverage ratio (0.0 to 1.0)
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return 0.0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return 0.0

        original_len = len(original_content)
        if original_len == 0:
            return 1.0

        # Calculate extracted length
        extracted_len = self._calculate_tree_content_length(tree)
        
        coverage = extracted_len / original_len
        
        print(f"\ncoverage analysis:")
        print(f"{'='*30}")
        print(f"Original file length: {original_len}")
        print(f"Extracted content length: {extracted_len}")
        print(f"Coverage ratio: {coverage:.2%}")
        print(f"Note: Coverage < 100% is expected as LaTeX commands/headers are not included in node content.")
        print(f"{'='*30}\n")
        
        return coverage

    def _calculate_tree_content_length(self, nodes: List[Dict[str, Any]]) -> int:
        """Recursively calculate total content length of structural nodes."""
        total_len = 0
        for node in nodes:
            # Only count structural nodes (SECTION, SUBSECTION, CONTENT) to avoid double counting CUSTOM objects
            # CUSTOM objects are extracted from parent content, so they are redundant for coverage stats.
            # Assuming 'custom' is the value for CUSTOM type.
            node_type = node.get("node_type", "").lower()
            
            if node_type != "custom":
                content = node.get("content", "")
                total_len += len(content)
                
            # Recurse
            children = node.get("children", [])
            if children:
                total_len += self._calculate_tree_content_length(children)
                
        return total_len

    def visualize(self, tree: List[Dict[str, Any]]):
        """Visualize the tree structure to stdout."""
        print(f"\nTree Visualization:")
        print("=" * 60)
        self._visualize_recursive(tree)
        print("=" * 60)

    def _visualize_recursive(self, nodes: List[Dict[str, Any]], prefix: str = "", is_last: bool = True):
        count = len(nodes)
        for i, node in enumerate(nodes):
            is_current_last = (i == count - 1)
            
            # Prepare display string
            node_id = node.get("node_id", "unknown_id")
            node_type = node.get("node_type", "unknown_type")
            summary = node.get("summary", "")
            if not summary:
                content = node.get("content", "")
                summary = content[:30] + "..." if len(content) > 30 else content
                
            display_str = f"[{node_type}] {summary} ({node_id})"
            
            # Tree connectors
            connector = "└── " if is_current_last else "├── "
            
            print(f"{prefix}{connector}{display_str}")
            
            # Prepare prefix for children
            child_prefix = prefix + ("    " if is_current_last else "│   ")
            
            # Recurse if children exist
            children = node.get("children", [])
            if children:
                self._visualize_recursive(children, child_prefix, True)
