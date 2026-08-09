def test_document_register(client):

    response = client.post(

        "/documents",

        json={

            "document_id": "pytest001",

            "title": "ガンダム",

            "category": "Anime",

            "keywords": "ガンダム,アムロ",

            "text": "ガンダムは地球連邦軍の試作モビルスーツです。"

        }

    )

    assert response.status_code == 200

    json = response.json()

    assert json["success"] is True

    assert json["document_id"] == "pytest001"

    assert json["chunks"] >= 1