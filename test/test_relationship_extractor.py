import json

from src.relationships.relationship_extractor import RelationshipExtractor, process_all_documents


def test_extracts_rule_based_relationships() -> None:
    chunks = [{
        "chunk_id": "doc:chunk:0001",
        "document_id": "DOC1",
        "text": "Unit-400 has TIC-401 pressure at maximum 100 bar and normal 80 bar.",
    }]
    entities = [
        {"entity_id": "document:doc1", "entity_type": "DOCUMENT", "name": "DOC1", "source_chunk": "doc:chunk:0001"},
        {"entity_id": "unit:unit-400", "entity_type": "UNIT", "name": "Unit-400", "source_chunk": "doc:chunk:0001"},
        {"entity_id": "control_loop:tic-401", "entity_type": "CONTROL_LOOP", "name": "TIC-401", "source_chunk": "doc:chunk:0001"},
        {"entity_id": "parameter:pressure", "entity_type": "PARAMETER", "name": "pressure", "source_chunk": "doc:chunk:0001"},
    ]

    relationships = RelationshipExtractor().extract_relationships(chunks, entities)
    triples = {(item["source"], item["relationship"], item["target"]) for item in relationships}

    assert ("unit:unit-400", "APPEARS_IN", "document:doc1") in triples
    assert ("document:doc1", "DESCRIBES", "control_loop:tic-401") in triples
    assert ("control_loop:tic-401", "HAS_PARAMETER", "parameter:pressure") in triples
    assert ("parameter:pressure", "HAS_VALUE", "100 bar") in triples
    assert any(item["relationship"] == "HAS_LIMIT" for item in relationships)
    assert not any(item["relationship"] == "RELATED_TO" for item in relationships)


def test_process_all_documents_writes_relationships(tmp_path) -> None:
    chunks_dir = tmp_path / "chunks"
    entities_dir = tmp_path / "entities"
    output_dir = tmp_path / "relationships"
    chunks_dir.mkdir()
    entities_dir.mkdir()
    (chunks_dir / "sample_chunks.json").write_text(
        json.dumps([{"chunk_id": "c1", "document_id": "D1", "text": "P-101"}]),
        encoding="utf-8",
    )
    (entities_dir / "sample_chunks_entities.json").write_text(
        json.dumps([{"entity_id": "equipment:p-101", "entity_type": "EQUIPMENT", "name": "P-101", "source_chunk": "c1"}]),
        encoding="utf-8",
    )

    paths = process_all_documents(chunks_dir, entities_dir, output_dir)

    assert [path.name for path in paths] == ["sample_chunks_relationships.json"]
    assert json.loads(paths[0].read_text(encoding="utf-8"))[0]["relationship"] == "APPEARS_IN"


def test_repeated_entity_occurrence_gets_current_document_relationship() -> None:
    chunks = [{
        "chunk_id": "doc3:chunk:0001",
        "document_id": "DOC3",
        "text": "Unit-400 Pass 1 temperature is limited to 620°C and measured by TSHH-401.",
    }]
    entities = [
        {"entity_id": "unit:unit-400", "entity_type": "UNIT", "name": "Unit-400", "source_chunk": "other:chunk"},
        {"entity_id": "parameter:pass-1-temperature", "entity_type": "PARAMETER", "name": "Pass-1 Temperature", "source_chunk": "other:chunk"},
        {"entity_id": "control_loop:tshh-401", "entity_type": "CONTROL_LOOP", "name": "TSHH-401", "source_chunk": "other:chunk"},
    ]

    relationships = RelationshipExtractor().extract_relationships(chunks, entities)
    triples = {(item["source"], item["relationship"], item["target"]) for item in relationships}

    assert ("unit:unit-400", "HAS_PARAMETER", "parameter:pass-1-temperature") in triples
    assert ("parameter:pass-1-temperature", "HAS_LIMIT", "620°C") in triples
    assert ("unit:unit-400", "APPEARS_IN", "document:doc3") in triples