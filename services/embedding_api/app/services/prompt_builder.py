import logging

from app.config import settings


logger = logging.getLogger(__name__)


class PromptBuilder:

    # ======================================================
    # 回答形式別の出力指示
    # ======================================================
    #
    # response_formatは、
    #
    # 「何を根拠にするか」
    #
    # ではなく、
    #
    # 「資料の内容をどのような形に変換して回答するか」
    #
    # を決める。
    #
    # 重要：
    #
    # RAG資料の表現形式と、受講生が要求する回答形式は
    # 必ずしも一致するとは限らない。
    #
    # 例えば、
    #
    # 資料：
    #   継承の説明 + サンプルコード
    #
    # 質問：
    #   継承のサンプルコードをフローチャートで表して
    #
    # の場合、
    #
    # 資料にフローチャートが存在しなくても、
    # 資料の説明・コードから処理や関係を整理して
    # フローチャートへ変換してよい。
    #
    # ======================================================

    FORMAT_INSTRUCTIONS = {

        "EXPLAIN": """
・資料の内容を分かりやすい説明文としてまとめてください。
・質問に直接答えてください。
・資料に関連情報が複数ある場合は、質問に必要な情報を整理してください。
・資料に記載された内容を優先してください。
・資料から読み取れる範囲で、説明の順序を整理して構いません。
""",

        "CODE": """
・質問がコードを要求している場合は、資料の内容を根拠として
  サンプルコードを提示してください。
・資料中にコード例がある場合は、そのコードを優先して利用してください。
・資料中にコード例がない場合でも、資料に記載された概念・仕様・
  API・構文などから明確に導出できる範囲でサンプルコードを生成して構いません。
・生成したコードは「資料に掲載されていたコード」であるかのように
  表現してはいけません。
・資料に記載されていない仕様・API・メソッド名などを必要以上に
 追加しないでください。
・生成したコードである場合は、必要に応じて
  「以下は資料の内容をもとにしたサンプルです。」
  などと明示してください。
""",

        "COMPARE": """
・複数の概念・技術・構文などを比較してください。
・資料に記載されている情報を優先してください。
・比較対象の一部だけが資料に記載されている場合は、
  資料から確認できる部分を回答してください。
・資料から確認できない比較項目については、
  「資料には記載がない」「資料からは確認できない」
  と明示してください。
・比較表または箇条書きを使用して、違いが分かるように整理してください。
""",

        "STEP_BY_STEP": """
・資料の内容を手順として、番号付きで順を追って説明してください。
・資料に手順として明記されていなくても、
  資料に記載された処理・コード・説明から明確に読み取れる順序であれば
  整理して構いません。
・資料にない処理や仕様を勝手に追加しないでください。
・コードが資料に存在する場合は、コードの処理順序を読み取り、
  必要に応じて手順として整理してください。
""",

        "DIAGRAM": """
・質問が図、フローチャート、構造図などを要求している場合は、
  資料の内容を図として整理して回答してください。

・資料にフローチャートそのものが存在しなくても、
  資料に記載された説明、コード、処理、クラス関係、データの流れなどから
  明確に読み取れる内容であれば、図として表現して構いません。

・特に、資料にサンプルコードがある場合は、
  そのコードの処理順序や関係を読み取り、
  フローチャートとして整理してください。

・例えば、
  「継承のサンプルコードをフローチャートで表してください」
  という質問に対して、
  資料に「フローチャート」という表現が存在しなくても、
  資料中の継承の説明やサンプルコードを根拠として
  フローチャートを作成して構いません。

・図を作成する場合は、原則としてMermaid記法を使用してください。

・Mermaidコードは必ず
  ```mermaid

のコードブロックで囲んでください。

・必要に応じて、

概念の簡単な説明
元となるコード
フローチャート
の順に回答してください。

・資料にないクラス名、メソッド名、条件分岐、処理、仕様などを
勝手に追加してはいけません。

・資料から読み取れる範囲で図示できる部分を先に回答してください。

・資料に図そのものがないことを理由として、
「資料からは確認できません」と回答を終了してはいけません。

・図として表現できる情報が資料に存在する場合は、
資料の内容を別の表現形式へ変換して回答してください。
""",

    "QUIZ": """

・資料の内容に基づいたクイズ形式で回答してください。
・問題と答えが分かる形式にしてください。
・資料にない知識を、資料に基づく問題であるかのように
出題してはいけません。
・資料から確認できる範囲で問題を作成してください。
""",

    "DEBUG": """

・提示されたコードやエラーの内容と、資料の内容を照らし合わせて
原因を説明してください。
・資料から確認できる原因と、資料だけでは判断できない点を
明確に分けてください。
・資料だけでは原因を特定できない場合は、その旨を明記してください。
・資料に関連する情報がある場合は、その情報を利用して
原因候補を整理してください。
""",

    "SUMMARY": """

・資料の内容を簡潔に要約してください。
・質問に関係する内容を優先してください。
・資料にない情報を事実として追加しないでください。
""",

    "EXAMPLE": """

・資料の内容に基づいた具体例を挙げて回答してください。
・資料に具体例がない場合でも、資料の説明内容を理解するための
サンプルを生成して構いません。
・生成した例を資料に掲載されていた例として扱わないでください。
・生成する場合も、資料から確認できる概念・仕様の範囲を維持してください。
"""
}

