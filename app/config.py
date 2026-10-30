"""Environment-driven configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("HUB_DB", "telemetry.db")
    mqtt_host: str = os.getenv("HUB_MQTT_HOST", "localhost")
    mqtt_port: int = int(os.getenv("HUB_MQTT_PORT", "1883"))
    mqtt_topic: str = os.getenv("HUB_MQTT_TOPIC", "home/+/+")
    mqtt_user: str = os.getenv("HUB_MQTT_USER", "")
    mqtt_pass: str = os.getenv("HUB_MQTT_PASS", "")
    mqtt_enabled: bool = _env_bool("HUB_MQTT_ENABLED", True)


settings = Settings()
