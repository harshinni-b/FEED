"""Hybrid GraphRAG retrieval for EDOCA engineering evidence."""

from __future__ import annotations

import re
from typing import Any, Protocol, Sequence

from src.knowledge.evidence_index import EvidenceChunk, EvidenceIndex
from src.knowledge.graph import PlantKnowledgeGraph
from src.retrieval.azure_search import AzureSearchRetriever
from src.retrieval.embeddings import EmbeddingsProvider


class HybridRetrieverPort(Protocol):
	"""Interface for retrieving graph context and grounded evidence."""

	def retrieve(self, query: str, selected_entities: list[str] | None = None, filters: dict[str, Any] | None = None, top_k: int = 10) -> dict[str, Any]:
		"""Retrieve an EDOCA GraphRAG context."""


class HybridGraphRAGRetriever:
	"""Combine graph, lexical, vector, and metadata retrieval deterministically."""

	def __init__(self, plant_graph: PlantKnowledgeGraph, evidence_index: EvidenceIndex, azure_retriever: AzureSearchRetriever | None = None, embeddings_provider: EmbeddingsProvider | None = None) -> None:
		self.plant_graph = plant_graph
		self.evidence_index = evidence_index
		self.azure_retriever = azure_retriever
		self.embeddings_provider = embeddings_provider

	def retrieve(self, query: str, selected_entities: list[str] | None = None, filters: dict[str, Any] | None = None, top_k: int = 10) -> dict[str, Any]:
		"""Return graph context and ranked evidence from the best available backend."""
		if not isinstance(query, str) or not query.strip():
			raise ValueError("query must be a non-empty string")
		if top_k <= 0:
			raise ValueError("top_k must be greater than zero")
		filters = dict(filters or {})
		entities = self._query_entities(query, selected_entities or [])
		graph_context = self._graph_context(query, entities)
		if self.azure_retriever is not None and self.embeddings_provider is not None:
			try:
				return self._azure_retrieve(query, entities, filters, top_k, graph_context)
			except Exception:
				pass
		return self._local_retrieve(query, entities, filters, top_k, graph_context)

	def _azure_retrieve(self, query: str, entities: list[str], filters: dict[str, Any], top_k: int, graph_context: dict[str, Any]) -> dict[str, Any]:
		query_vector = self.embeddings_provider.embed_query(query)
		hybrid = self.azure_retriever.hybrid_search(query, query_vector, filters, top_k)
		keyword: list[EvidenceChunk] = []
		for phrase in self._query_phrases(query, entities):
			keyword.extend(self.azure_retriever.keyword_search(phrase, filters, top_k))
		vector = self.azure_retriever.vector_search(query_vector, filters, top_k)
		candidates = [(record, 3) for record in hybrid]
		candidates.extend((record, 0) for record in keyword if self._contains_entity(record, entities))
		candidates.extend((record, 3) for record in keyword if not self._contains_entity(record, entities))
		candidates.extend((record, 2) for record in vector)
		evidence = self._rank_and_deduplicate(candidates, query, entities, top_k)
		return self._result(graph_context, evidence, len(keyword), len(vector), filters, "azure_hybrid_graph")

	def _local_retrieve(self, query: str, entities: list[str], filters: dict[str, Any], top_k: int, graph_context: dict[str, Any]) -> dict[str, Any]:
		if not getattr(self.evidence_index, "records", None):
			self.evidence_index.index_chunks()
		candidates: list[tuple[EvidenceChunk, int]] = []
		for entity in entities:
			search_by_entity = getattr(self.evidence_index, "search_by_entity", self.evidence_index.search_by_keyword)
			candidates.extend((record, 0) for record in search_by_entity(entity))
		for document in graph_context.get("documents", []):
			search_by_document = getattr(self.evidence_index, "search_by_document", self.evidence_index.search_by_keyword)
			candidates.extend((record, 1) for record in search_by_document(document))
		for phrase in self._query_phrases(query, entities):
			candidates.extend((record, 3) for record in self.evidence_index.search_by_keyword(phrase))
		candidates = [(record, source) for record, source in candidates if self._matches_filters(record, filters)]
		evidence = self._rank_and_deduplicate(candidates, query, entities, top_k)
		return self._result(graph_context, evidence, len(candidates), 0, filters, "local_graph_keyword")

	def _query_entities(self, query: str, selected_entities: list[str]) -> list[str]:
		entities = [str(entity) for entity in selected_entities if str(entity).strip()]
		query_text = _normalize(query)
		for _, attributes in self.plant_graph.graph.nodes(data=True):
			name = str(attributes.get("name", ""))
			if name and _normalize(name) in query_text:
				entities.append(name)
		for match in re.finditer(r"\b(?:unit|pass|[A-Z]{2,})\s*[- ]?\d+\b", query, re.IGNORECASE):
			entities.append(re.sub(r"\s+", "-", match.group(0).strip()))
		return list(dict.fromkeys(entity for entity in entities if entity.strip()))

	@staticmethod
	def _query_phrases(query: str, entities: list[str]) -> list[str]:
		stop_words = {"is", "there", "a", "an", "the", "with", "for", "and", "or", "of", "to", "in", "on", "does"}
		phrases = [query]
		phrases.extend(entities)
		phrases.extend(
			word for word in re.findall(r"[A-Za-z][A-Za-z0-9-]+", query)
			if word.casefold() not in stop_words and len(word) >= 3
		)
		return list(dict.fromkeys(phrase for phrase in phrases if phrase.strip()))

	@staticmethod
	def _contains_entity(record: EvidenceChunk, entities: list[str]) -> bool:
		text = _normalize(" ".join(str(record.get(field, "")) for field in ("section", "subsection", "text")))
		return any(_normalize(entity) and _normalize(entity) in text for entity in entities)

	def _graph_context(self, query: str, selected_entities: list[str]) -> dict[str, Any]:
		entity_ids = [self._resolve_entity(entity) for entity in selected_entities]
		entity_ids = [entity_id for entity_id in entity_ids if entity_id]
		if not entity_ids:
			query_text = _normalize(query)
			entity_ids = [str(entity_id) for entity_id, attributes in self.plant_graph.graph.nodes(data=True) if attributes.get("name") and _normalize(str(attributes["name"])) in query_text]
		nodes: dict[str, dict[str, Any]] = {}
		relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
		documents: set[str] = set()
		for entity_id in entity_ids:
			context = self.plant_graph.get_graph_context(entity_id)
			for node in context.get("nodes", []):
				if isinstance(node, dict) and node.get("entity_id"):
					nodes[str(node["entity_id"])] = dict(node)
					if node.get("entity_type") == "DOCUMENT":
						documents.add(str(node.get("name", node["entity_id"])))
			for relationship in context.get("relationships", []):
				if not isinstance(relationship, dict):
					continue
				key = (str(relationship.get("source", "")), str(relationship.get("target", "")), str(relationship.get("relationship", "")))
				relationships[key] = dict(relationship)
				if relationship.get("document"):
					documents.add(str(relationship["document"]))
		return {"nodes": list(nodes.values()), "relationships": list(relationships.values()), "documents": sorted(documents)}

	def _resolve_entity(self, value: str) -> str | None:
		try:
			if value in self.plant_graph.graph:
				return value
		except TypeError:
			pass
		for entity_id, attributes in self.plant_graph.graph.nodes(data=True):
			if str(attributes.get("name", "")).casefold() == value.casefold():
				return str(entity_id)
		return None

	@staticmethod
	def _matches_filters(record: EvidenceChunk, filters: dict[str, Any]) -> bool:
		for field, expected in filters.items():
			actual = record.get(field, "")
			values = expected if isinstance(expected, (list, tuple, set)) else [expected]
			if str(actual) not in {str(value) for value in values}:
				return False
		return True

	@staticmethod
	def _rank_and_deduplicate(candidates: Sequence[tuple[EvidenceChunk, int]], query: str, entities: list[str], top_k: int) -> list[EvidenceChunk]:
		best: dict[str, tuple[tuple[int, int, int, str], EvidenceChunk]] = {}
		query_text = _normalize(query)
		terms = set(query_text.split())
		for source_index, (candidate, source_rank) in enumerate(candidates):
			record = dict(candidate)
			chunk_id = str(record.get("chunk_id", ""))
			search_text = _normalize(" ".join(str(record.get(field, "")) for field in ("section", "subsection", "text")))
			exact_tag = any(_normalize(entity) and _normalize(entity) in search_text for entity in entities)
			exact_query = bool(query_text and query_text in search_text)
			score = (1000 if exact_tag else 0) + (200 if exact_query else 0) + len(terms.intersection(search_text.split()))
			rank = (0 if exact_tag else source_rank, -score, source_index, chunk_id)
			if chunk_id not in best or rank < best[chunk_id][0]:
				best[chunk_id] = (rank, record)
		ordered = sorted(best.values(), key=lambda item: item[0])
		return [record for _, record in ordered[:top_k]]

	@staticmethod
	def _result(graph_context: dict[str, Any], evidence: list[EvidenceChunk], keyword_count: int, vector_count: int, filters: dict[str, Any], mode: str) -> dict[str, Any]:
		return {"graph_context": graph_context, "evidence": evidence, "retrieval_metadata": {"keyword_count": keyword_count, "vector_count": vector_count, "graph_node_count": len(graph_context["nodes"]), "applied_filters": filters, "retrieval_mode": mode}}


def _normalize(value: str) -> str:
	return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
