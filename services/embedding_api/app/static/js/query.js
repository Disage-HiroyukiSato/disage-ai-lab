async function askQuestion(){

    const question = document.getElementById("question").value;

    document.getElementById("answer").textContent = "問い合わせ中...";
    document.getElementById("documents").innerHTML = "";

    try{

        const response = await fetch(

            "/query",

            {

                method:"POST",

                headers:{

                    "Content-Type":"application/json"

                },

                body:JSON.stringify({

                    question:question

                })

            }

        );

        const json = await response.json();

        document.getElementById("answer").textContent = json.answer;

        document.getElementById("elapsed").textContent =
            json.elapsed_ms + " ms";

        document.getElementById("retrieved").textContent =
            json.retrieved_count;

        const documents = document.getElementById("documents");

        json.documents.forEach((doc,index)=>{

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

    }

    catch(ex){

        document.getElementById("answer").textContent =
            "エラー：" + ex;

    }

}