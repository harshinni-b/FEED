"""NetworkX-backed plant knowledge graph for EDOCA."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

logger = logging.getLogger(__name__)

SUPPORTED_RELATIONSHIPS = {
	"APPEARS_IN",
	"DESCRIBES",
	"HAS_PARAMETER",
	"HAS_LIMIT",
	"HAS_VALUE",
	"RELATED_TO",
	"CONNECTED_TO",
	"CONTROLS",
	"INITIATES",
	"PROTECTS",
}


class PlantKnowledgeGraph:
	"""Build and query a directed, typed NetworkX plant knowledge graph."""

	def __init__(self) -> None:
		self.graph = nx.MultiDiGraph()

	def build_graph(
		self,
		entities_path: str | Path = "data/processed/entities",
		relationships_path: str | Path = "data/processed/relationships",
	) -> nx.MultiDiGraph:
		"""Load entities and relationships into the graph and return it."""
		entities = self._load_records(entities_path)
		relationships = self._load_records(relationships_path)
		self.graph.clear()

		for entity in entities:
			entity_id = str(entity["entity_id"])
			self.graph.add_node(
				entity_id,
				entity_type=str(entity.get("entity_type", "UNKNOWN")),
				name=str(entity.get("name", entity_id)),
				source_chunk=str(entity.get("source_chunk", "")),
			)

		for relationship in relationships:
			source = str(relationship["source"])
			target = str(relationship["target"])
			relation = str(relationship["relationship"])
			document = str(relationship.get("document", ""))
			if relation not in SUPPORTED_RELATIONSHIPS:
				logger.warning("Loading unsupported relationship type: %s", relation)
			self._ensure_target_node(target, relation, document)
			if source not in self.graph:
				self.graph.add_node(source, entity_type="UNKNOWN", name=source)
			self.graph.add_edge(
				source,
				target,
				relationship=relation,
				document=document,
			)

		logger.info(
			"Built plant knowledge graph with %d nodes and %d edges",
			self.graph.number_of_nodes(),
			self.graph.number_of_edges(),
		)
		return self.graph

	def get_entity(self, entity_id: str) -> dict[str, Any] | None:
		"""Return an entity and its graph attributes, or None when absent."""
		if entity_id not in self.graph:
			return None
		return {"entity_id": entity_id, **dict(self.graph.nodes[entity_id])}

	def get_neighbors(
		self,
		entity_id: str,
		relationship: str | None = None,
	) -> list[dict[str, Any]]:
		"""Return adjacent entities, optionally filtered by edge relationship."""
		if entity_id not in self.graph:
			return []
		neighbors: dict[str, dict[str, Any]] = {}
		for source, target, attributes in self.graph.in_edges(entity_id, data=True):
			if relationship is None or attributes.get("relationship") == relationship:
				neighbors[source] = self.get_entity(source) or {"entity_id": source}
		for source, target, attributes in self.graph.out_edges(entity_id, data=True):
			if relationship is None or attributes.get("relationship") == relationship:
				neighbors[target] = self.get_entity(target) or {"entity_id": target}
		return list(neighbors.values())

	def get_graph_context(self, entity_id: str, hops: int = 1) -> dict[str, Any]:
		"""Return a compact node-link context around an entity for downstream reasoning."""
		if entity_id not in self.graph:
			return {"entity_id": entity_id, "nodes": [], "relationships": []}
		if hops < 0:
			raise ValueError("hops must be non-negative")
		undirected = self.graph.to_undirected()
		node_ids = set(nx.single_source_shortest_path_length(undirected, entity_id, cutoff=hops))
		subgraph = self.graph.subgraph(node_ids)
		relationships = [
			{"source": source, "target": target, **attributes}
			for source, target, attributes in subgraph.edges(data=True)
		]
		return {
			"entity_id": entity_id,
			"nodes": [self.get_entity(node_id) for node_id in subgraph.nodes],
			"relationships": relationships,
		}

	def export_graph_json(self, output_path: str | Path) -> Path:
		"""Export the graph as JSON using NetworkX node-link format."""
		destination = Path(output_path)
		destination.parent.mkdir(parents=True, exist_ok=True)
		data = nx.node_link_data(self.graph)
		if "edges" in data and "links" not in data:
			data["links"] = data.pop("edges")
		destination.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
		logger.info("Exported graph to %s", destination)
		return destination

	def _ensure_target_node(self, target: str, relationship: str, document: str) -> None:
		if target in self.graph:
			return
		entity_type = "VALUE" if relationship == "HAS_VALUE" else "LIMIT" if relationship == "HAS_LIMIT" else "UNKNOWN"
		self.graph.add_node(
			target,
			entity_type=entity_type,
			name=target,
			document=document,
		)

	@staticmethod
	def _load_records(path: str | Path) -> list[dict[str, Any]]:
		source = Path(path)
		paths = sorted(source.glob("*.json")) if source.is_dir() else [source]
		if not paths or not all(item.is_file() for item in paths):
			raise FileNotFoundError(f"JSON input does not exist: {source}")
		records: list[dict[str, Any]] = []
		for item in paths:
			loaded = json.loads(item.read_text(encoding="utf-8"))
			if not isinstance(loaded, list):
				raise ValueError(f"JSON input must contain a list: {item}")
			records.extend(record for record in loaded if isinstance(record, dict))
		return records
