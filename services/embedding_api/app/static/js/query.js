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
 * ・要点表示
 * ・関連教材表示
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

const MAX_QUESTIONS_PER_THREAD = 30;

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

function appendLocalHistory(question, answer, answerabilityStatus, response) {
  const history = getLocalHistory();

  history.push({
    question: question,

    answer: answer,

    answerability_status: answerabilityStatus,

    answerability_reason: response.answerability_reason || "",

    sources: Array.isArray(response.sources) ? response.sources : [],

    source_pages: Array.isArray(response.source_pages)
      ? response.source_pages
      : [],

    documents: Array.isArray(response.documents) ? response.documents : [],

    metadata: response.metadata || {},

    created_at: new Date().toISOString(),
  });

  saveLocalHistory(history);

  renderThreadList();

  renderQuestionList();
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
 * DOM Helpers
 * ============================================================
 */

function setText(elementId, value) {
  const element = document.getElementById(elementId);

  if (!element) {
    return;
  }

  element.textContent = value == null ? "" : String(value);
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
 * Answer Status
 * ============================================================
 */

function renderAnswerStatus(status) {
  const element = document.getElementById("answerStatus");

  if (!element) {
    return;
  }

  const normalized = String(status || "").toUpperCase();

  if (!normalized) {
    element.textContent = "待機中";

    element.className = "answer-status";

    return;
  }

  element.textContent = getAnswerabilityLabel(normalized);

  element.className = "answer-status " + getAnswerabilityClass(normalized);
}

/* ============================================================
 * Answerability
 * ============================================================
 */

function renderAnswerability(status, reason) {
  const section = document.getElementById("answerabilitySection");

  const statusElement = document.getElementById("answerabilityStatus");

  const reasonElement = document.getElementById("answerabilityReason");

  if (!section) {
    return;
  }

  const normalized = String(status || "").toUpperCase();

  if (!normalized) {
    section.hidden = true;

    return;
  }

  section.hidden = false;

  if (statusElement) {
    statusElement.textContent = getAnswerabilityLabel(normalized);

    statusElement.className =
      "answerability-status " + getAnswerabilityClass(normalized);
  }

  if (reasonElement) {
    reasonElement.textContent = reason || "";
  }
}

/* ============================================================
 * Sources
 * ============================================================
 */

function renderSources(sources) {
  const container = document.getElementById("sources");

  if (!container) {
    return;
  }

  container.innerHTML = "";

  if (!Array.isArray(sources) || sources.length === 0) {
    container.innerHTML = `
            <p class="empty-message">
                根拠資料はありません。
            </p>
        `;

    return;
  }

  sources.forEach(function (source) {
    const item = document.createElement("div");

    item.className = "source-item";

    const title = source.title || source.document_name || "資料";

    const documentId = source.document_id || "";

    const chunkNo = source.chunk_no ?? "";

    const pageReference = source.page_reference || source.page || "";

    item.innerHTML = `

                <div
                    class="source-item-header"
                >

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
                  documentId || chunkNo !== ""
                    ? `
                            <p
                                class="source-meta"
                            >

                                ${
                                  documentId
                                    ? "Document: " + escapeHtml(documentId)
                                    : ""
                                }

                                ${
                                  chunkNo !== ""
                                    ? " / Chunk: " + escapeHtml(chunkNo)
                                    : ""
                                }

                            </p>
                        `
                    : ""
                }

            `;

    container.appendChild(item);
  });
}

/* ============================================================
 * Source Pages
 * ============================================================
 */

function renderSourcePages(sourcePages) {
  const section = document.getElementById("sourcePagesSection");

  const container = document.getElementById("sourcePages");

  if (!section || !container) {
    return;
  }

  container.innerHTML = "";

  if (!Array.isArray(sourcePages) || sourcePages.length === 0) {
    section.hidden = true;

    return;
  }

  const uniquePages = Array.from(
    new Set(
      sourcePages
        .filter((page) => page != null && String(page).trim() !== "")
        .map((page) => String(page)),
    ),
  );

  if (uniquePages.length === 0) {
    section.hidden = true;

    return;
  }

  section.hidden = false;

  uniquePages.forEach(function (page) {
    const element = document.createElement("span");

    element.className = "source-page";

    element.textContent = page;

    container.appendChild(element);
  });
}

/* ============================================================
 * Documents
 * ============================================================
 */

function renderDocuments(documents) {
  window.disageLastDocuments = Array.isArray(documents) ? documents : [];
}

/* ============================================================
 * Key Points
 * ============================================================
 */

function renderKeyPoints(keyPoints) {
  const section = document.getElementById("keyPointsSection");

  const container = document.getElementById("keyPoints");

  if (!section || !container) {
    return;
  }

  container.innerHTML = "";

  if (!Array.isArray(keyPoints) || keyPoints.length === 0) {
    section.hidden = true;

    return;
  }

  section.hidden = false;

  keyPoints.forEach(function (point) {
    const li = document.createElement("li");

    li.textContent = typeof point === "string" ? point : JSON.stringify(point);

    container.appendChild(li);
  });
}

/* ============================================================
 * Related Materials
 * ============================================================
 */

function renderRelatedMaterials(materials) {
  const section = document.getElementById("relatedMaterialsSection");

  const container = document.getElementById("relatedMaterials");

  if (!section || !container) {
    return;
  }

  container.innerHTML = "";

  if (!Array.isArray(materials) || materials.length === 0) {
    section.hidden = true;

    return;
  }

  section.hidden = false;

  materials.forEach(function (material) {
    const item = document.createElement("div");

    item.className = "related-material-item";

    if (typeof material === "string") {
      item.textContent = material;
    } else {
      item.textContent =
        material.title || material.name || JSON.stringify(material);
    }

    container.appendChild(item);
  });
}

/* ============================================================
 * Metadata
 * ============================================================
 *
 * 回答本文とは別の情報。
 * ============================================================
 */

function renderMetadata(metadata) {
  const data = metadata || {};

  setText(
    "queryAnalysisElapsed",
    formatMilliseconds(data.query_analysis_elapsed_ms),
  );

  setText("retrievalElapsed", formatMilliseconds(data.retrieval_elapsed_ms));

  setText(
    "answerabilityElapsed",
    formatMilliseconds(data.answerability_elapsed_ms),
  );

  setText("llmElapsed", formatMilliseconds(data.llm_elapsed_ms));

  setText("totalElapsed", formatMilliseconds(data.total_elapsed_ms));

  setText("retrievedCount", formatValue(data.retrieved_count));

  setText("gateCandidateCount", formatValue(data.gate_candidate_count));

  setText("finalContextCount", formatValue(data.final_context_count));

  setText("cacheHit", formatBoolean(data.cache_hit));

  setText("fallbackUsed", formatBoolean(data.fallback_used));
}

function formatMilliseconds(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value) + " ms";
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function formatBoolean(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return value ? "有" : "無";
}

/* ============================================================
 * Clear Answer
 * ============================================================
 */

function clearAnswer() {
  renderAnswer("");

  renderAnswerStatus("");

  renderAnswerability("", "");

  renderSources([]);

  renderSourcePages([]);

  renderKeyPoints([]);

  renderRelatedMaterials([]);

  renderMetadata({});

  window.disageLastDocuments = [];
}

/* ============================================================
 * Loading
 * ============================================================
 */

function showLoading() {
  const answer = document.getElementById("answer");

  const status = document.getElementById("answerStatus");

  if (answer) {
    answer.innerHTML = `
            <div class="loading-state">
                <p>
                    回答を生成しています...
                </p>
            </div>
        `;
  }

  if (status) {
    status.textContent = "回答生成中";

    status.className = "answer-status";
  }
}

/* ============================================================
 * Error
 * ============================================================
 */

function renderError(message) {
  const answer = document.getElementById("answer");

  const status = document.getElementById("answerStatus");

  if (answer) {
    answer.innerHTML = `

            <div
                class="error-message"
            >

                <h3>
                    エラー
                </h3>

                <p>
                    ${escapeHtml(message)}
                </p>

            </div>

        `;
  }

  if (status) {
    status.textContent = "エラー";

    status.className = "answer-status answerability-none";
  }
}

/* ============================================================
 * Question List
 * ============================================================
 */

function renderQuestionList() {
  const container = document.getElementById("questionList");

  const countElement = document.getElementById("questionCount");

  if (!container) {
    return;
  }

  const history = getLocalHistory();

  if (countElement) {
    countElement.textContent = history.length;
  }

  if (history.length === 0) {
    container.innerHTML = `

            <div class="empty-state">

                <p>
                    質問はまだありません。
                </p>

                <p>
                    下の入力欄から質問してください。
                </p>

            </div>

        `;

    return;
  }

  container.innerHTML = history
    .map(function (turn, index) {
      return `

                        <button
                            type="button"
                            class="question-item"
                            data-history-index="${index}"
                        >

                            <span>
                                ${escapeHtml(turn.question)}
                            </span>

                        </button>

                    `;
    })
    .join("");
}

/* ============================================================
 * Thread List
 * ============================================================
 */

function renderThreadList() {
  const container = document.getElementById("threadList");

  const countElement = document.getElementById("threadCount");

  if (!container) {
    return;
  }

  const history = getLocalHistory();

  if (countElement) {
    countElement.textContent = history.length > 0 ? "1" : "0";
  }

  if (history.length === 0) {
    container.innerHTML = `

            <div class="empty-state">

                <p>
                    スレッドはありません。
                </p>

            </div>

        `;

    return;
  }

  const firstQuestion = history[0].question || "新しいスレッド";

  container.innerHTML = `

        <button
            type="button"
            class="thread-item active"
            data-thread-index="0"
        >

            <span
                class="thread-item-title"
            >
                ${escapeHtml(firstQuestion)}
            </span>

            <span
                class="thread-item-meta"
            >
                ${history.length}件の質問
            </span>

        </button>

    `;
}

/* ============================================================
 * Thread Header
 * ============================================================
 */

function updateThreadHeader() {
  const title = document.getElementById("currentThreadTitle");

  const summary = document.getElementById("currentThreadSummary");

  const history = getLocalHistory();

  if (!title) {
    return;
  }

  if (history.length === 0) {
    title.textContent = "新しいスレッド";

    if (summary) {
      summary.textContent = "質問を送信して会話を開始してください。";
    }

    return;
  }

  title.textContent = history[0].question || "研修AIアシスタント";

  if (summary) {
    summary.textContent = `${history.length}件の質問`;
  }
}

/* ============================================================
 * History Selection
 * ============================================================
 */

function selectHistoryItem(index) {
  const history = getLocalHistory();

  const turn = history[index];

  if (!turn) {
    return;
  }

  renderAnswer(turn.answer || "");

  renderAnswerStatus(turn.answerability_status || "");

  renderAnswerability(
    turn.answerability_status || "",
    turn.answerability_reason || "",
  );

  renderSources(turn.sources || []);

  renderSourcePages(turn.source_pages || []);

  renderDocuments(turn.documents || []);

  renderMetadata(turn.metadata || {});
}

/* ============================================================
 * History Events
 * ============================================================
 */

function setupHistoryEvents() {
  const threadList = document.getElementById("threadList");

  const questionList = document.getElementById("questionList");

  if (threadList) {
    threadList.addEventListener("click", function (event) {
      const item = event.target.closest("[data-thread-index]");

      if (!item) {
        return;
      }

      renderQuestionList();
    });
  }

  if (questionList) {
    questionList.addEventListener("click", function (event) {
      const item = event.target.closest("[data-history-index]");

      if (!item) {
        return;
      }

      const index = Number(item.dataset.historyIndex);

      if (Number.isNaN(index)) {
        return;
      }

      selectHistoryItem(index);
    });
  }
}

/* ============================================================
 * Ask Button
 * ============================================================
 *
 * ここが今回の重要修正箇所。
 *
 * HTMLの #askButton と askQuestion() を
 * 明示的に接続する。
 *
 * data-bound によって二重登録も防止する。
 *
 * ============================================================
 */

function setupAskButton() {
  const button = document.getElementById("askButton");

  if (!button) {
    console.error("質問ボタン(#askButton)が見つかりません。");

    return;
  }

  if (button.dataset.bound === "true") {
    return;
  }

  button.addEventListener("click", askQuestion);

  button.dataset.bound = "true";
}

/* ============================================================
 * Question Input
 * ============================================================
 */

function setupQuestionInput() {
  const question = document.getElementById("question");

  if (!question) {
    console.error("質問入力欄(#question)が見つかりません。");

    return;
  }

  if (question.dataset.bound === "true") {
    return;
  }

  question.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();

      askQuestion();
    }
  });

  question.dataset.bound = "true";
}

