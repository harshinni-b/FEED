import json

import pytest

from src.findings.repository import FindingsRepository


def finding() -> dict:
	return {
		"finding_id": "F-001",
		"title": "Pass 1 temperature limit",
		"severity": "HIGH",
		"status": "OPEN",
		"affected_assets": ["R-401"],
		"root_cause": "Temperature exceeds limit",
		"reasoning": "Evidence comparison failed.",
		"evidence": [{"chunk_id": "DOC8:001"}],
		"recommendation": "Review SIF-05.",
		"confidence": 0.98,
	}


def test_save_get_and_filter_findings_without_changing_builder_fields(tmp_path) -> None:
	repository = FindingsRepository(tmp_path / "outputs" / "findings" / "findings.json")
	saved = repository.save_finding(finding())

	assert saved == finding()
	assert repository.get_finding("F-001") == finding()
	assert repository.list_findings(status="open") == [finding()]
	assert repository.list_findings(severity="high") == [finding()]
	assert json.loads(repository.path.read_text(encoding="utf-8")) == [finding()]


def test_duplicate_finding_ids_are_rejected(tmp_path) -> None:
	repository = FindingsRepository(tmp_path / "findings.json")
	repository.save_finding(finding())

	with pytest.raises(ValueError, match="Finding already exists"):
		repository.save_finding(finding())


def test_status_update_records_timestamped_review_history(tmp_path) -> None:
	repository = FindingsRepository(tmp_path / "findings.json")
	repository.save_finding(finding())

	updated = repository.update_status("F-001", "accepted", "A. Engineer", "Approved for MOC action")
	history = repository.get_review_history("F-001")

	assert updated["status"] == "ACCEPTED"
	assert history[0]["status"] == "ACCEPTED"
	assert history[0]["reviewer"] == "A. Engineer"
	assert history[0]["comment"] == "Approved for MOC action"
	assert history[0]["timestamp"].endswith("+00:00")


def test_comment_uses_current_status_and_atomic_write_leaves_no_temporary_file(tmp_path) -> None:
	repository = FindingsRepository(tmp_path / "findings.json")
	repository.save_finding(finding())
	repository.update_status("F-001", "REVIEW")
	repository.add_comment("F-001", "Reviewer", "Check updated SRS wording.")

	history = repository.get_review_history("F-001")
	assert history[-1]["status"] == "REVIEW"
	assert history[-1]["reviewer"] == "Reviewer"
	assert history[-1]["comment"] == "Check updated SRS wording."
	assert not list(tmp_path.glob(".*.tmp"))


def test_invalid_status_and_unknown_finding_are_rejected(tmp_path) -> None:
	repository = FindingsRepository(tmp_path / "findings.json")

	with pytest.raises(ValueError, match="Unsupported status"):
		repository.list_findings(status="PENDING")
	with pytest.raises(KeyError, match="Finding not found"):
		repository.update_status("F-missing", "OPEN")
