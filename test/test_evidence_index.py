import json

from src.knowledge.evidence_index import EvidenceIndex, index_chunks


def fixture_chunks() -> list[dict[str, str]]:
    return [
        {
            "chunk_id": "DOC3:chunk:0001",
            "document_id": "DOC3",
            "section": "UNIT 400 - CONVERTER",
            "subsection": "Pass 1 Temperature",
            "text": "Unit-400 temperature limit is 620°C; TSHH-401 protects the pass.",
            "source_type": "paragraph",
            "metadata": {"style": "Normal"},
        },
        {
            "chunk_id": "DOC8:chunk:0002",
            "document_id": "DOC8",
            "section": "Safety Instrumented Functions",
            "subsection": "SIF-05",
            "text": "SIF-05 trip record for TSHH-401.",
            "source_type": "table",
            "metadata": {"rows": [["SIF-05", "TSHH-401"]]},
        },
    ]


def test_index_and_search_methods(tmp_path) -> None:
    input_dir = tmp_path / "chunks"
    output_dir = tmp_path / "evidence"
    input_dir.mkdir()
    (input_dir / "chunks.json").write_text(json.dumps(fixture_chunks()), encoding="utf-8")
    index = EvidenceIndex()

    records = index.index_chunks(input_dir, output_dir)

    assert len(records) == 2
    assert set(records[0]) == {"chunk_id", "document_id", "document_type", "section", "subsection", "text", "source_type"}
    assert len(index.search_by_keyword("temperature limit")) == 1
    assert len(index.search_by_entity("TSHH-401")) == 2
    assert len(index.search_by_document("DOC8")) == 1
    assert len(index.search_by_section("converter")) == 1
    assert len(index.search_by_unit("Unit-400")) == 1
    assert len(index.search_by_sif("SIF-05")) == 1
    assert json.loads((output_dir / "index.json").read_text(encoding="utf-8")) == records


def test_module_entrypoint_indexes_real_shape(tmp_path) -> None:
    input_dir = tmp_path / "chunks"
    input_dir.mkdir()
    (input_dir / "empty.json").write_text("[]", encoding="utf-8")

    assert index_chunks(input_dir, tmp_path / "evidence") == []