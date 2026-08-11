from pathlib import Path

import pytest

from app.services.bm25_service import BM25Service


@pytest.fixture
def bm25(tmp_path, monkeypatch):

    index_path = tmp_path / "index.json"

    monkeypatch.setattr(
        BM25Service,
        "INDEX_PATH",
        index_path
    )

    return BM25Service()


def test_search_without_documents_returns_empty(
    bm25
):

    result = bm25.search(
        "検索"
    )

    assert result == []


def test_add_and_search(
    bm25
):

    bm25.add(
        chunk_id="chunk-1",
        text="これは検索機能について説明する文書です。",
        metadata={
            "title": "検索機能",
            "category": "manual"
        }
    )

    result = bm25.search(
        "検索機能"
    )

    assert len(result) == 1

    assert result[0]["chunk_id"] == "chunk-1"

    assert result[0]["document"] == (
        "これは検索機能について説明する文書です。"
    )

    assert result[0]["metadata"]["title"] == "検索機能"

    assert result[0]["score"] > 0


def test_relevant_document_has_higher_score(
    bm25
):

    bm25.add(
        chunk_id="chunk-1",
        text="PythonによるWeb API開発について説明します。",
    )

    bm25.add(
        chunk_id="chunk-2",
        text="データベースのバックアップ手順について説明します。",
    )

    result = bm25.search(
        "Python Web API"
    )

    assert len(result) >= 1

    assert result[0]["chunk_id"] == "chunk-1"

    assert result[0]["score"] > 0


def test_limit_is_applied(
    bm25
):

    bm25.add(
        chunk_id="chunk-1",
        text="Python Web API 開発",
    )

    bm25.add(
        chunk_id="chunk-2",
        text="Python Web API 設計",
    )

    bm25.add(
        chunk_id="chunk-3",
        text="Python Web API テスト",
    )

    result = bm25.search(
        "Python Web API",
        limit=2
    )

    assert len(result) == 2


def test_japanese_bigram_search(
    bm25
):

    bm25.add(
        chunk_id="chunk-1",
        text="検索機能を提供するシステムです。",
    )

    result = bm25.search(
        "検索"
    )

    assert len(result) == 1

    assert result[0]["chunk_id"] == "chunk-1"

    assert result[0]["score"] > 0


def test_duplicate_chunk_id_updates_document(
    bm25
):

    bm25.add(
        chunk_id="chunk-1",
        text="古い検索機能の説明です。",
    )

    bm25.add(
        chunk_id="chunk-1",
        text="新しいデータベース機能の説明です。",
    )

    result = bm25.search(
        "データベース"
    )

    assert len(result) == 1

    assert result[0]["chunk_id"] == "chunk-1"

    assert result[0]["document"] == (
        "新しいデータベース機能の説明です。"
    )


def test_remove_document(
    bm25
):

    bm25.add(
        chunk_id="chunk-1",
        text="検索機能の説明です。",
    )

    assert len(
        bm25.search("検索")
    ) == 1

    bm25.remove(
        "chunk-1"
    )

    assert bm25.search(
        "検索"
    ) == []


def test_remove_nonexistent_document(
    bm25
):

    bm25.remove(
        "not-exists"
    )

    assert bm25.search(
        "検索"
    ) == []


def test_add_rejects_empty_chunk_id(
    bm25
):

    with pytest.raises(
        ValueError,
        match="chunk_id must not be empty"
    ):

        bm25.add(
            chunk_id="",
            text="検索機能"
        )


def test_add_rejects_empty_text(
    bm25
):

    with pytest.raises(
        ValueError,
        match="text must not be empty"
    ):

        bm25.add(
            chunk_id="chunk-1",
            text=""
        )


def test_empty_query_returns_empty(
    bm25
):

    bm25.add(
        chunk_id="chunk-1",
        text="検索機能の説明です。",
    )

    assert bm25.search(
        ""
    ) == []


def test_metadata_is_preserved(
    bm25
):

    metadata = {
        "document_id": "doc-001",
        "chunk_no": 1,
        "title": "検索マニュアル",
        "category": "manual",
        "keywords": "検索,API"
    }

    bm25.add(
        chunk_id="chunk-1",
        text="検索APIの使用方法です。",
        metadata=metadata
    )

    result = bm25.search(
        "検索API"
    )

    assert len(result) == 1

    assert result[0]["metadata"] == metadata