"""Evidence-grounded GPT-4o reasoning for EDOCA."""

from __future__ import annotations

import logging
import json
from typing import Any

from src.reasoning.provider import OpenAIReasoningProvider, ReasoningOutputModel, ReasoningProvider

logger = logging.getLogger(__name__)


ReasoningOutput = dict[str, Any]


OUTPUT_FIELDS = (
	"finding_title",
	"severity",
	"confidence",
	"root_cause",
	"reasoning",
	"recommendation",
	"affected_assets",
)


class GPTReasoner:
	"""Use GPT-4o to explain supplied assurance results without adding facts."""

	def __init__(self, provider: ReasoningProvider | None = None) -> None:
		self.provider = provider or OpenAIReasoningProvider()

	def reason(
		self,
		question: str,
		graph_context: dict[str, Any] | None,
		evidence: list[dict[str, Any]],
		assurance_results: list[dict[str, Any]],
	) -> ReasoningOutput:
		"""Generate and validate one strict, evidence-grounded reasoning result."""
		if not isinstance(question, str) or not question.strip():
			raise ValueError("question must be a non-empty string")
		if not isinstance(evidence, list) or not isinstance(assurance_results, list):
			raise ValueError("evidence and assurance_results must be lists")
		try:
			if isinstance(self.provider, OpenAIReasoningProvider):
				raw_response = self.provider.generate_contextual(
					question, graph_context, evidence, assurance_results
				)
			else:
				raw_response = self.provider.generate(
					self._build_prompt(question, graph_context, evidence, assurance_results)
				)
			output = self._parse_response(raw_response)
			self._validate_grounding(output, graph_context)
			logger.info("Generated grounded GPT reasoning for question")
			return output
		except Exception:
			logger.exception("GPT reasoning failed")
			raise

	def _build_prompt(
		self,
		question: str,
		graph_context: dict[str, Any] | None,
		evidence: list[dict[str, Any]],
		assurance_results: list[dict[str, Any]],
	) -> str:
		"""Build a bounded prompt that explicitly defines the fact boundary."""
		payload = {
			"question": question,
			"graph_context": graph_context or {},
			"evidence": evidence,
			"assurance_results": assurance_results,
		}
		return (
			"You are an engineering assurance reviewer. Use ONLY the facts in the JSON "
			"input below. Assurance results and evidence are authoritative. Graph context "
			"may identify relationships and affected assets, but it is not permission to "
			"invent facts. Do not add measurements, tags, causes, standards, dates, or "
			"recommendations that are not supported by the supplied input. If evidence is "
			"insufficient, say so plainly in reasoning and root_cause. Return exactly one "
			"JSON object with exactly these fields: "
			+ json.dumps(OUTPUT_FIELDS)
			+ ". severity must be a string; confidence must be between 0 and 1; "
			"affected_assets must contain only asset names present in graph_context nodes.\n\n"
			+ json.dumps(payload, indent=2, ensure_ascii=False)
		)

	@staticmethod
	def _parse_response(raw_response: str | dict[str, Any] | ReasoningOutputModel) -> ReasoningOutput:
		if isinstance(raw_response, ReasoningOutputModel):
			return raw_response.model_dump()
		if not isinstance(raw_response, (str, dict)):
			raise ValueError("Reasoning response must be a JSON object")
		if isinstance(raw_response, str):
			try:
				parsed = json.loads(raw_response)
			except json.JSONDecodeError as exc:
				raise ValueError("GPT-4o response was not valid JSON") from exc
		else:
			parsed = raw_response
		if not isinstance(parsed, dict):
			raise ValueError("GPT-4o response must be a JSON object")
		if set(parsed) != set(OUTPUT_FIELDS):
			raise ValueError("GPT-4o response fields do not match the required schema")
		if not all(isinstance(parsed[field], str) for field in OUTPUT_FIELDS if field != "confidence" and field != "affected_assets"):
			raise ValueError("GPT-4o text fields must be strings")
		if not isinstance(parsed["confidence"], (int, float)) or not 0 <= parsed["confidence"] <= 1:
			raise ValueError("confidence must be between 0 and 1")
		if not isinstance(parsed["affected_assets"], list) or not all(isinstance(asset, str) for asset in parsed["affected_assets"]):
			raise ValueError("affected_assets must be a list of strings")
		return {
			"finding_title": parsed["finding_title"],
			"severity": parsed["severity"],
			"confidence": float(parsed["confidence"]),
			"root_cause": parsed["root_cause"],
			"reasoning": parsed["reasoning"],
			"recommendation": parsed["recommendation"],
			"affected_assets": parsed["affected_assets"],
		}

	@staticmethod
	def _validate_grounding(output: ReasoningOutput, graph_context: dict[str, Any] | None) -> None:
		if not graph_context:
			if output["affected_assets"]:
				raise ValueError("affected_assets require graph context")
			return
		nodes = graph_context.get("nodes", [])
		if not isinstance(nodes, list):
			raise ValueError("graph_context nodes must be a list")
		known_assets = {
			str(node.get("name", ""))
			for node in nodes
			if isinstance(node, dict)
		}
		unknown = set(output["affected_assets"]) - known_assets
		if unknown:
			raise ValueError(f"GPT-4o returned unknown affected assets: {sorted(unknown)}")
