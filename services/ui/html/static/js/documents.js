async function registerDocument(){

    const documentId = document.getElementById("documentId").value;

    const text = document.getElementById("documentText").value;

    const result = document.getElementById("result");

    result.textContent = "登録中...";

    try{

        const response = await fetch(

            "/documents",

            {

                method:"POST",

                headers:{

                    "Content-Type":"application/json"

                },

                body:JSON.stringify({

                    document_id:documentId,

                    text:text

                })

            }

        );

        const json = await response.json();

        result.textContent = JSON.stringify(

            json,

            null,

            2

        );

    }

    catch(ex){

        result.textContent = ex;

    }

}