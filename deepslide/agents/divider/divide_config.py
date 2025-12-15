# divider_config.py
"""
Divider 配置文件 - 所有可调参数集中管理
"""

# 默认 Planner 指令
DEFAULT_PLANNER_INSTRUCTIONS = {
    "max_section_depth": 3,
    "max_sections": 12,
    "merge_short_threshold": 150,
    "focus_keywords": ["introduction", "method", "experiment", "result", "conclusion"],
    "skip_keywords": ["reference", "bibliography", "appendix", "acknowledgement"],
    "debug_mode": False,
    
    # CAMEL 微调相关参数（后续使用）
    "refine_threshold": 800,
    "refine_style": "ppt_bullet_points",
    "preserve_formulas": True,
    "target_language": "zh"
}

# CAMEL 配置
CAMEL_CONFIG = {
    "model_type": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "base_url_env": "OPENAI_BASE_URL"
}