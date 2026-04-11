"""
config.py — All settings via environment variables with Pydantic Settings v2.

V2: centralized configuration for the AIAuditTrail platform.
Reads from environment variables with sensible defaults for demo mode.

Usage::

    from ai_audit_trail.config import settings
    print(settings.db_path)
    print(settings.api_key)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class Settings:
    """
    AIAuditTrail configuration.

    All settings are read from environment variables at import time.
    Defaults are chosen for zero-credential demo operation.

    Production environment variables:
        AUDIT_DB_PATH          — SQLite database file path
        AUDIT_API_KEY          — API key for REST endpoints (X-AIAuditTrail-Key header)
        AUDIT_DEV_MODE         — "true" to bypass auth for local demo
        AUDIT_STORE_PLAINTEXT  — "true" to persist prompt/response text (dev only)
        AUDIT_LOG_LEVEL        — DEBUG | INFO | WARNING | ERROR
        AUDIT_HOST             — API server host (default: 0.0.0.0)
        AUDIT_PORT             — API server port (default: 8000)
        AUDIT_CORS_ORIGINS     — Comma-separated allowed CORS origins
        AUDIT_MAX_PAGE_SIZE    — Max entries per paginated API response
        AUDIT_CHECKPOINT_INTERVAL — Merkle checkpoint frequency (entries)
    """

    def __init__(self) -> None:
        self.db_path: str = os.environ.get(
            "AUDIT_DB_PATH", "audit_trail.db"
        )
        self.api_key: str = os.environ.get(
            "AUDIT_API_KEY", "dev-key-change-in-production"
        )
        self.dev_mode: bool = os.environ.get(
            "AUDIT_DEV_MODE", "true"
        ).lower() in ("true", "1", "yes")
        self.store_plaintext: bool = os.environ.get(
            "AUDIT_STORE_PLAINTEXT", "false"
        ).lower() in ("true", "1", "yes")
        self.log_level: str = os.environ.get(
            "AUDIT_LOG_LEVEL", "INFO"
        ).upper()
        self.host: str = os.environ.get("AUDIT_HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("AUDIT_PORT", "8000"))
        self.cors_origins: list[str] = [
            o.strip()
            for o in os.environ.get("AUDIT_CORS_ORIGINS", "*").split(",")
        ]
        self.max_page_size: int = int(os.environ.get("AUDIT_MAX_PAGE_SIZE", "500"))
        self.checkpoint_interval: int = int(
            os.environ.get("AUDIT_CHECKPOINT_INTERVAL", "1000")
        )
        # Redis for future async background tasks (optional)
        self.redis_url: Optional[str] = os.environ.get("AUDIT_REDIS_URL")

    @property
    def db_path_resolved(self) -> Path:
        return Path(self.db_path).resolve()

    def __repr__(self) -> str:
        return (
            f"Settings(db_path={self.db_path!r}, dev_mode={self.dev_mode}, "
            f"host={self.host}:{self.port})"
        )


# Module-level singleton
settings = Settings()
