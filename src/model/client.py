"""OpenAI-compatible clients for CLI Proxy and SURF."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from src.standard import PaperInteractionExtraction

Provider = Literal["cliproxy", "surf"]
ResponseMode = Literal["json_schema", "json_object"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SURF_BASE_URL = "https://willma.surf.nl/api/v0"
CLIPROXY_BASE_URL = "https://cliproxy.sub2api-best.com/v1"

MODEL_ALIASES: dict[Provider, dict[str, str]] = {
    "cliproxy": {
        "gpt6luna": "gpt-6-luna",
        "gpt56luna": "gpt-5.6-luna",
    },
    "surf": {
        "gemma4": "RedHatAI/gemma-4-31B-it-NVFP4",
        "qwen35b": "Qwen/Qwen3.6-35B-A3B-FP8",
        "oss120b": "openai/gpt-oss-120b",
    },
}


class StructuredOutputError(RuntimeError):
    """The provider returned no usable schema-conforming output."""


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved connection settings for one OpenAI-compatible provider."""

    provider: Provider
    model: str
    api_key: str
    base_url: str
    timeout_seconds: float


def resolve_model(provider: Provider, model: str) -> str:
    """Resolve a friendly model alias, while allowing an explicit full model ID."""
    return MODEL_ALIASES[provider].get(model, model)


def load_provider_config(
    provider: Provider | None = None,
    model: str | None = None,
    *,
    timeout_seconds: float | None = None,
) -> ProviderConfig:
    """Load non-secret defaults and the selected provider's key from ``.env``."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    resolved_provider = provider or os.getenv("LLM_PROVIDER", "cliproxy")
    if resolved_provider not in MODEL_ALIASES:
        choices = ", ".join(MODEL_ALIASES)
        raise ValueError(f"Unknown provider {resolved_provider!r}; choose one of: {choices}")

    typed_provider: Provider = resolved_provider  # type: ignore[assignment]
    default_alias = "gpt6luna" if typed_provider == "cliproxy" else "oss120b"
    requested_model = model or os.getenv("LLM_MODEL", default_alias)
    key_name = "CLIPROXY_API_KEY" if typed_provider == "cliproxy" else "SURF_API_KEY"
    base_name = "CLIPROXY_API_BASE" if typed_provider == "cliproxy" else "SURF_API_BASE"
    default_base = CLIPROXY_BASE_URL if typed_provider == "cliproxy" else SURF_BASE_URL

    api_key = os.getenv(key_name)
    if not api_key or api_key.startswith("replace_with_"):
        raise RuntimeError(f"{key_name} is missing; copy .env.example to .env and set it")

    if timeout_seconds is None:
        timeout_seconds = float(os.getenv("LLM_REQUEST_TIMEOUT", "180"))
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    return ProviderConfig(
        provider=typed_provider,
        model=resolve_model(typed_provider, requested_model),
        api_key=api_key,
        base_url=os.getenv(base_name, default_base),
        timeout_seconds=timeout_seconds,
    )


def _request_options(config: ProviderConfig, max_output_tokens: int) -> dict:
    """Return provider/model-specific options observed in the reference runner."""
    if max_output_tokens < 1:
        raise ValueError("max_output_tokens must be positive")

    options: dict = {}
    if config.provider == "cliproxy":
        options["max_completion_tokens"] = max_output_tokens
        options["reasoning_effort"] = "none"
    else:
        options["max_tokens"] = max_output_tokens
        if config.model == MODEL_ALIASES["surf"]["qwen35b"]:
            options["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    return options


class StructuredLLMClient:
    """Extract ``PaperInteractionExtraction`` through an OpenAI-compatible API."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        client_options: dict = {}
        if config.provider == "surf":
            client_options["default_headers"] = {"X-API-KEY": config.api_key}
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=0,
            **client_options,
        )

    def extract(
        self,
        messages: list[dict[str, str]],
        *,
        response_mode: ResponseMode = "json_schema",
        max_output_tokens: int = 8_000,
    ) -> PaperInteractionExtraction:
        """Request and validate one structured extraction, retrying transient errors."""
        delays = (0, 5, 15, 30)
        for attempt, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                options = _request_options(self.config, max_output_tokens)
                if response_mode == "json_schema":
                    completion = self.client.chat.completions.parse(
                        model=self.config.model,
                        messages=messages,
                        temperature=0,
                        response_format=PaperInteractionExtraction,
                        **options,
                    )
                    choice = completion.choices[0]
                    if choice.finish_reason == "length":
                        raise StructuredOutputError(
                            "The response reached its output limit before completion"
                        )
                    if choice.message.refusal:
                        raise StructuredOutputError(
                            f"The model refused the extraction: {choice.message.refusal}"
                        )
                    if choice.message.parsed is None:
                        raise StructuredOutputError("The provider returned no parsed output")
                    return choice.message.parsed

                completion = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                    **options,
                )
                choice = completion.choices[0]
                if choice.finish_reason == "length":
                    raise StructuredOutputError(
                        "The response reached its output limit before completion"
                    )
                content = choice.message.content
                if not content:
                    raise StructuredOutputError("The provider returned an empty response")
                return PaperInteractionExtraction.model_validate(json.loads(content))
            except (APIConnectionError, APITimeoutError):
                if attempt == len(delays) - 1:
                    raise
            except APIStatusError as exc:
                retryable = exc.status_code in {408, 429, 500, 502, 503, 504}
                if not retryable or attempt == len(delays) - 1:
                    raise

        raise AssertionError("Retry loop ended unexpectedly")
