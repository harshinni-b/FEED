"""Verify the complete LangGraph Hybrid GraphRAG EDOCA architecture."""

from __future__ import annotations

import json
import os
import sys
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
from src.retrieval.embeddings import AzureOpenAIEmbeddingsProvider, FakeEmbeddingsProvider
from src.retrieval.hybrid import HybridGraphRAGRetriever

QUESTION = "Is there a consistency issue with Unit 400 Pass 1 temperature?"


class DeterministicReasoningProvider:
    """Return structured reasoning using only facts serialized in the prompt."""

    def generate(self, prompt: str) -> dict[str, Any]:
        payload = json.loads(prompt.split("\n\n", 1)[1])
        assurance = payload.get("assurance_results", [])
        graph_context = payload.get("graph_context", {})
        assets = [
            str(node.get("name", ""))
            for node in graph_context.get("nodes", [])
            if isinstance(node, dict)
            and node.get("entity_type") in {
                "UNIT", "EQUIPMENT", "INSTRUMENT", "CONTROL_LOOP",
                "SIF", "VALVE", "LINE",
            }
        ]
        failed = next((result for result in assurance if result.get("status") == "FAIL"), {})
        return {
            "finding_title": str(failed.get("check", "Engineering consistency issue")),
            "severity": str(failed.get("severity", "HIGH")),
            "confidence": 1.0 if failed else 0.5,
            "root_cause": str(failed.get("finding", "Insufficient assurance evidence.")),
            "reasoning": "Deterministic verification used only supplied EPC evidence and assurance results.",
            "recommendation": "Review the failed assurance result with the engineering team.",
            "affected_assets": assets[:10],
        }


def print_json(label: str, value: Any) -> None:
    print(f"{label}: {json.dumps(value, indent=2, ensure_ascii=False)}")


def build_components(live: bool) -> dict[str, Any]:
    evidence_index = EvidenceIndex()
    plant_graph = PlantKnowledgeGraph()
    evidence_index.index_chunks()
    plant_graph.build_graph()

    if live:
        azure_retriever = AzureSearchRetriever()
        embeddings_provider = AzureOpenAIEmbeddingsProvider()
        reasoner = GPTReasoner()
    else:
        azure_retriever = None
        embeddings_provider = FakeEmbeddingsProvider()
        reasoner = GPTReasoner(DeterministicReasoningProvider())

    hybrid_retriever = HybridGraphRAGRetriever(
        plant_graph=plant_graph,
        evidence_index=evidence_index,
        azure_retriever=azure_retriever,
        embeddings_provider=embeddings_provider,
    )
    return {
        "evidence_index": evidence_index,
        "plant_graph": plant_graph,
        "hybrid_retriever": hybrid_retriever,
        "attribute_engine": AttributeAssuranceEngine(),
        "connectivity_engine": ConnectivityAssuranceEngine(),
        "operational_intent_engine": OperationalIntentAssuranceEngine(),
        "change_impact_engine": ChangeImpactAssuranceEngine(plant_graph),
        "reasoner": reasoner,
        "finding_builder": FindingBuilder(),
    }


def main() -> int:
    """Run and report the real EPC corpus through the LangGraph workflow."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    live = os.getenv("EDOCA_LIVE_AZURE") == "1"
    print("======== LANGGRAPH HYBRID GRAPHRAG EDOCA ========")
    print(f"Query: {QUESTION}")
    print(f"Mode: {'live Azure' if live else 'deterministic offline'}")

    try:
        state = run_edoca_graph(QUESTION, **build_components(live))
    except Exception as exc:
        print_json("Errors", [str(exc)])
        print("LANGGRAPH HYBRID GRAPHRAG EDOCA = FAIL")
        return 1

    retrieval_metadata = state.get("retrieval_metadata", {})
    graph_context = state.get("graph_context", {})
    evidence = state.get("evidence", [])
    assurance_results = state.get("assurance_results", [])
    reasoning_output = state.get("reasoning_output", {})
    findings = state.get("findings", [])
    errors = state.get("errors", [])

    print_json("Executed LangGraph Nodes", state.get("executed_nodes", []))
    print(f"Retrieval Mode: {retrieval_metadata.get('retrieval_mode', '')}")
    print(f"Keyword Result Count: {retrieval_metadata.get('keyword_count', 0)}")
    print(f"Vector Result Count: {retrieval_metadata.get('vector_count', 0)}")
    print(f"Graph Node Count: {retrieval_metadata.get('graph_node_count', len(graph_context.get('nodes', [])))}")
    print_json("Matched Documents", sorted({record.get("document_id", "") for record in evidence}))
    print_json("Assurance Results", assurance_results)
    print_json("Reasoning Output", reasoning_output)
    print_json("Final Findings", findings)
    print_json("Errors", errors)

    required_reasoning = {
        "finding_title", "severity", "confidence", "root_cause",
        "reasoning", "recommendation", "affected_assets",
    }
    evidence_backed = any(
        isinstance(finding, dict) and isinstance(finding.get("evidence"), list) and finding["evidence"]
        for finding in findings
    )
    passed = all((
        state.get("executed_nodes"),
        retrieval_metadata.get("retrieval_mode") in {"local_graph_keyword", "azure_hybrid_graph"},
        evidence,
        graph_context.get("nodes"),
        assurance_results,
        required_reasoning.issubset(reasoning_output),
        findings,
        evidence_backed,
        not errors,
    ))
    print(
        "LANGGRAPH HYBRID GRAPHRAG EDOCA = PASS"
        if passed
        else "LANGGRAPH HYBRID GRAPHRAG EDOCA = FAIL"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
