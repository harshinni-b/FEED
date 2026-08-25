import json

import pytest

from src.reasoning.gpt_reasoner import GPTReasoner
from src.reasoning import provider as provider_module
from src.reasoning.provider import OpenAIReasoningProvider, ReasoningOutputModel


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.prompt = ""

    def generate(self, prompt: str):
        self.prompt = prompt
        return self.response


class FakeStructuredModel:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return ReasoningOutputModel(**valid_response())


class FakeChatModel:
    def __init__(self, structured_model):
        self.structured_model = structured_model
        self.schema = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self.structured_model


def valid_response() -> dict:
    return {
        "finding_title": "Temperature limit exceeded",
        "severity": "HIGH",
        "confidence": 0.98,
        "root_cause": "The operating value is above the supplied limit.",
        "reasoning": "The assurance result reports 621°C against a 620°C limit.",
        "recommendation": "Review operation before continuing at this condition.",
        "affected_assets": ["Unit-400"],
    }


def inputs():
    return (
        "Is the temperature condition acceptable?",
        {"nodes": [{"entity_id": "unit:400", "name": "Unit-400"}], "relationships": []},
        [{"chunk_id": "c1", "text": "Configured limit is 620°C; operating value is 621°C."}],
        [{"check": "Temperature Limit", "status": "FAIL", "severity": "HIGH", "actual": "621°C", "limit": "620°C", "finding": "Operating value exceeds configured limit"}],
    )


def test_reasoner_returns_strict_grounded_output() -> None:
    provider = FakeProvider(json.dumps(valid_response()))
    question, graph, evidence, assurance = inputs()

    result = GPTReasoner(provider).reason(question, graph, evidence, assurance)

    assert result == valid_response()
    assert "621°C" in provider.prompt
    assert "Unit-400" in provider.prompt
    assert "Temperature Limit" in provider.prompt


def test_reasoner_accepts_pydantic_structured_output() -> None:
    question, graph, evidence, assurance = inputs()

    result = GPTReasoner(FakeProvider(ReasoningOutputModel(**valid_response()))).reason(
        question, graph, evidence, assurance
    )

    assert result == valid_response()


def test_langchain_provider_uses_prompt_template_and_structured_output(monkeypatch) -> None:
    structured_model = FakeStructuredModel()
    chat_model = FakeChatModel(structured_model)
    monkeypatch.setattr(provider_module, "_create_chat_model", lambda api_key, model: chat_model)

    question, graph, evidence, assurance = inputs()
    result = OpenAIReasoningProvider(api_key="test").generate_contextual(
        question, graph, evidence, assurance
    )

    assert result == valid_response()
    assert chat_model.schema is ReasoningOutputModel
    assert "Unit-400" in str(structured_model.messages)
    assert "Temperature Limit" in str(structured_model.messages)


def test_rejects_malformed_json() -> None:
    question, graph, evidence, assurance = inputs()

    with pytest.raises(ValueError, match="valid JSON"):
        GPTReasoner(FakeProvider("not json")).reason(question, graph, evidence, assurance)


def test_rejects_unknown_graph_asset() -> None:
    response = valid_response()
    response["affected_assets"] = ["Unknown Pump"]
    question, graph, evidence, assurance = inputs()

    with pytest.raises(ValueError, match="unknown affected assets"):
        GPTReasoner(FakeProvider(response)).reason(question, graph, evidence, assurance)


def test_missing_evidence_is_forwarded_to_offline_provider() -> None:
    provider = FakeProvider(json.dumps(valid_response()))
    question, graph, _, assurance = inputs()

    result = GPTReasoner(provider).reason(question, graph, [], assurance)

    assert result == valid_response()
    assert '"evidence": []' in provider.prompt


def test_rejects_extra_output_fields() -> None:
    response = valid_response()
    response["unsupported_fact"] = "invented"
    question, graph, evidence, assurance = inputs()

    with pytest.raises(ValueError, match="required schema"):
        GPTReasoner(FakeProvider(response)).reason(question, graph, evidence, assurance)