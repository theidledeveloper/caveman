#!/usr/bin/env python3
"""Model provider selection for caveman-compress."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_OUTPUT_TOKENS = 8192
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
DEFAULT_OPENAI_MODEL = "gpt-5"
OUTER_FENCE_REGEX = re.compile(
    r"\A\s*(`{3,}|~{3,})[^\n]*\n(.*)\n\1\s*\Z", re.DOTALL
)


@dataclass(frozen=True)
class ModelBackend:
    provider: str
    model: str
    label: str
    call: Callable[[str], str]


def strip_llm_wrapper(text: str) -> str:
    """Strip outer ```markdown ... ``` fence when it wraps the entire output."""
    match = OUTER_FENCE_REGEX.match(text)
    if match:
        return match.group(2)
    return text


def _post_json(url: str, *, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"API request failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"API request failed: {exc.reason}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API response was not valid JSON: {payload}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"API response had unexpected shape: {data!r}")
    return data


def _provider_from_name(name: str | None) -> str | None:
    if not name:
        return None
    normalized = name.strip().lower()
    if normalized in {"auto", ""}:
        return None
    if normalized in {"anthropic", "claude"}:
        return "anthropic"
    if normalized in {"openai", "gpt"}:
        return "openai"
    raise RuntimeError(
        f"Unsupported CAVEMAN_PROVIDER={name!r}. Use auto, anthropic/claude, or openai/gpt."
    )


def _provider_from_model(model: str | None) -> str | None:
    if not model:
        return None
    normalized = model.strip().lower()
    if normalized.startswith("claude"):
        return "anthropic"
    if normalized.startswith(("gpt-", "o1", "o3", "o4", "o5")):
        return "openai"
    return None


def _resolve_model(provider: str, configured_model: str | None) -> str:
    if configured_model:
        model_provider = _provider_from_model(configured_model)
        if model_provider and model_provider != provider:
            raise RuntimeError(
                f"CAVEMAN_MODEL={configured_model!r} conflicts with provider {provider!r}."
            )
        return configured_model

    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    return os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def _call_anthropic_api(prompt: str, model: str) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        texts = [block.text for block in msg.content if getattr(block, "type", "") == "text"]
        if not texts:
            raise RuntimeError("Anthropic SDK response did not contain text output.")
        return strip_llm_wrapper("".join(texts).strip())
    except ImportError:
        pass

    response = _post_json(
        os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com") + "/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body={
            "model": model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    texts = [
        item.get("text", "")
        for item in response.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    if not texts:
        raise RuntimeError("Anthropic API response did not contain text output.")
    return strip_llm_wrapper("".join(texts).strip())


def _call_claude_cli(prompt: str) -> str:
    try:
        result = subprocess.run(
            ["claude", "--print"],
            input=prompt,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Claude CLI call failed:\n{exc.stderr}") from exc
    return strip_llm_wrapper(result.stdout.strip())


def _call_openai_api(prompt: str, model: str) -> str:
    api_key = os.environ["OPENAI_API_KEY"]
    response = _post_json(
        os.environ.get("OPENAI_BASE_URL", os.environ.get("OPENAI_API_BASE", "https://api.openai.com"))
        + "/v1/responses",
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        body={
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        },
    )

    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return strip_llm_wrapper(output_text.strip())

    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            content_type = content.get("type")
            if content_type in {"output_text", "text"}:
                text = content.get("text") or content.get("value")
                if isinstance(text, str) and text:
                    texts.append(text)

    if not texts:
        raise RuntimeError("OpenAI API response did not contain text output.")
    return strip_llm_wrapper("".join(texts).strip())


def _build_backend(provider: str, configured_model: str | None) -> ModelBackend:
    model = _resolve_model(provider, configured_model)

    if provider == "anthropic":
        if "ANTHROPIC_API_KEY" in os.environ:
            return ModelBackend(
                provider="anthropic",
                model=model,
                label=f"Anthropic API ({model})",
                call=lambda prompt: _call_anthropic_api(prompt, model),
            )
        if shutil.which("claude"):
            return ModelBackend(
                provider="anthropic",
                model=model,
                label="Claude CLI",
                call=_call_claude_cli,
            )
        raise RuntimeError(
            "Anthropic backend requested but neither ANTHROPIC_API_KEY nor `claude` CLI is available."
        )

    if provider == "openai":
        if "OPENAI_API_KEY" not in os.environ:
            raise RuntimeError("OpenAI backend requested but OPENAI_API_KEY is not set.")
        return ModelBackend(
            provider="openai",
            model=model,
            label=f"OpenAI API ({model})",
            call=lambda prompt: _call_openai_api(prompt, model),
        )

    raise RuntimeError(f"Unsupported provider: {provider}")


def resolve_backend() -> ModelBackend:
    configured_model = os.environ.get("CAVEMAN_MODEL")
    configured_provider = _provider_from_name(os.environ.get("CAVEMAN_PROVIDER"))
    model_provider = _provider_from_model(configured_model)

    if configured_provider:
        return _build_backend(configured_provider, configured_model)

    if model_provider:
        return _build_backend(model_provider, configured_model)

    for provider in ("anthropic", "openai"):
        try:
            return _build_backend(provider, configured_model)
        except RuntimeError:
            continue

    raise RuntimeError(
        "No supported model backend available. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or install `claude` CLI."
    )
