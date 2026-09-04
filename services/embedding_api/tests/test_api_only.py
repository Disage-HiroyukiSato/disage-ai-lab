from app.main import app


def test_web_ui_routes_are_not_served_by_api():
    paths = {route.path for route in app.routes}

    assert "/" not in paths
    assert "/documents-ui" not in paths
    assert "/query-ui" not in paths
    assert "/history-ui" not in paths
    assert "/static" not in paths