# ======================================================
# Answerability別の回答方針
# ======================================================
#
# FULL
#   → 資料を根拠に通常回答
#
# PARTIAL
#   → 資料にある部分を回答
#   → 不足部分を明示
#   → 資料をもとにした変換・生成を許可
#
# NONE
#   → 資料を根拠とした回答はできない
#
# ======================================================

ANSWERABILITY_INSTRUCTIONS = {

    "FULL": """

・資料に質問への回答に必要な情報が十分に含まれています。
・資料の内容を根拠として、質問に直接回答してください。
・質問が説明、コード、図、表、手順などの形式変換を要求している場合は、
資料の内容を要求された形式へ整理・変換してください。
・不要な推測や一般論を追加しないでください。
""",

    "PARTIAL": """

・資料には質問に関連する有用な情報があります。
・質問のすべての条件・要求が資料に記載されているとは限りません。
・まず、資料から確認できる情報を具体的に回答してください。

・資料から確認できない条件・順位・具体的な値などがある場合は、
その部分について
「資料には記載がない」
または
「資料からは確認できない」
と明示してください。

・ただし、資料に関連する情報が存在する場合、
資料にない回答形式へ変換することは可能です。

・例えば、資料にコードがありフローチャートがない場合でも、
コードの処理順序を資料から読み取れるのであれば、
その内容をフローチャートとして表現して構いません。

・資料に関連する情報を利用して、
サンプルコード、図、表、例、手順などを生成することも可能です。

・ただし、生成した内容を資料に記載されている事実であるかのように
表現してはいけません。

・「資料から確認できない部分がある」ことだけを理由に、
回答全体を
「資料からは確認できません。」
で終了してはいけません。

・資料から答えられる部分を必ず先に回答してください。
""",

    "NONE": """

・RAG資料には、質問に対する有用な根拠が確認できません。
・資料に存在しない内容を、資料から得た情報であるかのように
回答してはいけません。
・資料を根拠とした回答ができない場合は、
「資料からは確認できません。」
と簡潔に回答してください。
・資料に単に回答形式そのものが存在しないだけで、
関連する知識やコードが存在する場合はNONEとして扱わないでください。
"""
}

DEFAULT_ANSWERABILITY = "FULL"

# ======================================================
# Prompt生成
# ======================================================

def build(
    self,
    question: str,
    contexts: list[str],
    conversation_questions: list[dict] | None = None,
    is_off_topic: bool = False,
    response_format: str = "EXPLAIN",
    conversation_turns: list[dict] | None = None,
    answerability_status: str = "FULL",
    answerability_reason: str = "",
    source_pages: list[str] | None = None
) -> str:

    logger.debug(
        "Prompt created"
    )

    # --------------------------------------------------
    # 後方互換
    # --------------------------------------------------

    if conversation_questions is None:

        conversation_questions = (
            self._extract_questions(
                conversation_turns
            )
        )

    # --------------------------------------------------
    # 正規化
    # --------------------------------------------------

    response_format = (
        self._normalize_response_format(
            response_format
        )
    )

    answerability_status = (
        self._normalize_answerability_status(
            answerability_status
        )
    )

    if source_pages is None:

        source_pages = []

    prompt = self._build_internal(

        question=question,

        contexts=contexts,

        conversation_questions=
            conversation_questions,

        is_off_topic=
            is_off_topic,

        response_format=
            response_format,

        answerability_status=
            answerability_status,

        answerability_reason=
            answerability_reason,

        source_pages=
            source_pages
    )

    if settings.log_prompt:

        logger.debug(
            "Prompt\n%s",
            prompt
        )

    return prompt

