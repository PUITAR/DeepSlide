import json
import os
import requests
import re
import argparse
import sys
import time

def parse_arguments():
    parser = argparse.ArgumentParser(description="Generate detailed slide relationship graph with metric enhancements")
    default_base_dir = "/home/ym/DeepSlide/jiahangceshi_data_copy"
    parser.add_argument("--alignment", type=str, default=os.path.join(default_base_dir, "alignment.json"))
    parser.add_argument("--logic_chain", type=str, default=os.path.join(default_base_dir, "logic_chain.json"))
    parser.add_argument("--content", type=str, default=os.path.join(default_base_dir, "content.tex"))
    parser.add_argument("--output", type=str, default=os.path.join(default_base_dir, "slide_graph_with_metrics.json"))
    parser.add_argument("--api_key", type=str, default="sk-6286dc11a31e45649dbf55081b8aef20")
    parser.add_argument("--use_llm", action="store_true", help="Use LLM to generate detailed relationships and metric attributes")
    return parser.parse_args()

def get_section_ranges(content_path, logic_chain_nodes):
    with open(content_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    slide_section_map = {}
    current_section_name = "Intro" 
    frames_found = 0
    
    valid_node_names = set(node['name'] for node in logic_chain_nodes)
    
    for line in lines:
        if "\\section" in line:
            match = re.search(r'\\section\{([^}]+)\}', line)
            if match:
                raw_name = match.group(1)
                matched_name = None
                if raw_name in valid_node_names:
                    matched_name = raw_name
                else:
                    for node_name in valid_node_names:
                        if node_name in raw_name or raw_name in node_name:
                            matched_name = node_name
                            break
                
                if matched_name:
                    current_section_name = matched_name
                else:
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
        
        is_hook = (i < 2) 
        is_stimulus = False 
        
        nodes.append({
            "id": i,
            "content_tuple": pair,
            "section": sec,
            "summary": "Generated without LLM",
            "metric_attributes": {
                "is_hook": is_hook,
                "is_stimulus": is_stimulus,
                "key_concepts": []
            }
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
        speech_content = pair[1].strip()[:500] + "..." if len(pair[1]) > 500 else pair[1]
        
        section = slide_section_map.get(i, "Unknown")
        slides_text += f"Slide {i} (Section: {section}):\nContent: {slide_content}\nSpeech: {speech_content}\n\n"

    system_prompt = """You are an expert at analyzing presentation logic and quality metrics.
You are given a list of SLIDES (with their content and speech) and a HIGH-LEVEL LOGIC CHAIN.

Your task is to:
1. Generate a detailed graph of relationships between specific slides.
2. Analyze each slide for specific evaluation metrics attributes.

### 1. Edge Generation
Types of Edges:
- "reference": Slide A references Slide B (explicit mention, summary, or drill-down).
- DO NOT generate "sequential" edges.

### 2. Node Metric Attributes Analysis
For each slide, determine:
- **is_hook** (boolean): Does this slide/speech act as an "Open Hook"?
  - Criteria: Defines a clear problem/pain point, uses an interesting example/anomaly, or directly states why the audience should listen. Usually found at the beginning.
- **is_stimulus** (boolean): Is this a "Stimulus" segment?
  - Criteria: Contains speaker's personal view/positioning, asks a question, uses empathy/perspective taking, or provides a vivid example. Used for Retention Score.
- **key_concepts** (list of strings): Extract 1-3 key concepts defined or discussed in this slide.

### Output Format (JSON)
{
  "nodes": [
    {
      "id": 0, 
      "summary": "Short summary",
      "metric_attributes": {
        "is_hook": true,
        "is_stimulus": true,
        "key_concepts": ["concept1", "concept2"]
      }
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
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        print(f"Response status: {response.status_code}", flush=True)
        
        if response.status_code != 200:
            print(f"Error Body: {response.text}", flush=True)
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
                "summary": llm_node.get("summary", ""),
                "metric_attributes": llm_node.get("metric_attributes", {
                    "is_hook": False,
                    "is_stimulus": False,
                    "key_concepts": []
                })
            }
            final_nodes.append(node_obj)
            
        filtered_edges = [e for e in data.get("edges", []) if e.get("type") != "sequential"]
        
        return {"nodes": final_nodes, "edges": filtered_edges}
        
    except Exception as e:
        print(f"API Request Failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise

def main():
    args = parse_arguments()
    
    print("Reading inputs...", flush=True)
    try:
        with open(args.alignment, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            
        with open(args.logic_chain, 'r', encoding='utf-8') as f:
            logic_chain = json.load(f)
            
        slide_section_map = get_section_ranges(args.content, logic_chain.get('nodes', []))
        
        print(f"Loaded {len(alignment_data)} slides.", flush=True)
        
        final_output = None
        
        if args.use_llm:
            print("Using LLM for graph generation and metric analysis...", flush=True)
            try:
                final_output = generate_llm_graph(alignment_data, logic_chain, slide_section_map, args.api_key)
            except Exception as e:
                print("LLM generation failed, falling back to simple graph...", flush=True)
                final_output = generate_simple_graph(alignment_data, logic_chain, slide_section_map)
        else:
            print("Generating simple graph without LLM (basic metrics)...", flush=True)
            final_output = generate_simple_graph(alignment_data, logic_chain, slide_section_map)
            
        print(f"Got {len(final_output['nodes'])} nodes and {len(final_output['edges'])} edges.", flush=True)

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
            
        print(f"Graph with metrics saved to {args.output}", flush=True)
        
    except Exception as e:
        print(f"Error: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
