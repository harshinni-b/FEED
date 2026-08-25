from src.assurance.connectivity import ConnectivityAssuranceEngine


def context_with_complete_chain() -> dict:
	return {
		"nodes": [
			{"entity_id": "loop:tshh-401", "entity_type": "CONTROL_LOOP", "name": "TSHH-401"},
			{"entity_id": "sif:sif-05", "entity_type": "SIF", "name": "SIF-05"},
			{"entity_id": "valve:xv-101", "entity_type": "VALVE", "name": "XV-101"},
		],
		"relationships": [
			{"source": "loop:tshh-401", "relationship": "INITIATES", "target": "sif:sif-05"},
			{"source": "sif:sif-05", "relationship": "PROTECTS", "target": "valve:xv-101"},
		],
	}


def test_complete_safety_chain_has_no_dependency_failures() -> None:
	findings = ConnectivityAssuranceEngine().validate(context_with_complete_chain())

	assert findings == []


def test_detects_broken_safety_chain_and_orphan() -> None:
	context = context_with_complete_chain()
	context["relationships"] = [{
		"source": "loop:tshh-401",
		"relationship": "INITIATES",
		"target": "sif:sif-05",
	}]
	context["nodes"].append({"entity_id": "equipment:p-999", "entity_type": "EQUIPMENT", "name": "P-999"})

	findings = ConnectivityAssuranceEngine().check(context)

	checks = {finding["check"] for finding in findings}
	assert "Broken Safety Chain" in checks
	assert "Missing Dependency" in checks
	assert "Orphan Entity" in checks
	assert all(finding["status"] == "FAIL" for finding in findings)


def test_detects_disconnected_component() -> None:
	context = context_with_complete_chain()
	context["nodes"].append({"entity_id": "unit:400", "entity_type": "UNIT", "name": "Unit-400"})
	context["relationships"].append({
		"source": "unit:400",
		"relationship": "HAS_PARAMETER",
		"target": "parameter:temperature",
	})

	findings = ConnectivityAssuranceEngine().validate(context)

	assert any(finding["check"] == "Disconnected Entity" for finding in findings)


def test_detects_missing_dependency_in_single_component() -> None:
	context = {"nodes": [{"entity_id": "loop:tshh-401", "entity_type": "CONTROL_LOOP", "name": "TSHH-401"}], "relationships": []}

	findings = ConnectivityAssuranceEngine().validate(context)

	assert {finding["check"] for finding in findings} == {"Orphan Entity", "Missing Dependency", "Broken Safety Chain"}


def test_reports_disconnected_multi_node_group() -> None:
	context = context_with_complete_chain()
	context["nodes"].extend([
		{"entity_id": "unit:400", "entity_type": "UNIT", "name": "Unit-400"},
		{"entity_id": "equipment:p-400", "entity_type": "EQUIPMENT", "name": "P-400"},
	])
	context["relationships"].append({"source": "unit:400", "relationship": "CONTROLS", "target": "equipment:p-400"})

	findings = ConnectivityAssuranceEngine().validate(context)

	disconnected = [finding for finding in findings if finding["check"] == "Disconnected Entity"]
	assert disconnected
	assert any(set(finding["affected_assets"]) == {"Unit-400", "P-400"} for finding in disconnected)