//
// Phase17 : session_id管理
//
// localStorageにセッションIDを保持し、ページ再訪問時も
// 同じ会話を継続できるようにする。
//
// 「新しい会話を始める」ボタンで新規IDを発行し、
// 画面上の会話履歴表示もクリアする。
//

const SESSION_STORAGE_KEY = "disage_session_id";

const HISTORY_STORAGE_KEY = "disage_history";


function generateSessionId(){

    if (crypto.randomUUID){

        return crypto.randomUUID();

    }

    // crypto.randomUUIDが使えない環境向けの簡易フォールバック

    return "session-" + Date.now() + "-" +
        Math.random().toString(36).slice(2, 10);

}


function getSessionId(){

    let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);

    if (!sessionId){

        sessionId = generateSessionId();

        localStorage.setItem(SESSION_STORAGE_KEY, sessionId);

    }

    return sessionId;

}


function getLocalHistory(){

    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);

    if (!raw){

        return [];

    }

    try{

        return JSON.parse(raw);

    }

    catch(ex){

        return [];

    }

}


function appendLocalHistory(question, answer, isOffTopic){

    const history = getLocalHistory();

    history.push({

        question: question,

        answer: answer,

        isOffTopic: !!isOffTopic

    });

    localStorage.setItem(

        HISTORY_STORAGE_KEY,

        JSON.stringify(history)

    );

    renderHistory();

}


function renderHistory(){

    const container = document.getElementById("history");

    const history = getLocalHistory();

    if (history.length === 0){

        container.innerHTML =
            "<p>まだ会話がありません。</p>";

        return;

    }

    container.innerHTML = history.map(function(turn){

        const offTopicLabel = turn.isOffTopic
            ? ' <span class="off-topic-badge">教材外</span>'
            : "";

        return (
            '<div class="history-turn">' +
            '<p><b>Q.</b> ' + escapeHtml(turn.question) + '</p>' +
            '<p><b>A.</b> ' + escapeHtml(turn.answer) +
            offTopicLabel + '</p>' +
            '</div>'
        );

    }).join("");

}


function escapeHtml(text){

    const div = document.createElement("div");

    div.textContent = text;

    return div.innerHTML;

}


function resetSession(){

    const newSessionId = generateSessionId();

    localStorage.setItem(SESSION_STORAGE_KEY, newSessionId);

    localStorage.removeItem(HISTORY_STORAGE_KEY);

    document.getElementById("sessionId").value = newSessionId;

    renderHistory();

    document.getElementById("answer").textContent = "";

    document.getElementById("documents").innerHTML = "";

}


function initSessionUi(){

    document.getElementById("sessionId").value = getSessionId();

    renderHistory();

}


async function askQuestion(){

    const question = document.getElementById("question").value;

    const studentId = document.getElementById("studentId").value;

    const sessionId = getSessionId();

    document.getElementById("answer").textContent = "問い合わせ中...";
    document.getElementById("documents").innerHTML = "";
    document.getElementById("offTopic").textContent = "";

    try{

        const response = await fetch(

            "/query",

            {

                method:"POST",

                headers:{

                    "Content-Type":"application/json"

                },

                body:JSON.stringify({

                    question: question,

                    student_id: studentId || null,

                    session_id: sessionId

                })

            }

        );

        const json = await response.json();

        document.getElementById("answer").textContent = json.answer;

        document.getElementById("elapsed").textContent =
            json.elapsed_ms + " ms";

        document.getElementById("retrieved").textContent =
            json.retrieved_count;

        document.getElementById("offTopic").textContent =
            json.is_off_topic ? "教材外の可能性あり" : "教材内";

        const documents = document.getElementById("documents");

        documents.innerHTML = "";

        (json.documents || []).forEach((doc,index)=>{

            const div = document.createElement("div");

            div.className = "document";

            div.innerHTML = `

                <h3>Document ${index + 1}</h3>

                <p>
                    <b>Score</b><br>
                    ${doc.score.toFixed(4)}
                </p>

                <p>
                    <b>Distance</b><br>
                    ${doc.distance.toFixed(4)}
                </p>

                <p><b>Metadata</b></p>

                <pre>${JSON.stringify(doc.metadata, null, 2)}</pre>

                <p><b>Document</b></p>

                <pre>${doc.document}</pre>

            `;

            documents.appendChild(div);

        });

        //
        // Phase17 : 画面上の会話履歴表示を更新
        //
        // サーバー側（conversation_history）にも同時に
        // 保存されているが、画面表示用に簡易的にローカルへ
        // も保持する。
        //

        appendLocalHistory(

            question,

            json.answer,

            json.is_off_topic

        );

        document.getElementById("question").value = "";

    }

    catch(ex){

        document.getElementById("answer").textContent =
            "エラー：" + ex;

    }

}


document.addEventListener("DOMContentLoaded", initSessionUi);