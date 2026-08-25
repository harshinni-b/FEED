"""LangChain provider boundary for evidence-grounded EDOCA reasoning."""

from __future__ import annotations

import os
import json
from typing import Any, Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from pydantic import BaseModel, Field


class ReasoningOutputModel(BaseModel):
	"""Structured response expected from the reasoning model."""

	finding_title: str = Field(description="Concise title of the engineering finding")
	severity: str = Field(description="Finding severity")
	confidence: float = Field(description="Confidence between 0 and 1")
	root_cause: str = Field(description="Evidence-supported root cause")
	reasoning: str = Field(description="Evidence-supported explanation")
	recommendation: str = Field(description="Evidence-supported recommendation")
	affected_assets: list[str] = Field(description="Asset names present in graph context")


class ReasoningProvider(Protocol):
	"""Interface implemented by GPT and future reasoning providers."""

	def generate(self, prompt: str) -> str | dict[str, Any]:
		"""Generate a strict JSON reasoning response for a prompt."""


class DeterministicReasoningProvider:
	"""Credential-free provider for local demos and deterministic API tests."""

	def generate(self, prompt: str) -> dict[str, Any]:
		"""Summarize only the structured assurance payload supplied by GPTReasoner."""
		try:
			payload = json.loads(prompt.split("\n\n", 1)[1])
		except (IndexError, json.JSONDecodeError) as exc:
			raise ValueError("Deterministic reasoning requires the GPTReasoner JSON prompt") from exc
		results = payload.get("assurance_results", [])
		failed = next(
			(result for result in results if isinstance(result, dict) and result.get("status") == "FAIL"),
			{},
		)
		graph_context = payload.get("graph_context", {})
		assets = [
			str(node.get("name", ""))
			for node in graph_context.get("nodes", [])
			if isinstance(node, dict)
			and node.get("entity_type") in {
				"UNIT", "EQUIPMENT", "INSTRUMENT", "CONTROL_LOOP", "SIF", "VALVE", "LINE",
			}
			and node.get("name")
		]
		return {
			"finding_title": str(failed.get("check", "Engineering consistency review")),
			"severity": str(failed.get("severity", "INFO")),
			"confidence": 1.0 if failed else 0.5,
			"root_cause": str(failed.get("finding", "No failed assurance result was supplied.")),
			"reasoning": (
				f"{failed.get('check', failed.get('entity', 'Assurance'))}: "
				f"{failed.get('finding', 'No failed assurance result was supplied.')}"
			),
			"recommendation": "Review the supplied evidence and assurance result with the engineering team.",
			"affected_assets": list(dict.fromkeys(assets)),
		}


class OpenAIReasoningProvider:
	"""Generate structured reasoning with Azure OpenAI or OpenAI ChatGPT."""

	SYSTEM_PROMPT = (
		"You are an engineering assurance reviewer. Use ONLY the facts supplied in the "
		"question, graph context, retrieved evidence, and assurance results. Assurance "
		"results and evidence are authoritative. Do not invent tags, measurements, source "
		"documents, engineering standards, or affected assets. Graph context may identify "
		"relationships and assets, but does not authorize unsupported claims. If evidence "
		"is missing or insufficient, say so plainly in reasoning and root_cause. Return the "
		"requested structured output only."
	)

	def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
		self.api_key = api_key
		self.model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o")
		self._structured_model: Any | None = None
		self.prompt_template = ChatPromptTemplate.from_messages([
			("system", self.SYSTEM_PROMPT),
			(
				"human",
				"Engineer question:\n{question}\n\n"
				"Graph context (authoritative asset and relationship context):\n{graph_context}\n\n"
				"Retrieved evidence (authoritative source material):\n{evidence}\n\n"
				"Aggregated assurance results (authoritative checks):\n{assurance_results}",
			),
		])

	def generate(self, prompt: str) -> dict[str, Any]:
		"""Generate a Pydantic-validated response from a serialized reasoning prompt."""
		structured_model = self._get_structured_model()
		messages = self.prompt_template.format_messages(
			question=prompt,
			graph_context="{}",
			evidence="[]",
			assurance_results="[]",
		)
		response = structured_model.invoke(messages)
		if isinstance(response, ReasoningOutputModel):
			return response.model_dump()
		if isinstance(response, dict):
			return ReasoningOutputModel.model_validate(response).model_dump()
		raise ValueError("Structured reasoning model returned an invalid response")

	def generate_contextual(
		self,
		question: str,
		graph_context: dict[str, Any] | None,
		evidence: list[dict[str, Any]],
		assurance_results: list[dict[str, Any]],
	) -> dict[str, Any]:
		"""Generate directly from the structured EDOCA inputs."""
		structured_model = self._get_structured_model()
		messages = self.prompt_template.format_messages(
			question=question,
			graph_context=_serialize(graph_context or {}),
			evidence=_serialize(evidence),
			assurance_results=_serialize(assurance_results),
		)
		response = structured_model.invoke(messages)
		return ReasoningOutputModel.model_validate(response).model_dump()

	def _get_structured_model(self) -> Any:
		if self._structured_model is not None:
			return self._structured_model
		chat_model = _create_chat_model(self.api_key, self.model_name)
		self._structured_model = chat_model.with_structured_output(ReasoningOutputModel)
		return self._structured_model


def _create_chat_model(api_key: str | None, model_name: str) -> Any:
	azure_values = {
		"endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
		"api_key": os.getenv("AZURE_OPENAI_API_KEY"),
		"deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
		"version": os.getenv("AZURE_OPENAI_API_VERSION"),
	}
	if any(azure_values.values()):
		missing = [name for name, value in azure_values.items() if not value]
		if missing:
			raise RuntimeError(f"Incomplete Azure OpenAI configuration: missing {', '.join(missing)}")
		return AzureChatOpenAI(
			azure_endpoint=azure_values["endpoint"],
			api_key=azure_values["api_key"],
			azure_deployment=azure_values["deployment"],
			api_version=azure_values["version"],
			temperature=0,
		)
	if api_key or os.getenv("OPENAI_API_KEY"):
		return ChatOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), model=model_name, temperature=0)
	raise RuntimeError("No OpenAI or Azure OpenAI configuration is available")


def _serialize(value: Any) -> str:
	return json.dumps(value, indent=2, ensure_ascii=False)
