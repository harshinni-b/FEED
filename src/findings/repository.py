"""Local JSON persistence and engineer-review history for EDOCA findings."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SUPPORTED_STATUSES = frozenset({"OPEN", "REVIEW", "ACCEPTED", "REJECTED", "CLOSED"})
DEFAULT_FINDINGS_PATH = Path("outputs/findings/findings.json")


class FindingsRepository:
	"""Persist existing FindingBuilder records with optional engineer review metadata."""

	def __init__(self, path: str | Path = DEFAULT_FINDINGS_PATH) -> None:
		self.path = Path(path)

	def save_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
		"""Append a new FindingBuilder record, rejecting duplicate finding IDs."""
		if not isinstance(finding, dict):
			raise ValueError("finding must be an object")
		finding_id = self._finding_id(finding)
		findings = self._load()
		if any(item.get("finding_id") == finding_id for item in findings):
			raise ValueError(f"Finding already exists: {finding_id}")
		findings.append(copy.deepcopy(finding))
		self._write(findings)
		return copy.deepcopy(finding)

	def get_finding(self, finding_id: str) -> dict[str, Any] | None:
		"""Return one finding by ID, or None when it has not been stored."""
		for finding in self._load():
			if finding.get("finding_id") == finding_id:
				return copy.deepcopy(finding)
		return None

	def list_findings(
		self,
		status: str | None = None,
		severity: str | None = None,
	) -> list[dict[str, Any]]:
		"""List stored findings, optionally filtered by status and severity."""
		requested_status = self._normalise_status(status) if status is not None else None
		requested_severity = severity.strip().upper() if isinstance(severity, str) else None
		if requested_severity == "":
			raise ValueError("severity must be a non-empty string")
		return [
			copy.deepcopy(finding)
			for finding in self._load()
			if (requested_status is None or str(finding.get("status", "")).upper() == requested_status)
			and (requested_severity is None or str(finding.get("severity", "")).upper() == requested_severity)
		]

	def update_status(
		self,
		finding_id: str,
		status: str,
		reviewer: str | None = None,
		comment: str | None = None,
	) -> dict[str, Any]:
		"""Set a supported review status and append a timestamped review event."""
		updated_status = self._normalise_status(status)
		findings = self._load()
		finding = self._find_mutable(findings, finding_id)
		finding["status"] = updated_status
		self._history(finding).append(self._history_record(updated_status, reviewer, comment))
		self._write(findings)
		return copy.deepcopy(finding)

	def add_comment(self, finding_id: str, reviewer: str, comment: str) -> dict[str, Any]:
		"""Append a comment against the finding's current status without changing it."""
		if not isinstance(reviewer, str) or not reviewer.strip():
			raise ValueError("reviewer must be a non-empty string")
		if not isinstance(comment, str) or not comment.strip():
			raise ValueError("comment must be a non-empty string")
		findings = self._load()
		finding = self._find_mutable(findings, finding_id)
		current_status = self._normalise_status(str(finding.get("status", "OPEN")))
		self._history(finding).append(self._history_record(current_status, reviewer, comment))
		self._write(findings)
		return copy.deepcopy(finding)

	def get_review_history(self, finding_id: str) -> list[dict[str, Any]]:
		"""Return timestamped review events in their recorded order."""
		finding = self.get_finding(finding_id)
		if finding is None:
			raise KeyError(f"Finding not found: {finding_id}")
		history = finding.get("review_history", [])
		if not isinstance(history, list):
			raise ValueError(f"Invalid review history for finding: {finding_id}")
		return copy.deepcopy(history)

	def _load(self) -> list[dict[str, Any]]:
		if not self.path.exists():
			return []
		try:
			loaded = json.loads(self.path.read_text(encoding="utf-8"))
		except json.JSONDecodeError as exc:
			raise ValueError(f"Invalid findings JSON: {self.path}") from exc
		if not isinstance(loaded, list) or not all(isinstance(item, dict) for item in loaded):
			raise ValueError(f"Findings JSON must contain a list of objects: {self.path}")
		return loaded

	def _write(self, findings: list[dict[str, Any]]) -> None:
		"""Atomically replace the JSON file, preserving a valid prior file on interruption."""
		self.path.parent.mkdir(parents=True, exist_ok=True)
		file_descriptor, temporary_name = tempfile.mkstemp(
			prefix=f".{self.path.stem}-",
			suffix=".tmp",
			dir=self.path.parent,
		)
		try:
			with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
				json.dump(findings, handle, indent=2, ensure_ascii=False)
				handle.flush()
				os.fsync(handle.fileno())
			Path(temporary_name).replace(self.path)
		except Exception:
			Path(temporary_name).unlink(missing_ok=True)
			raise

	@staticmethod
	def _finding_id(finding: dict[str, Any]) -> str:
		finding_id = finding.get("finding_id")
		if not isinstance(finding_id, str) or not finding_id.strip():
			raise ValueError("finding must contain a non-empty finding_id")
		return finding_id

	@staticmethod
	def _normalise_status(status: str) -> str:
		if not isinstance(status, str) or not status.strip():
			raise ValueError("status must be a non-empty string")
		normalised = status.strip().upper()
		if normalised not in SUPPORTED_STATUSES:
			raise ValueError(f"Unsupported status: {status}")
		return normalised

	@staticmethod
	def _find_mutable(findings: list[dict[str, Any]], finding_id: str) -> dict[str, Any]:
		for finding in findings:
			if finding.get("finding_id") == finding_id:
				return finding
		raise KeyError(f"Finding not found: {finding_id}")

	@staticmethod
	def _history(finding: dict[str, Any]) -> list[dict[str, Any]]:
		history = finding.setdefault("review_history", [])
		if not isinstance(history, list):
			raise ValueError("review_history must be a list")
		return history

	@staticmethod
	def _history_record(status: str, reviewer: str | None, comment: str | None) -> dict[str, str | None]:
		return {
			"status": status,
			"reviewer": reviewer.strip() if isinstance(reviewer, str) and reviewer.strip() else None,
			"comment": comment.strip() if isinstance(comment, str) and comment.strip() else None,
			"timestamp": datetime.now(UTC).isoformat(),
		}


def save_finding(finding: dict[str, Any]) -> dict[str, Any]:
	"""Save a finding using the default MVP JSON location."""
	return FindingsRepository().save_finding(finding)


def get_finding(finding_id: str) -> dict[str, Any] | None:
	"""Get a finding from the default MVP JSON location."""
	return FindingsRepository().get_finding(finding_id)


def list_findings(status: str | None = None, severity: str | None = None) -> list[dict[str, Any]]:
	"""List findings from the default MVP JSON location."""
	return FindingsRepository().list_findings(status, severity)


def update_status(
	finding_id: str,
	status: str,
	reviewer: str | None = None,
	comment: str | None = None,
) -> dict[str, Any]:
	"""Update a finding status in the default MVP JSON location."""
	return FindingsRepository().update_status(finding_id, status, reviewer, comment)


def add_comment(finding_id: str, reviewer: str, comment: str) -> dict[str, Any]:
	"""Add a comment in the default MVP JSON location."""
	return FindingsRepository().add_comment(finding_id, reviewer, comment)


def get_review_history(finding_id: str) -> list[dict[str, Any]]:
	"""Get review history from the default MVP JSON location."""
	return FindingsRepository().get_review_history(finding_id)
