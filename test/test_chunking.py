import json

from src.chunking.engineering_chunker import EngineeringChunker, process_all_documents


def extracted_document() -> dict:
    return {
        "filename": "DOC1_Basis_of_Design.docx",
        "sections": [
            {
                "heading": {"text": "1. Design Basis", "level": 1},
                "level": 1,
                "paragraphs": [],
                "tables": [],
            },
            {
                "heading": {"text": "1.1 Capacity", "level": 2},
                "level": 2,
                "paragraphs": [{"text": "Plant capacity is 100 t/d.", "style": "Normal"}],
                "tables": [{"index": 0, "rows": [["Tag", "Value"], ["P-101", "100 t/d"]]}],
            },
        ],
    }


def test_chunk_document_preserves_engineering_hierarchy() -> None:
    chunks = EngineeringChunker().chunk_document(extracted_document())

    assert len(chunks) == 2
    assert chunks[0]["source_type"] == "paragraph"
    assert chunks[0]["section"] == "1. Design Basis"
    assert chunks[0]["subsection"] == "1.1 Capacity"
    assert chunks[1]["source_type"] == "table"
    assert chunks[1]["metadata"]["rows"] == [["Tag", "Value"], ["P-101", "100 t/d"]]
    assert chunks[1]["text"] == "Tag | Value\nP-101 | 100 t/d"


def test_process_all_documents_writes_chunk_files(tmp_path) -> None:
    extracted = tmp_path / "extracted"
    output = tmp_path / "chunks"
    extracted.mkdir()
    (extracted / "DOC1.json").write_text(json.dumps(extracted_document()), encoding="utf-8")

    paths = process_all_documents(extracted, output)

    assert [path.name for path in paths] == ["DOC1_chunks.json"]
    assert len(json.loads(paths[0].read_text(encoding="utf-8"))) == 2