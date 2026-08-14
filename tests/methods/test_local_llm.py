"""Unit tests for the Local LLM adapter."""

from collections.abc import Sequence
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
import pytest
from pydantic import ValidationError

from gendertagger.methods.local_llm import (
    LlmClient,
    LocalLlmConfig,
    LocalLlmMethod,
    PersonClassification,
)
from gendertagger.models.classification import CanonicalLabel, PredictionStatus
from gendertagger.models.person import PersonInput


@pytest.fixture
def config() -> LocalLlmConfig:
    return LocalLlmConfig(
        model="llama3",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        system_prompt="Test system prompt.",
        temperature=0.0,
        max_validation_retries=1,
    )


@pytest.fixture
def single_person() -> Sequence[PersonInput]:
    return [
        PersonInput(
            tei_id="per123",
            forenames=["Marie"],
            surname="Curie",
            birth="1867",
            death="1934",
            note="Physicist and chemist.",
        )
    ]


class MockResponse:
    def __init__(self, json_data: dict[str, Any], status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "Error",
                request=httpx.Request("POST", ""),
                response=httpx.Response(self.status_code, request=httpx.Request("POST", "")),
            )


def test_build_prompt() -> None:
    method = LocalLlmMethod()
    person = PersonInput(
        tei_id="per123",
        forenames=["Marie"],
        surname="Curie",
        birth="1867",
        death="1934",
        note="Note 1 Note 2",
    )
    prompt = method._build_prompt(person)
    assert "Marie Curie" in prompt
    assert "1867 - 1934" in prompt
    assert "Note 1 Note 2" in prompt


def test_llm_client_structured_success() -> None:
    client = LlmClient(
        model="llama3",
        base_url="http://test",
        api_key="test",
        temperature=0.0,
        max_validation_retries=1,
    )

    class MockHttpxClient:
        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> MockResponse:
            assert url == "http://test/chat/completions"
            assert json["model"] == "llama3"
            return MockResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"gender": "female", "confidence": 0.95, "certainty": "high", "reasoning": "Known physicist"}'
                            }
                        }
                    ]
                }
            )

    result, metadata = client.structured(
        MockHttpxClient(),
        prompt="Test prompt",
        output_type=PersonClassification,
    )
    assert result.gender == "female"
    assert result.confidence == 0.95
    assert metadata["attempt_count"] == 1


def test_llm_client_retry_then_success() -> None:
    client = LlmClient(
        model="llama3",
        base_url="http://test",
        api_key="test",
        temperature=0.0,
        max_validation_retries=1,
    )

    class MockHttpxClient:
        def __init__(self) -> None:
            self.calls = 0

        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> MockResponse:
            self.calls += 1
            if self.calls == 1:
                return MockResponse({"choices": [{"message": {"content": '{"invalid": "json"}'}}]})
            return MockResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"gender": "male", "confidence": 0.8, "certainty": "low", "reasoning": "Corrected"}'
                            }
                        }
                    ]
                }
            )

    mock_client = MockHttpxClient()
    result, metadata = client.structured(
        mock_client,
        prompt="Test prompt",
        output_type=PersonClassification,
    )
    assert mock_client.calls == 2
    assert result.gender == "male"
    assert metadata["attempt_count"] == 2


def test_llm_client_retry_exhausted() -> None:
    client = LlmClient(
        model="llama3",
        base_url="http://test",
        api_key="test",
        temperature=0.0,
        max_validation_retries=1,
    )

    class MockHttpxClient:
        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> MockResponse:
            return MockResponse({"choices": [{"message": {"content": '{"invalid": "json"}'}}]})

    with pytest.raises(ValidationError):
        client.structured(
            MockHttpxClient(),
            prompt="Test prompt",
            output_type=PersonClassification,
        )


def test_local_llm_method_success(
    config: LocalLlmConfig, single_person: Sequence[PersonInput], monkeypatch: pytest.MonkeyPatch
) -> None:
    class MockHttpxClientContext:
        def __enter__(self) -> "MockHttpxClientContext":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> MockResponse:
            return MockResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"gender": "female", "confidence": 0.9, "certainty": "high", "reasoning": "Marie Curie"}'
                            }
                        }
                    ]
                }
            )

    # Mock httpx.Client to return our context manager
    monkeypatch.setattr(httpx, "Client", lambda: MockHttpxClientContext())

    method = LocalLlmMethod()
    results = method.predict_batch(single_person, config)

    assert len(results) == 1
    assert results[0].status == PredictionStatus.success
    assert results[0].label == CanonicalLabel.female
    assert results[0].method_confidence == 0.9
    assert results[0].metadata["attempt_count"] == 1
    assert results[0].metadata["self_reported_certainty"] == "high"
    assert "Marie Curie" in results[0].raw_output["reasoning"]


def test_local_llm_method_transport_error(
    config: LocalLlmConfig, single_person: Sequence[PersonInput], monkeypatch: pytest.MonkeyPatch
) -> None:
    class MockHttpxClientContext:
        def __enter__(self) -> "MockHttpxClientContext":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> MockResponse:
            raise httpx.ConnectError("Connection failed")

    monkeypatch.setattr(httpx, "Client", lambda: MockHttpxClientContext())

    method = LocalLlmMethod()
    results = method.predict_batch(single_person, config)

    assert len(results) == 1
    assert results[0].status == PredictionStatus.error
    assert results[0].label is None
    assert "Connection failed" in results[0].raw_output["error"]
