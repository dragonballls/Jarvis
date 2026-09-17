from config.providers import get_active_provider, load_provider_config
from providers.openai_compat import OpenAICompatibleProvider
from providers.registry import get_provider_class


def test_legacy_ollama_default_prefers_cloud_routing_primary():
    config = {
        "default": {"provider": "ollama"},
        "routing": {"primary": "openai"},
    }

    assert get_active_provider(config) == "openai"


def test_explicit_remote_default_remains_authoritative():
    config = {
        "default": {"provider": "openrouter"},
        "routing": {"primary": "openai"},
    }

    assert get_active_provider(config) == "openrouter"


def test_missing_default_uses_routing_primary():
    config = {"routing": {"primary": "openai"}}

    assert get_active_provider(config) == "openai"


def test_openrouter_is_registered_with_cloud_defaults(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    config = load_provider_config()["openrouter"]

    assert config["base_url"] == "https://openrouter.ai/api/v1"
    assert config["model"] == "openrouter/free"
    assert config["provider_name"] == "openrouter"
    assert get_provider_class("openrouter") is OpenAICompatibleProvider
