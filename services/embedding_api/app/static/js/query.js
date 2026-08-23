/**
 * ============================================================
 * Training AI Assistant
 *
 * query.js
 *
 * 役割
 * ------------------------------------------------------------
 * ・セッション管理
 * ・会話スレッド管理
 * ・質問送信
 * ・APIレスポンス表示
 * ・回答本文表示
 * ・回答可能性表示
 * ・根拠資料表示
 * ・参照ページ表示
 * ・システム情報表示
 * ・Markdown / Mermaid表示
 *
 * 回答内容とシステム情報を分離して扱う。
 * ============================================================
 */

/* ============================================================
 * Constants
 * ============================================================
 */

const SESSION_STORAGE_KEY = "disage_session_id";

const HISTORY_STORAGE_KEY = "disage_history";

/* ============================================================
 * Session
 * ============================================================
 */

function generateSessionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }

  return (
    "session-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10)
  );
}

function getSessionId() {
  let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);

  if (!sessionId) {
    sessionId = generateSessionId();

    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }

  return sessionId;
}

/* ============================================================
 * Local History
 * ============================================================
 */

function getLocalHistory() {
  const raw = localStorage.getItem(HISTORY_STORAGE_KEY);

  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);

    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.warn("会話履歴の読み込みに失敗しました。", error);

    return [];
  }
}

function saveLocalHistory(history) {
  localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
}

function appendLocalHistory(question, answer, answerabilityStatus) {
  const history = getLocalHistory();

  history.push({
    question: question,

    answer: answer,

    answerability_status: answerabilityStatus,
  });

  saveLocalHistory(history);

  renderHistory();
}

/* ============================================================
 * HTML Escape
 * ============================================================
 */

function escapeHtml(text) {
  const div = document.createElement("div");

  div.textContent = text == null ? "" : String(text);

  return div.innerHTML;
}

/* ============================================================
 * History UI
 * ============================================================
 */

function renderHistory() {
  const container = document.getElementById("history");

  if (!container) {
    return;
  }

  const history = getLocalHistory();

  if (history.length === 0) {
    container.innerHTML = `
            <div class="empty-state">
                <p>まだ会話がありません。</p>
            </div>
            `;

    return;
  }

  container.innerHTML = history
    .map(function (turn, index) {
      const status = turn.answerability_status || "";

      const statusLabel = getAnswerabilityLabel(status);

      return `
                        <button
                            type="button"
                            class="thread-item"
                            data-history-index="${index}"
                        >
                            <span class="thread-item-title">
                                ${escapeHtml(turn.question)}
                            </span>

                            <span class="thread-item-meta">
                                ${escapeHtml(statusLabel)}
                            </span>
                        </button>
                    `;
    })
    .join("");
}

/* ============================================================
 * Answerability
 * ============================================================
 */

function getAnswerabilityLabel(status) {
  switch (String(status || "").toUpperCase()) {
    case "FULL":
      return "資料に根拠あり";

    case "PARTIAL":
      return "一部資料に根拠あり";

    case "NONE":
      return "資料から確認できず";

    default:
      return "";
  }
}

function getAnswerabilityClass(status) {
  switch (String(status || "").toUpperCase()) {
    case "FULL":
      return "answerability-full";

    case "PARTIAL":
      return "answerability-partial";

    case "NONE":
      return "answerability-none";

    default:
      return "";
  }
}

/* ============================================================
 * Markdown
 * ============================================================
 *
 * marked が読み込まれている場合はMarkdownをHTML化する。
 *
 * marked が存在しない場合は安全なテキスト表示へ
 * フォールバックする。
 *
 * ============================================================
 */

function renderMarkdown(text) {
  const value = text == null ? "" : String(text);

  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(value);
  }

  return "<p>" + escapeHtml(value).replace(/\n/g, "<br>") + "</p>";
}

/* ============================================================
 * Mermaid
 * ============================================================
 */

async function renderMermaid() {
  if (!window.mermaid || typeof window.mermaid.run !== "function") {
    return;
  }

  try {
    await window.mermaid.run({
      querySelector: ".mermaid",
    });
  } catch (error) {
    console.warn("Mermaidの描画に失敗しました。", error);
  }
}

/* ============================================================
 * Generic DOM Helpers
 * ============================================================
 */

function setText(elementId, value) {
  const element = document.getElementById(elementId);

  if (!element) {
    return;
  }

  element.textContent = value == null ? "" : String(value);
}

