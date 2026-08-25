from unittest.mock import Mock

import pytest

from src.retrieval.azure_search import AzureSearchIndexManager, AzureSearchRetriever, build_edoca_index


def azure_result():
    return {
        "chunk_id": "c1",
        "document_id": "DOC-1",
        "document_type": "process",
        "section": "Unit 400",
        "subsection": "Temperature",
        "text": "Operating value is 621 C.",
        "source_type": "table",
        "entities": ["Unit-400"],
        "revision": "A",
        "page_reference": "12",
        "content_vector": [0.1, 0.2],
    }


def test_index_schema_contains_required_fields_without_live_connection():
    index = build_edoca_index("edoca", vector_dimensions=2)

    assert {field.name for field in index.fields} == {
        "chunk_id", "document_id", "document_type", "section", "subsection", "text",
        "source_type", "entities", "revision", "page_reference", "content_vector",
    }


def test_upload_and_search_return_evidence_contract():
    client = Mock()
    client.upload_documents.return_value = [{"key": "c1", "succeeded": True}]
    client.search.return_value = [azure_result()]
    retriever = AzureSearchRetriever(search_client=client)

    upload_result = retriever.upload_chunks([azure_result()])
    evidence = retriever.keyword_search("temperature", {"document_type": "process"})

    assert upload_result[0]["succeeded"] is True
    assert evidence == [{key: azure_result()[key] for key in ("chunk_id", "document_id", "document_type", "section", "subsection", "text", "source_type")}]
    assert client.search.call_args.kwargs["filter"] == "document_type eq 'process'"


def test_vector_and_hybrid_search_use_vector_queries():
    client = Mock()
    client.search.return_value = [azure_result()]
    retriever = AzureSearchRetriever(search_client=client)

    retriever.vector_search([0.1, 0.2], top_k=3)
    vector_query = client.search.call_args.kwargs["vector_queries"][0]
    assert vector_query.k_nearest_neighbors == 3
    assert vector_query.fields == "content_vector"

    retriever.hybrid_search("temperature", [0.1, 0.2])
    assert client.search.call_args.kwargs["search_text"] == "temperature"


def test_filters_are_validated_and_index_manager_is_injectable():
    retriever = AzureSearchRetriever(search_client=Mock())
    with pytest.raises(ValueError, match="Unsupported metadata filter"):
        retriever.build_filter({"text": "unsafe"})

    index_client = Mock()
    index_client.create_or_update_index.side_effect = lambda index: index
    created = AzureSearchIndexManager(index_client=index_client).create_index("edoca", 2)
    assert created.name == "edoca"
    index_client.create_or_update_index.assert_called_once()