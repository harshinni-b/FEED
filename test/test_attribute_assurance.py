from src.assurance.attribute import AttributeAssuranceEngine


def test_fails_when_operating_temperature_exceeds_limit() -> None:
    evidence = [
        {
            "chunk_id": "DOC2:chunk:0010",
            "document_id": "DOC2",
            "section": "UNIT 400 - CONVERTER",
            "subsection": "Pass 1 Temperature",
            "text": "Configured limit is 620°C; operating value is 621°C.",
            "source_type": "table",
        }
    ]

    findings = AttributeAssuranceEngine().validate(evidence)

    assert findings == [
        {
            "check": "Temperature Limit",
            "status": "FAIL",
            "severity": "HIGH",
            "actual": "621°C",
            "limit": "620°C",
            "finding": "Operating value exceeds configured limit",
        }
    ]


def test_passes_when_operating_value_is_within_limit() -> None:
    evidence = [{"text": "Maximum design temperature limit 620°C; actual operating value 610°C."}]

    findings = AttributeAssuranceEngine().check(evidence)

    assert findings[0]["status"] == "PASS"
    assert findings[0]["severity"] == "INFO"


def test_detects_lower_bound_violation_and_ignores_unclassified_numbers() -> None:
    evidence = [{"text": "Minimum flow is 100 kg/h; measured operating flow is 80 kg/h. Revision 4."}]

    findings = AttributeAssuranceEngine().validate(evidence)

    assert len(findings) == 1
    assert findings[0]["status"] == "FAIL"
    assert findings[0]["finding"] == "Operating value is below configured minimum"


def test_infers_each_check_from_its_measurement_clauses_in_one_table() -> None:
    evidence = [{
        "document_id": "MULTI-PARAMETER-DOCUMENT",
        "section": "Design envelope.",
        "source_type": "table",
        "text": "\n".join([
            "Temperature maximum limit 455 °C; actual operating temperature 462 °C.",
            "Pressure maximum limit 18 bar; measured operating pressure 17 bar.",
            "Level maximum limit 8 m; actual operating level 9 m.",
            "Flow minimum limit 105 kg/h; measured operating flow 93 kg/h.",
        ]),
    }]

    findings = AttributeAssuranceEngine().validate(evidence)
    checks_by_actual = {finding["actual"]: finding["check"] for finding in findings}

    assert checks_by_actual == {
        "462 °C": "Temperature Limit",
        "17 bar": "Pressure Limit",
        "9 m": "Level Limit",
        "93 kg/h": "Flow Limit",
    }
