import json
import re
import requests
import os
from dotenv import load_dotenv

class SlideGraphGenerator:
    def __init__(self, env_path=None):
        # Load environment variables
        if env_path is None:
             # Default to project config path relative to this file
             env_path = os.path.join(os.path.dirname(__file__), '../config/env/.env')
        
        load_dotenv(env_path)
        
        self.api_key = os.getenv('DEFAULT_MODEL_API_KEY')
        self.api_url = os.getenv('DEFAULT_MODEL_API_URL', 'https://api.deepseek.com')
        self.model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')
        
        if not self.api_key:
            print("Warning: API Key not found in env, using default placeholder.")
            self.api_key = "sk-6286dc11a31e45649dbf55081b8aef20"

    def get_section_ranges(self, content_tex, logic_chain_nodes):
        """
        Parses content.tex string to find which slides belong to which section.
        """
        lines = content_tex.splitlines()
        
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

    def _analyze_section_pair(self, src_sec, dst_sec, src_slides, dst_slides):
        """
        Analyze reference relationship between two specific sections using LLM.
        """
        src_text = ""
        for s in src_slides:
            content = str(s['content'][:300]).replace("\n", " ")
            src_text += f"[ID: {s['id']}] {content}...\n"
            
        dst_text = ""
        for s in dst_slides:
            content = str(s['content'][:300]).replace("\n", " ")
            dst_text += f"[ID: {s['id']}] {content}...\n"

        system_prompt = f"""You are an expert at analyzing presentation logic.
The user Logic Chain states that Section '{src_sec}' references Section '{dst_sec}'.
Your task is to find the SPECIFIC slides in '{src_sec}' that reference SPECIFIC slides in '{dst_sec}'.

Input:
1. Source Slides (from '{src_sec}')
2. Target Slides (from '{dst_sec}')

Output JSON:
{{
  "edges": [
    {{"from": <source_slide_id>, "to": <target_slide_id>, "reason": "..."}}
  ]
}}
If no specific reference is found, return "edges": [].
"""
        user_prompt = f"""Source Slides ('{src_sec}'):
{src_text}

Target Slides ('{dst_sec}'):
{dst_text}
"""
        # Call LLM
        url = self.api_url
        if not url.endswith("/chat/completions"):
             if url.endswith("/v1"):
                  url = f"{url}/chat/completions"
             else:
                  url = f"{url.rstrip('/')}/chat/completions"

        payload = {
            "model": self.model_type,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            if "```" in content:
                content = re.sub(r'```json\s*', '', content)
                content = re.sub(r'```', '', content)
            return json.loads(content).get("edges", [])
        except Exception as e:
            print(f"Error analyzing {src_sec}->{dst_sec}: {e}")
            return []

    def generate_llm_graph(self, alignment_data, logic_chain, slide_section_map):
        # 1. Group slides by section
        section_slides = {}
        nodes = []
        for i, pair in enumerate(alignment_data):
            sec = slide_section_map.get(i, "Unknown")
            if sec not in section_slides:
                section_slides[sec] = []
            
            # Simplified content for token saving
            content_preview = pair[0] if len(pair[0]) < 500 else pair[0][:500]
            slide_obj = {"id": i, "content": content_preview, "section": sec}
            section_slides[sec].append(slide_obj)
            
            nodes.append({
                "id": i,
                "content_tuple": pair,
                "section": sec,
                "summary": "Processed via Logic Chain Agent"
            })

        # 2. Iterate Logic Chain Edges
        final_edges = []
        logic_nodes = {n['name']: n for n in logic_chain.get('nodes', [])}
        logic_idx_map = {i: n['name'] for i, n in enumerate(logic_chain.get('nodes', []))}

        print("Starting Logic Chain based analysis...")

        for edge in logic_chain.get('edges', []):
            if edge.get('type') == 'reference':
                src_name = logic_idx_map.get(edge['from'])
                dst_name = logic_idx_map.get(edge['to'])
                
                if src_name and dst_name:
                    src_s = section_slides.get(src_name, [])
                    dst_s = section_slides.get(dst_name, [])
                    
                    if src_s and dst_s:
                        print(f"Analyzing dependency: {src_name} ({len(src_s)} slides) -> {dst_name} ({len(dst_s)} slides)")
                        # Tool Call: Analyze specific section pair
                        sub_edges = self._analyze_section_pair(src_name, dst_name, src_s, dst_s)
                        final_edges.extend(sub_edges)

        return {"nodes": nodes, "edges": final_edges}

    def generate_simple_graph(self, alignment_data, logic_chain, slide_section_map):
        # ... (Keep existing simple implementation as fallback) ...
        nodes = []
        section_slides = {}
        for i, pair in enumerate(alignment_data):
            sec = slide_section_map.get(i, "Unknown")
            if sec not in section_slides: section_slides[sec] = []
            section_slides[sec].append(i)
            nodes.append({"id": i, "content_tuple": pair, "section": sec, "summary": "Simple Graph"})
            
        edges = []
        logic_idx_to_name = {i: node['name'] for i, node in enumerate(logic_chain.get('nodes', []))}
        for edge in logic_chain.get('edges', []):
            if edge.get('type') == 'reference': 
                src_name = logic_idx_to_name.get(edge['from'])
                dst_name = logic_idx_to_name.get(edge['to'])
                src_ids = section_slides.get(src_name, [])
                dst_ids = section_slides.get(dst_name, [])
                if src_ids and dst_ids:
                    for s in src_ids:
                        for d in dst_ids:
                            edges.append({"from": s, "to": d, "type": "reference", "reason": "Section-level inheritance"})
        return {"nodes": nodes, "edges": edges}

    def refine_speech(self, graph_data):
        """
        Refine speeches based on the generated graph edges.
        Only modifies speeches for nodes that are SOURCES of reference edges.
        """
        nodes = {n['id']: n for n in graph_data.get('nodes', [])}
        edges = graph_data.get('edges', [])
        
        # Group edges by source slide
        # slide_id -> list of referenced_slide_ids
        refs = {}
        for e in edges:
            src = e.get('from')
            dst = e.get('to')
            reason = e.get('reason', '')
            if src is not None and dst is not None:
                if src not in refs: refs[src] = []
                refs[src].append({"target_id": dst, "reason": reason})

        refined_speeches = {} # slide_id -> new_speech

        for src_id, targets in refs.items():
            src_node = nodes.get(src_id)
            if not src_node: continue
            
            current_speech = src_node['content_tuple'][1] # (frame, speech)
            
            # Construct context about referenced slides
            ref_context = ""
            for t in targets:
                dst_node = nodes.get(t['target_id'])
                if dst_node:
                    ref_context += f"- Referenced Slide {t['target_id']} (Section: {dst_node['section']}): {dst_node['content_tuple'][0][:200]}... (Reason: {t['reason']})\n"
            
            prompt = f"""You are refining a presentation speech.
Current Speech for Slide {src_id}:
"{current_speech}"

This slide logically references the following previous slides:
{ref_context}

Task:
Rewrite the speech to explicitly connect with these referenced slides. Use phrases like "As we saw in Slide X...", "Recall that...", etc., to strengthen the logical flow.
Keep the original meaning but add these connective elements.
Return ONLY the new speech text.
"""
            # Call LLM
            try:
                # ... reuse LLM call logic ...
                url = self.api_url
                if not url.endswith("/chat/completions"):
                     if url.endswith("/v1"): url = f"{url}/chat/completions"
                     else: url = f"{url.rstrip('/')}/chat/completions"
                
                payload = {
                    "model": self.model_type,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    new_speech = resp.json()['choices'][0]['message']['content']
                    refined_speeches[src_id] = new_speech
                    print(f"Refined speech for Slide {src_id}")
            except Exception as e:
                print(f"Failed to refine speech for {src_id}: {e}")
        
        return refined_speeches

    def run(self, content_tex, speeches, logic_chain, use_llm=False, precomputed_alignment=None):
        if precomputed_alignment:
            alignment_data = precomputed_alignment
            print(f"Using precomputed alignment with {len(alignment_data)} pairs.")
        else:
            matches = list(re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', content_tex, re.DOTALL))
            frames_content = [m.group(1) for m in matches]
            alignment_data = []
            for i in range(max(len(frames_content), len(speeches))):
                f_txt = frames_content[i] if i < len(frames_content) else ""
                s_txt = speeches[i] if i < len(speeches) else ""
                alignment_data.append((f_txt, s_txt))
            
        slide_section_map = self.get_section_ranges(content_tex, logic_chain.get('nodes', []))
        
        graph_result = {}
        if use_llm:
            graph_result = self.generate_llm_graph(alignment_data, logic_chain, slide_section_map)
        else:
            graph_result = self.generate_simple_graph(alignment_data, logic_chain, slide_section_map)
            
        return graph_result
