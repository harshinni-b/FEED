"""Demo API routes backed by the existing EDOCA workflow."""

from __future__ import annotations

from functools import lru_cache
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemas import (
	AnalyzeRequest,
	AnalyzeResponse,
	AddCommentRequest,
	FindingDetailResponse,
	FindingsResponse,
	GraphResponse,
	ImpactAnalysisRequest,
	ImpactAnalysisResponse,
	ReviewFindingRequest,
)
from src.assurance.change_impact import ChangeImpactAssuranceEngine
from src.knowledge.evidence_index import EvidenceIndex
from src.knowledge.graph import PlantKnowledgeGraph
from src.findings.repository import FindingsRepository
from src.orchestration.analyze import analyze
from src.reasoning.gpt_reasoner import GPTReasoner
from src.reasoning.provider import DeterministicReasoningProvider
from src.retrieval.hybrid import HybridGraphRAGRetriever

router = APIRouter(prefix="/api", tags=["EDOCA analysis"])

PRIMARY_GRAPH_NODE_TYPES = {
	"UNIT", "EQUIPMENT", "INSTRUMENT", "CONTROL_LOOP", "SIF", "VALVE", "LINE", "DOCUMENT",
}
CONTEXT_GRAPH_NODE_TYPES = {"PARAMETER", "VALUE", "LIMIT"}


class EDOCAApiRuntime:
	"""Initializes reusable read models; all assurance remains in existing modules."""

	def __init__(self, reasoner: GPTReasoner | None = None) -> None:
		self.evidence_index = EvidenceIndex()
		self.evidence_index.index_chunks()
		self.plant_graph = PlantKnowledgeGraph()
		self.plant_graph.build_graph()
		self.change_impact = ChangeImpactAssuranceEngine(self.plant_graph)
		self.hybrid_retriever = HybridGraphRAGRetriever(
			plant_graph=self.plant_graph,
			evidence_index=self.evidence_index,
		)
		self.reasoner = reasoner or self._default_reasoner()
		self.findings_repository = FindingsRepository()
		self.findings: list[dict[str, Any]] = []

	@staticmethod
	def _default_reasoner() -> GPTReasoner:
		"""Use GPT only when explicitly enabled; demos remain credential-free by default."""
		if os.getenv("EDOCA_LIVE_REASONING") == "1":
			return GPTReasoner()
		return GPTReasoner(DeterministicReasoningProvider())

	def analyze(self, query: str) -> dict[str, Any]:
		"""Delegate analysis unchanged to the public LangGraph facade."""
		result = analyze(
			query,
			evidence_index=self.evidence_index,
			plant_graph=self.plant_graph,
			hybrid_retriever=self.hybrid_retriever,
			change_impact_engine=self.change_impact,
			reasoner=self.reasoner,
		)
		result["graph_context"] = {
			"nodes": [],
			"relationships": [],
			"documents": [],
			**result["graph_context"],
		}
		for finding in result["findings"]:
			stored = self.findings_repository.get_finding(str(finding.get("finding_id", "")))
			if stored is None:
				self.findings_repository.save_finding(dict(finding))
		self.findings = [dict(finding) for finding in result["findings"]]
		return result

	def graph_context(self, entity: str, depth: int = 1) -> tuple[dict[str, Any], dict[str, Any]] | None:
		"""Resolve an ID or displayed tag and return the graph-owned neighborhood."""
		entity_id = entity if entity in self.plant_graph.graph else next(
			(
				str(node_id)
				for node_id, attributes in self.plant_graph.graph.nodes(data=True)
				if str(attributes.get("name", "")).casefold() == entity.casefold()
			),
			None,
		)
		if entity_id is None:
			return None
		entity_record = self.plant_graph.get_entity(entity_id)
		return entity_record or {"entity_id": entity_id}, self.plant_graph.get_graph_context(entity_id, hops=depth)


@lru_cache(maxsize=1)
def get_runtime() -> EDOCAApiRuntime:
	"""Create the local corpus runtime once per API process."""
	return EDOCAApiRuntime()


