from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.agents.runtime import execute_bot_run
from app.api.routes.computer.computers import computer_provider
from app.infrastructure.blob_store import BlobTooLargeError, LocalBlobStore, safe_filename
from app.infrastructure.computer import ComputerLimits, ComputerObservation, FakeComputerProvider
from app.main import app
from app.tools.tool_gateway import ToolGateway
from computer_daemon.main import app as daemon_app


def create_bot_and_dm(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    bot = client.post(
        "/api/v1/bots",
        json={
            "name": "Mira",
            "role_title": "File analyst",
            "description": "Turns source material into useful results.",
            "system_instructions": "Read attached evidence and summarize it precisely.",
            "avatar_value": "M",
        },
    ).json()
    conversation = client.post(f"/api/v1/bots/{bot['id']}/dm").json()
    return bot, conversation


def test_local_blob_store_contract_and_traversal(tmp_path) -> None:
    store = LocalBlobStore(tmp_path)
    first = store.put("uploads/aa/one", io.BytesIO(b"same bytes"))
    second = store.put("uploads/bb/two", io.BytesIO(b"same bytes"))
    assert first.sha256 == second.sha256
    assert store.open(first.key).read() == b"same bytes"
    assert store.path_for(first.key) != store.path_for(second.key)
    with pytest.raises(ValueError):
        store.path_for("../escape")
    with pytest.raises(BlobTooLargeError):
        store.put("uploads/cc/large", io.BytesIO(b"12345"), max_bytes=4)
    assert safe_filename("../../quarter:report?.txt") == "quarter_report_.txt"


def test_tool_gateway_schema_path_timeout_and_truncation() -> None:
    provider = FakeComputerProvider(
        lambda command: ComputerObservation(True, stdout="x" * 100, exit_code=0)
    )
    session = provider.provision("workspace", ComputerLimits())
    gateway = ToolGateway(provider, output_bytes=12)
    written = gateway.invoke(
        session.provider_session_id,
        "filesystem.write",
        {"path": "notes/source.txt", "content": "hello"},
    )
    assert written["ok"] is True
    assert (
        gateway.invoke(
            session.provider_session_id, "filesystem.read", {"path": "notes/source.txt"}
        )["stdout"]
        == "hello"
    )
    truncated = gateway.invoke(
        session.provider_session_id, "shell.run", {"command": ["echo", "hello"]}
    )
    assert truncated["truncated"] is True
    with pytest.raises(ValueError):
        gateway.invoke(session.provider_session_id, "filesystem.read", {})
    escaped = gateway.invoke(session.provider_session_id, "filesystem.read", {"path": "../secret"})
    assert escaped["ok"] is False


def test_daemon_internal_boundary_rejects_missing_token() -> None:
    daemon = TestClient(daemon_app)
    assert daemon.get("/health/live").status_code == 200
    assert (
        daemon.post(
            "/v1/sessions",
            json={
                "workspace_key": "abc",
                "image": "sandbox:test",
                "limits": {"memory_mb": 512, "cpus": 1, "pids": 128},
            },
        ).status_code
        == 401
    )


def test_upload_download_assets_and_attachment_authorization(client: TestClient) -> None:
    _, conversation = create_bot_and_dm(client)
    uploaded = client.post(
        f"/api/v1/conversations/{conversation['id']}/files",
        files={"upload": ("brief.txt", b"evidence survives", "text/plain")},
    )
    assert uploaded.status_code == 201
    file_record = uploaded.json()
    assert file_record["sha256"]
    download = client.get(file_record["download_url"])
    assert download.content == b"evidence survives"
    assets = client.get(f"/api/v1/conversations/{conversation['id']}/assets").json()
    assert assets["files"][0]["id"] == file_record["id"]
    submitted = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "text": "Summarize this source.",
            "client_idempotency_key": "web:v02-attachment",
            "file_ids": [file_record["id"]],
        },
    )
    assert submitted.status_code == 202
    assert submitted.json()["message"]["structured_content"]["files"][0]["name"] == "brief.txt"
    missing = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "text": "Use an unavailable source.",
            "client_idempotency_key": "web:v02-missing",
            "file_ids": [str(uuid.uuid4())],
        },
    )
    assert missing.status_code == 400


def test_computer_lifecycle_uses_stable_workspace(client: TestClient) -> None:
    bot, _ = create_bot_and_dm(client)
    fake = FakeComputerProvider()
    app.dependency_overrides[computer_provider] = lambda: fake
    try:
        initial = client.get(f"/api/v1/bots/{bot['id']}/computer").json()
        started = client.post(f"/api/v1/bots/{bot['id']}/computer")
        assert started.status_code == 201
        assert started.json()["status"] == "running"
        assert started.json()["workspace_id"] == initial["workspace_id"]
        assert started.json()["browser_available"] is True
        assert client.delete(f"/api/v1/bots/{bot['id']}/computer").status_code == 204
    finally:
        app.dependency_overrides.pop(computer_provider, None)


def test_attachment_run_exports_durable_artifact(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.agents.runtime as runtime

    _, conversation = create_bot_and_dm(client)
    uploaded = client.post(
        f"/api/v1/conversations/{conversation['id']}/files",
        files={"upload": ("source.txt", b"alpha beta", "text/plain")},
    ).json()
    submitted = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "text": "Create the result.",
            "client_idempotency_key": "web:v02-artifact",
            "file_ids": [uploaded["id"]],
        },
    ).json()
    fake = FakeComputerProvider()
    monkeypatch.setattr(runtime, "provider_from_settings", lambda settings: fake)
    assert execute_bot_run(uuid.UUID(submitted["run"]["id"]))["status"] == "completed"
    assets = client.get(f"/api/v1/conversations/{conversation['id']}/assets").json()
    assert len(assets["artifacts"]) == 1
    artifact = assets["artifacts"][0]
    assert client.get(artifact["download_url"]).content.startswith(b"# Result")
    history = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()["items"]
    assert history[-1]["structured_content"]["artifacts"][0]["id"] == artifact["id"]
