import cui.llm.config as config_mod
from cui.llm.config import load_llm_config


def _noop_load_dotenv():
    """Prevent load_dotenv from loading .env during tests."""


class TestLoadLLMConfig:
    def test_load_config_from_env(self, monkeypatch):
        monkeypatch.setattr(config_mod, "load_dotenv", _noop_load_dotenv)
        monkeypatch.setenv("CUI_LLM_KEY", "sk-test-key")
        monkeypatch.setenv("CUI_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("CUI_LLM_MODEL", "claude-sonnet-5")
        monkeypatch.setenv("CUI_LLM_BASE_URL", "https://api.anthropic.com")

        cfg = load_llm_config()
        assert cfg is not None
        assert cfg.provider == "anthropic"
        assert cfg.api_key == "sk-test-key"
        assert cfg.model == "claude-sonnet-5"
        assert cfg.base_url == "https://api.anthropic.com"

    def test_load_config_returns_none_without_key(self, monkeypatch):
        monkeypatch.setattr(config_mod, "load_dotenv", _noop_load_dotenv)
        monkeypatch.delenv("CUI_LLM_KEY", raising=False)
        cfg = load_llm_config()
        assert cfg is None

    def test_provider_defaults_to_openai(self, monkeypatch):
        monkeypatch.setattr(config_mod, "load_dotenv", _noop_load_dotenv)
        monkeypatch.setenv("CUI_LLM_KEY", "sk-test")
        monkeypatch.setenv("CUI_LLM_MODEL", "gpt-4")
        monkeypatch.delenv("CUI_LLM_PROVIDER", raising=False)

        cfg = load_llm_config()
        assert cfg is not None
        assert cfg.provider == "openai"

    def test_load_config_returns_none_without_model(self, monkeypatch):
        monkeypatch.setattr(config_mod, "load_dotenv", _noop_load_dotenv)
        monkeypatch.setenv("CUI_LLM_KEY", "sk-test-key")
        monkeypatch.delenv("CUI_LLM_MODEL", raising=False)
        cfg = load_llm_config()
        assert cfg is None

    def test_base_url_optional(self, monkeypatch):
        monkeypatch.setattr(config_mod, "load_dotenv", _noop_load_dotenv)
        monkeypatch.setenv("CUI_LLM_KEY", "sk-test")
        monkeypatch.setenv("CUI_LLM_MODEL", "gpt-4")
        monkeypatch.delenv("CUI_LLM_BASE_URL", raising=False)

        cfg = load_llm_config()
        assert cfg is not None
        assert cfg.base_url is None