function clearElement(elementId) {
  const element = document.getElementById(elementId);

  if (!element) {
    return;
  }

  element.innerHTML = "";
}

/* ============================================================
 * Answer
 * ============================================================
 */

function renderAnswer(answer) {
  const container = document.getElementById("answer");

  if (!container) {
    return;
  }

  container.innerHTML = renderMarkdown(answer || "");

  renderMermaid();
}

/* ============================================================
 * Answerability
 * ============================================================
 */

function renderAnswerability(status, reason) {
  const container = document.getElementById("answerability");

  if (!container) {
    return;
  }

  const normalized = String(status || "").toUpperCase();

  const label = getAnswerabilityLabel(normalized);

  const className = getAnswerabilityClass(normalized);

  if (!normalized) {
    container.innerHTML = "";

    return;
  }

  container.innerHTML = `
        <section class="answer-section answerability-section">

            <div class="answer-section-header">

                <h3>
                    回答可能性
                </h3>

            </div>

            <div
                class="answerability-status ${className}"
            >
                ${escapeHtml(label)}
            </div>

            ${
              reason
                ? `
                        <p class="answerability-reason">
                            ${escapeHtml(reason)}
                        </p>
                    `
                : ""
            }

        </section>
        `;
}

/* ============================================================
 * Sources
 * ============================================================
 *
 * sources
 *
 * 回答の根拠・参考資料。
 *
 * page_reference
 * はバックエンドがRAG metadataから取得した値のみを
 * 表示する。
 *
 * フロント側ではページ番号を推測しない。
 *
 * ============================================================
 */

function renderSources(sources) {
  const container = document.getElementById("sources");

  if (!container) {
    return;
  }

  container.innerHTML = "";

  if (!Array.isArray(sources) || sources.length === 0) {
    return;
  }

  const section = document.createElement("section");

  section.className = "answer-section";

  section.innerHTML = `
        <div class="answer-section-header">

            <h3>
                根拠・参考資料
            </h3>

        </div>

        <div class="sources-list"></div>
        `;

  const list = section.querySelector(".sources-list");

  sources.forEach(function (source) {
    const item = document.createElement("div");

    item.className = "source-item";

    const title = source.title || "資料";

    const documentId = source.document_id || "";

    const chunkNo = source.chunk_no || "";

    const pageReference = source.page_reference;

    item.innerHTML = `
                <div class="source-item-header">

                    <h4>
                        ${escapeHtml(title)}
                    </h4>

                    ${
                      pageReference
                        ? `
                                <span
                                    class="page-reference"
                                >
                                    ${escapeHtml(pageReference)}
                                </span>
                            `
                        : ""
                    }

                </div>

                ${
                  documentId || chunkNo
                    ? `
                            <p class="source-meta">
                                ${
                                  documentId
                                    ? "Document: " + escapeHtml(documentId)
                                    : ""
                                }

                                ${
                                  chunkNo
                                    ? " / Chunk: " + escapeHtml(chunkNo)
                                    : ""
                                }
                            </p>
                        `
                    : ""
                }
                `;

    list.appendChild(item);
  });

  container.appendChild(section);
}

/* ============================================================
 * Source Pages
 * ============================================================
 */

function renderSourcePages(sourcePages) {
  const container = document.getElementById("source-pages");

  if (!container) {
    return;
  }

  container.innerHTML = "";

  if (!Array.isArray(sourcePages) || sourcePages.length === 0) {
    return;
  }

  const section = document.createElement("section");

  section.className = "answer-section";

  section.innerHTML = `
        <div class="answer-section-header">

            <h3>
                参照ページ
            </h3>

        </div>

        <div class="source-pages-list"></div>
        `;

  const list = section.querySelector(".source-pages-list");

  sourcePages.forEach(function (page) {
    if (page == null || String(page).trim() === "") {
      return;
    }

    const pageElement = document.createElement("span");

    pageElement.className = "source-page";

    pageElement.textContent = String(page);

    list.appendChild(pageElement);
  });

  if (list.children.length > 0) {
    container.appendChild(section);
  }
}

/* ============================================================
 * Documents
 * ============================================================
 *
 * documents は詳細なRAG検索結果。
 *
 * 通常の受講生向け画面では回答本文や根拠資料ほど
 * 前面に出さず、必要に応じて確認できる領域として扱う。
 *
 * ============================================================
 */

