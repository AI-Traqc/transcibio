from backend.app.services.model_discovery import thinking_support_from_show


def test_reasoning_model_with_off_switch_is_optional():
    show = {"capabilities": ["completion", "thinking"], "details": {"family": "gemma4"}}
    assert thinking_support_from_show(show) == "optional"


def test_gpt_oss_always_thinks():
    show = {"capabilities": ["completion", "tools", "thinking"], "details": {"family": "gptoss"}}
    assert thinking_support_from_show(show) == "always"


def test_model_without_thinking_capability():
    show = {"capabilities": ["completion", "tools"], "details": {"family": "granite"}}
    assert thinking_support_from_show(show) == "none"
    assert thinking_support_from_show({}) == "none"
