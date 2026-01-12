import json
import os
import requests
import re
import argparse
import sys

def parse_arguments():
    parser = argparse.ArgumentParser(description="Generate detailed slide relationship graph")
    default_base_dir = "/home/ym/DeepSlide/jiahangceshi_data_copy"
    parser.add_argument("--alignment", type=str, default=os.path.join(default_base_dir, "alignment.json"))
    parser.add_argument("--logic_chain", type=str, default=os.path.join(default_base_dir, "logic_chain.json"))
    parser.add_argument("--content", type=str, default=os.path.join(default_base_dir, "content.tex"))
    parser.add_argument("--output", type=str, default=os.path.join(default_base_dir, "slide_relationships.json"))
    parser.add_argument("--api_key", type=str, default="sk-6286dc11a31e45649dbf55081b8aef20")
    parser.add_argument("--use_llm", action="store_true", help="Use LLM to generate detailed relationships")
    return parser.parse_args()

def get_section_ranges(content_path, logic_chain_nodes):
    """
    Parses content.tex to find which slides belong to which section.
    Crucially, it tries to match section names to the 'name' field in logic_chain nodes.
    """
    with open(content_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    slide_section_map = {}
    current_section_name = "Intro" 
    frames_found = 0
    
    # Create a set of valid logic node names for easier matching
    valid_node_names = set(node['name'] for node in logic_chain_nodes)
    
    for line in lines:
        if "\\section" in line:
            match = re.search(r'\\section\{([^}]+)\}', line)
            if match:
                raw_name = match.group(1)
                
                # Strict/Fuzzy matching to logic chain nodes
                matched_name = None
                
                # 1. Exact match
                if raw_name in valid_node_names:
                    matched_name = raw_name
                else:
                    # 2. Containment match (e.g. "Methods: CSPG" matches "Methods")
                    for node_name in valid_node_names:
                        if node_name in raw_name or raw_name in node_name:
                            matched_name = node_name
                            break
                
                if matched_name:
                    current_section_name = matched_name
                else:
                    # Fallback: use raw name if no logic node matches (shouldn't happen if aligned)
                    current_section_name = raw_name
        
        if "\\end{frame}" in line:
            slide_section_map[frames_found] = current_section_name
            frames_found += 1
            
    return slide_section_map

def generate_simple_graph(alignment_data, logic_chain, slide_section_map):
    nodes = []
    section_slides = {}
    
    for i, pair in enumerate(alignment_data):
        sec = slide_section_map.get(i, "Unknown")
        if sec not in section_slides:
            section_slides[sec] = []
        section_slides[sec].append(i)
        
        nodes.append({
            "id": i,
            "content_tuple": pair,
            "section": sec,
            "summary": "Generated without LLM"
        })
        
    edges = []
    
    logic_idx_to_name = {i: node['name'] for i, node in enumerate(logic_chain.get('nodes', []))}
    
    for edge in logic_chain.get('edges', []):
        if edge.get('type') == 'reference': 
            src_name = logic_idx_to_name.get(edge['from'])
            dst_name = logic_idx_to_name.get(edge['to'])
            
            src_slide_ids = section_slides.get(src_name, [])
            dst_slide_ids = section_slides.get(dst_name, [])
            
            if src_slide_ids and dst_slide_ids:
                for src_id in src_slide_ids:
                    for dst_id in dst_slide_ids:
                        edges.append({
                            "from": src_id,
                            "to": dst_id,
                            "type": "reference",
                            "reason": f"Inherited from section-level reference: {src_name} -> {dst_name}"
                        })
                
    return {"nodes": nodes, "edges": edges}

def generate_llm_graph(alignment_data, logic_chain, slide_section_map, api_key):
    logic_edges_desc = ""
    for edge in logic_chain.get('edges', []):
        try:
            src = logic_chain['nodes'][edge['from']]['name']
            dst = logic_chain['nodes'][edge['to']]['name']
            etype = edge['type']
            reason = edge.get('reason', '')
            logic_edges_desc += f"- {src} -> {dst} ({etype}): {reason}\n"
        except Exception:
            pass

    slides_text = ""
    for i, pair in enumerate(alignment_data):
        slide_content = pair[0]
        slide_content = slide_content.strip()[:500] + "..." if len(slide_content) > 500 else slide_content
        section = slide_section_map.get(i, "Unknown")
        slides_text += f"Slide {i} (Section: {section}):\nContent: {slide_content}\n\n"

    system_prompt = """You are an expert at analyzing presentation logic.
You are given a list of SLIDES (with their content and the logical section they belong to) and a HIGH-LEVEL LOGIC CHAIN describing relationships between sections.

Your task is to generate a detailed graph of relationships between specific slides.

Types of Edges:
1. "reference": Slide A references Slide B.
   - This happens if Slide A explicitly mentions a concept defined in Slide B.
   - Or if Slide A is a summary/conclusion that refers back to details in Slide B.
   - IMPORTANT: If Section 'Conclusion' references Section 'Methods', find the specific slides in 'Conclusion' that reference specific slides in 'Methods'.
   - DO NOT generate "sequential" edges. Only generate "reference" edges.

Nodes:
- You must use the provided slide indices (0 to N-1).

Output Format (JSON):
{
  "nodes": [
    {
      "id": 0, 
      "summary": "Short summary"
    },
    ...
  ],
  "edges": [
    {"from": 12, "to": 3, "type": "reference", "reason": "Summarizes Slide 3"}
  ]
}

Only return the JSON.
"""

    user_prompt = f"""HIGH-LEVEL LOGIC CHAIN:
{logic_edges_desc}

SLIDES:
{slides_text}
"""

    print("Sending request to DeepSeek...", flush=True)
    url = "https://api.deepseek.com/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    result = response.json()
    content = result['choices'][0]['message']['content']
    
    if "```" in content:
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```', '', content)
        
    data = json.loads(content)
    
    final_nodes = []
    for i, pair in enumerate(alignment_data):
        llm_node = next((n for n in data.get('nodes', []) if n.get('id') == i), {})
        node_obj = {
            "id": i,
            "content_tuple": pair,
            "section": slide_section_map.get(i, "Unknown"),
            "summary": llm_node.get("summary", "")
        }
        final_nodes.append(node_obj)
        
    filtered_edges = [e for e in data.get("edges", []) if e.get("type") != "sequential"]
    
    return {"nodes": final_nodes, "edges": filtered_edges}

def main():
    args = parse_arguments()
    
    print("Reading inputs...")
    try:
        with open(args.alignment, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            
        with open(args.logic_chain, 'r', encoding='utf-8') as f:
            logic_chain = json.load(f)
            
        # Pass logic_chain['nodes'] to get_section_ranges for better matching
        slide_section_map = get_section_ranges(args.content, logic_chain.get('nodes', []))
        
        print(f"Loaded {len(alignment_data)} slides.")
        print(f"Slide to Section Map: {slide_section_map}")
        
        final_output = None
        
        if args.use_llm:
            print("Using LLM for graph generation...")
            final_output = generate_llm_graph(alignment_data, logic_chain, slide_section_map, args.api_key)
        else:
            print("Generating simple graph without LLM...")
            final_output = generate_simple_graph(alignment_data, logic_chain, slide_section_map)
            
        print(f"Got {len(final_output['nodes'])} nodes and {len(final_output['edges'])} edges.")

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
            
        print(f"Slide relationships saved to {args.output}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
