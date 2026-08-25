"""Azure AI Search adapters for EDOCA evidence retrieval."""

from __future__ import annotations

import os
from typing import Any, Protocol, Sequence

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
	HnswAlgorithmConfiguration,
	SearchField,
	SearchFieldDataType,
	SearchIndex,
	SearchableField,
	SimpleField,
	VectorSearch,
	VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from src.knowledge.evidence_index import EvidenceChunk


class IndexCreationPort(Protocol):
	"""Interface for creating or updating a search index."""

	def create_or_update_index(self, index: SearchIndex) -> SearchIndex:
		"""Create or update an Azure AI Search index."""


class ChunkUploadPort(Protocol):
	"""Interface for uploading normalized engineering chunks."""

	def upload_chunks(self, chunks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
		"""Upload chunks and return the service response."""


class KeywordSearchPort(Protocol):
	"""Interface for lexical search."""

	def keyword_search(self, query: str, filters: dict[str, Any] | None = None, top_k: int = 10) -> list[EvidenceChunk]:
		"""Search indexed evidence by keyword."""


class VectorSearchPort(Protocol):
	"""Interface for vector search."""

	def vector_search(self, query_vector: Sequence[float], filters: dict[str, Any] | None = None, top_k: int = 10) -> list[EvidenceChunk]:
		"""Search indexed evidence by vector similarity."""


class HybridSearchPort(Protocol):
	"""Interface for combined lexical and vector search."""

	def hybrid_search(self, query: str, query_vector: Sequence[float], filters: dict[str, Any] | None = None, top_k: int = 10) -> list[EvidenceChunk]:
		"""Search indexed evidence using lexical and vector signals."""


class MetadataFilterPort(Protocol):
	"""Interface for translating safe metadata filters to OData."""

	def build_filter(self, filters: dict[str, Any] | None = None) -> str | None:
		"""Build an OData filter from supported metadata fields."""


class AzureSearchIndexManager:
	"""Create the EDOCA Azure AI Search index through an injected client."""

	def __init__(self, index_client: SearchIndexClient | IndexCreationPort | None = None) -> None:
		self.index_client = index_client or _create_index_client()

	def create_index(self, index_name: str | None = None, vector_dimensions: int | None = None) -> SearchIndex:
		"""Create or update the index using the EDOCA document schema."""
		index = build_edoca_index(
			index_name or _required_env("AZURE_SEARCH_INDEX_NAME"),
			vector_dimensions or int(os.getenv("EDOCA_VECTOR_DIMENSIONS", "1536")),
		)
		return self.index_client.create_or_update_index(index)


class AzureSearchRetriever(ChunkUploadPort, KeywordSearchPort, VectorSearchPort, HybridSearchPort, MetadataFilterPort):
	"""Azure-backed retrieval adapter with injectable SearchClient."""

	FILTERABLE_FIELDS = {"document_id", "document_type", "section", "subsection", "source_type", "revision", "page_reference"}

	def __init__(
		self,
		search_client: SearchClient | None = None,
		endpoint: str | None = None,
		index_name: str | None = None,
		api_key: str | None = None,
		credential: Any | None = None,
	) -> None:
		self.search_client = search_client or _create_search_client(endpoint, index_name, api_key, credential)

	def upload_chunks(self, chunks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
		"""Upload chunks while retaining all fields in the Azure index schema."""
		documents = [_to_search_document(chunk) for chunk in chunks]
		if not documents:
			return []
		results = self.search_client.upload_documents(documents=documents)
		return [_result_to_dict(result) for result in results]

	def keyword_search(self, query: str, filters: dict[str, Any] | None = None, top_k: int = 10) -> list[EvidenceChunk]:
		return self._search(query, filters, top_k)

	def vector_search(self, query_vector: Sequence[float], filters: dict[str, Any] | None = None, top_k: int = 10) -> list[EvidenceChunk]:
		vector_query = VectorizedQuery(vector=list(query_vector), k_nearest_neighbors=top_k, fields="content_vector")
		return self._search(None, filters, top_k, [vector_query])

	def hybrid_search(self, query: str, query_vector: Sequence[float], filters: dict[str, Any] | None = None, top_k: int = 10) -> list[EvidenceChunk]:
		vector_query = VectorizedQuery(vector=list(query_vector), k_nearest_neighbors=top_k, fields="content_vector")
		return self._search(query, filters, top_k, [vector_query])

	def build_filter(self, filters: dict[str, Any] | None = None) -> str | None:
		if not filters:
			return None
		parts: list[str] = []
		for field, value in filters.items():
			if field not in self.FILTERABLE_FIELDS:
				raise ValueError(f"Unsupported metadata filter field: {field}")
			values = value if isinstance(value, (list, tuple, set)) else [value]
			conditions = [f"{field} eq '{_escape_filter_value(item)}'" for item in values]
			parts.append(conditions[0] if len(conditions) == 1 else "(" + " or ".join(conditions) + ")")
		return " and ".join(parts)

	def _search(
		self,
		query: str | None,
		filters: dict[str, Any] | None,
		top_k: int,
		vector_queries: list[VectorizedQuery] | None = None,
	) -> list[EvidenceChunk]:
		if top_k <= 0:
			raise ValueError("top_k must be greater than zero")
		results = self.search_client.search(
			search_text=query,
			filter=self.build_filter(filters),
			top=top_k,
			vector_queries=vector_queries,
		)
		return [_to_evidence_chunk(result) for result in results]


def build_edoca_index(index_name: str, vector_dimensions: int = 1536) -> SearchIndex:
	"""Build the EDOCA Azure index definition without contacting Azure."""
	if vector_dimensions <= 0:
		raise ValueError("vector_dimensions must be greater than zero")
	fields = [
		SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True, filterable=True),
		SearchableField(name="document_id", type=SearchFieldDataType.String, filterable=True),
		SearchableField(name="document_type", type=SearchFieldDataType.String, filterable=True),
		SearchableField(name="section", type=SearchFieldDataType.String, filterable=True),
		SearchableField(name="subsection", type=SearchFieldDataType.String, filterable=True),
		SearchableField(name="text", type=SearchFieldDataType.String),
		SimpleField(name="source_type", type=SearchFieldDataType.String, filterable=True),
		SearchField(name="entities", type=SearchFieldDataType.Collection(SearchFieldDataType.String), searchable=True, filterable=True),
		SimpleField(name="revision", type=SearchFieldDataType.String, filterable=True),
		SimpleField(name="page_reference", type=SearchFieldDataType.String, filterable=True),
		SearchField(name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), searchable=True, vector_search_dimensions=vector_dimensions, vector_search_profile_name="edoca-vector-profile"),
	]
	return SearchIndex(
		name=index_name,
		fields=fields,
		vector_search=VectorSearch(
			algorithms=[HnswAlgorithmConfiguration(name="edoca-hnsw")],
			profiles=[VectorSearchProfile(name="edoca-vector-profile", algorithm_configuration_name="edoca-hnsw")],
		),
	)


