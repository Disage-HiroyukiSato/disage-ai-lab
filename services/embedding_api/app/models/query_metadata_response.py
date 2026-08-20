from pydantic import BaseModel


class QueryMetadataResponse(BaseModel):

    query_analysis_elapsed_ms: int = 0

    retrieval_elapsed_ms: int = 0

    answerability_elapsed_ms: int = 0

    llm_elapsed_ms: int = 0

    total_elapsed_ms: int = 0

    cache_hit: bool = False

    fallback_used: bool = False

    retrieved_count: int = 0

    gate_candidate_count: int = 0

    final_context_count: int = 0