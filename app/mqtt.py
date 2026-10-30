"""MQTT subscriber that normalises numeric telemetry."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

ReadingCallback = Callable[[str, str, float], None]


class MqttIngestor:
    """Subscribe to ``home/<device>/<metric>`` and call ``on_reading`` for numeric payloads."""

    def __init__(
        self,
        host: str,
        port: int,
        on_reading: ReadingCallback,
        topic: str = "home/+/+",
        username: str = "",
        password: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.topic = topic
        self.on_reading = on_reading
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="telemetry-hub")
        if username:
            self._client.username_pw_set(username, password or None)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._client.connect_async(self.host, self.port, keepalive=30)
        self._client.loop_start()
        logger.info("MQTT ingestor connecting to %s:%s", self.host, self.port)

    def stop(self) -> None:
        self._stop.set()
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:  # pragma: no cover - best effort shutdown
            pass

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            logger.info("MQTT connected, subscribing to %s", self.topic)
            client.subscribe(self.topic, qos=0)
        else:
            logger.warning("MQTT connection failed: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            parts = message.topic.split("/")
            if len(parts) < 3:
                return
            device_id, metric = parts[1], "/".join(parts[2:])
            value = float(message.payload.decode().strip())
        except (ValueError, UnicodeDecodeError):
            logger.debug("ignoring non-numeric payload on %s", message.topic)
            return
        try:
            self.on_reading(device_id, metric, value)
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception("reading handler failed for %s", message.topic)
