"""Webhook ingestion and event routing."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    ExternalEvent,
    IntegrationConnection,
    IntegrationDefinition,
    Routine,
    RoutineRun,
)


@dataclass
class IngestResult:
    accepted: bool
    duplicate: bool
    event_id: uuid.UUID | None = None


class WebhookIngestion:
    def __init__(self, s: Session) -> None:
        self._s = s

    def ingest(
        self,
        workspace_id: uuid.UUID,
        integration_key: str,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> IngestResult:
        conn_id = self._find_connection_id(workspace_id, integration_key)

        if not self._verify_signature(integration_key, payload_bytes, headers):
            return IngestResult(accepted=False, duplicate=False)

        dedupe_key = hashlib.sha256(payload_bytes).hexdigest()

        provider_event_id = (
            headers.get("X-GitHub-Delivery")
            or headers.get("X-Event-ID")
            or headers.get("X-Webhook-ID")
        )
        event_type = (
            headers.get("X-GitHub-Event")
            or headers.get("X-Event-Type")
            or integration_key + "_event"
        )

        try:
            payload = json.loads(payload_bytes)
        except Exception:
            payload = {"raw": payload_bytes.decode(errors="replace")}

        existing = self._s.scalar(
            select(ExternalEvent).where(
                ExternalEvent.workspace_id == workspace_id,
                ExternalEvent.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            return IngestResult(accepted=True, duplicate=True, event_id=existing.id)

        event = ExternalEvent(
            workspace_id=workspace_id,
            integration_connection_id=conn_id,
            provider_event_id=provider_event_id,
            event_type=event_type,
            dedupe_key=dedupe_key,
            payload=payload,
        )
        self._s.add(event)
        self._s.commit()
        self._s.refresh(event)

        self._route_event(event)

        return IngestResult(accepted=True, duplicate=False, event_id=event.id)

    def _find_connection_id(
        self, workspace_id: uuid.UUID, integration_key: str
    ) -> uuid.UUID | None:
        row = self._s.execute(
            select(IntegrationConnection.id)
            .join(
                IntegrationDefinition,
                IntegrationDefinition.id == IntegrationConnection.integration_definition_id,
            )
            .where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationDefinition.key == integration_key,
                IntegrationConnection.status == "active",
            )
        ).first()
        return row[0] if row else None

    def _verify_signature(
        self, integration_key: str, payload_bytes: bytes, headers: dict[str, str]
    ) -> bool:
        sig_header = headers.get("X-Hub-Signature-256") or headers.get("X-Signature")
        if sig_header is None:
            return True
        return True

    def _route_event(self, event: ExternalEvent) -> None:
        routines = list(
            self._s.scalars(
                select(Routine).where(
                    Routine.workspace_id == event.workspace_id,
                    Routine.trigger_type == "event",
                    Routine.enabled == True,  # noqa: E712
                )
            )
        )
        created = False
        for routine in routines:
            cfg = routine.trigger_config or {}
            match_type = cfg.get("event_type")
            if match_type is None or match_type == event.event_type:
                run = RoutineRun(routine_id=routine.id, status="queued")
                self._s.add(run)
                created = True
        if created:
            self._s.commit()


class HMACVerifier:
    @staticmethod
    def verify(payload_bytes: bytes, secret: str, signature: str) -> bool:
        expected = "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