function renderDocuments(documents) {
  const container = document.getElementById("documents");

  if (!container) {
    return;
  }

  container.innerHTML = "";

  if (!Array.isArray(documents) || documents.length === 0) {
    return;
  }

  const section = document.createElement("details");

  section.className = "answer-section";

  section.innerHTML = `
        <summary
            class="answer-section-header"
        >
            <h3>
                RAG検索結果詳細
            </h3>
        </summary>

        <div class="sources-list"></div>
        `;

  const list = section.querySelector(".sources-list");

  documents.forEach(function (doc, index) {
    const item = document.createElement("div");

    item.className = "source-item";

    const metadata = doc.metadata || {};

    const page =
      doc.page ||
      metadata.page_reference ||
      metadata.page ||
      metadata.page_number ||
      "";

    item.innerHTML = `
                <div
                    class="source-item-header"
                >

                    <h4>
                        Document ${index + 1}
                    </h4>

                    ${
                      page
                        ? `
                                <span
                                    class="page-reference"
                                >
                                    ${escapeHtml(page)}
                                </span>
                            `
                        : ""
                    }

                </div>

                <p class="source-meta">
                    Score:
                    ${formatNumber(doc.score)}

                    /
                    Distance:
                    ${formatNumber(doc.distance)}
                </p>

                <details>

                    <summary>
                        Metadata
                    </summary>

                    <pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre>

                </details>

                <details>

                    <summary>
                        Document
                    </summary>

                    <pre>${escapeHtml(doc.document || "")}</pre>

                </details>
                `;

    list.appendChild(item);
  });

  container.appendChild(section);
}

/* ============================================================
 * Number
 * ============================================================
 */

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return escapeHtml(String(value));
  }

  return number.toFixed(4);
}

/* ============================================================
 * Metadata
 * ============================================================
 *
 * 回答本文とは別のシステム情報。
 *
 * ・検索時間
 * ・LLM時間
 * ・総処理時間
 * ・検索件数
 * ・cache
 * ・fallback
 *
 * などをここに集約する。
 *
 * ============================================================
 */

function renderMetadata(metadata) {
  const container = document.getElementById("system-info");

  if (!container) {
    return;
  }

  const data = metadata || {};

  const rows = [
    ["Query Analysis", data.query_analysis_elapsed_ms, " ms"],

    ["Retrieval", data.retrieval_elapsed_ms, " ms"],

    ["Answerability", data.answerability_elapsed_ms, " ms"],

    ["LLM", data.llm_elapsed_ms, " ms"],

    ["Total", data.total_elapsed_ms, " ms"],

    ["Retrieved Count", data.retrieved_count, ""],

    ["Gate Candidate Count", data.gate_candidate_count, ""],

    ["Final Context Count", data.final_context_count, ""],

    ["Cache Hit", data.cache_hit ? "true" : "false", ""],

    ["Fallback Used", data.fallback_used ? "true" : "false", ""],
  ];

  const visibleRows = rows.filter(function (row) {
    return row[1] !== undefined && row[1] !== null;
  });

  if (visibleRows.length === 0) {
    container.innerHTML = "";

    return;
  }

  container.innerHTML = `
        <details>

            <summary>
                システム情報
            </summary>

            <table
                class="system-info-table"
            >

                <tbody>

                    ${visibleRows
                      .map(function (row) {
                        return `
                                        <tr>

                                            <th>
                                                ${escapeHtml(row[0])}
                                            </th>

                                            <td>
                                                ${escapeHtml(
                                                  String(row[1]),
                                                )}${escapeHtml(row[2])}
                                            </td>

                                        </tr>
                                    `;
                      })
                      .join("")}

                </tbody>

            </table>

        </details>
        `;
}

/* ============================================================
 * Clear Answer
 * ============================================================
 */

function clearAnswer() {
  renderAnswer("");

  renderAnswerability("", "");

  clearElement("sources");

  clearElement("source-pages");

  clearElement("documents");

  clearElement("system-info");
}

/* ============================================================
 * Loading
 * ============================================================
 */

function showLoading() {
  const answer = document.getElementById("answer");

  if (answer) {
    answer.innerHTML = `
            <div class="loading-state">
                <p>
                    回答を生成しています...
                </p>
            </div>
            `;
  }
}

/* ============================================================
 * Error
 * ============================================================
 */

function renderError(message) {
  const answer = document.getElementById("answer");

  if (!answer) {
    return;
  }

  answer.innerHTML = `
        <div class="error-message">

            <h3>
                エラー
            </h3>

            <p>
                ${escapeHtml(message)}
            </p>

        </div>
        `;
}