@router.post(
	"/analyze",
	response_model=AnalyzeResponse,
	summary="Run an EDOCA document-consistency investigation",
	description="Runs the existing public LangGraph analysis workflow and returns evidence, graph context, assurance results, reasoning, and findings.",
)
def analyze_documents(request: AnalyzeRequest, runtime: EDOCAApiRuntime = Depends(get_runtime)) -> dict[str, Any]:
	"""Run the existing LangGraph assurance workflow for an engineer query."""
	result = runtime.analyze(request.query)
	return {
		**result,
		"recommendations": list(dict.fromkeys(
			str(finding["recommendation"])
			for finding in result["findings"]
			if finding.get("recommendation")
		)),
	}


@router.get(
	"/findings",
	response_model=FindingsResponse,
	summary="List persisted findings",
	description="Lists findings produced by API investigations, optionally filtered by lifecycle status or severity.",
)
def get_findings(
	status_filter: str | None = Query(default=None, alias="status", description="Optional lifecycle status filter."),
	severity: str | None = Query(default=None, description="Optional severity filter."),
	runtime: EDOCAApiRuntime = Depends(get_runtime),
) -> dict[str, list[dict[str, Any]]]:
	"""Return persisted EDOCA findings rather than process-local workflow output."""
	try:
		return {"findings": runtime.findings_repository.list_findings(status_filter, severity)}
	except ValueError as exc:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
	"/findings/{finding_id}",
	response_model=FindingDetailResponse,
	summary="Get one finding and its review history",
)
def get_finding(finding_id: str, runtime: EDOCAApiRuntime = Depends(get_runtime)) -> dict[str, dict[str, Any]]:
	"""Return a persisted finding with an explicit, possibly empty review history."""
	finding = runtime.findings_repository.get_finding(finding_id)
	if finding is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown finding: {finding_id}")
	finding["review_history"] = runtime.findings_repository.get_review_history(finding_id)
	return {"finding": finding}


@router.patch(
	"/findings/{finding_id}/review",
	response_model=FindingDetailResponse,
	summary="Update finding lifecycle status",
	description="Records a supported engineer-review status and a timestamped review-history event.",
)
def review_finding(
	finding_id: str,
	request: ReviewFindingRequest,
	runtime: EDOCAApiRuntime = Depends(get_runtime),
) -> dict[str, dict[str, Any]]:
	"""Delegate lifecycle persistence to the existing FindingsRepository."""
	try:
		finding = runtime.findings_repository.update_status(
			finding_id, request.status, request.reviewer, request.comment
		)
	except KeyError as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
	return {"finding": finding}


@router.post(
	"/findings/{finding_id}/comments",
	response_model=FindingDetailResponse,
	summary="Add an engineer review comment",
	description="Adds a timestamped comment while preserving the finding's current lifecycle status.",
)
def add_finding_comment(
	finding_id: str,
	request: AddCommentRequest,
	runtime: EDOCAApiRuntime = Depends(get_runtime),
) -> dict[str, dict[str, Any]]:
	"""Delegate comment persistence to the existing FindingsRepository."""
	try:
		finding = runtime.findings_repository.add_comment(finding_id, request.reviewer, request.comment)
	except KeyError as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
	return {"finding": finding}


@router.get(
	"/graph/{entity}",
	response_model=GraphResponse,
	summary="Get an entity-centered plant knowledge graph",
	description="Resolves an engineering ID or display name and returns a bounded graph neighborhood with document provenance.",
)
def get_graph(
	entity: str,
	depth: int = Query(default=1, ge=0, le=3, description="Traversal depth, limited to three hops for the demo."),
	include_context: bool = Query(default=False, description="Include parameter, value, and limit nodes in the primary node list."),
	runtime: EDOCAApiRuntime = Depends(get_runtime),
) -> dict[str, Any]:
	"""Project existing PlantKnowledgeGraph context into the demo graph contract."""
	result = runtime.graph_context(entity, depth)
	if result is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown graph entity: {entity}")
	entity_record, graph_context = result
	all_nodes = [dict(node) for node in graph_context.get("nodes", []) if isinstance(node, dict)]
	context_nodes = [node for node in all_nodes if str(node.get("entity_type", "")).upper() in CONTEXT_GRAPH_NODE_TYPES]
	primary_nodes = [node for node in all_nodes if str(node.get("entity_type", "")).upper() in PRIMARY_GRAPH_NODE_TYPES]
	nodes = all_nodes if include_context else primary_nodes
	relationships = [
		{
			"source": str(relationship.get("source", "")),
			"target": str(relationship.get("target", "")),
			"relationship_type": str(relationship.get("relationship", "")),
			"document": str(relationship.get("document", "")),
		}
		for relationship in graph_context.get("relationships", [])
		if isinstance(relationship, dict)
	]
	documents = sorted({
		str(document)
		for document in graph_context.get("documents", [])
		if str(document)
	} | {
		str(node.get("name", node.get("entity_id", "")))
		for node in nodes
		if node.get("entity_type") == "DOCUMENT"
	} | {
		relationship["document"]
		for relationship in relationships
		if relationship["document"]
	})
	known_entity_names = {
		str(entity_record.get("entity_id", "")).casefold(),
		str(entity_record.get("name", "")).casefold(),
	}
	related_findings = [
		finding
		for finding in runtime.findings_repository.list_findings()
		if any(
			str(asset).casefold() in known_entity_names
			for asset in finding.get("affected_assets", [])
		)
	]
	return {
		"requested_entity": entity,
		"resolved_entity": entity_record,
		"nodes": nodes,
		"context_nodes": context_nodes,
		"context_included": include_context,
		"relationships": relationships,
		"documents": documents,
		"related_findings": related_findings,
	}