# ======================================================
# response_format正規化
# ======================================================

def _normalize_response_format(
    self,
    response_format: str
) -> str:

    value = str(
        response_format or ""
    ).strip().upper()

    if value in self.FORMAT_INSTRUCTIONS:

        return value

    logger.warning(
        "Unknown response_format=%s. "
        "Using EXPLAIN.",
        response_format
    )

    return "EXPLAIN"

# ======================================================
# Answerability正規化
# ======================================================

def _normalize_answerability_status(
    self,
    status: str
) -> str:

    value = str(
        status or ""
    ).strip().upper()

    if value in (
        "FULL",
        "PARTIAL",
        "NONE"
    ):

        return value

    logger.warning(
        "Unknown answerability_status=%s. "
        "Using %s.",
        status,
        self.DEFAULT_ANSWERABILITY
    )

    return self.DEFAULT_ANSWERABILITY

# ======================================================
# 会話履歴から質問だけを抽出
# ======================================================

def _extract_questions(
    self,
    conversation_turns: list[dict] | None
) -> list[dict]:

    if not conversation_turns:

        return []

    questions = []

    for turn in conversation_turns:

        role = turn.get(
            "role",
            ""
        )

        if role != "user":

            continue

        content = turn.get(
            "content",
            ""
        )

        if not content:

            continue

        questions.append(
            {
                "role":
                    "user",

                "content":
                    content,

                "is_off_topic":
                    turn.get(
                        "is_off_topic",
                        False
                    )
            }
        )

    return questions

# ======================================================
# 会話文脈
# ======================================================
#
# assistantの過去回答は入れない。
#
# ======================================================

def _format_conversation_context(
    self,
    conversation_questions: list[dict] | None
) -> str:

    if not conversation_questions:

        return ""

    lines = []

    for turn in conversation_questions:

        content = turn.get(
            "content",
            ""
        )

        if not content:

            continue

        lines.append(
            f"受講生: {content}"
        )

    if not lines:

        return ""

    history_text = "\n".join(
        lines
    )

    return f"""
会話の文脈

以下は、今回の質問の意味を理解するための
会話上の文脈です。

この文脈は、指示語や省略された対象を理解するために
使用してください。

過去のアシスタント回答は含まれていません。

{history_text}
"""

# ======================================================
# ページ情報
# ======================================================

def _format_source_pages(
    self,
    source_pages: list[str] | None
) -> str:

    if not source_pages:

        return """

参考ページ情報：
なし

ページ番号を推測してはいけません。
"""

    unique_pages = []

    for page in source_pages:

        value = str(
            page
        ).strip()

        if not value:

            continue

        if value in unique_pages:

            continue

        unique_pages.append(
            value
        )

    if not unique_pages:

        return """

参考ページ情報：
なし

ページ番号を推測してはいけません。
"""

    page_text = "、".join(
        unique_pages
    )

    return f"""

参考ページ情報：

{page_text}

上記はRAG検索結果のmetadataから取得された情報です。

ページ番号を変更・推測・創作してはいけません。

回答で参考ページを示す場合は、
上記の情報だけを使用してください。
"""

# ======================================================
# Context整形
# ======================================================

def _format_contexts(
    self,
    contexts: list[str]
) -> str:

    if not contexts:

        return "資料なし"

    return "\n\n".join(
        contexts
    )

# ======================================================
# 範囲外質問
# ======================================================

def _build_off_topic_instruction(
    self,
    is_off_topic: bool
) -> str:

    if not is_off_topic:

        return ""

    return """

・この質問はJava研修教材の主要範囲外である可能性があります。

・ただし、RAG資料に質問へ関連する情報が存在する場合、
「Java研修の範囲外」という理由だけで回答を拒否してはいけません。

・RAG資料に関連情報がある場合は、
その資料を根拠として回答してください。

・HTML、CSS、JavaScript、SQLなどについても、
RAG資料に関連情報が存在する場合は回答対象としてください。

・資料に関連情報がない場合のみ、
資料から確認できない旨を明示してください。
"""

