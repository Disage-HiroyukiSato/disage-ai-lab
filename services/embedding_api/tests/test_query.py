from app.models.retrieval_item import RetrievalItem
from app.models.retrieval_result import RetrievalResult
from app.services.query_service import query_service


def create_item(
    document_id,
    chunk_no,
    document,
    distance=0.20,
    score=0.80
):

    return RetrievalItem(
        document=document,
        metadata={
            "document_id": document_id,
            "chunk_no": chunk_no
        },
        distance=distance,
        score=score
    )


def test_query_without_documents(
    monkeypatch
):

    monkeypatch.setattr(
        "app.services.query_service."
        "multi_query_retrieval_service.search",
        lambda question, limit: RetrievalResult(
            query=question,
            total=0,
            elapsed_ms=10,
            items=[]
        )
    )

    result = query_service.ask(
        "javascriptとは"
    )

    assert result["answer"] == (
        "資料から回答できませんでした。"
    )

    assert result["retrieved_count"] == 0
    assert result["documents"] == []


def test_query_does_not_call_llm_without_documents(
    monkeypatch
):

    monkeypatch.setattr(
        "app.services.query_service."
        "multi_query_retrieval_service.search",
        lambda question, limit: RetrievalResult(
            query=question,
            total=0,
            elapsed_ms=10,
            items=[]
        )
    )

    def fail_llm(prompt):

        raise AssertionError(
            "LLM must not be called."
        )

    monkeypatch.setattr(
        "app.services.query_service."
        "llm_service.ask",
        fail_llm
    )

    result = query_service.ask(
        "javascriptとは"
    )

    assert result["retrieved_count"] == 0


def test_query_reranks_after_multi_query_retrieval(
    monkeypatch
):

    item1 = create_item(
        "doc-001",
        1,
        "JavaScriptの説明",
        distance=0.30
    )

    item2 = create_item(
        "doc-002",
        1,
        "JavaScriptの実装方法",
        distance=0.20
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "multi_query_retrieval_service.search",
        lambda question, limit: RetrievalResult(
            query=question,
            total=2,
            elapsed_ms=10,
            items=[
                item1,
                item2
            ]
        )
    )

    def mock_rerank(
        question,
        items,
        limit
    ):

        assert question == "javascript"

        assert len(items) == 2

        items[0].score = 0.90
        items[1].score = 0.80

        return items[:limit]

    monkeypatch.setattr(
        "app.services.query_service."
        "reranker_service.rerank",
        mock_rerank
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "prompt_builder.build",
        lambda question, contexts: (
            f"Question: {question}\n"
            f"Context: {contexts}"
        )
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "llm_service.ask",
        lambda prompt: "JavaScriptについての回答"
    )

    result = query_service.ask(
        "JavaScriptについて教えて"
    )

    assert result["answer"] == (
        "JavaScriptについての回答"
    )

    assert result["retrieved_count"] == 2

    assert len(result["documents"]) == 2


def test_query_does_not_call_llm_when_reranker_returns_empty(
    monkeypatch
):

    item = create_item(
        "doc-001",
        1,
        "JavaScriptの説明"
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "multi_query_retrieval_service.search",
        lambda question, limit: RetrievalResult(
            query=question,
            total=1,
            elapsed_ms=10,
            items=[
                item
            ]
        )
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "reranker_service.rerank",
        lambda question, items, limit: []
    )

    def fail_llm(prompt):

        raise AssertionError(
            "LLM must not be called."
        )

    monkeypatch.setattr(
        "app.services.query_service."
        "llm_service.ask",
        fail_llm
    )

    result = query_service.ask(
        "javascript"
    )

    assert result["answer"] == (
        "資料から回答できませんでした。"
    )

    assert result["retrieved_count"] == 0
    assert result["documents"] == []


def test_query_calls_llm_only_after_reranker(
    monkeypatch
):

    item = create_item(
        "doc-001",
        1,
        "JavaScriptの説明"
    )

    execution_order = []

    monkeypatch.setattr(
        "app.services.query_service."
        "multi_query_retrieval_service.search",
        lambda question, limit: (
            execution_order.append(
                "retrieval"
            )
            or RetrievalResult(
                query=question,
                total=1,
                elapsed_ms=10,
                items=[
                    item
                ]
            )
        )
    )

    def mock_rerank(
        question,
        items,
        limit
    ):

        execution_order.append(
            "reranker"
        )

        return items

    monkeypatch.setattr(
        "app.services.query_service."
        "reranker_service.rerank",
        mock_rerank
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "prompt_builder.build",
        lambda question, contexts: (
            execution_order.append(
                "prompt"
            )
            or "prompt"
        )
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "llm_service.ask",
        lambda prompt: (
            execution_order.append(
                "llm"
            )
            or "answer"
        )
    )

    query_service.ask(
        "javascript"
    )

    assert execution_order == [
        "retrieval",
        "reranker",
        "prompt",
        "llm"
    ]

def test_query_context_uses_reranked_documents(
    monkeypatch
):

    item1 = create_item(
        "doc-001",
        1,
        "検索結果A"
    )

    item2 = create_item(
        "doc-002",
        1,
        "検索結果B"
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "multi_query_retrieval_service.search",
        lambda question, limit: RetrievalResult(
            query=question,
            total=2,
            elapsed_ms=10,
            items=[
                item1,
                item2
            ]
        )
    )

    def mock_rerank(
        question,
        items,
        limit
    ):

        return [
            item2,
            item1
        ]

    monkeypatch.setattr(
        "app.services.query_service."
        "reranker_service.rerank",
        mock_rerank
    )

    captured = {}

    def mock_prompt_build(
        question,
        contexts
    ):

        captured["question"] = question
        captured["contexts"] = contexts

        return "test prompt"

    monkeypatch.setattr(
        "app.services.query_service."
        "prompt_builder.build",
        mock_prompt_build
    )

    monkeypatch.setattr(
        "app.services.query_service."
        "llm_service.ask",
        lambda prompt: "test answer"
    )

    query_service.ask(
        "javascriptについて教えて"
    )

    assert captured["question"] == "javascriptについて教えて"

    assert captured["contexts"] == [
        "検索結果B",
        "検索結果A"
    ]