from app.core.model_config import build_model_config, sanitize_model_config


def test_sanitize_model_config_removes_temperature_for_gpt5_family():
    cfg = sanitize_model_config("gpt-5-mini", {"temperature": 0.2, "max_tokens": 10})
    assert "temperature" not in cfg
    assert cfg["max_tokens"] == 10


def test_build_model_config_omits_temperature_for_gpt5_family_and_uses_max_completion_tokens():
    cfg = build_model_config(model_type="gpt-5-mini", temperature=0.2, max_tokens=123, timeout=7)
    assert "temperature" not in cfg
    assert cfg["max_completion_tokens"] == 123
    assert cfg["timeout"] == 7


def test_build_model_config_keeps_temperature_for_non_gpt5_models():
    cfg = build_model_config(model_type="deepseek-chat", temperature=0.2, max_tokens=123, timeout=None)
    assert cfg["temperature"] == 0.2
    assert cfg["max_tokens"] == 123

