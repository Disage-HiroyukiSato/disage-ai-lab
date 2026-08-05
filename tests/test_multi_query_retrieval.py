from app.models.retrieval_item import RetrievalItem
from app.models.retrieval_result import RetrievalResult
from app.services.multi_query_retrieval_service import (
    multi_query_retrieval_service
)


def create_item(
    document_id,
    chunk_no,
    document,
    distance
):
    return RetrievalItem(
        document=document,
        metadata={
            "document_id": document_id,
            "chunk_no": chunk_no
        },
        distance=distance
    )


def test_single_query_retrieval(monkeypatch):

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "query_expansion_service.expand",
        lambda question: [
            question
        ]
    )

    item = create_item(
        "doc-001",
        1,
        "JavaScriptの説明",
        0.20
    )

    def mock_search(
        question,
        limit,
        document_id=None,
        category=None,
        title=None,
        keywords=None
    ):
        return RetrievalResult(
            query=question,
            total=1,
            elapsed_ms=10,
            items=[
                item
            ]
        )

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "retrieval_service.search",
        mock_search
    )

    result = multi_query_retrieval_service.search(
        "javascript",
        limit=5
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].document == "JavaScriptの説明"


def test_multiple_queries_are_merged(monkeypatch):

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "query_expansion_service.expand",
        lambda question: [
            "javascript",
            "js",
            "java script"
        ]
    )

    items = {
        "javascript": create_item(
            "doc-001",
            1,
            "JavaScriptの説明",
            0.20
        ),
        "js": create_item(
            "doc-002",
            1,
            "JSの説明",
            0.30
        ),
        "java script": create_item(
            "doc-003",
            1,
            "Java Scriptの説明",
            0.40
        )
    }

    def mock_search(
        question,
        limit,
        document_id=None,
        category=None,
        title=None,
        keywords=None
    ):
        item = items[question]

        return RetrievalResult(
            query=question,
            total=1,
            elapsed_ms=10,
            items=[item]
        )

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "retrieval_service.search",
        mock_search
    )

    result = multi_query_retrieval_service.search(
        "javascript",
        limit=10
    )

    assert result.total == 3

    documents = [
        item.document
        for item in result.items
    ]

    assert "JavaScriptの説明" in documents
    assert "JSの説明" in documents
    assert "Java Scriptの説明" in documents


def test_duplicate_chunks_are_removed(monkeypatch):

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "query_expansion_service.expand",
        lambda question: [
            "javascript",
            "js"
        ]
    )

    item_from_first_query = create_item(
        "doc-001",
        1,
        "JavaScriptの説明",
        0.30
    )

    item_from_second_query = create_item(
        "doc-001",
        1,
        "JavaScriptの説明",
        0.20
    )

    call_count = {
        "value": 0
    }

    def mock_search(
        question,
        limit,
        document_id=None,
        category=None,
        title=None,
        keywords=None
    ):

        if call_count["value"] == 0:

            item = item_from_first_query

        else:

            item = item_from_second_query

        call_count["value"] += 1

        return RetrievalResult(
            query=question,
            total=1,
            elapsed_ms=10,
            items=[
                item
            ]
        )

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "retrieval_service.search",
        mock_search
    )

    result = multi_query_retrieval_service.search(
        "javascript",
        limit=10
    )

    assert result.total == 1

    assert result.items[0].distance == 0.20


def test_fallback_duplicate_removal_without_metadata(
    monkeypatch
):

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "query_expansion_service.expand",
        lambda question: [
            "javascript",
            "js"
        ]
    )

    item1 = RetrievalItem(
        document="同じドキュメント",
        metadata={},
        distance=0.30
    )

    item2 = RetrievalItem(
        document="同じドキュメント",
        metadata={},
        distance=0.20
    )

    call_count = {
        "value": 0
    }

    def mock_search(
        question,
        limit,
        document_id=None,
        category=None,
        title=None,
        keywords=None
    ):

        if call_count["value"] == 0:

            item = item1

        else:

            item = item2

        call_count["value"] += 1

        return RetrievalResult(
            query=question,
            total=1,
            elapsed_ms=10,
            items=[
                item
            ]
        )

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "retrieval_service.search",
        mock_search
    )

    result = multi_query_retrieval_service.search(
        "javascript",
        limit=10
    )

    assert result.total == 1
    assert result.items[0].distance == 0.20


def test_distance_order_is_preserved_after_merge(
    monkeypatch
):

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "query_expansion_service.expand",
        lambda question: [
            "javascript",
            "js"
        ]
    )

    item1 = create_item(
        "doc-001",
        1,
        "Document 1",
        0.50
    )

    item2 = create_item(
        "doc-002",
        1,
        "Document 2",
        0.20
    )

    def mock_search(
        question,
        limit,
        document_id=None,
        category=None,
        title=None,
        keywords=None
    ):

        if question == "javascript":

            item = item1

        else:

            item = item2

        return RetrievalResult(
            query=question,
            total=1,
            elapsed_ms=10,
            items=[
                item
            ]
        )

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "retrieval_service.search",
        mock_search
    )

    result = multi_query_retrieval_service.search(
        "javascript",
        limit=10
    )

    assert result.items[0].distance == 0.20
    assert result.items[1].distance == 0.50


def test_limit_is_applied(monkeypatch):

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "query_expansion_service.expand",
        lambda question: [
            "javascript",
            "js",
            "java script"
        ]
    )

    def mock_search(
        question,
        limit,
        document_id=None,
        category=None,
        title=None,
        keywords=None
    ):

        return RetrievalResult(
            query=question,
            total=2,
            elapsed_ms=10,
            items=[
                create_item(
                    question,
                    1,
                    f"{question} document 1",
                    0.20
                ),
                create_item(
                    question,
                    2,
                    f"{question} document 2",
                    0.30
                )
            ]
        )

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "retrieval_service.search",
        mock_search
    )

    result = multi_query_retrieval_service.search(
        "javascript",
        limit=3
    )

    assert result.total == 3


def test_no_results(monkeypatch):

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "query_expansion_service.expand",
        lambda question: [
            "javascript",
            "js"
        ]
    )

    def mock_search(
        question,
        limit,
        document_id=None,
        category=None,
        title=None,
        keywords=None
    ):

        return RetrievalResult(
            query=question,
            total=0,
            elapsed_ms=10,
            items=[]
        )

    monkeypatch.setattr(
        "app.services.multi_query_retrieval_service."
        "retrieval_service.search",
        mock_search
    )

    result = multi_query_retrieval_service.search(
        "javascript",
        limit=5
    )

    assert result.total == 0
    assert result.items == []