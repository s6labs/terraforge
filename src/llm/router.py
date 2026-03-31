"""
TerraForge LLM Router
Auto-detects available LLM providers (Ollama, Anthropic, OpenRouter, LM Studio, etc.)
and routes requests through the best available provider.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Optional
import httpx


class ProviderType(Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    LMSTUDIO = "lmstudio"
    OPENAI_COMPATIBLE = "openai_compatible"
    GEMINI = "gemini"


@dataclass
class LLMProvider:
    type: ProviderType
    name: str
    base_url: str
    model: str
    api_key: Optional[str] = None
    available: bool = False
    models: list[str] = field(default_factory=list)
    priority: int = 0  # lower = higher priority


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    cached: bool = False


# ─────────────────────────────────────────────
# Provider Detection
# ─────────────────────────────────────────────

OLLAMA_PORTS = [11434]
LMSTUDIO_PORTS = [1234, 8080]
OPENAI_COMPATIBLE_PORTS = [8000, 8001, 5000, 5001]

PREFERRED_OLLAMA_MODELS = [
    "qwen2.5-coder:32b", "qwen2.5-coder:14b", "qwen2.5-coder:7b",
    "deepseek-coder-v2:16b", "deepseek-coder-v2:latest",
    "codellama:34b", "codellama:13b", "codellama:7b",
    "llama3.1:70b", "llama3.1:8b", "llama3.2:latest",
    "mistral:latest", "mixtral:latest",
    "phi3:medium", "phi3:mini",
    "gemma2:27b", "gemma2:9b",
]


async def _check_ollama(port: int = 11434) -> Optional[LLMProvider]:
    """Detect Ollama and enumerate available models."""
    base_url = f"http://localhost:{port}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base_url}/api/tags")
            if r.status_code == 200:
                data = r.json()
                models = [m["name"] for m in data.get("models", [])]
                if not models:
                    return None

                # Pick best model by preference order
                chosen = models[0]
                for preferred in PREFERRED_OLLAMA_MODELS:
                    for m in models:
                        if preferred.lower() in m.lower():
                            chosen = m
                            break
                    else:
                        continue
                    break

                return LLMProvider(
                    type=ProviderType.OLLAMA,
                    name="Ollama (Local)",
                    base_url=base_url,
                    model=chosen,
                    available=True,
                    models=models,
                    priority=10,
                )
    except Exception:
        pass
    return None


async def _check_lmstudio(port: int = 1234) -> Optional[LLMProvider]:
    """Detect LM Studio local server."""
    base_url = f"http://localhost:{port}/v1"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base_url}/models")
            if r.status_code == 200:
                data = r.json()
                models = [m["id"] for m in data.get("data", [])]
                if not models:
                    return None
                return LLMProvider(
                    type=ProviderType.LMSTUDIO,
                    name="LM Studio (Local)",
                    base_url=base_url,
                    model=models[0],
                    available=True,
                    models=models,
                    priority=11,
                )
    except Exception:
        pass
    return None


async def _check_openai_compatible(port: int) -> Optional[LLMProvider]:
    """Detect any OpenAI-compatible local server."""
    base_url = f"http://localhost:{port}/v1"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{base_url}/models")
            if r.status_code == 200:
                data = r.json()
                models = [m["id"] for m in data.get("data", [])]
                if models:
                    return LLMProvider(
                        type=ProviderType.OPENAI_COMPATIBLE,
                        name=f"Local LLM (port {port})",
                        base_url=base_url,
                        model=models[0],
                        available=True,
                        models=models,
                        priority=12,
                    )
    except Exception:
        pass
    return None


def _check_gemini() -> Optional[LLMProvider]:
    """Detect Google Gemini API key."""
    key = os.environ.get("GOOGLE_API_KEY") or _read_from_config("google_api_key")
    if not key:
        return None
    try:
        from google import genai  # noqa: F401 — verify SDK is installed
    except ImportError:
        return None
    return LLMProvider(
        type=ProviderType.GEMINI,
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-1.5-flash",
        api_key=key,
        available=True,
        models=["gemini-1.5-flash", "gemini-1.5-pro"],
        priority=15,
    )


def _check_anthropic() -> Optional[LLMProvider]:
    """Detect Anthropic API key."""
    key = os.environ.get("ANTHROPIC_API_KEY") or _read_from_config("anthropic_api_key")
    if key and key.startswith("sk-ant-"):
        return LLMProvider(
            type=ProviderType.ANTHROPIC,
            name="Anthropic Claude",
            base_url="https://api.anthropic.com",
            model="claude-sonnet-4-6",
            api_key=key,
            available=True,
            models=["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
            priority=20,
        )
    return None


def _check_openrouter() -> Optional[LLMProvider]:
    """Detect OpenRouter API key."""
    key = os.environ.get("OPENROUTER_API_KEY") or _read_from_config("openrouter_api_key")
    if key:
        return LLMProvider(
            type=ProviderType.OPENROUTER,
            name="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            model="anthropic/claude-sonnet-4-6",
            api_key=key,
            available=True,
            models=["anthropic/claude-sonnet-4-6", "meta-llama/llama-3.1-70b-instruct", "mistralai/mixtral-8x7b-instruct"],
            priority=21,
        )
    return None


def _read_from_config(key: str) -> Optional[str]:
    """Read from ~/.terraforge/config.json if exists."""
    config_path = os.path.expanduser("~/.terraforge/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                return json.load(f).get(key)
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────
# Main Auto-Detection
# ─────────────────────────────────────────────

async def detect_providers() -> list[LLMProvider]:
    """
    Auto-detect ALL available LLM providers in parallel.
    Returns sorted list by priority (best first).
    """
    tasks = []

    # Local providers (checked in parallel for speed)
    for port in OLLAMA_PORTS:
        tasks.append(_check_ollama(port))
    for port in LMSTUDIO_PORTS:
        tasks.append(_check_lmstudio(port))
    for port in OPENAI_COMPATIBLE_PORTS:
        tasks.append(_check_openai_compatible(port))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    providers = []
    for r in results:
        if isinstance(r, LLMProvider) and r is not None:
            providers.append(r)

    # Cloud providers (sync key checks) — Gemini first (priority 15 beats Anthropic/OpenRouter)
    for checker in [_check_gemini, _check_anthropic, _check_openrouter]:
        p = checker()
        if p:
            providers.append(p)

    return sorted(providers, key=lambda p: p.priority)


# ─────────────────────────────────────────────
# Unified LLM Call
# ─────────────────────────────────────────────

TERRAFORM_SYSTEM_PROMPT = """/no_think
You are TerraForge, an expert Terraform and Coder workspace template engineer.

