from unittest.mock import Mock

import pytest

from src.knowledge.evidence_index import EvidenceIndex
from src.knowledge.graph import PlantKnowledgeGraph
from src.retrieval.embeddings import FakeEmbeddingsProvider
from src.retrieval.hybrid import HybridGraphRAGRetriever


def record(chunk_id, text, document_type="process"):
    return {"chunk_id": chunk_id, "document_id": "DOC-1", "document_type": document_type, "section": "Unit-400", "subsection": "Temperature", "text": text, "source_type": "table"}


class FakeEvidenceIndex:
    def __init__(self):
        self.records = [record("c2", "Unit-400 temperature is documented."), record("c1", "Unit-400 limit is 620 C.")]

    def search_by_keyword(self, query):
        return list(self.records)

    def search_by_entity(self, entity):
        return [self.records[0]]

    def search_by_document(self, document):
        return [record for record in self.records if record["document_id"] == document]


class FakeGraph:
    class Nodes:
        def __call__(self, data=False):
            values = [("unit:400", {"name": "Unit-400", "entity_type": "UNIT"}), ("doc:1", {"name": "DOC-1", "entity_type": "DOCUMENT"})]
            return values if data else [item[0] for item in values]

    def __init__(self):
        self.graph = Mock()
        self.graph.__contains__ = lambda graph, value: value == "unit:400"
        self.graph.nodes = self.Nodes()

    def get_graph_context(self, entity_id):
        return {"nodes": [{"entity_id": "unit:400", "name": "Unit-400", "entity_type": "UNIT"}, {"entity_id": "doc:1", "name": "DOC-1", "entity_type": "DOCUMENT"}], "relationships": [{"source": "unit:400", "target": "doc:1", "relationship": "APPEARS_IN"}]}


def test_local_fallback_merges_and_deduplicates_keyword_evidence():
    result = HybridGraphRAGRetriever(FakeGraph(), FakeEvidenceIndex()).retrieve("Unit-400 temperature", ["Unit-400"])

    assert result["retrieval_metadata"]["retrieval_mode"] == "local_graph_keyword"
    assert [item["chunk_id"] for item in result["evidence"]] == ["c2", "c1"]
    assert result["graph_context"]["documents"] == ["DOC-1"]
    assert result["retrieval_metadata"]["graph_node_count"] == 2


def test_azure_hybrid_uses_embeddings_and_applies_filters():
    azure = Mock()
    azure.hybrid_search.return_value = [record("c1", "semantic result")]
    azure.keyword_search.return_value = [record("c1", "keyword result")]
    azure.vector_search.return_value = [record("c3", "vector result")]
    retriever = HybridGraphRAGRetriever(FakeGraph(), FakeEvidenceIndex(), azure, FakeEmbeddingsProvider(4))

    result = retriever.retrieve("temperature", filters={"document_type": "process"}, top_k=2)

    assert result["retrieval_metadata"]["retrieval_mode"] == "azure_hybrid_graph"
    assert result["retrieval_metadata"]["keyword_count"] == 1
    assert result["retrieval_metadata"]["vector_count"] == 1
    assert azure.hybrid_search.call_args.args[0] == "temperature"
    assert azure.hybrid_search.call_args.args[2] == {"document_type": "process"}


def test_azure_failure_returns_local_mode():
    azure = Mock()
    azure.hybrid_search.side_effect = RuntimeError("unavailable")
    result = HybridGraphRAGRetriever(FakeGraph(), FakeEvidenceIndex(), azure, FakeEmbeddingsProvider(4)).retrieve("temperature")

    assert result["retrieval_metadata"]["retrieval_mode"] == "local_graph_keyword"


@pytest.mark.parametrize("query, entity", [
    ("Is there a consistency issue with Unit 400 Pass 1 temperature?", "Unit-400"),
    ("What does TSHH-401 protect?", "TSHH-401"),
    ("Is WHB-201 steam pressure consistent?", "WHB-201"),
    ("What happens if SIF-05 fails?", "SIF-05"),
])
def test_real_epc_queries_expand_entities_and_return_evidence(query, entity):
    evidence_index = EvidenceIndex()
    evidence_index.index_chunks()
    plant_graph = PlantKnowledgeGraph()
    plant_graph.build_graph()

    result = HybridGraphRAGRetriever(plant_graph, evidence_index).retrieve(query)

    assert result["evidence"]
    assert any(node.get("name") == entity for node in result["graph_context"]["nodes"])
    assert result["retrieval_metadata"]["retrieval_mode"] == "local_graph_keyword"


def test_query_with_no_matching_entity_keeps_graph_context_empty():
    evidence_index = EvidenceIndex()
    evidence_index.index_chunks()
    plant_graph = PlantKnowledgeGraph()
    plant_graph.build_graph()

    result = HybridGraphRAGRetriever(plant_graph, evidence_index).retrieve("What is Unknown-999?")

    assert result["graph_context"]["nodes"] == []
    assert result["retrieval_metadata"]["graph_node_count"] == 0