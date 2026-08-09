from app.services.query_expansion_service import query_expansion_service


def test_expand_disabled(monkeypatch):

    monkeypatch.setattr(

        "app.config.settings.enable_query_expansion",

        False

    )

    queries = query_expansion_service.expand(

        "javascript"

    )

    assert queries == [

        "javascript"

    ]


def test_expand_enabled(monkeypatch):

    monkeypatch.setattr(

        "app.config.settings.enable_query_expansion",

        True

    )

    monkeypatch.setattr(

        "app.config.settings.expansion_limit",

        10

    )

    query_expansion_service.dictionary = {

        "javascript": [

            "js",

            "java script"

        ]

    }

    query_expansion_service.loaded = True

    queries = query_expansion_service.expand(

        "javascript"

    )

    assert "javascript" in queries

    assert "js" in queries

    assert "java script" in queries


def test_duplicate_removed(monkeypatch):

    monkeypatch.setattr(

        "app.config.settings.enable_query_expansion",

        True

    )

    monkeypatch.setattr(

        "app.config.settings.expansion_limit",

        10

    )

    query_expansion_service.dictionary = {

        "javascript": [

            "js",

            "js",

            "javascript"

        ]

    }

    query_expansion_service.loaded = True

    queries = query_expansion_service.expand(

        "javascript"

    )

    assert len(queries) == len(set(queries))


def test_expansion_limit(monkeypatch):

    monkeypatch.setattr(

        "app.config.settings.enable_query_expansion",

        True

    )

    monkeypatch.setattr(

        "app.config.settings.expansion_limit",

        2

    )

    query_expansion_service.dictionary = {

        "javascript": [

            "js",

            "java script",

            "java-script"

        ]

    }

    query_expansion_service.loaded = True

    queries = query_expansion_service.expand(

        "javascript"

    )

    assert len(queries) == 2