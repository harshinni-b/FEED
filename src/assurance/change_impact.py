"""Deterministic change-impact analysis over the plant knowledge graph."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypedDict

import networkx as nx

from src.knowledge.graph import PlantKnowledgeGraph

logger = logging.getLogger(__name__)


class ChangeImpactResult(TypedDict):
	"""Impact summary for a changed engineering entity."""

	entity: str
	affected_assets: list[str]
	affected_documents: list[str]
	impact_radius: dict[str, Any]


class ChangeImpactAssuranceEngine:
	"""Determine graph-reachable engineering impact without model inference."""

	ASSET_TYPES = {
		"UNIT",
		"EQUIPMENT",
		"INSTRUMENT",
		"CONTROL_LOOP",
		"SIF",
		"VALVE",
		"LINE",
	}

	def __init__(
		self,
		plant_graph: PlantKnowledgeGraph | None = None,
		entities_path: str | Path = "data/processed/entities",
		relationships_path: str | Path = "data/processed/relationships",
	) -> None:
		self.plant_graph = plant_graph or PlantKnowledgeGraph()
		self.entities_path = entities_path
		self.relationships_path = relationships_path
		self._built = plant_graph is not None and plant_graph.graph.number_of_nodes() > 0

	def analyze(self, entity_id: str, hops: int = 2) -> ChangeImpactResult:
		"""Return graph-reachable assets and documents for an entity."""
		if not isinstance(entity_id, str) or not entity_id.strip():
			raise ValueError("entity_id must be a non-empty string")
		if hops < 0:
			raise ValueError("hops must be non-negative")
		self._ensure_graph()
		resolved_id = self._resolve_entity(entity_id)
		if resolved_id is None:
			raise KeyError(f"Entity not found in plant graph: {entity_id}")

		context = self.plant_graph.get_graph_context(resolved_id, hops=hops)
		nodes = {
			str(node["entity_id"]): node
			for node in context["nodes"]
			if isinstance(node, dict) and node.get("entity_id")
		}
		source = nodes[resolved_id]
		assets = sorted(
			str(node.get("name", node_id))
			for node_id, node in nodes.items()
			if node_id != resolved_id and node.get("entity_type") in self.ASSET_TYPES
		)
		documents = sorted(
			str(node.get("name", node_id))
			for node_id, node in nodes.items()
			if node.get("entity_type") == "DOCUMENT"
		)
		impact_radius = self._impact_radius(resolved_id, nodes, hops)
		logger.info(
			"Calculated change impact for %s: %d assets and %d documents",
			source.get("name", resolved_id),
			len(assets),
			len(documents),
		)
		return {
			"entity": str(source.get("name", entity_id)),
			"affected_assets": assets,
			"affected_documents": documents,
			"impact_radius": impact_radius,
		}

	def assess(self, entity_id: str, hops: int = 2) -> ChangeImpactResult:
		"""Alias for analyze for generic assurance orchestration."""
		return self.analyze(entity_id, hops)

	def _ensure_graph(self) -> None:
		if not self._built:
			self.plant_graph.build_graph(self.entities_path, self.relationships_path)
			self._built = True

	def _resolve_entity(self, value: str) -> str | None:
		if value in self.plant_graph.graph:
			return value
		for node_id, attributes in self.plant_graph.graph.nodes(data=True):
			if str(attributes.get("name", "")).casefold() == value.casefold():
				return str(node_id)
		return None

	def _impact_radius(
		self,
		entity_id: str,
		nodes: dict[str, dict[str, Any]],
		hops: int,
	) -> dict[str, Any]:
		undirected = self.plant_graph.graph.to_undirected()
		distances = nx.single_source_shortest_path_length(undirected, entity_id, cutoff=hops)
		by_hop: dict[str, dict[str, Any]] = {}
		for distance in range(hops + 1):
			ids = sorted(node_id for node_id, value in distances.items() if value == distance)
			by_hop[str(distance)] = {
				"count": len(ids),
				"entities": [str(nodes.get(node_id, {}).get("name", node_id)) for node_id in ids],
			}
		return {"max_hops": hops, "by_hop": by_hop}