# ======================================================
# 回答変換に関する共通ルール
# ======================================================
#
# 今回の改善で特に重要な部分。
#
# 「資料に書いてある形式」と
# 「受講生が要求した形式」を分離する。
#
# ======================================================

def _build_transformation_instruction(
    self
) -> str:

    return """
資料から回答形式への変換

RAG資料の表現形式と、受講生が要求している回答形式は
必ずしも一致しません。

資料に要求された形式そのものが存在しない場合でも、
資料に必要な知識・説明・コード・処理関係が存在するなら、
その内容を要求された形式へ変換して回答してください。

例えば、

資料：
・継承とは何か
・親クラスと子クラスの関係
・継承を使用したサンプルコード

質問：
「継承のサンプルコードをフローチャートで表してください。」

の場合、

「資料にフローチャートがありません。」

だけで回答を終了してはいけません。

資料の説明とサンプルコードを読み取り、

継承の関係を説明
必要に応じてサンプルコードを提示
コードの処理や関係を整理
Mermaidフローチャートとして表現

という形で回答してください。

ただし、資料から読み取れない処理・条件・仕様を
勝手に追加してはいけません。

つまり、

「資料に存在する情報」
↓
「受講生が要求した形式」

という変換は許可します。

一方、

「資料に存在しない情報」
↓
「一般知識による勝手な補完」

は行ってはいけません。
"""

# ======================================================
# 回答構造
# ======================================================

def _build_answer_structure_instruction(
    self,
    response_format: str
) -> str:

    if response_format == "DIAGRAM":

        return """
今回の回答構造

図を要求されている場合は、次の構造を基本としてください。

結論・概要
資料から確認できる対象
必要に応じて元となるコードや処理
Mermaidによる図
図の読み方・補足

ただし、質問が単純な図だけを要求している場合は、
不要な説明を増やしすぎないでください。
"""

    if response_format == "CODE":

        return """
今回の回答構造

コードを要求されている場合は、必要に応じて、

対象となる概念の簡単な説明
サンプルコード
コードのポイント

の順に整理してください。
"""

    if response_format == "STEP_BY_STEP":

        return """
今回の回答構造

手順を要求されている場合は、

最初の処理
次の処理
次の処理

のように、処理順序が明確になるよう整理してください。
"""

    return """
今回の回答構造

質問に直接答え、
必要な情報を分かりやすい順序で整理してください。
"""

# ======================================================
# 最終Prompt
# ======================================================

