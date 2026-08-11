from typing import Any

from pydantic import BaseModel
from pydantic import Field


class RetrievalItem(BaseModel):

    document: str

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    distance: float

    score: float = 0.0

    #
    # Hybrid Search
    #
    # BM25 score と Vector類似度を正規化・合成した値。
    #
    # ENABLE_HYBRID_SEARCH=false の場合は 0.0 のまま。
    #
    # Reranker実行後に上書きされる score とは役割が異なるため、
    # 別フィールドとして分離する。
    #

    hybrid_score: float = 0.0

    #
    # Hybrid Search : 内訳スコア
    #
    # 検索ログ分析（Phase14-6）でVector/BM25それぞれの
    # 寄与度を確認できるように、正規化前の値を保持する。
    #
    # bm25_raw_score      : BM25の生スコア（正規化前）
    # vector_similarity   : Vector類似度 (1 - distance)（正規化前）
    #
    # ENABLE_HYBRID_SEARCH=false の場合は 0.0 のまま。
    #

    bm25_raw_score: float = 0.0

    vector_similarity: float = 0.0