@router.post("/impact-analysis", response_model=ImpactAnalysisResponse, summary="Run deterministic change-impact analysis")
def impact_analysis(
	request: ImpactAnalysisRequest,
	runtime: EDOCAApiRuntime = Depends(get_runtime),
) -> dict[str, Any]:
	"""Run existing deterministic impact traversal and preserve graph provenance."""
	try:
		impact_result = dict(runtime.change_impact.analyze(request.entity, request.hops))
	except ValueError as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
	graph_result = runtime.graph_context(request.entity, request.hops)
	if graph_result is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown graph entity: {request.entity}")
	resolved_entity, graph_context = graph_result
	all_nodes = [dict(node) for node in graph_context.get("nodes", []) if isinstance(node, dict)]
	context_nodes = [node for node in all_nodes if str(node.get("entity_type", "")).upper() in CONTEXT_GRAPH_NODE_TYPES]
	primary_names = {
		str(node.get("name", node.get("entity_id", "")))
		for node in all_nodes
		if str(node.get("entity_type", "")).upper() in PRIMARY_GRAPH_NODE_TYPES
	}
	primary_impact_radius = _filter_impact_radius(impact_result["impact_radius"], primary_names)
	affected_relationships = [
		{
			"source": str(relationship.get("source", "")),
			"target": str(relationship.get("target", "")),
			"relationship_type": str(relationship.get("relationship", "")),
			"document": str(relationship.get("document", "")),
		}
		for relationship in graph_context.get("relationships", [])
		if isinstance(relationship, dict)
	]
	known_assets = {
		str(request.entity).casefold(),
		str(resolved_entity.get("entity_id", "")).casefold(),
		str(resolved_entity.get("name", "")).casefold(),
		*(str(asset).casefold() for asset in impact_result["affected_assets"]),
	}
	related_findings = [
		finding
		for finding in runtime.findings_repository.list_findings()
		if any(str(asset).casefold() in known_assets for asset in finding.get("affected_assets", []))
	]
	return {
		"entity": impact_result["entity"],
		"proposed_change": request.proposed_change,
		"affected_assets": impact_result["affected_assets"],
		"affected_documents": impact_result["affected_documents"],
		"affected_relationships": affected_relationships,
		"impact_radius": primary_impact_radius,
		"expanded_impact_radius": impact_result["impact_radius"],
		"context_nodes": context_nodes,
		"assurance_results": [impact_result],
		"related_findings": related_findings,
		"review_required": True,
	}


def _filter_impact_radius(radius: dict[str, Any], allowed_names: set[str]) -> dict[str, Any]:
	"""Project a traversal radius without mutating the deterministic engine result."""
	by_hop = radius.get("by_hop", {})
	if not isinstance(by_hop, dict):
		return dict(radius)
	projected: dict[str, Any] = {}
	for hop, details in by_hop.items():
		if isinstance(details, dict):
			entities = [str(entity) for entity in details.get("entities", []) if str(entity) in allowed_names]
			projected[str(hop)] = {**details, "count": len(entities), "entities": entities}
		elif isinstance(details, list):
			projected[str(hop)] = [str(entity) for entity in details if str(entity) in allowed_names]
	return {**radius, "by_hop": projected}
