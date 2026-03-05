import json
import re

def extract_json_from_response(response_text: str):
    """
    Extract JSON object from a string.
    Supports markdown code blocks ```json ... ``` or raw JSON.
    """
    if not response_text:
        return None
    
    # Try finding code block
    match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # Try finding raw json brace
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            json_str = match.group(0)
        else:
            return None
            
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None
