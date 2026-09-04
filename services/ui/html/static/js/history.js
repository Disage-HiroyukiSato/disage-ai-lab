function escapeHtml(text){

    const div = document.createElement("div");

    div.textContent = text;

    return div.innerHTML;

}


function formatDateTime(isoString){

    if (!isoString){

        return "";

    }

    try{

        const date = new Date(isoString);

        return date.toLocaleString("ja-JP");

    }

    catch(ex){

        return isoString;

    }

}


async function loadSessions(){

    const studentId = document.getElementById("studentId").value.trim();

    const sessionList = document.getElementById("sessionList");

    const sessionDetail = document.getElementById("sessionDetail");

    sessionDetail.innerHTML =
        "<p>セッションを選択すると、ここに会話全体が表示されます。</p>";

    if (!studentId){

        sessionList.innerHTML =
            "<p>受講生IDを入力してください。</p>";

        return;

    }

    sessionList.innerHTML = "<p>読み込み中...</p>";

    try{

        const response = await fetch(

            "/history/sessions?student_id=" +
                encodeURIComponent(studentId)

        );

        const json = await response.json();

        if (!json.sessions || json.sessions.length === 0){

            sessionList.innerHTML =
                "<p>この受講生の会話履歴は見つかりませんでした。</p>";

            return;

        }

        sessionList.innerHTML = "";

        json.sessions.forEach((session) => {

            const div = document.createElement("div");

            div.className = "document";

            div.style.cursor = "pointer";

            div.innerHTML = `

                <h3>${escapeHtml(session.first_question || "(質問なし)")}</h3>

                <p>
                    <b>セッションID</b><br>
                    ${escapeHtml(session.session_id)}
                </p>

                <p>
                    <b>開始日時</b><br>
                    ${formatDateTime(session.started_at)}
                </p>

                <p>
                    <b>最終更新</b><br>
                    ${formatDateTime(session.last_activity_at)}
                </p>

                <p>
                    <b>発話数</b><br>
                    ${session.message_count}
                </p>

            `;

            div.addEventListener("click", () => {

                loadSessionDetail(

                    session.session_id

                );

            });

            sessionList.appendChild(

                div

            );

        });

    }

    catch(ex){

        sessionList.innerHTML =
            "<p>エラー：" + ex + "</p>";

    }

}


async function loadSessionDetail(sessionId){

    const sessionDetail = document.getElementById("sessionDetail");

    sessionDetail.innerHTML = "<p>読み込み中...</p>";

    try{

        const response = await fetch(

            "/history/sessions/" +
                encodeURIComponent(sessionId)

        );

        if (!response.ok){

            sessionDetail.innerHTML =
                "<p>セッション詳細の取得に失敗しました。</p>";

            return;

        }

        const json = await response.json();

        sessionDetail.innerHTML = "";

        json.messages.forEach((message) => {

            const div = document.createElement("div");

            div.className = "history-turn";

            const speaker =
                message.role === "user" ? "受講生" : "アシスタント";

            const offTopicLabel = message.is_off_topic
                ? ' <span class="off-topic-badge">教材外</span>'
                : "";

            div.innerHTML = `

                <p>
                    <b>${speaker}</b>
                    <small>${formatDateTime(message.created_at)}</small>
                    ${offTopicLabel}
                </p>

                <p>${escapeHtml(message.content)}</p>

            `;

            sessionDetail.appendChild(

                div

            );

        });

    }

    catch(ex){

        sessionDetail.innerHTML =
            "<p>エラー：" + ex + "</p>";

    }

}