"""Tests for the provider-agnostic LLM wrapper."""
import pytest
from unittest.mock import patch, MagicMock

from ml.agents.llm_provider import (
    LLMProvider, GeminiProvider, GroqProvider, OllamaProvider,
    OpenAIProvider, AnthropicProvider, HuggingFaceProvider,
    NullProvider, get_llm_provider, list_providers, PROVIDERS,
)


class TestProviderRegistry:
    def test_all_providers_registered(self):
        assert set(PROVIDERS.keys()) == {"gemini", "groq", "ollama", "openai", "anthropic", "hf"}

    def test_each_provider_subclasses_base(self):
        for cls in PROVIDERS.values():
            assert issubclass(cls, LLMProvider)


class TestNullProvider:
    def test_null_is_never_available(self):
        p = NullProvider()
        assert p.is_available() is False

    def test_null_returns_fallback_message(self):
        p = NullProvider()
        out = p.generate("anything")
        assert "LLM unavailable" in out
        assert "FINAL_ANSWER" in out


class TestGeminiProvider:
    def test_missing_key_marks_unavailable(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        p = GeminiProvider()
        assert p.is_available() is False
        assert "not set" in p.info().detail

    def test_default_model(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        p = GeminiProvider()
        # Google rolling alias — always points to the current flash model
        assert p.model == "gemini-flash-latest"


class TestGroqProvider:
    def test_missing_key_unavailable(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        p = GroqProvider()
        assert p.is_available() is False

    def test_present_key_available(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
        p = GroqProvider()
        assert p.is_available() is True

    def test_generate_uses_openai_compatible_endpoint(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
        p = GroqProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
        mock_resp.raise_for_status.return_value = None
        with patch("requests.post", return_value=mock_resp) as mock_post:
            out = p.generate("test")
            assert out == "hello"
            call_url = mock_post.call_args[0][0]
            assert "groq.com" in call_url


class TestOllamaProvider:
    def test_connection_failure_marks_unavailable(self, monkeypatch):
        p = OllamaProvider(base_url="http://localhost:1")
        assert p.is_available() is False
        assert "failed" in p.info().detail

    def test_model_check_when_server_up(self, monkeypatch):
        p = OllamaProvider(model="llama3.1:8b", base_url="http://localhost:11434")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3.1:8b"}]}
        with patch("requests.get", return_value=mock_resp):
            assert p.is_available() is True


class TestOpenAIProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert OpenAIProvider().is_available() is False

    def test_with_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert OpenAIProvider().is_available() is True


class TestAnthropicProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert AnthropicProvider().is_available() is False


class TestHFProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("HF_API_KEY", raising=False)
        assert HuggingFaceProvider().is_available() is False


class TestFactory:
    def test_auto_falls_back_to_null_when_nothing_configured(self, monkeypatch):
        for k in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
                  "ANTHROPIC_API_KEY", "HF_API_KEY", "LLM_PROVIDER"]:
            monkeypatch.delenv(k, raising=False)
        with patch("requests.get", side_effect=Exception("no ollama")):
            p = get_llm_provider("auto")
            assert isinstance(p, NullProvider)

    def test_explicit_choice_returns_requested(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
        p = get_llm_provider("groq")
        assert isinstance(p, GroqProvider)
        assert p.is_available() is True

    def test_env_var_choice(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = get_llm_provider()
        assert isinstance(p, OpenAIProvider)

    def test_unknown_provider_returns_null(self, monkeypatch):
        p = get_llm_provider("nonsense")
        assert isinstance(p, NullProvider)

    def test_auto_prefers_available(self, monkeypatch):
        for k in ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        with patch("requests.get", side_effect=Exception("no ollama")):
            p = get_llm_provider("auto")
            assert p.name == "groq"


class TestListProviders:
    def test_returns_info_for_every_provider(self, monkeypatch):
        for k in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
                  "ANTHROPIC_API_KEY", "HF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)
        infos = list_providers()
        names = {i.name for i in infos}
        assert "gemini" in names
        assert "groq" in names
        assert "ollama" in names
        assert "openai" in names


class TestBaseAgentUsesWrapper:
    def test_base_agent_uses_provider(self, monkeypatch):
        """BaseAgent should delegate LLM calls to the wrapper."""
        from ml.agents.base import BaseAgent
        for k in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
                  "ANTHROPIC_API_KEY", "HF_API_KEY", "LLM_PROVIDER"]:
            monkeypatch.delenv(k, raising=False)
        with patch("requests.get", side_effect=Exception("no ollama")):
            agent = BaseAgent("t", "tester", "prompt")
            assert agent._provider is not None
            assert agent._llm_available is False
            out = agent._call_llm("hi")
            assert "LLM unavailable" in out
