import os
import json
import requests
import subprocess
import sys
from dotenv import load_dotenv

class EvalLLM:
    def __init__(self, env_path=None):
        if env_path is None:
             env_path = os.path.join(os.path.dirname(__file__), '../../../../config/env/.env')
        
        load_dotenv(env_path)
        
        self.api_key = os.getenv('DEFAULT_MODEL_API_KEY')
        self.api_url = os.getenv('DEFAULT_MODEL_API_URL', 'https://api.deepseek.com')
        self.model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')
        
        if not self.api_key:
            # Fallback key from previous context
            self.api_key = "sk-6286dc11a31e45649dbf55081b8aef20"

    def _call_llm(self, system_prompt, user_prompt, json_mode=True):
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
            "temperature": 0.0
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content']
                if json_mode:
                    import re
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    # Fallback if no json found
                    return json.loads(content)
                return content
        except Exception as e:
            print(f"LLM Call Failed: {e}")
            return None
        return None

    def check_rules_batch(self, items, rule_descriptions):
        """
        Check multiple rules for multiple items (slide+speech pairs) in one go to save tokens/time.
        items: list of (frame_text, speech_text)
        rule_descriptions: dict {rule_name: description}
        
        Returns: list of dicts {rule_name: bool} corresponding to items
        """
        if not items:
            return []

        # Batch processing: Process 5 items at a time
        results = []
        batch_size = 5
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            
            # Construct prompt
            content_str = ""
            for idx, (frame, speech) in enumerate(batch):
                content_str += f"--- Item {idx+1} ---\nSlide Content: {frame[:500]}...\nSpeech: {speech[:500]}...\n\n"
            
            rules_str = json.dumps(rule_descriptions, indent=2)
            
            system_prompt = f"""You are an expert presentation evaluator.
Your task is to check if the following Presentation Items (Slide + Speech) satisfy specific rules.

Rules to Check:
{rules_str}

For each Item, return a JSON object indicating whether each rule is satisfied (true/false).
Output format:
{{
  "results": [
    {{ "rule_name_1": true, "rule_name_2": false, ... }},
    ...
  ]
}}
Ensure the order of results matches the order of Items.
"""
            user_prompt = f"Items to Evaluate:\n{content_str}"
            
            print(f"  Processing batch {i//batch_size + 1}...", flush=True)
            resp = self._call_llm(system_prompt, user_prompt, json_mode=True)
            
            if resp and "results" in resp:
                results.extend(resp["results"])
            else:
                # Fallback: append False for all
                for _ in batch:
                    results.append({k: False for k in rule_descriptions})
                    
        return results

    def extract_pdf_text(self, pdf_path):
        """Extract text from PDF using a subprocess."""
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
            pages.append(text)
        doc.close()
        print(json.dumps(pages))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    extract(sys.argv[1])
"""
        try:
            result = subprocess.run(
                [sys.executable, "-c", script, pdf_path],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    data = json.loads(output)
                    if isinstance(data, list):
                        return data
            else:
                print(f"PDF Subprocess Failed (Code {result.returncode}): {result.stderr}")
        except Exception as e:
            print(f"PDF Extract Error: {e}")
        return []
