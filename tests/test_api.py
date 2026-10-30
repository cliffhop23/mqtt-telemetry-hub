"""API tests run against a temporary SQLite database; no broker required."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "test.db"), start_mqtt=False)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["devices"] == 0


def test_devices_empty(client: TestClient) -> None:
    assert client.get("/api/devices").json() == {"items": []}


def test_insert_and_query_readings(client: TestClient) -> None:
    db = client.app.state.db
    db.insert_reading("esp32c3", "rssi", -48)
    db.insert_reading("esp32c3", "rssi", -51)
    db.insert_reading("esp32c3", "heap", 199296)

    devices = client.get("/api/devices").json()["items"]
    assert len(devices) == 1
    assert devices[0]["device_id"] == "esp32c3"
    assert devices[0]["latest"]["rssi"] == -51
    assert devices[0]["latest"]["heap"] == 199296

    readings = client.get(
        "/api/devices/esp32c3/readings", params={"metric": "rssi", "limit": 10}
    ).json()
    assert [item["value"] for item in readings["items"]] == [-48, -51]

    latest = client.get("/api/devices/esp32c3/latest").json()
    assert latest["latest"]["rssi"] == -51


def test_reading_limit_validation(client: TestClient) -> None:
    response = client.get("/api/devices/esp32c3/readings", params={"limit": 0})
    assert response.status_code == 422


def test_websocket_hello(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "hello"
        assert message["devices"] == []


def test_dashboard_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "MQTT Telemetry Hub" in response.text
