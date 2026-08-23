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

    sources: response.sources || [],

    source_pages: response.source_pages || [],

    documents: response.documents || [],

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
 *
 * sources
 *
 * 回答の根拠・参考資料。
 *
 * page_reference
 * はバックエンドがRAG metadataから取得した値。
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

    const title = source.title || "資料";

    const documentId = source.document_id || "";

    const chunkNo = source.chunk_no ?? "";

    const pageReference = source.page_reference || "";

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
                  documentId || chunkNo
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
    container.innerHTML = `
            <p class="empty-message">
                参照ページはありません。
            </p>
        `;

    return;
  }

  const uniquePages = Array.from(
    new Set(
      sourcePages
        .filter((page) => page != null && String(page).trim() !== "")
        .map((page) => String(page)),
    ),
  );

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
  /*
   * 現在のquery.htmlには
   * documents専用の表示領域がない。
   *
   * そのため、ここではkeyPoints等と混ぜず、
   * APIレスポンスを内部状態として保持するだけにする。
   *
   * 回答本文には表示しない。
   */

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

    li.textContent = point;

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

    item.textContent =
      typeof material === "string"
        ? material
        : material.title || material.name || JSON.stringify(material);

    container.appendChild(item);
  });
}

/* ============================================================
 * Metadata
 * ============================================================
 *
 * 回答本文とは完全に分離する。
 *
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
 * Thread Title
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

  document.querySelectorAll("[data-history-index]").forEach(function (element) {
    element.classList.remove("active");
  });

  document.querySelectorAll("[data-history-index]").forEach(function (element) {
    if (Number(element.dataset.historyIndex) === index) {
      element.classList.add("active");
    }
  });
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

  button.addEventListener("click", function () {
    resetSession();
  });
}

/* ============================================================
 * Bookmark
 * ============================================================
 *
 * 現段階ではブックマークAPIが存在しないため、
 * ブラウザ上のUI状態だけを保持する。
 *
 * サーバー保存は実施しない。
 *
 * ============================================================
 */

function setupBookmarkButton() {
  const button = document.getElementById("bookmarkButton");

  if (!button) {
    return;
  }

  button.addEventListener("click", function () {
    const active = button.dataset.bookmarked === "true";

    button.dataset.bookmarked = active ? "false" : "true";

    button.textContent = active ? "☆" : "★";

    button.setAttribute("aria-pressed", active ? "false" : "true");
  });
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

  input.addEventListener("input", function () {
    const keyword = input.value.trim().toLowerCase();

    const items = document.querySelectorAll("#threadList .thread-item");

    items.forEach(function (item) {
      const text = item.textContent.toLowerCase();

      item.hidden = keyword !== "" && !text.includes(keyword);
    });
  });
}

/* ============================================================
 * Question Status
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

    renderAnswerStatus(json.answerability_status || "");

    /* --------------------------------------------
     * Answerability
     * --------------------------------------------
     */

    renderAnswerability(
      json.answerability_status || "",
      json.answerability_reason || "",
    );

    /* --------------------------------------------
     * Sources
     * --------------------------------------------
     */

    renderSources(json.sources || []);

    /* --------------------------------------------
     * Source Pages
     * --------------------------------------------
     */

    renderSourcePages(json.source_pages || []);

    /* --------------------------------------------
     * Documents
     * --------------------------------------------
     */

    renderDocuments(json.documents || []);

    /* --------------------------------------------
     * Optional UI Information
     * --------------------------------------------
     */

    renderKeyPoints(json.key_points || []);

    renderRelatedMaterials(json.related_materials || []);

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

    renderError(error.message || "質問処理中にエラーが発生しました。");
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

  createButton.addEventListener("click", function () {
    dialog.close();

    resetSession();
  });
}

/* ============================================================
 * Input Event
 * ============================================================
 */

function setupQuestionInputStatus() {
  const question = document.getElementById("question");

  if (!question) {
    return;
  }

  question.addEventListener("input", updateQuestionInputStatus);
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

  renderThreadList();

  renderQuestionList();

  updateThreadHeader();

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

document.addEventListener("DOMContentLoaded", initSessionUi);
