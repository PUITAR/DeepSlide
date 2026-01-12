# utils.py
import json
import re

def extract_json_from_response(response_text):
    """从 AI 回复中提取 JSON 数据"""
    json_match = re.search(r'\{[^}]*\}', response_text, re.DOTALL)
    if json_match:
        try:
            json_str = json_match.group()
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
    return None

def validate_requirements(requirements):
    """验证需求数据格式"""
    required_fields = ['audience', 'duration', 'focus_sections']
    for field in required_fields:
        if field not in requirements:
            return False, f"Missing required field: {field}"
    return True, "Validation passed"
