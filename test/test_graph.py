import json

from src.knowledge.graph import PlantKnowledgeGraph


def graph_inputs() -> tuple[list[dict], list[dict]]:
    entities = [
        {"entity_id": "equipment:p-101", "entity_type": "EQUIPMENT", "name": "P-101", "source_chunk": "c1"},
        {"entity_id": "instrument:tic-401", "entity_type": "INSTRUMENT", "name": "TIC-401", "source_chunk": "c1"},
        {"entity_id": "document:doc1", "entity_type": "DOCUMENT", "name": "DOC1", "source_chunk": "c1"},
    ]
    relationships = [
        {"source": "equipment:p-101", "relationship": "CONTROLS", "target": "instrument:tic-401", "document": "DOC1"},
        {"source": "instrument:tic-401", "relationship": "CONNECTED_TO", "target": "equipment:p-101", "document": "DOC1"},
        {"source": "equipment:p-101", "relationship": "HAS_VALUE", "target": "100 bar", "document": "DOC1"},
    ]
    return entities, relationships


def test_build_graph_and_query_context(tmp_path) -> None:
    entities, relationships = graph_inputs()
    entities_path = tmp_path / "entities.json"
    relationships_path = tmp_path / "relationships.json"
    entities_path.write_text(json.dumps(entities), encoding="utf-8")
    relationships_path.write_text(json.dumps(relationships), encoding="utf-8")

    graph = PlantKnowledgeGraph()
    graph.build_graph(entities_path, relationships_path)

    assert graph.get_entity("equipment:p-101")["entity_type"] == "EQUIPMENT"
    assert {node["entity_id"] for node in graph.get_neighbors("equipment:p-101")} == {"instrument:tic-401", "100 bar"}
    context = graph.get_graph_context("equipment:p-101")
    assert len(context["nodes"]) == 3
    assert any(item["relationship"] == "CONTROLS" for item in context["relationships"])


def test_build_graph_from_json_and_export(tmp_path) -> None:
    entities, relationships = graph_inputs()
    entities_path = tmp_path / "entities.json"
    relationships_path = tmp_path / "relationships.json"
    export_path = tmp_path / "graph.json"
    entities_path.write_text(json.dumps(entities), encoding="utf-8")
    relationships_path.write_text(json.dumps(relationships), encoding="utf-8")

    graph = PlantKnowledgeGraph()
    graph.build_graph(entities_path, relationships_path)
    output = graph.export_graph_json(export_path)

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert len(exported["nodes"]) == 4
    assert len(exported["links"]) == 3