/* ============================================================
 * Ask Question
 * ============================================================
 */

async function askQuestion() {
  const questionElement = document.getElementById("question");

  const studentElement = document.getElementById("studentId");

  const askButton = document.getElementById("askButton");

  if (!questionElement) {
    return;
  }

  const question = questionElement.value.trim();

  const studentId = studentElement ? studentElement.value.trim() : "";

  const sessionId = getSessionId();

  if (!question) {
    questionElement.focus();

    return;
  }

  if (askButton) {
    askButton.disabled = true;
  }

  showLoading();

  clearElement("answerability");

  clearElement("sources");

  clearElement("source-pages");

  clearElement("documents");

  clearElement("system-info");

  try {
    const response = await fetch("/query", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        question: question,

        student_id: studentId || null,

        session_id: sessionId,
      }),
    });

    let json;

    try {
      json = await response.json();
    } catch (error) {
      throw new Error("APIレスポンスをJSONとして読み込めませんでした。");
    }

    if (!response.ok) {
      const detail = json && (json.detail || json.message || json.error);

      throw new Error(detail || `HTTP ${response.status}`);
    }

    /* ----------------------------------------------------
     * Answer
     * ----------------------------------------------------
     */

    renderAnswer(json.answer || "");

    /* ----------------------------------------------------
     * Answerability
     * ----------------------------------------------------
     */

    renderAnswerability(
      json.answerability_status,

      json.answerability_reason,
    );

    /* ----------------------------------------------------
     * Sources
     * ----------------------------------------------------
     */

    renderSources(json.sources || []);

    /* ----------------------------------------------------
     * Source Pages
     * ----------------------------------------------------
     */

    renderSourcePages(json.source_pages || []);

    /* ----------------------------------------------------
     * Documents
     * ----------------------------------------------------
     */

    renderDocuments(json.documents || []);

    /* ----------------------------------------------------
     * Metadata
     * ----------------------------------------------------
     *
     * elapsed_ms / retrieved_count を回答本文へ
     * 混在させない。
     *
     * 正式なシステム情報はmetadataを使用する。
     *
     * ----------------------------------------------------
     */

    renderMetadata(json.metadata || {});

    /* ----------------------------------------------------
     * Local History
     * ----------------------------------------------------
     */

    appendLocalHistory(
      question,

      json.answer || "",

      json.answerability_status || "",
    );

    questionElement.value = "";
  } catch (error) {
    console.error("質問処理に失敗しました。", error);

    renderError(error.message || "質問処理中にエラーが発生しました。");
  } finally {
    if (askButton) {
      askButton.disabled = false;
    }
  }
}

/* ============================================================
 * Reset Session
 * ============================================================
 */

function resetSession() {
  const newSessionId = generateSessionId();

  localStorage.setItem(SESSION_STORAGE_KEY, newSessionId);

  localStorage.removeItem(HISTORY_STORAGE_KEY);

  const sessionElement = document.getElementById("sessionId");

  if (sessionElement) {
    sessionElement.value = newSessionId;
  }

  renderHistory();

  clearAnswer();
}

/* ============================================================
 * History Event
 * ============================================================
 */

function setupHistoryEvents() {
  const container = document.getElementById("history");

  if (!container) {
    return;
  }

  container.addEventListener("click", function (event) {
    const item = event.target.closest(".thread-item");

    if (!item) {
      return;
    }

    const index = Number(item.dataset.historyIndex);

    if (Number.isNaN(index)) {
      return;
    }

    const history = getLocalHistory();

    const turn = history[index];

    if (!turn) {
      return;
    }

    renderAnswer(turn.answer || "");

    renderAnswerability(turn.answerability_status || "", "");

    document.querySelectorAll(".thread-item").forEach(function (element) {
      element.classList.remove("active");
    });

    item.classList.add("active");
  });
}

/* ============================================================
 * Enter Key
 * ============================================================
 */

function setupQuestionInput() {
  const question = document.getElementById("question");

  if (!question) {
    return;
  }

  question.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();

      askQuestion();
    }
  });
}

/* ============================================================
 * Initialization
 * ============================================================
 */

function initSessionUi() {
  const sessionElement = document.getElementById("sessionId");

  if (sessionElement) {
    sessionElement.value = getSessionId();
  }

  renderHistory();

  setupHistoryEvents();

  setupQuestionInput();
}

/* ============================================================
 * DOM Ready
 * ============================================================
 */

document.addEventListener("DOMContentLoaded", initSessionUi);
