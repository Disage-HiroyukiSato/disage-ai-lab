from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):

    #
    # Embedding
    #

    embedding_model: str

    #
    # Chunk
    #

    chunk_size: int

    chunk_overlap: int

    #
    # ChromaDB
    #

    chroma_host: str

    chroma_port: int

    chroma_collection: str

    request_timeout: int

    #
    # Phase16 : 複数コレクション対応
    #

    collection_java_training: str = Field(

        default="java_training",

        alias="COLLECTION_JAVA_TRAINING"

    )

    collection_instructor_ops: str = Field(

        default="instructor_ops",

        alias="COLLECTION_INSTRUCTOR_OPS"

    )

    #
    # LLM
    #

    llm_url: str

    llm_api_url: str

    llm_health_url: str

    llm_timeout: int

    temperature: float

    top_p: float

    repeat_penalty: float

    max_tokens: int

    #
    # Retrieval
    #

    retrieval_candidate_size: int

    default_limit: int

    max_distance: float

    #
    # Reranker
    #

    rerank_model: str

    min_rerank_score: float = Field(

        default=0.30,

        alias="MIN_RERANK_SCORE"

    )

    #
    # Query Expansion
    #

    enable_query_expansion: bool = Field(

        default=False,

        alias="ENABLE_QUERY_EXPANSION"

    )

    expansion_limit: int = Field(

        default=3,

        alias="EXPANSION_LIMIT"

    )

    query_dictionary: str = Field(

        default="/app/config/query_dictionary.json",

        alias="QUERY_DICTIONARY"

    )

    #
    # Hybrid Search
    #

    enable_hybrid_search: bool = Field(

        default=False,

        alias="ENABLE_HYBRID_SEARCH"

    )

    bm25_weight: float = Field(

        default=0.30,

        alias="BM25_WEIGHT"

    )

    vector_weight: float = Field(

        default=0.70,

        alias="VECTOR_WEIGHT"

    )

    #
    # Search Cache
    #

    enable_search_cache: bool = Field(

        default=False,

        alias="ENABLE_SEARCH_CACHE"

    )

    redis_host: str = Field(

        default="redis",

        alias="REDIS_HOST"

    )

    redis_port: int = Field(

        default=6379,

        alias="REDIS_PORT"

    )

    redis_db: int = Field(

        default=1,

        alias="REDIS_DB"

    )

    cache_ttl: int = Field(

        default=300,

        alias="CACHE_TTL"

    )

    cache_key_prefix: str = Field(

        default="disage:retrieval:",

        alias="CACHE_KEY_PREFIX"

    )

    #
    # Phase16 : Collection Router
    #

    collection_router_dictionary: str = Field(

        default="/app/config/collection_router_dictionary.json",

        alias="COLLECTION_ROUTER_DICTIONARY"

    )

    #
    # Phase17 : PostgreSQL（進捗管理・会話履歴）
    #

    postgres_host: str = Field(

        default="postgres",

        alias="POSTGRES_HOST"

    )

    postgres_port: int = Field(

        default=5432,

        alias="POSTGRES_PORT_INTERNAL"

    )

    postgres_db: str = Field(

        default="disage_ai",

        alias="POSTGRES_DB"

    )

    postgres_user: str = Field(

        default="disage",

        alias="POSTGRES_USER"

    )

    postgres_password: str = Field(

        default="",

        alias="POSTGRES_PASSWORD"

    )

    #
    # Phase17 : 研修用AIアシスタント
    #

    enable_training_assistant: bool = Field(

        default=False,

        alias="ENABLE_TRAINING_ASSISTANT"

    )

    #
    # マルチターン対話で遡る往復数（user+assistantで1往復）
    #

    conversation_history_turns: int = Field(

        default=3,

        alias="CONVERSATION_HISTORY_TURNS"

    )

    #
    # 現在学習中chapterのブースト強度
    #
    # hybrid_score（またはdistanceベースの類似度）に
    # 加算する形で作用する。0.0で無効化。
    #

    chapter_boost_weight: float = Field(

        default=0.15,

        alias="CHAPTER_BOOST_WEIGHT"

    )

    #
    # 教材外判定用キーワード辞書
    #

    off_topic_dictionary: str = Field(

        default="/app/config/off_topic_dictionary.json",

        alias="OFF_TOPIC_DICTIONARY"

    )

    #
    # Phase17 : Query Rewriting専用LLM（軽量モデル）
    #

    llm_rewriter_url: str = Field(

        default="http://llama-rewriter:8080",

        alias="LLM_REWRITER_URL"

    )

    llm_rewriter_timeout: int = Field(

        default=30,

        alias="LLM_REWRITER_TIMEOUT"

    )

    #
    # Parent Retrieval
    #

    enable_parent_document: bool = Field(

        default=False,

        alias="ENABLE_PARENT_DOCUMENT"

    )

    parent_chunk_size: int = Field(

        default=3,

        alias="PARENT_CHUNK_SIZE"

    )

    #
    # Metadata Search
    #

    enable_metadata_search: bool = Field(

        default=False,

        alias="ENABLE_METADATA_SEARCH"

    )

    #
    # Prompt
    #

    max_context_documents: int = Field(

        default=5,

        alias="MAX_CONTEXT_DOCUMENTS"

    )

    max_context_length: int = Field(

        default=6000,

        alias="MAX_CONTEXT_LENGTH"

    )

    #
    # Logging
    #

    log_level: str

    log_prompt: bool

    log_sql: bool

    #
    # Settings
    #

    model_config = SettingsConfigDict(

        env_file="/app/config/rag.env",

        extra="ignore"

    )


@lru_cache
def get_settings():

    return Settings()


settings = get_settings()