"""Embedding provider interfaces and Azure OpenAI implementation for EDOCA."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from langchain_openai import AzureOpenAIEmbeddings


class EmbeddingsProvider(Protocol):
	"""Provider boundary used by Azure AI Search vector indexing and retrieval."""

	def embed_documents(self, texts: list[str]) -> list[list[float]]:
		"""Embed a batch of document texts."""

	def embed_query(self, query: str) -> list[float]:
		"""Embed one search query."""


class AzureOpenAIEmbeddingsProvider:
	"""Validate and expose LangChain Azure OpenAI embeddings for EDOCA."""

	def __init__(
		self,
		embeddings: Any | None = None,
		expected_dimension: int | None = None,
		model: str | None = None,
	) -> None:
		self.expected_dimension = expected_dimension or int(
			os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", os.getenv("EDOCA_VECTOR_DIMENSIONS", "1536"))
		)
		if self.expected_dimension <= 0:
			raise ValueError("expected_dimension must be greater than zero")
		self.embeddings = embeddings or _create_azure_embeddings(model)

	def embed_documents(self, texts: list[str]) -> list[list[float]]:
		"""Embed a non-empty batch and validate every returned vector."""
		_validate_texts(texts)
		vectors = self.embeddings.embed_documents(texts)
		return _validate_vectors(vectors, self.expected_dimension)

	def embed_query(self, query: str) -> list[float]:
		"""Embed one non-empty query and validate its vector dimension."""
		_validate_text(query, "query")
		vector = self.embeddings.embed_query(query)
		validated = _validate_vectors([vector], self.expected_dimension)
		return validated[0]


class FakeEmbeddingsProvider:
	"""Deterministic, network-free embedding provider for tests and local demos."""

	def __init__(self, dimension: int = 8) -> None:
		if dimension <= 0:
			raise ValueError("dimension must be greater than zero")
		self.dimension = dimension

	def embed_documents(self, texts: list[str]) -> list[list[float]]:
		_validate_texts(texts)
		return [self._embed(text) for text in texts]

	def embed_query(self, query: str) -> list[float]:
		_validate_text(query, "query")
		return self._embed(query)

	def _embed(self, text: str) -> list[float]:
		digest = hashlib.sha256(text.encode("utf-8")).digest()
		return [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(self.dimension)]


def _create_azure_embeddings(model: str | None) -> AzureOpenAIEmbeddings:
	endpoint = _required_env("AZURE_OPENAI_ENDPOINT")
	deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
	if not deployment:
		raise RuntimeError(
			"Missing required environment variable: AZURE_OPENAI_EMBEDDING_DEPLOYMENT "
			"or AZURE_OPENAI_DEPLOYMENT_NAME"
		)
	api_version = _required_env("AZURE_OPENAI_API_VERSION")
	api_key = os.getenv("AZURE_OPENAI_API_KEY")
	kwargs: dict[str, Any] = {
		"azure_endpoint": endpoint,
		"azure_deployment": deployment,
		"api_version": api_version,
		"model": model or os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
	}
	if api_key:
		kwargs["api_key"] = api_key
	else:
		credential = DefaultAzureCredential()
		kwargs["azure_ad_token_provider"] = lambda: credential.get_token(
			"https://cognitiveservices.azure.com/.default"
		).token
	return AzureOpenAIEmbeddings(**kwargs)


def _required_env(name: str) -> str:
	value = os.getenv(name)
	if not value:
		raise RuntimeError(f"Missing required environment variable: {name}")
	return value


def _validate_text(text: str, label: str) -> None:
	if not isinstance(text, str) or not text.strip():
		raise ValueError(f"{label} must be a non-empty string")


def _validate_texts(texts: list[str]) -> None:
	if not isinstance(texts, list) or not texts:
		raise ValueError("texts must be a non-empty list")
	for index, text in enumerate(texts):
		_validate_text(text, f"texts[{index}]")


def _validate_vectors(vectors: Any, expected_dimension: int) -> list[list[float]]:
	if not isinstance(vectors, list):
		raise ValueError("embedding provider must return a list of vectors")
	validated: list[list[float]] = []
	for index, vector in enumerate(vectors):
		if not isinstance(vector, list) or len(vector) != expected_dimension:
			raise ValueError(
				f"embedding vector {index} has dimension {len(vector) if isinstance(vector, list) else 'invalid'}; "
				f"expected {expected_dimension}"
			)
		if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector):
			raise ValueError(f"embedding vector {index} contains a non-numeric value")
		validated.append([float(value) for value in vector])
	return validated