def _build_internal(
    self,
    question: str,
    contexts: list[str],
    conversation_questions: list[dict] | None,
    is_off_topic: bool,
    response_format: str,
    answerability_status: str,
    answerability_reason: str,
    source_pages: list[str]
) -> str:

    context = self._format_contexts(
        contexts
    )

    history_section = (
        self._format_conversation_context(
            conversation_questions
        )
    )

    source_page_section = (
        self._format_source_pages(
            source_pages
        )
    )

    format_instruction = (
        self.FORMAT_INSTRUCTIONS.get(
            response_format,
            self.FORMAT_INSTRUCTIONS[
                "EXPLAIN"
            ]
        )
    )

    answerability_instruction = (
        self.ANSWERABILITY_INSTRUCTIONS.get(
            answerability_status,
            self.ANSWERABILITY_INSTRUCTIONS[
                self.DEFAULT_ANSWERABILITY
            ]
        )
    )

    off_topic_instruction = (
        self._build_off_topic_instruction(
            is_off_topic
        )
    )

    transformation_instruction = (
        self._build_transformation_instruction()
    )

    answer_structure_instruction = (
        self._build_answer_structure_instruction(
            response_format
        )
    )

    return f"""

あなたはJava研修受講生向けのAI学習アシスタントです。

最重要ルール

今回の回答では、以下の3つを明確に区別してください。

RAG資料から確認できる情報
RAG資料に関連する情報をもとに生成・変換した内容
RAG資料から確認できない情報

この3つを混同してはいけません。

特に、RAG資料に関連情報が存在するにもかかわらず、
「資料からは確認できません。」
だけで回答を終了してはいけません。

{transformation_instruction}

回答可能性判定

今回のRAG検索結果に対する判定：

{answerability_status}

判定理由：

{answerability_reason}

判定ごとの回答方針

{answerability_instruction}

資料について

・以下の「今回の回答の根拠となる資料」がRAGから取得された資料です。

・資料に記載された内容を根拠として回答してください。

・資料に存在しない事実を、資料に記載されているかのように
表現してはいけません。

・資料に関連情報がある場合は、その情報を活用してください。

・資料にない表現形式へ変換することは可能です。

・例えば、資料にコードがありフローチャートがない場合でも、
コードの処理を資料の内容に沿ってフローチャート化できます。

・資料に説明があり表がない場合でも、
資料の内容を比較表や整理表として表現できます。

・資料に手順として書かれていなくても、
コードや処理説明から明確に読み取れる順序であれば、
手順として整理できます。

・ただし、資料にない処理・仕様・条件などを
勝手に追加してはいけません。

サンプルコード・生成内容について

質問がサンプルコードを求めている場合、

・資料にサンプルコードがある
→ 資料のコードを根拠として回答してください。

・資料にサンプルコードはないが、
対象となる概念・仕様が資料にある
→ 資料の説明を根拠として、
関連するサンプルコードを生成して構いません。

・生成したサンプルコードを、
資料に掲載されていたコードとして表現してはいけません。

・生成コードに資料から確認できない追加仕様を
大量に持ち込まないでください。

図・フローチャートについて

質問が図やフローチャートを要求している場合、

・資料に図がある
→ 資料の図の内容を根拠として回答してください。

・資料に図がないが、
資料に説明・コード・処理・構造などがある
→ それらを整理して図として表現して構いません。

・特にコードがある場合は、
コードの処理順序・条件分岐・クラス関係など、
資料から確認できる内容を図示してください。

・資料にフローチャートがないことだけを理由に
回答を拒否してはいけません。

・図示する際に、資料から確認できない条件分岐や処理を
勝手に追加してはいけません。

・Mermaidを使用する場合は、
必ず以下の形式にしてください。

flowchart TD
    A[開始] --> B[処理]
部分的にしか回答できない質問

質問に複数の条件が含まれている場合、

例：

「よく使用するもの上位3つに対してサンプルコードを出してください。」

資料に、

「基本データ型にはboolean、byte、short、int、long、float、doubleがある」

という情報があるが、

「よく使用する上位3つ」

という順位がない場合、

回答全体を拒否してはいけません。

次のように分けてください。

・資料から確認できること
→ 基本データ型の一覧

・資料から確認できないこと
→ 「よく使用するもの上位3つ」という順位

・資料の情報をもとに生成できること
→ サンプルコード

このように、

「確認できる情報」
「確認できない情報」
「資料をもとに生成・変換できる情報」

を明確に分けて回答してください。

HTML等の技術について

RAG資料にHTML、CSS、JavaScript、SQLなどの説明が存在する場合、

「Java研修の主要範囲ではない」

という理由だけで回答を拒否してはいけません。

RAG資料に関連情報が存在するなら、
その資料を根拠として回答してください。

会話文脈

{history_section}

会話文脈は質問の意味や指示語を理解するために使用してください。

過去のアシスタント回答を今回の回答の根拠として使用してはいけません。

回答形式

今回指定された回答形式：

{response_format}

{format_instruction}

{answer_structure_instruction}

参考ページ情報

{source_page_section}

参考ページ情報はRAG metadataから取得されています。

ページ番号を推測してはいけません。

回答の最後に必要に応じて、

「参考ページ：p.12」

または

「参考ページ：p.12、p.13」

のように示してください。

ページ情報が「なし」の場合、
ページ番号を作ってはいけません。

範囲外判定について

{off_topic_instruction}

回答スタイル

・質問に直接答えてください。

・結論を先に示してください。

・前置きや不要な免責事項を繰り返さないでください。

・資料に関連情報がある場合は、
回答可能な範囲を具体的に説明してください。

・部分的にしか回答できない場合は、

「資料から確認できること」

と

「資料から確認できないこと」

を必要に応じて分けてください。

・資料に存在しない回答形式へ変換することは可能ですが、
変換の根拠は必ず資料に存在する情報としてください。

・同じ内容を繰り返さないでください。

・過去のアシスタント回答をそのまま再掲・模倣しないでください。

・不要な追加質問や次の話題の提案を付け加えないでください。

今回の回答の根拠となる資料

以下の資料を、今回の回答の根拠として使用してください。

{context}

今回の質問

{question}

回答

日本語で回答してください。
"""

prompt_builder = PromptBuilder()