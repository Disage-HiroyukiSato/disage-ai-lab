-- ============================================================
-- Phase17 : 研修用AIアシスタント
-- ============================================================
--
-- student_progress      : 受講生の現在の学習章（外部の進捗管理
--                          システムが更新し、RAG側は参照のみ）
--
-- conversation_history   : マルチターン対話のための会話履歴
--                          （RAG側=embedding_apiが書き込む、
--                          Phase19の前倒し実装分）
--
-- ============================================================

CREATE TABLE IF NOT EXISTS student_progress (

    student_id      VARCHAR(64) PRIMARY KEY,

    -- 現在学習中の章。document.pyのchapterフィールドと
    -- 同じ自由記述文字列を想定（例: "第3章 オブジェクト指向"）
    current_chapter  VARCHAR(255) NOT NULL DEFAULT '',

    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()

);

COMMENT ON TABLE student_progress IS
    '受講生の現在の学習進捗。外部の進捗管理システムが更新し、RAG側（embedding_api）は参照のみ行う。';

COMMENT ON COLUMN student_progress.current_chapter IS
    'document.pyのchapterフィールドと同じ自由記述文字列。retrieval_serviceのchapterブーストで使用する。';


CREATE TABLE IF NOT EXISTS conversation_history (

    id               BIGSERIAL PRIMARY KEY,

    session_id       VARCHAR(64) NOT NULL,

    student_id       VARCHAR(64) NOT NULL,

    -- "user" | "assistant"
    role             VARCHAR(16) NOT NULL,

    content          TEXT NOT NULL,

    -- 教材外の質問と判定された場合にTrueを記録する
    -- （分析・Phase20以降のスキル評価で利用予定）
    is_off_topic     BOOLEAN NOT NULL DEFAULT false,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()

);

CREATE INDEX IF NOT EXISTS idx_conversation_history_session
    ON conversation_history (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_conversation_history_student
    ON conversation_history (student_id, created_at);

COMMENT ON TABLE conversation_history IS
    'マルチターン対話のための会話履歴。session_id単位で直近N件を取得し、プロンプトに含める。Phase19（質問・回答履歴の保存）の前倒し実装分。';
