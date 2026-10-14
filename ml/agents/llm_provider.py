"""WattWise AI — LLM provider abstraction.

Provider-agnostic LLM interface so the agents can run against:
- Gemini (Google, free tier)
- Groq (Llama/Mixtral on custom chips, free tier, sub-1s)
- Ollama (local LLMs, zero cost, private)
- OpenAI (GPT-4o, paid)
- Anthropic Claude (paid)
- HuggingFace (OSS fallback)

Pick with env vars:
    LLM_PROVIDER=gemini|groq|ollama|openai|anthropic|hf|auto
    LLM_MODEL=<model-id>   # optional override per provider
If LLM_PROVIDER=auto (default), the first provider with valid credentials wins.
"""
from __future__ import annotations
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ProviderInfo:
    name: str
    model: str
    available: bool
    detail: str = ""


class LLMProvider(ABC):
    """Base interface — every provider must implement these two methods."""

    name: str = "unknown"
    default_model: str = ""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Run the LLM on `prompt` and return the raw text response."""

    @abstractmethod
    def is_available(self) -> bool:
        """True if credentials/connection are valid and this provider can be called."""

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            model=getattr(self, "model", self.default_model),
            available=self.is_available(),
            detail=getattr(self, "_detail", ""),
        )


# ─────────────────────────── Gemini ───────────────────────────

class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-flash-latest"  # Google's rolling alias — always points to the current flash model

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("LLM_MODEL") or self.default_model
        self._api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._client = None
        self._detail = ""
        if not self._api_key:
            self._detail = "GEMINI_API_KEY not set"
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self.model)
            self._detail = f"ready ({self.model})"
        except Exception as e:
            self._detail = f"init failed: {e}"
            log.warning("[Gemini] init failed: %s", e)

    def is_available(self) -> bool:
        return self._client is not None

    def generate(self, prompt: str) -> str:
        response = self._client.generate_content(prompt)
        return response.text


# ─────────────────────────── Groq ───────────────────────────

class GroqProvider(LLMProvider):
    """Groq is a hosted provider that runs GPT-OSS / Qwen at ~500 tokens/sec.
    Free tier: 30 req/min. OpenAI-compatible API."""
    name = "groq"
    default_model = "openai/gpt-oss-20b"

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("LLM_MODEL") or self.default_model
        self._api_key = os.getenv("GROQ_API_KEY", "").strip()
        self._detail = ""
        if not self._api_key:
            self._detail = "GROQ_API_KEY not set"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, prompt: str) -> str:
        import requests, re, time
        # gpt-oss-20b and similar tool-calling models on Groq will try to emit
        # OpenAI-style function_call JSON when a prompt mentions tools, then
        # Groq 400s with "Tool choice is none, but model called a tool" because
        # we haven't declared a tools array. Our ReAct loop parses our own
        # TOOL_CALL: text format, so force the model to pure text output.
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "tool_choice": "none",
        }
        for attempt in range(2):
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
                timeout=60,
            )
            if r.status_code == 429 and attempt == 0:
                # Qwen free tier has a 7k input-tokens-per-minute window; a
                # multi-call ReAct loop can burst past it. Retry once after
                # the delay Groq hints at (capped at 20s so we don't hang).
                wait_s = 2.0
                try:
                    err_msg = r.json().get("error", {}).get("message", "")
                    m = re.search(r"try again in ([\d.]+)s", err_msg)
                    if m:
                        wait_s = min(float(m.group(1)) + 0.5, 20.0)
                except Exception:
                    pass
                time.sleep(wait_s)
                continue
            if r.status_code >= 400:
                # Surface Groq's actual error body so a 400 isn't a mystery
                try:
                    err = r.json().get("error", r.json())
                except Exception:
                    err = r.text[:500]
                raise RuntimeError(f"Groq {r.status_code}: {err}")
            return r.json()["choices"][0]["message"]["content"]
        raise RuntimeError(f"Groq {r.status_code}: rate limit retry exhausted")


# ─────────────────────────── Ollama (local) ───────────────────────────

class OllamaProvider(LLMProvider):
    """Local LLM via Ollama. 100% free, private, offline.
    Setup: `podman compose --profile llm up -d` then
    `podman exec wattwise-ollama ollama pull llama3.1:8b`
    """
    name = "ollama"
    default_model = "llama3.1:8b"

    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.model = model or os.getenv("LLM_MODEL") or self.default_model
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self._detail = ""

    def is_available(self) -> bool:
        try:
            import requests
            r = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if r.status_code != 200:
                self._detail = f"Ollama returned {r.status_code}"
                return False
            models = {m["name"] for m in r.json().get("models", [])}
            if self.model not in models and not any(m.startswith(self.model) for m in models):
                self._detail = f"model {self.model} not pulled (have: {list(models)[:3]})"
                return False
            self._detail = f"ready ({self.model})"
            return True
        except Exception as e:
            self._detail = f"connection failed: {e}"
            return False

    def generate(self, prompt: str) -> str:
        import requests
        r = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2}},
            timeout=180,
        )
        r.raise_for_status()
        return r.json()["response"]


# ─────────────────────────── OpenAI ───────────────────────────

class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o-mini"

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("LLM_MODEL") or self.default_model
        self._api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self._base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self._detail = "OPENAI_API_KEY not set" if not self._api_key else f"ready ({self.model})"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, prompt: str) -> str:
        import requests
        r = requests.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ─────────────────────────── Anthropic Claude ───────────────────────────

class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-haiku-4-5"

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("LLM_MODEL") or self.default_model
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self._detail = "ANTHROPIC_API_KEY not set" if not self._api_key else f"ready ({self.model})"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, prompt: str) -> str:
        import requests
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]


# ─────────────────────────── HuggingFace (fallback) ───────────────────────────

class HuggingFaceProvider(LLMProvider):
    name = "hf"
    default_model = "mistralai/Mistral-7B-Instruct-v0.3"

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("LLM_MODEL") or self.default_model
        self._api_key = os.getenv("HF_API_KEY", "").strip()
        self._detail = "HF_API_KEY not set" if not self._api_key else f"ready ({self.model})"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, prompt: str) -> str:
        import requests
        r = requests.post(
            f"https://api-inference.huggingface.co/models/{self.model}",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"inputs": prompt, "parameters": {"temperature": 0.2, "max_new_tokens": 1024}},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0].get("generated_text", "")
        return str(data)


# ─────────────────────────── Null / fallback ───────────────────────────

class NullProvider(LLMProvider):
    """No LLM configured — the agents fall back to a canned message."""
    name = "none"
    default_model = "n/a"

    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str) -> str:
        return "FINAL_ANSWER: LLM unavailable — configure a provider in Alert Settings or set the GEMINI_API_KEY / GROQ_API_KEY env var."


# ─────────────────────────── Factory ───────────────────────────

PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "hf": HuggingFaceProvider,
}

# Auto-selection priority: free & fast first, local second, paid last
AUTO_ORDER = ["gemini", "groq", "ollama", "anthropic", "openai", "hf"]


def get_llm_provider(name: str | None = None) -> LLMProvider:
    """Return a configured LLM provider.

    If `name` is None, read LLM_PROVIDER env var (default "auto").
    If "auto", try providers in AUTO_ORDER and return the first available.
    If no provider is available, return NullProvider (agents will use the fallback message).
    """
    choice = (name or os.getenv("LLM_PROVIDER") or "auto").lower().strip()

    if choice == "auto":
        for candidate in AUTO_ORDER:
            provider = PROVIDERS[candidate]()
            if provider.is_available():
                log.info("[LLM] auto-selected provider: %s (%s)", candidate, provider.info().model)
                return provider
        log.warning("[LLM] auto: no provider available, falling back to NullProvider")
        return NullProvider()

    if choice in PROVIDERS:
        provider = PROVIDERS[choice]()
        if not provider.is_available():
            log.warning("[LLM] explicit choice '%s' not available (%s) — falling back",
                        choice, provider.info().detail)
        return provider

    log.warning("[LLM] unknown provider '%s' — valid: %s", choice, list(PROVIDERS))
    return NullProvider()


def list_providers() -> list[ProviderInfo]:
    """Return info about every provider — useful for the UI status panel."""
    return [PROVIDERS[n]().info() for n in AUTO_ORDER]
