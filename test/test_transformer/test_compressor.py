import os
import sys
import json
import logging
from typing import List

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from deepslide.agents.transformer.chapter_node import ChapterNode
from deepslide.agents.transformer.data_types import LogicFlow, LogicNode
from deepslide.agents.transformer.compressor import Compressor

logging.basicConfig(level=logging.INFO)

def load_nodes_from_json(json_path: str) -> List[ChapterNode]:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    nodes = []
    # Helper to recursively build nodes if nested, or just flat list
    # Assuming flat list or similar structure from divider_result.json
    
    # If data is a list of dicts
    if isinstance(data, list):
        for item in data:
            # We need to handle potential nested structure if present, 
            # but usually ChapterNode.to_dict flattened it? 
            # Actually ChapterNode has children_ids.
            # Let's assume the JSON is a flat list of all nodes or we reconstruct.
            # If it's the output of divider, it might be a list of root nodes with children nested?
            # Let's check divider_result.json structure.
            pass

    # Simple mock for testing if file doesn't match exactly or just load it
    # We will use the existing divider_result.json logic from previous test files if possible
    # But for now, let's just use a simple reconstruction or mock
    
    # Let's actually read the file structure from the previous turn's context
    # It was a list of nodes.
    
    def dict_to_node(d):
        node = ChapterNode(
            node_id=d.get("node_id"),
            title=d.get("title", ""),
            content=d.get("content", ""),
            level=d.get("level", 1),
            node_type=d.get("node_type", "section"),
            summary=d.get("summary", "")
        )
        node.children_ids = d.get("children_ids", [])
        return node

    # To fully reconstruct the tree, we need a map.
    # If the JSON is a flat list of all nodes, we are good.
    # If it is a tree (nested children), we need to flatten it.
    
    flat_nodes = []
    def traverse(obj):
        if isinstance(obj, dict):
            node = dict_to_node(obj)
            flat_nodes.append(node)
            for child in obj.get("children", []): # if nested under 'children'
                traverse(child)
                # And update parent/child relationship if needed?
                # But divider_result.json usually has children_ids
        elif isinstance(obj, list):
            for item in obj:
                traverse(item)

    traverse(data)
    return flat_nodes

def main():
    # 1. Load Nodes
    json_path = os.path.join(os.path.dirname(__file__), "divider_result.json")
    if not os.path.exists(json_path):
        print(f"Test file not found: {json_path}")
        return

    print(f"Loading nodes from {json_path}...")
    nodes = load_nodes_from_json(json_path)
    print(f"Loaded {len(nodes)} nodes.")

    # 2. Define Logic Flow (Mock)
    # We use a LogicFlow that matches the content in divider_result.json (ANNS, CSPG, RL, SFT)
    logic_flow = LogicFlow(
        nodes=[
            LogicNode(
                name="Introduction", 
                description="Explain the background of LLM Post-Training (SFT vs RL) and the motivation for the unified view.",
                duration="1 min"
            ),
             LogicNode(
                name="Unified Framework", 
                description="Describe the Unified Policy Gradient Estimator and its components.",
                duration="1 min"
            )
        ]
    )

    # 3. Initialize Compressor
    compressor = Compressor()
    
    # 4. Run Compression
    print("\n=== Running Compressor ===")
    content, speeches = compressor.compress(logic_flow, nodes)
    
    # 5. Output Results
    print("\n=== Compression Results ===")
    print(f"Total Frames/Sections generated: {len(content)}")
    print(f"Total Speech segments: {len(speeches)}")
    
    output_tex = "test_presentation.tex"
    content.to_file(output_tex)
    
    print(f"Saved LaTeX content to {output_tex}")

    # TODO 在演讲稿段落之间加<next>间隔
    for i in range(1, len(speeches)):
        speeches[i] = "<next>" + speeches[i]
    
    with open("test_speech.txt", "w") as f:
        for i, s in enumerate(speeches):
            # f.write(f"--- Segment {i+1} ---\n{s}\n\n")
            # f.write("<next>")
            f.write(s + "\n")
    print("Saved speech to test_speech.txt")

if __name__ == "__main__":
    main()