Your job is to generate production-grade, valid Terraform HCL for Coder workspace templates.

Rules:
- Always output ONLY valid HCL. No markdown fences. No explanation.
- Use the latest stable provider versions
- Include coder_agent resource with proper init scripts
- Add metadata blocks with display_name, icon, description
- Include sensible defaults and parameter validation
- Add lifecycle blocks for cost management (auto-stop TTL)
- Structure: variables → data sources → resources → outputs
- Follow Coder template best practices: https://coder.com/docs/templates

Output format: Start immediately with `terraform {` — no preamble, no explanation.
"""


async def stream_llm(
    provider: LLMProvider,
    prompt: str,
    system: str = TERRAFORM_SYSTEM_PROMPT,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    """Stream tokens from the given provider."""

    if provider.type == ProviderType.OLLAMA:
        async for chunk in _stream_ollama(provider, prompt, system, temperature):
            yield chunk

    elif provider.type in (ProviderType.LMSTUDIO, ProviderType.OPENAI_COMPATIBLE):
        async for chunk in _stream_openai_compatible(provider, prompt, system, temperature):
            yield chunk

    elif provider.type == ProviderType.ANTHROPIC:
        async for chunk in _stream_anthropic(provider, prompt, system, temperature):
            yield chunk

    elif provider.type == ProviderType.OPENROUTER:
        async for chunk in _stream_openrouter(provider, prompt, system, temperature):
            yield chunk

    elif provider.type == ProviderType.GEMINI:
        async for chunk in _stream_gemini(provider, prompt, system, temperature):
            yield chunk


async def _stream_ollama(provider, prompt, system, temperature) -> AsyncIterator[str]:
    payload = {
        "model": provider.model,
        "prompt": prompt,
        "system": system,
        "stream": True,
        "think": False,  # disable Qwen3/thinking-model CoT — avoids minutes of reasoning before HCL
        "options": {"temperature": temperature, "num_ctx": 2048},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{provider.base_url}/api/generate", json=payload) as r:
            async for line in r.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        # Only yield the response field, not thinking field
                        if "response" in data and not data.get("thinking"):
                            yield data["response"]
                    except Exception:
                        pass


async def _stream_openai_compatible(provider, prompt, system, temperature) -> AsyncIterator[str]:
    payload = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "temperature": temperature,
    }
    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{provider.base_url}/chat/completions", json=payload, headers=headers) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        data = json.loads(line[6:])
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        pass


async def _stream_anthropic(provider, prompt, system, temperature) -> AsyncIterator[str]:
    payload = {
        "model": provider.model,
        "max_tokens": 8192,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": temperature,
    }
    headers = {
        "x-api-key": provider.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{provider.base_url}/v1/messages", json=payload, headers=headers) as r:
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("type") == "content_block_delta":
                            yield data["delta"].get("text", "")
                    except Exception:
                        pass


async def _stream_openrouter(provider, prompt, system, temperature) -> AsyncIterator[str]:
    payload = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "HTTP-Referer": "https://github.com/terraforge",
        "X-Title": "TerraForge",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{provider.base_url}/chat/completions", json=payload, headers=headers) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        data = json.loads(line[6:])
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        pass


async def _stream_gemini(provider, prompt, system, temperature) -> AsyncIterator[str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=provider.api_key)
    async for chunk in await client.aio.models.generate_content_stream(
        model=provider.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
        ),
    ):
        try:
            text = chunk.text
            if text:
                yield text
        except Exception:
            # Safety-filtered chunks have no .text — skip silently
            pass
