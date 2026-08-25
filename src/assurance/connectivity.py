"""Deterministic engineering connectivity assurance checks."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class ConnectivityFinding(TypedDict):
	"""Result of one deterministic graph connectivity check."""

	check: str
	status: str
	severity: str
	affected_assets: list[str]
	finding: str


class ConnectivityAssuranceEngine:
	"""Validate plant dependencies and safety paths using graph traversal."""

	ASSET_TYPES = {
		"UNIT",
		"EQUIPMENT",
		"INSTRUMENT",
		"CONTROL_LOOP",
		"SIF",
		"VALVE",
		"LINE",
	}

	def validate(self, graph_context: dict[str, Any]) -> list[ConnectivityFinding]:
		"""Return findings for orphan, disconnected, missing, and broken graph paths."""
		if not isinstance(graph_context, dict):
			raise ValueError("graph_context must be an object")
		nodes = graph_context.get("nodes", [])
		relationships = graph_context.get("relationships", [])
		if not isinstance(nodes, list) or not isinstance(relationships, list):
			raise ValueError("graph_context nodes and relationships must be lists")

		node_map = {
			str(node.get("entity_id")): node
			for node in nodes
			if isinstance(node, dict) and node.get("entity_id")
		}
		assets = {
			entity_id: node
			for entity_id, node in node_map.items()
			if node.get("entity_type") in self.ASSET_TYPES
		}
		edges = [
			{
				"source": str(edge.get("source", "")),
				"target": str(edge.get("target", "")),
				"relationship": str(edge.get("relationship", "")),
			}
			for edge in relationships
			if isinstance(edge, dict)
		]
		incident = defaultdict(list)
		outgoing = defaultdict(list)
		for edge in edges:
			incident[edge["source"]].append(edge)
			incident[edge["target"]].append(edge)
			outgoing[edge["source"]].append(edge)

		findings: list[ConnectivityFinding] = []
		for entity_id, node in assets.items():
			if not incident[entity_id]:
				findings.append(self._finding("Orphan Entity", "HIGH", node, "Entity has no graph relationships"))

		components = self._components(set(assets), incident)
		if len(components) > 1:
			for component in components:
				findings.append(self._finding(
					"Disconnected Entity",
					"MEDIUM",
					[node_map[node_id].get("name", node_id) for node_id in component],
					"Entity group is disconnected from the other engineering graph components",
				))

		for entity_id, node in assets.items():
			if node.get("entity_type") == "CONTROL_LOOP" and not self._has_target_type(
				entity_id, outgoing, node_map, "INITIATES", "SIF"
			):
				findings.append(self._finding(
					"Missing Dependency",
					"HIGH",
					node,
					"Control loop has no INITIATES dependency to a SIF",
				))
			elif node.get("entity_type") == "SIF" and not self._has_target_type(
				entity_id, outgoing, node_map, "PROTECTS", "VALVE"
			):
				findings.append(self._finding(
					"Missing Dependency",
					"HIGH",
					node,
					"SIF has no PROTECTS dependency to a valve",
				))

		for loop_id, loop in assets.items():
			if loop.get("entity_type") != "CONTROL_LOOP":
				continue
			sifs = self._targets(loop_id, outgoing, "INITIATES")
			valves = [
				target
				for sif in sifs
				for target in self._targets(sif, outgoing, "PROTECTS")
				if node_map.get(target, {}).get("entity_type") == "VALVE"
			]
			if not sifs or not valves:
				findings.append(self._finding(
					"Broken Safety Chain",
					"HIGH",
					[loop],
					"Safety chain is incomplete: expected CONTROL_LOOP -> SIF -> VALVE",
				))

		logger.info("Completed connectivity assurance with %d findings", len(findings))
		return findings

	def check(self, graph_context: dict[str, Any]) -> list[ConnectivityFinding]:
		"""Alias for validate for generic assurance-engine orchestration."""
		return self.validate(graph_context)

	@staticmethod
	def _targets(entity_id: str, outgoing: dict[str, list[dict[str, str]]], relationship: str) -> list[str]:
		return [edge["target"] for edge in outgoing[entity_id] if edge["relationship"] == relationship]

	@classmethod
	def _has_target_type(
		cls,
		entity_id: str,
		outgoing: dict[str, list[dict[str, str]]],
		node_map: dict[str, dict[str, Any]],
		relationship: str,
		target_type: str,
	) -> bool:
		return any(node_map.get(target, {}).get("entity_type") == target_type for target in cls._targets(entity_id, outgoing, relationship))

	@staticmethod
	def _components(asset_ids: set[str], incident: dict[str, list[dict[str, str]]]) -> list[list[str]]:
		remaining = set(asset_ids)
		components: list[list[str]] = []
		while remaining:
			start = remaining.pop()
			component = [start]
			queue = deque([start])
			while queue:
				current = queue.popleft()
				for edge in incident[current]:
					neighbor = edge["target"] if edge["source"] == current else edge["source"]
					if neighbor in remaining:
						remaining.remove(neighbor)
						component.append(neighbor)
						queue.append(neighbor)
			components.append(component)
		return components

	@staticmethod
	def _finding(check: str, severity: str, node_or_name: Any, message: str) -> ConnectivityFinding:
		if isinstance(node_or_name, list):
			assets = [str(item) for item in node_or_name]
		elif isinstance(node_or_name, dict):
			assets = [str(node_or_name.get("name", node_or_name.get("entity_id", "")))]
		else:
			assets = [str(node_or_name)]
		return {
			"check": check,
			"status": "FAIL",
			"severity": severity,
			"affected_assets": [asset for asset in assets if asset],
			"finding": message,
		}
