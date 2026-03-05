import json
import re
import requests
import os
import subprocess
import sys
from dotenv import load_dotenv
from .tex_compile import compile_content
from app.core.agent_model_env import resolve_text_llm_env


def _preview_text(value, limit: int = 200) -> str:
    try:
        s = str(value)
    except Exception:
        return "<unprintable>"
    return s if len(s) <= limit else s[:limit] + "..."

class SlideGraphGenerator:
    def __init__(self, env_path=None):
        # Load environment variables
        if env_path is None:
             # Default to project config path relative to this file
             # backend/app/services/core -> deepslide-v3 -> ../.env
             env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../.env'))
        
        load_dotenv(env_path)

        cfg = resolve_text_llm_env("SLIDE_GRAPH")
        self.api_key = cfg.api_key
        self.api_url = cfg.api_url or "https://api.deepseek.com"
        self.model_type = cfg.model_type or "deepseek-chat"
        
        if not self.api_key:
            print("Warning: API Key not found in env, using default placeholder.")
            # Use a dummy key if none found, to prevent crash, but requests will fail if auth required
            self.api_key = "dummy_key"

    def _extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF using a subprocess to avoid segfaults."""
        try:
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
            pages.append(f"Page {i+1}: {text[:min(800, len(text))]}")
        doc.close()
        print(json.dumps(pages))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    extract(sys.argv[1])
"""
            result = subprocess.run(
                [sys.executable, "-c", script, pdf_path],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                print(f"Subprocess failed: {result.stderr}")
                return []

            output = result.stdout.strip()
            if not output: return []
            return json.loads(output)
        except Exception as e:
            print(f"Error extracting PDF text: {e}")
            return []

    def generate_alignment(self, pdf_path, speeches, content_tex):
        """
        Generate alignment data (frame, speech) using LLM.
        """
        if not os.path.exists(pdf_path):
            print(f"PDF not found: {pdf_path}")
            return []

        pdf_pages_text = self._extract_text_from_pdf(pdf_path)
        if not pdf_pages_text: return []

        # Parse frames
        matches = list(re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', content_tex, re.DOTALL))
        frames = [m.group(1) for m in matches]
        
        # Construct Prompt
        formatted_speeches = [f"Script Fragment {i+1}: {str(s)}" for i, s in enumerate(speeches)]
        formatted_frames = [f"Frame {i+1}: {str(f)[:min(500, len(f))]}..." for i, f in enumerate(frames)]

        pdf_context = "\n\n".join(pdf_pages_text)
        script_context = "\n\n".join(formatted_speeches)
        frame_context = "\n\n".join(formatted_frames) if frames else "No LaTeX frames provided."

        system_prompt = """You are a professional presentation structural analyst.
Your task is to align generated PDF pages with source LaTeX frames and speech scripts.

Inputs:
1. Text from PDF pages.
2. Speech fragments.
3. LaTeX Frame codes.

Output:
Generate a JSON list where each element corresponds to a PDF page.
{
  "pdf_page_index": <int>,
  "speech": "<string>",
  "matched_frame_index": <int or null>
}
- matched_frame_index: 1-based index of the matching LaTeX frame, or null if it's a structural page (Cover, TOC, etc).
- speech: The corresponding speech text.

IMPORTANT:
- Output valid JSON only.
- If the speech or content contains backslashes (e.g. LaTeX commands), you MUST escape them (e.g. use "\\\\section" instead of "\\section").

Return ONLY the JSON list.
"""
        user_prompt = f"""
Number of PDF Pages: {len(pdf_pages_text)}
Number of Script Fragments: {len(speeches)}
Number of Frames: {len(frames)}

--- PDF CONTENT ---
{pdf_context}

--- SCRIPT FRAGMENTS ---
{script_context}

--- LATEX FRAMES ---
{frame_context}
"""
        # Call LLM
        url = self.api_url
        if not url.endswith("/chat/completions"):
             if url.endswith("/v1"): url = f"{url}/chat/completions"
             else: url = f"{url.rstrip('/')}/chat/completions"

        payload = {
            "model": self.model_type,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }
        if str(self.model_type or "").lower().strip().startswith("gpt-5"):
            payload.pop("temperature", None)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            if response.status_code == 400 and ("temperature" in (response.text or "").lower()):
                payload.pop("temperature", None)
                response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            
            # Parse JSON
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    data = json.loads(json_str)
                except Exception:
                    # Fallback: escape backslashes if standard parsing fails
                    try:
                        data = json.loads(json_str.replace('\\', '\\\\'))
                    except Exception:
                        print("Error: JSON parsing failed even after backslash fix.")
                        return []

                final_alignment = []
                for item in data:
                    sp = item.get("speech", "")
                    fr_idx = item.get("matched_frame_index")
                    if fr_idx is not None and isinstance(fr_idx, int):
                        zero_idx = fr_idx - 1
                        if 0 <= zero_idx < len(frames):
                            final_alignment.append((frames[zero_idx], sp))
                
                if not final_alignment:
                    print("Warning: Generated alignment data is empty.")

                return final_alignment
            return []
        except Exception as e:
            print(f"Error in generate_alignment: {e}")
            return []

    def _match_sections_with_llm(self, raw_sections, logic_nodes):
        """
        Use LLM to semantically match LaTeX section names to Logic Chain node names.
        """
        if not raw_sections or not logic_nodes:
            return {}
            
        system_prompt = """You are a semantic matcher.
Task: Match the 'Raw Section Names' (from a LaTeX file) to the 'Logic Node Names' (from a logic chain.
Rules:
1. Return a JSON object where keys are Raw Section Names and values are the corresponding Logic Node Names.
2. If a Raw Section implies or covers a Logic Node (even if wording differs), map it.
3. If no match is found for a raw section, map it to null.
4. One Logic Node can be matched by multiple Raw Sections (e.g. splitting a section).
"""
        user_prompt = f"""
Raw Section Names: {json.dumps(raw_sections)}
Logic Node Names: {json.dumps(logic_nodes)}

Return JSON map: {{ "Raw Name": "Logic Name" }}
"""
        # Reuse existing LLM call logic
        url = self.api_url
        if not url.endswith("/chat/completions"):
             if url.endswith("/v1"): url = f"{url}/chat/completions"
             else: url = f"{url.rstrip('/')}/chat/completions"

        payload = {
            "model": self.model_type,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }
        if str(self.model_type or "").lower().strip().startswith("gpt-5"):
            payload.pop("temperature", None)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        try:
            print("Invoking LLM for semantic section matching...")
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 400 and ("temperature" in (resp.text or "").lower()):
                payload.pop("temperature", None)
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content']
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    mapping = json.loads(match.group(0))
                    print(f"LLM Section Mapping: {mapping}")
                    return mapping
        except Exception as e:
            print(f"LLM Section Matching failed: {e}")
        
        return {}

    def get_section_ranges(self, content_tex, logic_chain_nodes):
        """
        Parses content.tex string to find which slides belong to which section.
        """
        lines = content_tex.splitlines()
        
        # 1. First Pass: Extract all raw section names from LaTeX
        raw_sections_list = []
        for line in lines:
            match = re.search(r'\\section\{([^}]+)\}', line)
            if match:
                raw_sections_list.append(match.group(1))
        
        def _node_label(n):
            if not isinstance(n, dict):
                return ""
            for k in ("name", "title", "text", "role"):
                v = n.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return ""

        logic_node_names = [_node_label(n) for n in (logic_chain_nodes or []) if _node_label(n)]
        
        # 2. Get Semantic Mapping from LLM
        # Fallback to simple mapping if LLM fails
        semantic_map = self._match_sections_with_llm(raw_sections_list, logic_node_names)
        
        slide_section_map = {}
        current_section_name = "Intro" 
        frames_found = 0
        
        # Helper to normalize strings for comparison (Still useful for fallback)
        def normalize(s):
            return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()

        valid_node_names = {lbl: lbl for lbl in logic_node_names}
        normalized_node_names = {normalize(lbl): lbl for lbl in logic_node_names}
        
        for line in lines:
            if "\\section" in line:
                match = re.search(r'\\section\{([^}]+)\}', line)
                if match:
                    raw_name = match.group(1)
                    matched_name = None
                    
                    # Strategy 1: LLM Map
                    if raw_name in semantic_map and semantic_map[raw_name]:
                        matched_name = semantic_map[raw_name]
                        print(f"LLM Matched: '{raw_name}' -> '{matched_name}'")
                    
                    # Strategy 2: Exact/Normalized Match (Fallback)
                    elif raw_name in valid_node_names:
                        matched_name = raw_name
                    elif normalize(raw_name) in normalized_node_names:
                        matched_name = normalized_node_names[normalize(raw_name)]
                    
                    # Strategy 3: Heuristic Substring (Fallback)
                    else:
                        for node_name in valid_node_names:
                            if normalize(node_name) in normalize(raw_name):
                                matched_name = node_name
                                break
                    
                    if matched_name:
                        current_section_name = matched_name
                    else:
                        current_section_name = raw_name
                        print(f"Unmatched Section: '{raw_name}' (kept as is)")
            
            if "\\end{frame}" in line:
                slide_section_map[frames_found] = current_section_name
                frames_found += 1

        if logic_node_names and (not any(v in set(logic_node_names) for v in slide_section_map.values())):
            try:
                frames = [m.group(1) for m in re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', content_tex, re.DOTALL)]

                def tokens(s: str) -> set:
                    t = re.sub(r"\\\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", s)
                    t = re.sub(r"\{[^\}]*\}", " ", t)
                    t = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", " ", t)
                    parts = [p.strip().lower() for p in t.split() if p.strip()]
                    return set([p for p in parts if len(p) > 1])

                node_tokens = [(name, tokens(name)) for name in logic_node_names]
                for i, fr in enumerate(frames):
                    ft = tokens(fr)
                    best_score = 0
                    best_name = "Unknown"
                    for name, nt in node_tokens:
                        if not nt:
                            continue
                        score = len(ft & nt)
                        if score > best_score:
                            best_score = score
                            best_name = name
                    slide_section_map[i] = best_name if best_score >= 1 else "Unknown"
            except Exception:
                pass

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
        nodes_in = logic_chain.get('nodes', [])
        by_id = {}
        idx_to_name = {}
        for i, n in enumerate(nodes_in or []):
            if not isinstance(n, dict):
                continue
            name = str(n.get('name') or n.get('title') or n.get('text') or n.get('role') or '').strip()
            if name:
                idx_to_name[i] = name
            nid = str(n.get('node_id') or '').strip()
            if nid and name:
                by_id[nid] = name

        def edge_end_to_name(v):
            if isinstance(v, int):
                return idx_to_name.get(v)
            s = str(v)
            if s.isdigit():
                return idx_to_name.get(int(s))
            return by_id.get(s)

        print("Starting Logic Chain based analysis...")
        print(f"Available Sections in Slides: {list(section_slides.keys())}")
        print(f"Logic Chain Edges: {len(logic_chain.get('edges', []))}")

        for edge in logic_chain.get('edges', []):
            try:
                et = edge.get('type', 'reference')
            except Exception:
                et = 'reference'
            if et == 'reference':
                src_name = edge_end_to_name(edge.get('from'))
                dst_name = edge_end_to_name(edge.get('to'))
                
                print(f"Checking Edge: {src_name} -> {dst_name}")
                
                if src_name and dst_name:
                    src_s = section_slides.get(src_name, [])
                    dst_s = section_slides.get(dst_name, [])
                    
                    if src_s and dst_s:
                        print(f"Analyzing dependency: {src_name} ({len(src_s)} slides) -> {dst_name} ({len(dst_s)} slides)")
                        # Tool Call: Analyze specific section pair
                        sub_edges = self._analyze_section_pair(src_name, dst_name, src_s, dst_s)
                        final_edges.extend(sub_edges)
                    else:
                        print(f"Skipping: One or both sections empty. Src: {len(src_s)}, Dst: {len(dst_s)}")

        return {"nodes": nodes, "edges": final_edges}

    def generate_simple_graph(self, alignment_data, logic_chain, slide_section_map, max_refs_per_slide: int = 3):
        nodes = []
        section_slides = {}
        for i, pair in enumerate(alignment_data):
            sec = slide_section_map.get(i, "Unknown")
            if sec not in section_slides: section_slides[sec] = []
            section_slides[sec].append(i)
            nodes.append({"id": i, "content_tuple": pair, "section": sec, "summary": "Simple Graph"})
            
        edges = []
        nodes_in = logic_chain.get('nodes', [])
        by_id = {}
        idx_to_name = {}
        for i, n in enumerate(nodes_in or []):
            if not isinstance(n, dict):
                continue
            name = str(n.get('name') or n.get('title') or n.get('text') or n.get('role') or '').strip()
            if name:
                idx_to_name[i] = name
            nid = str(n.get('node_id') or '').strip()
            if nid and name:
                by_id[nid] = name

        def edge_end_to_name(v):
            if isinstance(v, int):
                return idx_to_name.get(v)
            s = str(v)
            if s.isdigit():
                return idx_to_name.get(int(s))
            return by_id.get(s)

        max_refs = int(max_refs_per_slide or 0)
        if max_refs <= 0:
            max_refs = 3
        max_refs = max(1, min(10, max_refs))

        for edge in logic_chain.get('edges', []):
            try:
                et = edge.get('type', 'reference')
            except Exception:
                et = 'reference'
            if et == 'reference':
                src_name = edge_end_to_name(edge.get('from'))
                dst_name = edge_end_to_name(edge.get('to'))
                src_ids = section_slides.get(src_name, [])
                dst_ids = section_slides.get(dst_name, [])
                if src_ids and dst_ids:
                    reason = str(edge.get('reason') or 'Section-level inheritance')
                    dst_sorted = sorted(set(int(x) for x in dst_ids))
                    for s in sorted(set(int(x) for x in src_ids)):
                        candidates = [d for d in dst_sorted if d < s]
                        if not candidates:
                            continue
                        chosen = candidates[-max_refs:]
                        for d in chosen:
                            edges.append({"from": s, "to": d, "type": "reference", "reason": reason})
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

        def _dedupe_targets(items):
            seen = set()
            out = []
            for t in items or []:
                try:
                    k = int(t.get('target_id'))
                except Exception:
                    continue
                if k in seen:
                    continue
                seen.add(k)
                out.append({"target_id": k, "reason": str(t.get('reason') or '').strip()})
            return out

        if not self.api_key:
            for src_id, targets in refs.items():
                try:
                    src_id_int = int(src_id)
                except Exception:
                    continue
                src_node = nodes.get(src_id_int)
                current_speech = ""
                try:
                    if src_node and isinstance(src_node.get('content_tuple'), (list, tuple)) and len(src_node['content_tuple']) >= 2:
                        current_speech = str(src_node['content_tuple'][1] or '').strip()
                except Exception:
                    current_speech = ""

                uniq = _dedupe_targets(targets)
                if not uniq:
                    continue

                refs_txt = []
                for t in uniq[:3]:
                    dst = int(t["target_id"]) + 1
                    reason = t.get("reason")
                    if reason:
                        refs_txt.append(f"如前面第{dst}页所述，{reason}")
                    else:
                        refs_txt.append(f"如前面第{dst}页所述")
                bridge = "，".join(refs_txt)
                if current_speech:
                    refined_speeches[src_id_int] = (current_speech.rstrip() + "\n\n" + bridge).strip()
                else:
                    refined_speeches[src_id_int] = bridge.strip()
            return refined_speeches

        for src_id, targets in refs.items():
            src_node = nodes.get(src_id)
            if not src_node: continue
            
            if len(src_node['content_tuple']) < 2:
                continue

            current_speech = src_node['content_tuple'][1] # (frame, speech)
            
            # Construct context about referenced slides
            ref_context = ""
            for t in targets:
                dst_node = nodes.get(t['target_id'])
                if dst_node and len(dst_node['content_tuple']) >= 1:
                    ref_context += f"- Referenced Slide {t['target_id']} (Section: {dst_node['section']}): {_preview_text(dst_node['content_tuple'][0])} (Reason: {t['reason']})\n"
            
            uniq = _dedupe_targets(targets)
            ref_context = ""
            for t in uniq:
                dst_node = nodes.get(t['target_id'])
                if dst_node and len(dst_node['content_tuple']) >= 1:
                    ref_context += f"- Slide {int(t['target_id']) + 1} (Section: {dst_node['section']}): {_preview_text(dst_node['content_tuple'][0])} (Why: {t['reason']})\n"

            prompt = f"""You are rewriting a presentation speech script.
Current speech (Slide {int(src_id) + 1}):
{current_speech}

The current slide should reference these previous slides:
{ref_context}

Requirements:
1) Rewrite the FULL speech into a natural, fluent narrative (do not append a separate reference list).
2) Use first-person narrator voice (e.g., "we", "I", "let's").
3) Integrate the references into suitable positions in the speech (e.g., opening bridge or when introducing a concept).
4) Do NOT output any markers like "ref", "[ref:...]", "⟦ref:...⟧".
5) Avoid duplication; each referenced slide should be used at most once.
Return ONLY the rewritten speech text.
"""
            # Call LLM
            try:
                url = self.api_url
                if not url.endswith("/chat/completions"):
                     if url.endswith("/v1"): url = f"{url}/chat/completions"
                     else: url = f"{url.rstrip('/')}/chat/completions"
                
                payload = {
                    "model": self.model_type,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }
                if str(self.model_type or "").lower().strip().startswith("gpt-5"):
                    payload.pop("temperature", None)
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 400 and ("temperature" in (resp.text or "").lower()):
                    payload.pop("temperature", None)
                    resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    new_speech = resp.json()['choices'][0]['message']['content']
                    refined_speeches[src_id] = str(new_speech).strip()
                    print(f"Refined speech for Slide {src_id}")
            except Exception as e:
                print(f"Failed to refine speech for {src_id}: {e}")
        
        return refined_speeches

    def run(self, content_tex, speeches, logic_chain, pdf_path=None, use_llm=False, precomputed_alignment=None, max_refs_per_slide: int = 3):
        try:
            nodes_in = logic_chain.get('nodes', []) if isinstance(logic_chain, dict) else []
            norm_nodes = []
            for n in nodes_in or []:
                if not isinstance(n, dict):
                    continue
                if str(n.get('name', '')).strip():
                    norm_nodes.append(n)
                    continue
                for k in ("title", "text", "role"):
                    v = n.get(k)
                    if v is not None and str(v).strip():
                        nn = dict(n)
                        nn['name'] = str(v).strip()
                        norm_nodes.append(nn)
                        break
                else:
                    norm_nodes.append(n)
            if isinstance(logic_chain, dict):
                logic_chain = dict(logic_chain)
                logic_chain['nodes'] = norm_nodes
        except Exception:
            pass
        if precomputed_alignment:
            alignment_data = precomputed_alignment
            print(f"Using precomputed alignment with {len(alignment_data)} pairs.")
        elif pdf_path and use_llm:
            print("Generating alignment on-the-fly...")
            alignment_data = self.generate_alignment(pdf_path, speeches, content_tex)
            print(f"Generated {len(alignment_data)} alignment pairs.")
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
            graph_result = self.generate_simple_graph(alignment_data, logic_chain, slide_section_map, max_refs_per_slide=max_refs_per_slide)
            
        return graph_result
