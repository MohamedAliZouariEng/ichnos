from fastapi.testclient import TestClient

from ichnos import __version__
from ichnos.main import create_app
from ichnos.settings import Settings


def test_healthz_reports_ok() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "database": "ok"}


def test_healthz_reports_unavailable_database() -> None:
    settings = Settings(database_url="sqlite:////nonexistent-dir/ichnos.db")
    client = TestClient(create_app(settings))  # no lifespan, so no migration attempt
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "unavailable"


def test_openapi_is_served_under_api() -> None:
    client = TestClient(create_app(Settings()))
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Ichnos API"
