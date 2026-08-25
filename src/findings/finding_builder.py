"""Build deterministic engineering findings from assurance results."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class EngineeringFinding(TypedDict):
	"""Standardized finding produced for engineer review."""

	finding_id: str
	title: str
	severity: str
	status: str
	affected_assets: list[str]
	root_cause: str
	reasoning: str
	evidence: list[dict[str, Any]]
	recommendation: str
	confidence: float


class FindingBuilder:
	"""Convert Attribute Assurance failures into stable engineering findings."""

	ENGINEERING_ASSET_TYPES = {
		"UNIT",
		"EQUIPMENT",
		"INSTRUMENT",
		"CONTROL_LOOP",
		"SIF",
		"VALVE",
		"LINE",
	}

	def build(
		self,
		evidence_records: list[dict[str, Any]],
		graph_context: dict[str, Any] | None,
		assurance_results: list[dict[str, Any]],
		reasoning: dict[str, Any] | None = None,
		query: str = "",
	) -> list[EngineeringFinding]:
		"""Build OPEN findings from all supported failed assurance result types."""
		if not isinstance(evidence_records, list):
			raise ValueError("evidence_records must be a list")
		if not isinstance(assurance_results, list):
			raise ValueError("assurance_results must be a list")
		assets = self._affected_assets(graph_context)
		findings: dict[str, tuple[EngineeringFinding, dict[str, Any], int]] = {}
		for result_index, result in enumerate(assurance_results):
			self._validate_assurance_result(result)
			if result.get("status", "FAIL") != "FAIL":
				continue
			matched_evidence = self._evidence_for(result, evidence_records)
			result_assets = sorted(set(assets + [str(asset) for asset in result.get("affected_assets", [])]))
			finding = self._build_one(
				result,
				matched_evidence,
				result_assets,
				self._reasoning_for_result(reasoning, result_index),
			)
			findings.setdefault(finding["finding_id"], (finding, result, result_index))
		ordered_records = sorted(
			findings.values(),
			key=lambda item: (
				-self._relevance_score(query, item[1], item[0]),
				item[2],
				item[0]["finding_id"],
			),
		)
		ordered = [record[0] for record in ordered_records]
		logger.info("Built %d engineering findings from %d assurance results", len(ordered), len(assurance_results))
		return ordered

	def persist(
		self,
		findings: list[EngineeringFinding],
		output_path: str | Path = "outputs/findings/findings.json",
	) -> Path:
		"""Persist findings as a UTF-8 JSON array and return its path."""
		if not isinstance(findings, list):
			raise ValueError("findings must be a list")
		destination = Path(output_path)
		destination.parent.mkdir(parents=True, exist_ok=True)
		destination.write_text(
			json.dumps(findings, indent=2, ensure_ascii=False),
			encoding="utf-8",
		)
		logger.info("Persisted %d findings to %s", len(findings), destination)
		return destination

	def build_and_persist(
		self,
		evidence_records: list[dict[str, Any]],
		graph_context: dict[str, Any] | None,
		assurance_results: list[dict[str, Any]],
		output_path: str | Path = "outputs/findings/findings.json",
		reasoning: dict[str, Any] | None = None,
		query: str = "",
	) -> list[EngineeringFinding]:
		"""Build findings and persist them to the configured output path."""
		findings = self.build(evidence_records, graph_context, assurance_results, reasoning, query)
		self.persist(findings, output_path)
		return findings

	@staticmethod
	def _validate_assurance_result(result: Any) -> None:
		if not isinstance(result, dict):
			raise ValueError("Each assurance result must be an object")
		if not result.get("check") and not result.get("entity"):
			raise ValueError("Assurance result must contain check or entity")
		if result.get("status", "FAIL") not in {"FAIL", "PASS"}:
			raise ValueError("Assurance status must be FAIL or PASS")

	def _build_one(
		self,
		result: dict[str, Any],
		evidence: list[dict[str, Any]],
		assets: list[str],
		reasoning: dict[str, Any] | None,
	) -> EngineeringFinding:
		title = str(result.get("check") or "Change Impact")
		severity = str(result.get("severity") or "MEDIUM")
		root_cause = str(result.get("finding") or "Engineering change impact requires review")
		merged_assets = assets
		stable_fields = {
			"source_check": str(result.get("check") or result.get("entity") or "Assurance"),
			"check": title,
			"severity": severity,
			"actual": str(result.get("actual", "")),
			"limit": str(result.get("limit", "")),
			"finding": root_cause,
			"evidence": [str(item.get("chunk_id", "")) for item in evidence],
			"assets": merged_assets,
		}
		digest = hashlib.sha256(
			json.dumps(stable_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
		).hexdigest()[:16]
		return {
			"finding_id": f"F-{digest}",
			"title": title,
			"severity": severity,
			"status": "OPEN",
			"affected_assets": merged_assets,
			"root_cause": root_cause,
			"reasoning": str((reasoning or {}).get("reasoning", "")),
			"evidence": evidence,
			"recommendation": str((reasoning or {}).get("recommendation") or f"Investigate and resolve the {title.lower()} before operation."),
			"confidence": float((reasoning or {}).get("confidence", 1.0 if evidence else 0.5)),
		}

	@staticmethod
	def _reasoning_for_result(
		reasoning: dict[str, Any] | None,
		result_index: int,
	) -> dict[str, Any] | None:
		"""Select reasoning scoped to one assurance result, with legacy fallback."""
		if not reasoning:
			return None
		per_result = reasoning.get("per_assurance_result")
		if isinstance(per_result, list):
			for entry in per_result:
				if not isinstance(entry, dict) or entry.get("assurance_index") != result_index:
					continue
				output = entry.get("reasoning")
				return dict(output) if isinstance(output, dict) else None
			return None
		return reasoning

	@classmethod
	def _relevance_score(
		cls,
		query: str,
		result: dict[str, Any],
		finding: EngineeringFinding,
	) -> int:
		"""Rank without changing or filtering the deterministic assurance results."""
		query_terms = cls._tokens(query)
		if not query_terms:
			return 0
		identity = " ".join(str(result.get(field, "")) for field in ("check", "entity", "finding"))
		assets = " ".join(str(asset) for asset in result.get("affected_assets", []))
		focused_evidence = cls._focused_evidence_text(result, finding["evidence"])
		full_evidence = " ".join(
			" ".join(str(record.get(field, "")) for field in ("section", "subsection", "text"))
			for record in finding["evidence"]
			if isinstance(record, dict)
		)
		return (
			8 * len(query_terms & cls._tokens(identity))
			+ 6 * len(query_terms & cls._tokens(assets))
			+ 4 * len(query_terms & cls._tokens(focused_evidence))
			+ len(query_terms & cls._tokens(full_evidence))
		)

	@staticmethod
	def _tokens(value: Any) -> set[str]:
		stop_words = {
			"a", "an", "and", "are", "check", "consistency", "for", "in", "is",
			"issue", "of", "on", "the", "there", "to", "with",
		}
		return {
			token
			for token in re.findall(r"[a-z0-9]+", str(value).casefold())
			if token not in stop_words
		}

	@staticmethod
	def _focused_evidence_text(
		result: dict[str, Any],
		evidence: list[dict[str, Any]],
	) -> str:
		"""Use local document context around result values to identify its parameter."""
		needles = [str(result.get(field, "")).strip().casefold() for field in ("actual", "limit")]
		needles = [needle for needle in needles if needle]
		windows: list[str] = []
		for record in evidence:
			if not isinstance(record, dict):
				continue
			text = " ".join(str(record.get(field, "")) for field in ("section", "subsection", "text"))
			lowered = text.casefold()
			positions = [lowered.find(needle) for needle in needles]
			positions = [position for position in positions if position >= 0]
			for position in positions:
				windows.append(text[max(0, position - 100) : position + 100])
		return " ".join(windows)

	@classmethod
	def _affected_assets(cls, graph_context: dict[str, Any] | None) -> list[str]:
		if not graph_context:
			return []
		nodes = graph_context.get("nodes", [])
		if not isinstance(nodes, list):
			raise ValueError("graph_context nodes must be a list")
		assets = {
			str(node.get("name", node.get("entity_id", "")))
			for node in nodes
			if isinstance(node, dict)
			and node.get("entity_type") in cls.ENGINEERING_ASSET_TYPES
		}
		return sorted(asset for asset in assets if asset)

	@staticmethod
	def _matching_evidence(
		result: dict[str, Any],
		evidence_records: list[dict[str, Any]],
	) -> list[dict[str, Any]]:
		actual = str(result["actual"]).strip().casefold()
		limit = str(result["limit"]).strip().casefold()
		matched: list[dict[str, Any]] = []
		for record in evidence_records:
			if not isinstance(record, dict):
				raise ValueError("Each evidence record must be an object")
			text = " ".join(str(record.get(field, "")) for field in ("section", "subsection", "text"))
			normalized_text = re.sub(r"\s+", " ", text).casefold()
			if actual in normalized_text and limit in normalized_text:
				matched.append(dict(record))
		return matched

	@staticmethod
	def _evidence_for(
		result: dict[str, Any],
		evidence_records: list[dict[str, Any]],
	) -> list[dict[str, Any]]:
		"""Prefer evidence attached by an assurance engine, then match attributes."""
		supporting = result.get("supporting_evidence")
		if isinstance(supporting, list):
			return [dict(record) for record in supporting if isinstance(record, dict)]
		if "actual" in result and "limit" in result:
			return FindingBuilder._matching_evidence(result, evidence_records)
		assets = [str(asset).casefold() for asset in result.get("affected_assets", [])]
		return [
			dict(record)
			for record in evidence_records
			if any(asset in json.dumps(record, ensure_ascii=False).casefold() for asset in assets)
		]


def build_findings(
	evidence_records: list[dict[str, Any]],
	graph_context: dict[str, Any] | None,
	assurance_results: list[dict[str, Any]],
	output_path: str | Path = "outputs/findings/findings.json",
) -> list[EngineeringFinding]:
	"""Build and persist deterministic findings using the default builder."""
	return FindingBuilder().build_and_persist(
		evidence_records,
		graph_context,
		assurance_results,
		output_path,
	)
