"""Public EDOCA analysis entrypoints backed by the LangGraph workflow."""

from __future__ import annotations

from typing import Any

from src.assurance.attribute import AttributeAssuranceEngine
from src.assurance.change_impact import ChangeImpactAssuranceEngine
from src.assurance.connectivity import ConnectivityAssuranceEngine
from src.assurance.operational_intent import OperationalIntentAssuranceEngine
from src.findings.finding_builder import FindingBuilder
from src.knowledge.evidence_index import EvidenceIndex
from src.knowledge.graph import PlantKnowledgeGraph
from src.orchestration.langgraph_workflow import run_edoca_graph
from src.reasoning.gpt_reasoner import GPTReasoner
from src.retrieval.azure_search import AzureSearchRetriever
from src.retrieval.embeddings import EmbeddingsProvider
from src.retrieval.hybrid import HybridRetrieverPort


WORKFLOW_FIELDS = (
	"query",
	"intent",
	"retrieval_metadata",
	"assurance_results",
	"reasoning_output",
	"findings",
	"graph_context",
	"evidence",
	"executed_nodes",
	"errors",
)


class EDOCAAnalyzer:
	"""Backward-compatible facade returning the first workflow finding."""

	def __init__(
		self,
		evidence_index: EvidenceIndex | None = None,
		graph: PlantKnowledgeGraph | None = None,
		assurance_engine: AttributeAssuranceEngine | None = None,
		connectivity_engine: ConnectivityAssuranceEngine | None = None,
		operational_intent_engine: OperationalIntentAssuranceEngine | None = None,
		change_impact_engine: ChangeImpactAssuranceEngine | None = None,
		reasoner: GPTReasoner | None = None,
		finding_builder: FindingBuilder | None = None,
		hybrid_retriever: HybridRetrieverPort | None = None,
		azure_retriever: AzureSearchRetriever | None = None,
		embeddings_provider: EmbeddingsProvider | None = None,
	) -> None:
		self.components = {
			"evidence_index": evidence_index,
			"plant_graph": graph,
			"attribute_engine": assurance_engine,
			"connectivity_engine": connectivity_engine,
			"operational_intent_engine": operational_intent_engine,
			"change_impact_engine": change_impact_engine or ChangeImpactAssuranceEngine(),
			"reasoner": reasoner,
			"finding_builder": finding_builder,
			"hybrid_retriever": hybrid_retriever,
			"azure_retriever": azure_retriever,
			"embeddings_provider": embeddings_provider,
		}
		self.components = {key: value for key, value in self.components.items() if value is not None}

	def analyze(self, query: str) -> dict[str, Any] | None:
		"""Run LangGraph and return the first finding for legacy callers."""
		state = analyze(query, **self.components)
		findings = state["findings"]
		if not findings:
			return None
		return dict(findings[0])


def analyze(query: str, **components: Any) -> dict[str, Any]:
	"""Run the compiled LangGraph workflow and return its complete state."""
	aliases = {
		"graph": "plant_graph",
		"assurance_engine": "attribute_engine",
	}
	for legacy_name, workflow_name in aliases.items():
		if legacy_name in components and workflow_name not in components:
			components[workflow_name] = components.pop(legacy_name)
	state = dict(run_edoca_graph(query, **components))
	return {field: state.get(field, {}) if field in {"retrieval_metadata", "reasoning_output", "graph_context"} else state.get(field, []) if field in {"assurance_results", "findings", "executed_nodes", "errors", "evidence"} else state.get(field, "") for field in WORKFLOW_FIELDS}