/* ============================================================
 * New Thread
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

  clearAnswer();

  renderThreadList();

  renderQuestionList();

  updateThreadHeader();
}

/* ============================================================
 * New Thread Button
 * ============================================================
 */

function setupNewThreadButton() {
  const button = document.getElementById("newThreadButton");

  if (!button) {
    return;
  }

  if (button.dataset.bound === "true") {
    return;
  }

  button.addEventListener("click", resetSession);

  button.dataset.bound = "true";
}

/* ============================================================
 * Bookmark
 * ============================================================
 */

function setupBookmarkButton() {
  const button = document.getElementById("bookmarkButton");

  if (!button) {
    return;
  }

  if (button.dataset.bound === "true") {
    return;
  }

  button.addEventListener("click", function () {
    const active = button.dataset.bookmarked === "true";

    button.dataset.bookmarked = active ? "false" : "true";

    button.textContent = active ? "☆" : "★";

    button.setAttribute("aria-pressed", active ? "false" : "true");
  });

  button.dataset.bound = "true";
}

/* ============================================================
 * Thread Search
 * ============================================================
 */

function setupThreadSearch() {
  const input = document.getElementById("threadSearch");

  if (!input) {
    return;
  }

  if (input.dataset.bound === "true") {
    return;
  }

  input.addEventListener("input", function () {
    const keyword = input.value.trim().toLowerCase();

    const items = document.querySelectorAll("#threadList .thread-item");

    items.forEach(function (item) {
      const text = item.textContent.toLowerCase();

      item.hidden = keyword !== "" && !text.includes(keyword);
    });
  });

  input.dataset.bound = "true";
}

