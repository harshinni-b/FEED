"""Deterministic cross-document operational-intent assurance checks."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class OperationalIntentFinding(TypedDict):
	"""Result of one deterministic operational-intent comparison."""

	check: str
	status: str
	severity: str
	finding: str
	supporting_evidence: list[dict[str, Any]]


@dataclass(frozen=True)
class _Measurement:
	"""A scenario-labelled numerical measurement from one evidence record."""

	scenario: str
	metric: str
	value: float
	display: str
	unit: str
	record_index: int


class OperationalIntentAssuranceEngine:
	"""Compare explicit limits and operating intent across evidence records."""

	MEASUREMENT_PATTERN = re.compile(
		r"(?<![A-Za-z])(?P<number>[-+]?\d[\d,]*(?:\.\d+)?)\s*"
		r"(?P<unit>%|t/d|kg/h|Nm[³3]/h|m[³3]/h|kW|barg?|bar|°C|℃|C|mm|m|yr)\b",
		re.IGNORECASE,
	)
	SCENARIO_PATTERN = re.compile(
		r"\b(emergency\s+surge|surge(?:\s+mode)?|normal(?:\s+mode)?)\b",
		re.IGNORECASE,
	)
	LIMIT_PATTERN = re.compile(
		r"\b(?:limit|maximum|max\.?|minimum|min\.?|upper|lower|rated|design|allowable|trip|cutoff)\b",
		re.IGNORECASE,
	)
	OPERATING_PATTERN = re.compile(
		r"\b(?:operating|actual|measured|value|reading|normal|surge|emergency)\b",
		re.IGNORECASE,
	)
	METRICS = (
		"temperature",
		"pressure",
		"flow",
		"level",
		"power",
		"capacity",
		"concentration",
	)

	def validate(
		self,
		evidence: list[dict[str, Any]],
		graph_context: dict[str, Any] | None = None,
	) -> list[OperationalIntentFinding]:
		"""Return deterministic findings from evidence and optional graph context."""
		if not isinstance(evidence, list):
			raise ValueError("evidence must be a list")
		if graph_context is not None and not isinstance(graph_context, dict):
			raise ValueError("graph_context must be an object or None")
		measurements: list[_Measurement] = []
		for index, record in enumerate(evidence):
			if not isinstance(record, dict):
				raise ValueError("Each evidence record must be an object")
			measurements.extend(self._extract_measurements(record, index))

		findings: list[OperationalIntentFinding] = []
		findings.extend(self._limit_conflicts(evidence, measurements))
		findings.extend(self._intent_conflicts(evidence, measurements))
		findings.extend(self._scenario_conflicts(evidence, measurements))
		logger.info("Completed operational intent assurance with %d findings", len(findings))
		return findings

	def check(
		self,
		evidence: list[dict[str, Any]],
		graph_context: dict[str, Any] | None = None,
	) -> list[OperationalIntentFinding]:
		"""Alias for validate for generic assurance orchestration."""
		return self.validate(evidence, graph_context)

	def _extract_measurements(self, record: dict[str, Any], record_index: int) -> list[_Measurement]:
		text = " ".join(
			str(record.get(field, ""))
			for field in ("section", "subsection", "text")
			if record.get(field)
		)
		matches = list(self.MEASUREMENT_PATTERN.finditer(text))
		result: list[_Measurement] = []
		for position, match in enumerate(matches):
			context = text[max(0, match.start() - 100) : min(len(text), match.end() + 40)]
			if not self.OPERATING_PATTERN.search(context):
				continue
			scenario_match = self.SCENARIO_PATTERN.search(context)
			if not scenario_match:
				continue
			metric = self._metric(context)
			result.append(
				_Measurement(
					scenario=self._scenario(scenario_match.group(1)),
					metric=metric,
					value=float(match.group("number").replace(",", "")),
					display=match.group(0).strip().replace("℃", "°C"),
					unit=self._normalize_unit(match.group("unit")),
					record_index=record_index,
				)
			)
		return result

	def _limit_conflicts(
		self,
		evidence: list[dict[str, Any]],
		measurements: list[_Measurement],
	) -> list[OperationalIntentFinding]:
		findings: list[OperationalIntentFinding] = []
		for actual in measurements:
			text = self._record_text(evidence[actual.record_index])
			limits = []
			for match in self.MEASUREMENT_PATTERN.finditer(text):
				context = text[max(0, match.start() - 80) : match.end() + 20]
				if self.LIMIT_PATTERN.search(context) and self._normalize_unit(match.group("unit")) == actual.unit:
					limits.append((float(match.group("number").replace(",", "")), match.group(0).strip()))
			for limit_value, limit_display in limits:
				if actual.value > limit_value:
					findings.append({
						"check": "Operating Value vs Limit",
						"status": "FAIL",
						"severity": "HIGH",
						"finding": f"{actual.scenario} {actual.metric} operating value {actual.display} exceeds limit {limit_display}",
						"supporting_evidence": [dict(evidence[actual.record_index])],
					})
		return findings

	def _intent_conflicts(
		self,
		evidence: list[dict[str, Any]],
		measurements: list[_Measurement],
	) -> list[OperationalIntentFinding]:
		groups: dict[tuple[str, str, str], list[_Measurement]] = defaultdict(list)
		for measurement in measurements:
			groups[(measurement.scenario, measurement.metric, measurement.unit)].append(measurement)
		findings: list[OperationalIntentFinding] = []
		for (scenario, metric, unit), values in groups.items():
			unique_values = {measurement.value for measurement in values}
			if len(unique_values) <= 1 or len({measurement.record_index for measurement in values}) < 2:
				continue
			records = [dict(evidence[index]) for index in sorted({item.record_index for item in values})]
			findings.append({
				"check": "Inconsistent Engineering Intent",
				"status": "FAIL",
				"severity": "MEDIUM",
				"finding": f"{scenario} {metric} has conflicting {unit} values across documents",
				"supporting_evidence": records,
			})
		return findings

	def _scenario_conflicts(
		self,
		evidence: list[dict[str, Any]],
		measurements: list[_Measurement],
	) -> list[OperationalIntentFinding]:
		groups: dict[tuple[str, str], dict[str, _Measurement]] = defaultdict(dict)
		for measurement in measurements:
			groups[(measurement.metric, measurement.unit)].setdefault(measurement.scenario, measurement)
		findings: list[OperationalIntentFinding] = []
		order = {"Normal Mode": 0, "Surge Mode": 1, "Emergency Surge": 2}
		for (metric, unit), scenarios in groups.items():
			ordered = [scenarios[name] for name in order if name in scenarios]
			for previous, current in zip(ordered, ordered[1:]):
				if current.value < previous.value:
					findings.append({
						"check": "Conflicting Operating Scenarios",
						"status": "FAIL",
						"severity": "MEDIUM",
						"finding": f"{current.scenario} {metric} value {current.display} is below {previous.scenario} value {previous.display}",
						"supporting_evidence": [dict(evidence[previous.record_index]), dict(evidence[current.record_index])],
					})
		return findings

	@staticmethod
	def _record_text(record: dict[str, Any]) -> str:
		return " ".join(str(record.get(field, "")) for field in ("section", "subsection", "text") if record.get(field))

	@staticmethod
	def _metric(context: str) -> str:
		lower = context.casefold()
		return next((metric for metric in OperationalIntentAssuranceEngine.METRICS if metric in lower), "attribute")

	@staticmethod
	def _scenario(value: str) -> str:
		value = re.sub(r"\s+", " ", value.strip()).casefold()
		return "Emergency Surge" if value == "emergency surge" else "Surge Mode" if value.startswith("surge") else "Normal Mode"

	@staticmethod
	def _normalize_unit(unit: str) -> str:
		value = unit.casefold().replace("℃", "°c")
		return "°c" if value == "c" else value
