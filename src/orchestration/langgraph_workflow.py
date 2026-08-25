"""LangGraph orchestration for the EDOCA assurance workflow."""

from __future__ import annotations

import re
import os
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from src.assurance.attribute import AttributeAssuranceEngine
from src.assurance.change_impact import ChangeImpactAssuranceEngine
from src.assurance.connectivity import ConnectivityAssuranceEngine
from src.assurance.operational_intent import OperationalIntentAssuranceEngine
from src.findings.finding_builder import FindingBuilder
from src.knowledge.evidence_index import EvidenceIndex
from src.knowledge.graph import PlantKnowledgeGraph
from src.orchestration.state import EDOCAState
from src.reasoning.gpt_reasoner import GPTReasoner
from src.retrieval.azure_search import AzureSearchRetriever
from src.retrieval.embeddings import AzureOpenAIEmbeddingsProvider, EmbeddingsProvider
from src.retrieval.hybrid import HybridGraphRAGRetriever, HybridRetrieverPort


CHANGE_INTENT_PATTERN = re.compile(
	r"\b(?:change|modify|replace|increase|decrease|impact|affected)\b"
	 r"|\bwhat\s+happens\s+if\b",
	re.IGNORECASE,
)


def build_edoca_graph(
	evidence_index: EvidenceIndex | None = None,
	plant_graph: PlantKnowledgeGraph | None = None,
	attribute_engine: AttributeAssuranceEngine | None = None,
	connectivity_engine: ConnectivityAssuranceEngine | None = None,
	operational_intent_engine: OperationalIntentAssuranceEngine | None = None,
	change_impact_engine: ChangeImpactAssuranceEngine | None = None,
	reasoner: GPTReasoner | None = None,
	finding_builder: FindingBuilder | None = None,
	hybrid_retriever: HybridRetrieverPort | None = None,
	azure_retriever: AzureSearchRetriever | None = None,
	embeddings_provider: EmbeddingsProvider | None = None,
) -> Any:
	"""Build and compile the dependency-injected EDOCA StateGraph."""
	evidence_index = evidence_index or EvidenceIndex()
	plant_graph = plant_graph or PlantKnowledgeGraph()
	attribute_engine = attribute_engine or AttributeAssuranceEngine()
	connectivity_engine = connectivity_engine or ConnectivityAssuranceEngine()
	operational_intent_engine = operational_intent_engine or OperationalIntentAssuranceEngine()
	change_impact_engine = change_impact_engine or ChangeImpactAssuranceEngine(plant_graph)
	finding_builder = finding_builder or FindingBuilder()

	def safe_node(
		name: str,
		operation: Callable[[EDOCAState], dict[str, Any]],
	) -> Callable[[EDOCAState], dict[str, Any]]:
		def execute(state: EDOCAState) -> dict[str, Any]:
			try:
				updates = operation(state)
			except Exception as exc:
				return {
					"executed_nodes": [name],
					"errors": [f"{name}: {exc}"],
				}
			updates["executed_nodes"] = [name]
			return updates

		return execute

	def detect_intent(state: EDOCAState) -> dict[str, Any]:
		query = state["query"]
		if not isinstance(query, str) or not query.strip():
			raise ValueError("query must be a non-empty string")
		change_requested = bool(CHANGE_INTENT_PATTERN.search(query))
		return {
			"intent": "change_impact" if change_requested else "consistency_assurance",
			"change_impact_requested": change_requested,
		}

	def retrieve_context(state: EDOCAState) -> dict[str, Any]:
		retriever = hybrid_retriever or HybridGraphRAGRetriever(
			plant_graph,
			evidence_index,
			azure_retriever or _configured_azure_retriever(),
			embeddings_provider or _configured_embeddings_provider(),
		)
		retrieval = retriever.retrieve(
			state["query"],
			selected_entities=state["selected_entities"],
			filters={},
			top_k=10,
		)
		selected_entities = list(state["selected_entities"])
		if not selected_entities:
			selected_entities = [
				str(node["name"])
				for node in retrieval.get("graph_context", {}).get("nodes", [])
				if isinstance(node, dict) and node.get("name") and node.get("entity_type") != "DOCUMENT"
			]
		return {
			"evidence": [dict(record) for record in retrieval.get("evidence", [])],
			"graph_context": dict(retrieval.get("graph_context", {})),
			"retrieval_metadata": dict(retrieval.get("retrieval_metadata", {})),
			"selected_entities": list(dict.fromkeys(selected_entities)),
		}

	def run_attribute_assurance(state: EDOCAState) -> dict[str, Any]:
		return {"assurance_results": attribute_engine.validate(state["evidence"])}

	def run_connectivity_assurance(state: EDOCAState) -> dict[str, Any]:
		return {"assurance_results": connectivity_engine.validate(state["graph_context"])}

	def run_operational_intent_assurance(state: EDOCAState) -> dict[str, Any]:
		return {
			"assurance_results": operational_intent_engine.validate(
				state["evidence"], state["graph_context"]
			)
		}

	def run_change_impact_assurance(state: EDOCAState) -> dict[str, Any]:
		entity = state["selected_entities"][0] if state["selected_entities"] else ""
		if not entity:
			raise ValueError("change impact requires a selected entity")
		return {"assurance_results": [dict(change_impact_engine.analyze(entity))]}

	def reason_with_genai(state: EDOCAState) -> dict[str, Any]:
		reasoning_engine = reasoner or GPTReasoner()
		per_result: list[dict[str, Any]] = []
		for result_index, result in enumerate(state["assurance_results"]):
			if result.get("status", "FAIL") != "FAIL":
				continue
			output = dict(reasoning_engine.reason(
				state["query"],
				state["graph_context"],
				state["evidence"],
				[result],
			))
			per_result.append({
				"assurance_index": result_index,
				"check": str(result.get("check") or result.get("entity") or "Assurance"),
				"reasoning": output,
			})
		if not per_result:
			return {"reasoning_output": {}}
		return {
			"reasoning_output": {
				**per_result[0]["reasoning"],
				"per_assurance_result": per_result,
			}
		}

	def build_findings(state: EDOCAState) -> dict[str, Any]:
		return {
			"findings": finding_builder.build(
				state["evidence"],
				state["graph_context"],
				state["assurance_results"],
				state["reasoning_output"],
				query=state["query"],
			)
		}

	graph = StateGraph(EDOCAState)
	graph.add_node("detect_intent", safe_node("detect_intent", detect_intent))
	graph.add_node("retrieve_context", safe_node("retrieve_context", retrieve_context))
	graph.add_node("run_attribute_assurance", safe_node("run_attribute_assurance", run_attribute_assurance))
	graph.add_node("run_connectivity_assurance", safe_node("run_connectivity_assurance", run_connectivity_assurance))
	graph.add_node("run_operational_intent_assurance", safe_node("run_operational_intent_assurance", run_operational_intent_assurance))
	graph.add_node("run_change_impact_assurance", safe_node("run_change_impact_assurance", run_change_impact_assurance))
	graph.add_node("reason_with_genai", safe_node("reason_with_genai", reason_with_genai))
	graph.add_node("build_findings", safe_node("build_findings", build_findings))
	graph.add_edge(START, "detect_intent")
	graph.add_edge("detect_intent", "retrieve_context")
	graph.add_edge("retrieve_context", "run_attribute_assurance")
	graph.add_edge("run_attribute_assurance", "run_connectivity_assurance")
	graph.add_edge("run_connectivity_assurance", "run_operational_intent_assurance")
	graph.add_conditional_edges(
		"run_operational_intent_assurance",
		lambda state: "run_change_impact_assurance" if state["change_impact_requested"] else "reason_with_genai",
	)
	graph.add_edge("run_change_impact_assurance", "reason_with_genai")
	graph.add_edge("reason_with_genai", "build_findings")
	graph.add_edge("build_findings", END)
	return graph.compile()


def run_edoca_graph(query: str, **components: Any) -> EDOCAState:
	"""Run the compiled EDOCA workflow with an initialized shared state."""
	initial_state: EDOCAState = {
		"query": query,
		"intent": "",
		"selected_entities": [],
		"evidence": [],
		"graph_context": {},
		"retrieval_metadata": {},
		"assurance_results": [],
		"reasoning_output": {},
		"findings": [],
		"change_impact_requested": False,
		"executed_nodes": [],
		"errors": [],
	}
	return build_edoca_graph(**components).invoke(initial_state)


def _configured_azure_retriever() -> AzureSearchRetriever | None:
	if os.getenv("AZURE_SEARCH_ENDPOINT") and os.getenv("AZURE_SEARCH_INDEX_NAME"):
		return AzureSearchRetriever()
	return None


def _configured_embeddings_provider() -> EmbeddingsProvider | None:
	if os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_VERSION"):
		return AzureOpenAIEmbeddingsProvider()
	return None
