import json

import httpx
from openai import OpenAI

from src.model.client import (
    MODEL_ALIASES,
    ProviderConfig,
    StructuredLLMClient,
    _request_options,
    resolve_model,
)


def test_model_aliases_resolve() -> None:
    assert resolve_model("cliproxy", "gpt6luna") == "gpt-6-luna"
    assert resolve_model("surf", "oss120b") == "openai/gpt-oss-120b"
    assert resolve_model("surf", "custom/model") == "custom/model"


def test_provider_specific_request_options() -> None:
    cliproxy = ProviderConfig("cliproxy", "gpt-6-luna", "secret", "https://x", 30)
    surf_qwen = ProviderConfig("surf", MODEL_ALIASES["surf"]["qwen35b"], "secret", "https://x", 30)

    assert _request_options(cliproxy, 100) == {
        "max_completion_tokens": 100,
        "reasoning_effort": "none",
    }
    assert _request_options(surf_qwen, 100) == {
        "max_tokens": 100,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }


def test_openai_sdk_parses_the_pydantic_schema_without_network() -> None:
    captured_request: dict = {}
    response_data = {
        "evidence_type": "direct observation",
        "interactions": [
            {
                "source_taxon_name": "Garrulus glandarius",
                "interaction_type_name": "eats",
                "target_taxon_name": "Fagus sylvatica",
                "part_of_target_taxon": "seed",
                "time_of_occurrence": None,
                "locality_name": "Netherlands",
                "decimal_latitude": None,
                "decimal_longitude": None,
                "observation_date_time": "2020",
                "remarks": None,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "test-completion",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(response_data),
                            "refusal": None,
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            },
        )

    config = ProviderConfig("cliproxy", "gpt-6-luna", "secret", "https://example.test/v1", 30)
    structured_client = StructuredLLMClient(config)
    structured_client.client = OpenAI(
        api_key="secret",
        base_url="https://example.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = structured_client.extract(
        [{"role": "user", "content": "Extract the interactions."}],
        max_output_tokens=100,
    )

    assert result.interactions[0].source_taxon_name == "Garrulus glandarius"
    assert captured_request["response_format"]["type"] == "json_schema"
    assert captured_request["response_format"]["json_schema"]["strict"] is True
