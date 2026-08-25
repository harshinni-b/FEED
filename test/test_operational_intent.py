from src.assurance.operational_intent import OperationalIntentAssuranceEngine


def test_detects_operating_limit_conflict() -> None:
	evidence = [{"document_id": "DOC2", "section": "UNIT 400", "text": "Surge Mode operating temperature is 621°C; configured limit is 620°C."}]

	findings = OperationalIntentAssuranceEngine().validate(evidence)

	assert findings[0]["check"] == "Operating Value vs Limit"
	assert findings[0]["status"] == "FAIL"
	assert "621°C" in findings[0]["finding"]


def test_detects_inconsistent_intent_across_documents() -> None:
	evidence = [
		{"document_id": "DOC1", "text": "Normal Mode operating flow is 100 kg/h."},
		{"document_id": "DOC2", "text": "Normal Mode operating flow is 120 kg/h."},
	]

	findings = OperationalIntentAssuranceEngine().check(evidence)

	assert any(finding["check"] == "Inconsistent Engineering Intent" for finding in findings)
	assert all(finding["supporting_evidence"] for finding in findings)


def test_detects_conflicting_operating_scenarios() -> None:
	evidence = [
		{"document_id": "DOC1", "text": "Normal Mode operating flow is 100 kg/h."},
		{"document_id": "DOC2", "text": "Surge Mode operating flow is 80 kg/h."},
		{"document_id": "DOC3", "text": "Emergency Surge operating flow is 70 kg/h."},
	]

	findings = OperationalIntentAssuranceEngine().validate(evidence, {"nodes": []})

	assert any(finding["check"] == "Conflicting Operating Scenarios" for finding in findings)