import json

from src.entities.entity_extractor import RuleBasedEntityExtractor, process_all_documents


def test_extracts_configured_engineering_entities() -> None:
    chunks = [
        {
            "chunk_id": "doc:chunk:0001",
            "document_id": "DOC1",
            "text": "Unit-400 contains TSHH-401 and TIC-401. SIF-05 protects P-101.",
        },
        {
            "chunk_id": "doc:chunk:0002",
            "document_id": "DOC1",
            "text": "The pressure at P-101 is checked against the design capacity.",
        },
    ]

    entities = RuleBasedEntityExtractor().extract_entities(chunks)

    by_type = {(entity["entity_type"], entity["name"]): entity for entity in entities}
    assert ("UNIT", "Unit-400") in by_type
    assert ("CONTROL_LOOP", "TSHH-401") in by_type
    assert ("CONTROL_LOOP", "TIC-401") in by_type
    assert ("SIF", "SIF-05") in by_type
    assert ("EQUIPMENT", "P-101") in by_type
    assert ("PARAMETER", "Pass-1 Temperature") not in by_type
    assert ("PARAMETER", "pressure") in by_type
    assert by_type[("DOCUMENT", "DOC1")]["source_chunk"] == "doc:chunk:0001"
    assert len([entity for entity in entities if entity["name"] == "P-101"]) == 1


def test_requires_complete_hyphenated_tags_and_extracts_contextual_parameter() -> None:
    chunks = [{"chunk_id": "c1", "document_id": "DOC1", "text": "AT 50, PT 0, TSHH 620, Pass-1 temperature, AT-501 and FCV-101."}]

    entities = RuleBasedEntityExtractor().extract_entities(chunks)
    names = {entity["name"] for entity in entities}

    assert "AT 50" not in names
    assert "PT 0" not in names
    assert "TSHH 620" not in names
    assert "Pass-1 Temperature" in names
    assert "AT-501" in names
    assert "FCV-101" in names


def test_normalizes_unit_spacing_without_accepting_partial_instrument_tags() -> None:
    chunks = [{"chunk_id": "c1", "document_id": "DOC1", "text": "UNIT 400 includes PT 0 and PT-101."}]

    names = {entity["name"] for entity in RuleBasedEntityExtractor().extract_entities(chunks)}

    assert "Unit-400" in names
    assert "PT 0" not in names
    assert "PT-101" in names


def test_extracts_entities_from_chunk_hierarchy() -> None:
    chunks = [{"chunk_id": "c1", "document_id": "DOC2", "section": "UNIT 400 - CONVERTER", "text": "Pass 1 temperature"}]

    entities = RuleBasedEntityExtractor().extract_entities(chunks)

    assert {entity["name"] for entity in entities} >= {"Unit-400", "Pass-1 Temperature"}


def test_custom_patterns_and_output(tmp_path) -> None:
    chunks_dir = tmp_path / "chunks"
    output_dir = tmp_path / "entities"
    chunks_dir.mkdir()
    (chunks_dir / "sample_chunks.json").write_text(
        json.dumps([{"chunk_id": "c1", "document_id": "D1", "text": "SKID-7"}]),
        encoding="utf-8",
    )

    paths = RuleBasedEntityExtractor({"EQUIPMENT": r"\bSKID-\d+\b"}).process_all_documents(
        chunks_dir, output_dir
    )

    data = json.loads(paths[0].read_text(encoding="utf-8"))
    assert data[0]["name"] == "D1"
    assert data[1]["entity_id"] == "equipment:skid-7"


def test_module_entrypoint_accepts_directory(tmp_path) -> None:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "empty.json").write_text("[]", encoding="utf-8")

    assert len(process_all_documents(chunks_dir, tmp_path / "entities")) == 1