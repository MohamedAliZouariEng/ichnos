from fastapi.testclient import TestClient

from ichnos import __version__
from ichnos.main import create_app
from ichnos.settings import Settings


def test_healthz_reports_ok() -> None:
    client = TestClient(create_app(Settings()))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_openapi_is_served_under_api() -> None:
    client = TestClient(create_app(Settings()))
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Ichnos API"
