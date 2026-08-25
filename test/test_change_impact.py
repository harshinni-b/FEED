import json

import pytest

from src.assurance.change_impact import ChangeImpactAssuranceEngine
from src.knowledge.graph import PlantKnowledgeGraph


def test_analyzes_reachable_assets_documents_and_radius() -> None:
	graph = PlantKnowledgeGraph()
	graph.graph.add_node("loop:tshh-401", entity_type="CONTROL_LOOP", name="TSHH-401")
	graph.graph.add_node("sif:sif-05", entity_type="SIF", name="SIF-05")
	graph.graph.add_node("valve:xv-101", entity_type="VALVE", name="XV-101")
	graph.graph.add_node("document:doc8", entity_type="DOCUMENT", name="DOC8")
	graph.graph.add_edge("loop:tshh-401", "sif:sif-05", relationship="INITIATES")
	graph.graph.add_edge("sif:sif-05", "valve:xv-101", relationship="PROTECTS")
	graph.graph.add_edge("sif:sif-05", "document:doc8", relationship="APPEARS_IN")

	result = ChangeImpactAssuranceEngine(graph).analyze("TSHH-401", hops=2)

	assert result["entity"] == "TSHH-401"
	assert result["affected_assets"] == ["SIF-05", "XV-101"]
	assert result["affected_documents"] == ["DOC8"]
	assert result["impact_radius"]["by_hop"]["0"]["count"] == 1
	assert result["impact_radius"]["by_hop"]["2"]["count"] == 2


def test_builds_graph_from_json_and_validates_inputs(tmp_path) -> None:
	entities_path = tmp_path / "entities.json"
	relationships_path = tmp_path / "relationships.json"
	entities_path.write_text(json.dumps([{"entity_id": "equipment:whb-201", "entity_type": "EQUIPMENT", "name": "WHB-201"}]), encoding="utf-8")
	relationships_path.write_text("[]", encoding="utf-8")

	engine = ChangeImpactAssuranceEngine(None, entities_path, relationships_path)
	with pytest.raises(KeyError):
		engine.analyze("MISSING")
	with pytest.raises(ValueError):
		engine.analyze("WHB-201", hops=-1)

	assert engine.analyze("WHB-201")["affected_assets"] == []