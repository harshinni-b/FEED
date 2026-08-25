import json

from src.findings.finding_builder import FindingBuilder


def inputs() -> tuple[list[dict], dict, list[dict]]:
	return (
		[{
			"chunk_id": "DOC2:chunk:0010",
			"document_id": "DOC2",
			"section": "UNIT 400 - CONVERTER",
			"subsection": "Pass 1 Temperature",
			"text": "Configured limit is 620°C; operating value is 621°C.",
			"source_type": "table",
		}],
		{"nodes": [
			{"entity_id": "unit:unit-400", "entity_type": "UNIT", "name": "Unit-400"},
			{"entity_id": "parameter:temperature", "entity_type": "PARAMETER", "name": "temperature"},
		]},
		[{
			"check": "Temperature Limit",
			"status": "FAIL",
			"severity": "HIGH",
			"actual": "621°C",
			"limit": "620°C",
			"finding": "Operating value exceeds configured limit",
		}],
	)


def test_builds_standardized_deterministic_finding(tmp_path) -> None:
	evidence, context, assurance = inputs()
	builder = FindingBuilder()

	first = builder.build(evidence, context, assurance)
	second = builder.build(evidence, context, assurance)
	path = builder.persist(first, tmp_path / "outputs" / "findings.json")

	assert first == second
	assert first[0]["finding_id"].startswith("F-")
	assert first[0]["status"] == "OPEN"
	assert first[0]["affected_assets"] == ["Unit-400"]
	assert first[0]["evidence"] == evidence
	assert first[0]["confidence"] == 1.0
	assert json.loads(path.read_text(encoding="utf-8")) == first


def test_ignores_pass_and_deduplicates_failures() -> None:
	evidence, context, assurance = inputs()
	assurance.extend([dict(assurance[0]), {**assurance[0], "status": "PASS"}])

	findings = FindingBuilder().build(evidence, context, assurance)

	assert len(findings) == 1


def test_supports_non_attribute_assurance_results_and_gpt_merge() -> None:
	evidence, context, _ = inputs()
	assurance = [
		{"check": "Broken Safety Chain", "status": "FAIL", "severity": "HIGH", "affected_assets": ["Unit-400"], "finding": "Safety chain is incomplete", "supporting_evidence": evidence},
		{"check": "Intent Conflict", "status": "FAIL", "severity": "MEDIUM", "finding": "Operating intent conflicts", "supporting_evidence": evidence},
		{"entity": "Unit-400", "affected_assets": ["Unit-400"], "affected_documents": ["DOC2"], "impact_radius": {"max_hops": 2}},
	]
	reasoning = {
		"finding_title": "Unit 400 assurance issue",
		"severity": "HIGH",
		"confidence": 0.9,
		"root_cause": "Supplied assurance detected an issue.",
		"reasoning": "The supplied assurance result is a failure.",
		"recommendation": "Review the affected asset.",
		"affected_assets": ["Unit-400"],
	}

	findings = FindingBuilder().build(evidence, context, assurance, reasoning)

	assert len(findings) == 3
	evidence_finding = next(finding for finding in findings if finding["evidence"])
	assert evidence_finding["title"] in {"Broken Safety Chain", "Intent Conflict"}
	assert evidence_finding["reasoning"] == reasoning["reasoning"]
	assert evidence_finding["evidence"] == evidence
	assert all(finding["severity"] in {"HIGH", "MEDIUM"} for finding in findings)


def test_query_aware_ranking_uses_generic_parameter_and_entity_context() -> None:
	evidence = [
		{"chunk_id": "A", "section": "Compressor K-17", "subsection": "Flow", "text": "Flow actual 88 kg/h; maximum 75 kg/h."},
		{"chunk_id": "B", "section": "Compressor K-17", "subsection": "Discharge Pressure", "text": "Discharge pressure actual 14.7 bar; maximum 12.2 bar."},
	]
	assurance = [
		{"check": "Flow Limit", "status": "FAIL", "severity": "HIGH", "actual": "88 kg/h", "limit": "75 kg/h", "finding": "Operating value exceeds configured limit"},
		{"check": "Pressure Limit", "status": "FAIL", "severity": "HIGH", "actual": "14.7 bar", "limit": "12.2 bar", "finding": "Operating value exceeds configured limit"},
	]

	findings = FindingBuilder().build(evidence, {"nodes": []}, assurance, query="Review K-17 discharge pressure")

	assert findings[0]["title"] == "Pressure Limit"
	assert len(findings) == 2


def test_distinct_assurance_checks_keep_deterministic_identity_and_provenance() -> None:
	evidence = [{"chunk_id": "source-7", "document_id": "DOC-7", "text": "Authoritative source text"}]
	assurance = [
		{"check": "Pressure Limit", "status": "FAIL", "severity": "HIGH", "actual": "14.7 bar", "limit": "12.2 bar", "finding": "Pressure exceeds its configured limit", "supporting_evidence": evidence},
		{"check": "Broken Dependency", "status": "FAIL", "severity": "MEDIUM", "affected_assets": ["K-17"], "finding": "Required dependency is absent", "supporting_evidence": evidence},
	]
	reasoning = {
		"finding_title": "Must not replace deterministic identity",
		"per_assurance_result": [
			{"assurance_index": 0, "reasoning": {"reasoning": "Pressure explanation", "recommendation": "Review pressure source", "confidence": 0.8}},
			{"assurance_index": 1, "reasoning": {"reasoning": "Dependency explanation", "recommendation": "Review dependency source", "confidence": 0.7}},
		],
	}

	findings = FindingBuilder().build(evidence, {"nodes": []}, assurance, reasoning)
	by_title = {finding["title"]: finding for finding in findings}

	assert set(by_title) == {"Pressure Limit", "Broken Dependency"}
	assert by_title["Pressure Limit"]["root_cause"] == "Pressure exceeds its configured limit"
	assert by_title["Broken Dependency"]["root_cause"] == "Required dependency is absent"
	assert by_title["Pressure Limit"]["reasoning"] == "Pressure explanation"
	assert by_title["Broken Dependency"]["reasoning"] == "Dependency explanation"
	assert all(finding["evidence"] == evidence for finding in findings)