/* ============================================================
 * Question Input Status
 * ============================================================
 */

function updateQuestionInputStatus() {
  const question = document.getElementById("question");

  const status = document.getElementById("questionInputStatus");

  if (!question || !status) {
    return;
  }

  const length = question.value.length;

  if (length === 0) {
    status.textContent = "質問を入力してください。";

    return;
  }

  status.textContent = `${length}文字`;
}

/* ============================================================
 * Question Input Status Event
 * ============================================================
 */

function setupQuestionInputStatus() {
  const question = document.getElementById("question");

  if (!question) {
    return;
  }

  if (question.dataset.statusBound === "true") {
    return;
  }

  question.addEventListener("input", updateQuestionInputStatus);

  question.dataset.statusBound = "true";
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
    renderError("質問入力欄が見つかりません。");

    return;
  }

  const question = questionElement.value.trim();

  const studentId = studentElement ? studentElement.value.trim() : "";

  if (!question) {
    questionElement.focus();

    return;
  }

  const sessionId = getSessionId();

  const history = getLocalHistory();

  if (history.length >= MAX_QUESTIONS_PER_THREAD) {
    const dialog = document.getElementById("newThreadDialog");

    if (dialog && typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      resetSession();
    }

    return;
  }

  if (askButton) {
    askButton.disabled = true;
  }

  showLoading();

  try {
    const response = await fetch("/query", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",

        Accept: "application/json",
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

    /* --------------------------------------------
     * Answer
     * --------------------------------------------
     */

    renderAnswer(json.answer || "");

    /* --------------------------------------------
     * Answerability
     * --------------------------------------------
     */

    renderAnswerStatus(json.answerability_status || "");

    renderAnswerability(
      json.answerability_status || "",
      json.answerability_reason || "",
    );

    /* --------------------------------------------
     * Sources
     * --------------------------------------------
     */

    renderSources(Array.isArray(json.sources) ? json.sources : []);

    /* --------------------------------------------
     * Source Pages
     * --------------------------------------------
     */

    renderSourcePages(
      Array.isArray(json.source_pages) ? json.source_pages : [],
    );

    /* --------------------------------------------
     * Documents
     * --------------------------------------------
     */

    renderDocuments(Array.isArray(json.documents) ? json.documents : []);

    /* --------------------------------------------
     * Optional UI Information
     * --------------------------------------------
     */

    renderKeyPoints(Array.isArray(json.key_points) ? json.key_points : []);

    renderRelatedMaterials(
      Array.isArray(json.related_materials) ? json.related_materials : [],
    );

    /* --------------------------------------------
     * Metadata
     *
     * 回答本文とは別項目。
     * --------------------------------------------
     */

    renderMetadata(json.metadata || {});

    /* --------------------------------------------
     * Local History
     * --------------------------------------------
     */

    appendLocalHistory(
      question,

      json.answer || "",

      json.answerability_status || "",

      json,
    );

    /* --------------------------------------------
     * Clear Input
     * --------------------------------------------
     */

    questionElement.value = "";

    updateQuestionInputStatus();

    updateThreadHeader();
  } catch (error) {
    console.error("質問処理に失敗しました。", error);

    renderError(
      error instanceof Error
        ? error.message
        : "質問処理中にエラーが発生しました。",
    );
  } finally {
    if (askButton) {
      askButton.disabled = false;
    }
  }
}

/* ============================================================
 * Dialog
 * ============================================================
 */

function setupNewThreadDialog() {
  const createButton = document.getElementById("createNewThreadButton");

  const dialog = document.getElementById("newThreadDialog");

  if (!createButton || !dialog) {
    return;
  }

  if (createButton.dataset.bound === "true") {
    return;
  }

  createButton.addEventListener("click", function () {
    dialog.close();

    resetSession();
  });

  createButton.dataset.bound = "true";
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

  /*
   * UI初期化
   */

  renderThreadList();

  renderQuestionList();

  updateThreadHeader();

  /*
   * イベント登録
   *
   * 特に setupAskButton() が重要。
   */

  setupAskButton();

  setupHistoryEvents();

  setupQuestionInput();

  setupQuestionInputStatus();

  setupNewThreadButton();

  setupBookmarkButton();

  setupThreadSearch();

  setupNewThreadDialog();

  updateQuestionInputStatus();
}

/* ============================================================
 * DOM Ready
 * ============================================================
 */

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initSessionUi, {
    once: true,
  });
} else {
  initSessionUi();
}
