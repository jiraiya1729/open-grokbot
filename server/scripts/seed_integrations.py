"""Seed integration_definitions with built-in integration types."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.domain.models import IntegrationDefinition

DEFINITIONS = [
    {
        "key": "github",
        "name": "GitHub",
        "auth_type": "api_key",
        "capabilities": {"read": ["repos", "issues", "prs"], "write": ["issues", "prs"]},
        "risk_metadata": {"write_requires_approval": True},
        "enabled": True,
    },
    {
        "key": "google_drive",
        "name": "Google Drive",
        "auth_type": "oauth2",
        "capabilities": {"read": ["files", "folders"], "write": ["files"]},
        "risk_metadata": {"write_requires_approval": True},
        "enabled": True,
    },
    {
        "key": "generic_webhook",
        "name": "Generic Webhook",
        "auth_type": "webhook_secret",
        "capabilities": {"receive": ["events"]},
        "risk_metadata": {"write_requires_approval": False},
        "enabled": True,
    },
]


def seed() -> None:
    with SessionLocal() as s:
        for defn in DEFINITIONS:
            existing = s.query(IntegrationDefinition).filter_by(key=defn["key"]).first()
            if existing is None:
                s.add(IntegrationDefinition(**defn))
        s.commit()
    print(f"Seeded {len(DEFINITIONS)} integration definitions.")


if __name__ == "__main__":
    seed()