def _create_search_client(endpoint: str | None, index_name: str | None, api_key: str | None, credential: Any | None) -> SearchClient:
	endpoint = endpoint or _required_env("AZURE_SEARCH_ENDPOINT")
	index_name = index_name or _required_env("AZURE_SEARCH_INDEX_NAME")
	api_key = api_key or os.getenv("AZURE_SEARCH_API_KEY")
	if api_key:
		credential = AzureKeyCredential(api_key)
	else:
		credential = credential or DefaultAzureCredential()
	return SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)


def _create_index_client() -> SearchIndexClient:
	endpoint = _required_env("AZURE_SEARCH_ENDPOINT")
	api_key = os.getenv("AZURE_SEARCH_API_KEY")
	credential = AzureKeyCredential(api_key) if api_key else DefaultAzureCredential()
	return SearchIndexClient(endpoint=endpoint, credential=credential)


def _required_env(name: str) -> str:
	value = os.getenv(name)
	if not value:
		raise RuntimeError(f"Missing required environment variable: {name}")
	return value


def _escape_filter_value(value: Any) -> str:
	return str(value).replace("'", "''")


def _to_search_document(chunk: dict[str, Any]) -> dict[str, Any]:
	return {
		"chunk_id": str(chunk.get("chunk_id", "")),
		"document_id": str(chunk.get("document_id", "")),
		"document_type": str(chunk.get("document_type", "")),
		"section": str(chunk.get("section", "")),
		"subsection": str(chunk.get("subsection", "")),
		"text": str(chunk.get("text", "")),
		"source_type": str(chunk.get("source_type", "")),
		"entities": list(chunk.get("entities", [])),
		"revision": str(chunk.get("revision", "")),
		"page_reference": str(chunk.get("page_reference", "")),
		"content_vector": list(chunk.get("content_vector", [])),
	}


def _to_evidence_chunk(result: Any) -> EvidenceChunk:
	return {
		"chunk_id": str(result.get("chunk_id", "")),
		"document_id": str(result.get("document_id", "")),
		"document_type": str(result.get("document_type", "")),
		"section": str(result.get("section", "")),
		"subsection": str(result.get("subsection", "")),
		"text": str(result.get("text", "")),
		"source_type": str(result.get("source_type", "")),
	}


def _result_to_dict(result: Any) -> dict[str, Any]:
	if isinstance(result, dict):
		return dict(result)
	return {"key": getattr(result, "key", None), "succeeded": getattr(result, "succeeded", None), "error_message": getattr(result, "error_message", None)}