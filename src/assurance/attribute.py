"""Deterministic numerical assurance checks for engineering evidence."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class AssuranceFinding(TypedDict):
	"""Result of comparing an operating value with an engineering limit."""

	check: str
	status: str
	severity: str
	actual: str
	limit: str
	finding: str


@dataclass(frozen=True)
class _Measurement:
	"""A numeric measurement and its position in evidence text."""

	value: float
	display: str
	unit: str
	position: int
	is_limit: bool
	is_lower_bound: bool


class AttributeAssuranceEngine:
	"""Compare operating measurements with explicit numerical limits."""

	MEASUREMENT_PATTERN = re.compile(
		r"(?<![A-Za-z])(?P<number>[-+]?\d[\d,]*(?:\.\d+)?)\s*"
		r"(?P<unit>%|t/d|kg/h|Nm[³3]/h|m[³3]/h|kW|barg?|bar|°C|℃|C|mm|m|yr)\b",
		re.IGNORECASE,
	)
	LIMIT_WORDS = re.compile(
		r"\b(?:limit|maximum|max\.?|minimum|min\.?|upper|lower|rated|design|allowable|trip|cutoff)\b",
		re.IGNORECASE,
	)
	OPERATING_WORDS = re.compile(
		r"\b(?:operating|actual|measured|value|surge|normal|observed|reading)\b",
		re.IGNORECASE,
	)
	LOWER_BOUND_WORDS = re.compile(
		r"\b(?:minimum|min\.?|lower|at least|greater than)\b|≥|>=|>",
		re.IGNORECASE,
	)

	def validate(self, evidence_records: list[dict[str, Any]]) -> list[AssuranceFinding]:
		"""Return deterministic findings for explicit limit/value comparisons."""
		findings: list[AssuranceFinding] = []
		for record in evidence_records:
			if not isinstance(record, dict):
				raise ValueError("Each evidence record must be an object")
			text = " ".join(
				str(record.get(field, ""))
				for field in ("section", "subsection", "text")
				if record.get(field)
			)
			measurements = self._extract_measurements(text)
			limits = [measurement for measurement in measurements if measurement.is_limit]
			actuals = [measurement for measurement in measurements if not measurement.is_limit]
			for actual in actuals:
				candidates = [
					limit
					for limit in limits
					if limit.unit == actual.unit
					and abs(limit.position - actual.position) <= 120
				]
				if not candidates:
					continue
				limit = min(candidates, key=lambda item: abs(item.position - actual.position))
				violates = (
					actual.value < limit.value
					if limit.is_lower_bound
					else actual.value > limit.value
				)
				check = self._check_name(
					self._comparison_context(text, actual, limit),
					actual.unit,
				)
				findings.append(
					{
						"check": check,
						"status": "FAIL" if violates else "PASS",
						"severity": "HIGH" if violates else "INFO",
						"actual": actual.display,
						"limit": limit.display,
						"finding": (
							"Operating value exceeds configured limit"
							if violates and not limit.is_lower_bound
							else "Operating value is below configured minimum"
							if violates
							else "Operating value is within configured limit"
						),
					}
				)
		logger.info("Completed attribute assurance with %d findings", len(findings))
		return findings

	def check(self, evidence_records: list[dict[str, Any]]) -> list[AssuranceFinding]:
		"""Alias for validate, useful as a generic assurance-engine interface."""
		return self.validate(evidence_records)

	def _extract_measurements(self, text: str) -> list[_Measurement]:
		measurements: list[_Measurement] = []
		for match in self.MEASUREMENT_PATTERN.finditer(text):
			value = float(match.group("number").replace(",", ""))
			context = self._local_context(text, match.start(), match.end())
			is_limit = bool(self.LIMIT_WORDS.search(context))
			is_operating = bool(self.OPERATING_WORDS.search(context))
			if not is_limit and not is_operating:
				continue
			measurements.append(
				_Measurement(
					value=value,
					display=match.group(0).strip().replace("℃", "°C"),
					unit=self._normalize_unit(match.group("unit")),
					position=match.start(),
					is_limit=is_limit and not is_operating,
					is_lower_bound=bool(self.LOWER_BOUND_WORDS.search(context)),
				)
			)
		return measurements

	@staticmethod
	def _local_context(text: str, start: int, end: int) -> str:
		"""Return the sentence or table clause containing one measurement."""
		left = max(text.rfind(marker, 0, start) for marker in (".", ";", "\n"))
		right_candidates = [text.find(marker, end) for marker in (".", ";", "\n")]
		right_candidates = [position for position in right_candidates if position >= 0]
		right = min(right_candidates, default=len(text))
		return text[left + 1 : right]

	@classmethod
	def _comparison_context(
		cls,
		text: str,
		actual: _Measurement,
		limit: _Measurement,
	) -> str:
		"""Return only the source clauses containing the paired measurements."""
		contexts = (
			cls._local_context(text, limit.position, limit.position + len(limit.display)),
			cls._local_context(text, actual.position, actual.position + len(actual.display)),
		)
		return " ".join(dict.fromkeys(context.strip() for context in contexts if context.strip()))

	@staticmethod
	def _normalize_unit(unit: str) -> str:
		normalized = unit.casefold().replace("℃", "°c")
		return "°c" if normalized == "c" else normalized

	@staticmethod
	def _check_name(text: str, unit: str) -> str:
		terms = (
			("temperature", "Temperature Limit"),
			("pressure", "Pressure Limit"),
			("flow", "Flow Limit"),
			("level", "Level Limit"),
			("power", "Power Limit"),
		)
		prefix = text.casefold()
		for term, check in terms:
			if term in prefix:
				return check
		return f"{unit.upper()} Limit"
