"""Verify the EDOCA PlantKnowledgeGraph against processed graph inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.knowledge.graph import PlantKnowledgeGraph

TARGETS = ("Pass-1", "WHB-201", "TK-101A")


def find_entity_id(graph: PlantKnowledgeGraph, name: str) -> str | None:
    """Find a graph node ID by case-insensitive entity name."""
    for entity_id, attributes in graph.graph.nodes(data=True):
        if str(attributes.get("name", "")).casefold() == name.casefold():
            return str(entity_id)
    return None


def print_graph_context(graph: PlantKnowledgeGraph, name: str) -> bool:
    """Print neighbors and relationships for one named graph entity."""
    entity_id = find_entity_id(graph, name)
    print(f"\n{name}")
    if entity_id is None:
        print("  NOT FOUND")
        return False

    context = graph.get_graph_context(entity_id)
    for relationship in context["relationships"]:
        source = graph.get_entity(relationship["source"]) or {}
        target = graph.get_entity(relationship["target"]) or {}
        source_name = source.get("name", relationship["source"])
        target_name = target.get("name", relationship["target"])
        print(
            f"  {source_name} --{relationship['relationship']}--> {target_name}"
        )

    if not context["relationships"]:
        print("  No neighboring relationships")
    return True


def main() -> int:
    """Build the plant graph and print verification results."""
    graph = PlantKnowledgeGraph()
    graph.build_graph(
        Path("data/processed/entities"),
        Path("data/processed/relationships"),
    )

    node_count = graph.graph.number_of_nodes()
    edge_count = graph.graph.number_of_edges()
    print("======== GRAPH SUMMARY ========")
    print(f"Total Nodes: {node_count}")
    print(f"Total Edges: {edge_count}")

    print("\n======== GRAPH CONTEXT ========")
    targets_found = all(print_graph_context(graph, target) for target in TARGETS)

    print("\n======== FIRST 20 GRAPH EDGES ========")
    for index, (source, target, attributes) in enumerate(
        graph.graph.edges(data=True),
        start=1,
    ):
        print(
            f"{index:02d}. {source} --{attributes.get('relationship', '')}--> "
            f"{target} ({attributes.get('document', '')})"
        )
        if index == 20:
            break

    ready = node_count > 0 and edge_count > 0 and targets_found
    print("\nGraph = PASS" if ready else "\nGraph = FAIL")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
