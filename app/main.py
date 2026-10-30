"""FastAPI application: MQTT ingestion, REST API, WebSocket stream, dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Database
from .mqtt import MqttIngestor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class ConnectionManager:
    """Track connected dashboard sockets and fan out live readings."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        text = json.dumps(payload)
        for websocket in list(self.clients):
            try:
                await websocket.send_text(text)
            except Exception:  # pragma: no cover - socket already gone
                self.disconnect(websocket)


def create_app(db_path: str | None = None, start_mqtt: bool = True) -> FastAPI:
    """Application factory so tests can run against a temp DB without a broker."""
    db = Database(db_path or settings.db_path)
    manager = ConnectionManager()
    started = time.time()
    ingestor: MqttIngestor | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal ingestor
        db.connect()
        if start_mqtt:
            loop = asyncio.get_running_loop()

            def on_reading(device: str, metric: str, value: float) -> None:
                reading = db.insert_reading(device, metric, value)
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "reading", **reading}), loop
                )

            ingestor = MqttIngestor(
                settings.mqtt_host,
                settings.mqtt_port,
                on_reading,
                settings.mqtt_topic,
                settings.mqtt_user,
                settings.mqtt_pass,
            )
            ingestor.start()
        yield
        if ingestor is not None:
            ingestor.stop()
        db.close()

    app = FastAPI(title="MQTT Telemetry Hub", version="1.0.0", lifespan=lifespan)
    app.state.db = db
    app.state.manager = manager
    app.state.started = started

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "ok",
            "uptime_seconds": round(time.time() - started, 1),
            "devices": db.device_count(),
        }

    @app.get("/api/devices", tags=["devices"])
    def list_devices() -> dict:
        return {"items": db.devices()}

    @app.get("/api/devices/{device}/latest", tags=["devices"])
    def latest(device: str) -> dict:
        return {"device_id": device, "latest": db.latest(device)}

    @app.get("/api/devices/{device}/readings", tags=["devices"])
    def readings(
        device: str,
        metric: str | None = None,
        limit: int = Query(default=100, ge=1, le=5000),
    ) -> dict:
        return {"device_id": device, "metric": metric, "items": db.readings(device, metric, limit)}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            await websocket.send_text(json.dumps({"type": "hello", "devices": db.devices()}))
            while True:
                await websocket.receive_text()  # client pings keep the socket open
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
