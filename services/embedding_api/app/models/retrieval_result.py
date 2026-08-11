from pydantic import BaseModel

from app.models.retrieval_item import RetrievalItem


class RetrievalResult(BaseModel):

    query: str

    total: int

    elapsed_ms: int

    items: list[RetrievalItem]

    #
    # Search Cache : Hitしたかどうか
    #
    # 検索ログ分析（Phase14-6）でCache Hit率を算出するために
    # query_service側まで伝播させる。
    #
    # ENABLE_SEARCH_CACHE=false、またはMiss/未使用の場合は
    # False のまま。
    #

    cache_hit: bool = False