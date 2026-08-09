from app.models.retrieval_item import RetrievalItem
from app.services.reranker_service import reranker_service


class MockCrossEncoder:

    def __init__(self, scores):

        self.scores = scores
        self.called_pairs = None

    def predict(
        self,
        pairs,
        batch_size=16,
        show_progress_bar=False
    ):

        self.called_pairs = pairs

        return self.scores


def create_item(
    document,
    distance=0.20
):

    return RetrievalItem(
        document=document,
        metadata={
            "document_id": "doc-001",
            "chunk_no": 1
        },
        distance=distance
    )


def test_empty_items():

    result = reranker_service.rerank(
        question="javascriptとは",
        items=[],
        limit=5
    )

    assert result == []


def test_rerank_orders_by_score(monkeypatch):

    mock_model = MockCrossEncoder(
        [
            0.20,
            0.90,
            0.50
        ]
    )

    monkeypatch.setattr(
        reranker_service,
        "model",
        mock_model
    )

    items = [
        create_item("Document A"),
        create_item("Document B"),
        create_item("Document C")
    ]

    monkeypatch.setattr(
        "app.services.reranker_service.settings."
        "min_rerank_score",
        0.0
    )

    result = reranker_service.rerank(
        question="javascript",
        items=items,
        limit=5
    )

    assert len(result) == 3

    assert result[0].document == "Document B"
    assert result[1].document == "Document C"
    assert result[2].document == "Document A"

    assert result[0].score == 0.90
    assert result[1].score == 0.50
    assert result[2].score == 0.20


def test_min_rerank_score_filters_results(
    monkeypatch
):

    mock_model = MockCrossEncoder(
        [
            0.20,
            0.80,
            0.40
        ]
    )

    monkeypatch.setattr(
        reranker_service,
        "model",
        mock_model
    )

    monkeypatch.setattr(
        "app.services.reranker_service.settings."
        "min_rerank_score",
        0.50
    )

    items = [
        create_item("Document A"),
        create_item("Document B"),
        create_item("Document C")
    ]

    result = reranker_service.rerank(
        question="javascript",
        items=items,
        limit=5
    )

    assert len(result) == 1

    assert result[0].document == "Document B"
    assert result[0].score == 0.80


def test_limit_is_applied_after_score_filter(
    monkeypatch
):

    mock_model = MockCrossEncoder(
        [
            0.90,
            0.80,
            0.70,
            0.60
        ]
    )

    monkeypatch.setattr(
        reranker_service,
        "model",
        mock_model
    )

    monkeypatch.setattr(
        "app.services.reranker_service.settings."
        "min_rerank_score",
        0.50
    )

    items = [
        create_item("Document A"),
        create_item("Document B"),
        create_item("Document C"),
        create_item("Document D")
    ]

    result = reranker_service.rerank(
        question="javascript",
        items=items,
        limit=2
    )

    assert len(result) == 2

    assert result[0].score == 0.90
    assert result[1].score == 0.80


def test_reranker_receives_question_and_documents(
    monkeypatch
):

    mock_model = MockCrossEncoder(
        [
            0.80,
            0.70
        ]
    )

    monkeypatch.setattr(
        reranker_service,
        "model",
        mock_model
    )

    monkeypatch.setattr(
        "app.services.reranker_service.settings."
        "min_rerank_score",
        0.0
    )

    items = [
        create_item("Document A"),
        create_item("Document B")
    ]

    reranker_service.rerank(
        question="javascript",
        items=items,
        limit=5
    )

    assert mock_model.called_pairs == [
        (
            "javascript",
            "Document A"
        ),
        (
            "javascript",
            "Document B"
        )
    ]