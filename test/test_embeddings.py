from unittest.mock import Mock

import pytest

from src.retrieval import embeddings as embeddings_module
from src.retrieval.embeddings import AzureOpenAIEmbeddingsProvider, FakeEmbeddingsProvider


def test_fake_provider_is_deterministic_and_supports_batches():
	provider = FakeEmbeddingsProvider(dimension=4)

	first = provider.embed_documents(["Unit-400 temperature", "SIF-05"])
	second = provider.embed_documents(["Unit-400 temperature", "SIF-05"])

	assert first == second
	assert len(first) == 2
	assert all(len(vector) == 4 for vector in first)
	assert provider.embed_query("Unit-400 temperature") == first[0]


def test_azure_provider_validates_dimensions_and_uses_batch_api():
	embeddings = Mock()
	embeddings.embed_documents.return_value = [[1, 2, 3], [4, 5, 6]]
	provider = AzureOpenAIEmbeddingsProvider(embeddings=embeddings, expected_dimension=3)

	result = provider.embed_documents(["first", "second"])

	assert result == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
	embeddings.embed_documents.assert_called_once_with(["first", "second"])


def test_azure_provider_rejects_empty_text_and_bad_vectors():
	embeddings = Mock()
	embeddings.embed_query.return_value = [1, 2]
	provider = AzureOpenAIEmbeddingsProvider(embeddings=embeddings, expected_dimension=3)

	with pytest.raises(ValueError, match="non-empty"):
		provider.embed_query(" ")
	with pytest.raises(ValueError, match="dimension"):
		provider.embed_query("query")


def test_fake_provider_rejects_empty_batch():
	provider = FakeEmbeddingsProvider()

	with pytest.raises(ValueError, match="non-empty list"):
		provider.embed_documents([])


def test_azure_configuration_is_read_from_environment(monkeypatch):
	created = {}

	class FakeAzureEmbeddings:
		def __init__(self, **kwargs):
			created.update(kwargs)

	monkeypatch.setattr(embeddings_module, "AzureOpenAIEmbeddings", FakeAzureEmbeddings)
	monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
	monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "embedding-deployment")
	monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
	monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

	AzureOpenAIEmbeddingsProvider(expected_dimension=3)

	assert created["azure_endpoint"] == "https://example.openai.azure.com"
	assert created["azure_deployment"] == "embedding-deployment"
	assert created["api_version"] == "2024-10-21"
	assert "api_key" not in created
	assert callable(created["azure_ad_token_provider"])