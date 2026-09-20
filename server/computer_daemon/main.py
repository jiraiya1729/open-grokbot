from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import time
from pathlib import PurePosixPath
from typing import Annotated

import httpx
import websockets
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

app = FastAPI(title="Open-GrokBot computer daemon", version="0.3.0")
TOKEN = os.environ.get("COMPUTER_DAEMON_TOKEN", "local-computer-daemon")
VIEWER_SECRET = os.environ.get("COMPUTER_VIEWER_SECRET", "local-viewer-secret-change-me")
WORKSPACE_VOLUME_PREFIX = os.environ.get("COMPUTER_WORKSPACE_VOLUME_PREFIX", "grokbot-workspace")
COMPUTER_NETWORK = os.environ.get("COMPUTER_NETWORK", "open-grokbot-computer")
COMPUTER_EGRESS_NETWORK = os.environ.get("COMPUTER_EGRESS_NETWORK", "open-grokbot-egress")


def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "Invalid daemon token")


class Limits(BaseModel):
    memory_mb: int = Field(ge=128, le=8192)
    cpus: float = Field(ge=0.1, le=8)
    pids: int = Field(ge=32, le=2048)


class ProvisionRequest(BaseModel):
    workspace_key: str = Field(pattern=r"^[a-zA-Z0-9-]{1,80}$")
    image: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_./:-]{0,200}$")
    limits: Limits


class ExecRequest(BaseModel):
    command: list[str] = Field(min_length=1, max_length=64)
    timeout: int = Field(default=30, ge=1, le=120)


class FileWrite(BaseModel):
    path: str
    content: str


def docker(*args: str, timeout: int = 45, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=check
    )


def container_name(value: str) -> str:
    if not re.fullmatch(r"grokbot-[a-zA-Z0-9-]{3,80}", value):
        raise HTTPException(404, "Computer not found")
    return value


def workspace_path(value: str) -> str:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise HTTPException(400, "Invalid workspace path")
    return pure.as_posix()


def inspect_status(name: str) -> str:
    result = docker("inspect", "--format", "{{.State.Status}}", name, check=False)
    if result.returncode != 0:
        return "destroyed"
    return {
        "created": "starting",
        "running": "running",
        "paused": "paused",
        "exited": "stopped",
        "dead": "failed",
    }.get(result.stdout.strip(), "failed")


def wait_for_viewer(name: str) -> None:
    readiness_command = (
        "for i in {1..50}; do "
        "(echo >/dev/tcp/127.0.0.1/6080) >/dev/null 2>&1 && exit 0; "
        "sleep 0.2; done; exit 1"
    )
    result = docker(
        "exec",
        name,
        "bash",
        "-lc",
        readiness_command,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(502, "Computer viewer did not become ready")


def container_ip(name: str) -> str:
    network_template = '{{(index .NetworkSettings.Networks "' + COMPUTER_NETWORK + '").IPAddress}}'
    result = docker(
        "inspect",
        "--format",
        network_template,
        name,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise HTTPException(404, "Computer viewer is unavailable")
    return result.stdout.strip()


def attach_egress_network(name: str) -> None:
    network = docker("network", "inspect", COMPUTER_EGRESS_NETWORK, check=False)
    if network.returncode != 0:
        created = docker(
            "network", "create", "--driver", "bridge", COMPUTER_EGRESS_NETWORK, check=False
        )
        if created.returncode != 0:
            raise HTTPException(
                502, created.stderr[-1000:] or "Could not create computer egress network"
            )
    connected = docker("network", "connect", COMPUTER_EGRESS_NETWORK, name, check=False)
    if connected.returncode != 0 and "already exists" not in connected.stderr.lower():
        raise HTTPException(
            502, connected.stderr[-1000:] or "Could not attach computer egress network"
        )


def validate_viewer_token(token: str | None, session_id: str) -> dict[str, object]:
    if not token:
        raise HTTPException(401, "Viewer token required")
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(VIEWER_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if payload.get("session_id") != session_id or int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Viewer token is invalid or expired") from exc
    return {str(key): value for key, value in payload.items()}


@app.get("/health/live")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/sessions", dependencies=[Depends(authorize)])
def provision(data: ProvisionRequest) -> dict[str, object]:
    name = f"grokbot-{data.workspace_key}"
    existing = inspect_status(name)
    if existing == "destroyed":
        volume = f"{WORKSPACE_VOLUME_PREFIX}-{data.workspace_key}"
        result = docker(
            "run",
            "-d",
            "--init",
            "--name",
            name,
            "--label",
            "open-grokbot.sandbox=true",
            "--memory",
            f"{data.limits.memory_mb}m",
            "--cpus",
            str(data.limits.cpus),
            "--pids-limit",
            str(data.limits.pids),
            "--shm-size",
            "512m",
            "--security-opt",
            "no-new-privileges",
            "--network",
            COMPUTER_NETWORK,
            "-v",
            f"{volume}:/workspace",
            data.image,
            check=False,
        )
        if result.returncode != 0:
            raise HTTPException(502, result.stderr[-1000:] or "Docker provision failed")
    elif existing == "stopped":
        docker("start", name)
    attach_egress_network(name)
    wait_for_viewer(name)
    return {
        "id": name,
        "status": inspect_status(name),
        "viewer_url": f"/v1/viewer/{name}",
        "capabilities": ["terminal", "files", "python", "node", "browser", "viewer", "takeover"],
    }


@app.get("/v1/sessions/{session_id}", dependencies=[Depends(authorize)])
def status(session_id: str) -> dict[str, object]:
    name = container_name(session_id)
    return {
        "id": name,
        "status": inspect_status(name),
        "viewer_url": f"/v1/viewer/{name}",
        "capabilities": ["terminal", "files", "python", "node", "browser", "viewer", "takeover"],
    }


@app.delete("/v1/sessions/{session_id}", dependencies=[Depends(authorize)])
def destroy(session_id: str) -> dict[str, str]:
    name = container_name(session_id)
    docker("rm", "-f", name, check=False)
    return {"status": "destroyed"}


@app.post("/v1/sessions/{session_id}/exec", dependencies=[Depends(authorize)])
def execute(session_id: str, data: ExecRequest) -> dict[str, object]:
    name = container_name(session_id)
    try:
        result = docker(
            "exec", "-w", "/workspace", name, *data.command, timeout=data.timeout, check=False
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "timed_out": False,
            "truncated": False,
            "data": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "Command timed out",
            "exit_code": None,
            "timed_out": True,
            "truncated": False,
            "data": None,
        }


@app.put("/v1/sessions/{session_id}/files", dependencies=[Depends(authorize)])
def write_file(session_id: str, data: FileWrite) -> dict[str, str]:
    name = container_name(session_id)
    path = workspace_path(data.path)
    try:
        content = base64.b64decode(data.content, validate=True)
    except ValueError as exc:
        raise HTTPException(400, "Invalid base64 content") from exc
    parent = str(PurePosixPath(path).parent)
    docker("exec", name, "mkdir", "-p", f"/workspace/{parent}")
    process = subprocess.run(
        ["docker", "exec", "-i", name, "tee", f"/workspace/{path}"],
        input=content,
        capture_output=True,
        timeout=45,
    )
    if process.returncode != 0:
        raise HTTPException(502, process.stderr.decode(errors="replace")[-1000:])
    return {"status": "written"}


@app.get("/v1/sessions/{session_id}/files", dependencies=[Depends(authorize)])
def read_file(session_id: str, path: Annotated[str, Query()]) -> dict[str, str]:
    name = container_name(session_id)
    safe_path = workspace_path(path)
    process = subprocess.run(
        ["docker", "exec", name, "cat", f"/workspace/{safe_path}"], capture_output=True, timeout=45
    )
    if process.returncode != 0:
        raise HTTPException(404, "Workspace file not found")
    return {"content": base64.b64encode(process.stdout).decode()}


@app.post("/v1/orphans/cleanup", dependencies=[Depends(authorize)])
def cleanup_orphans() -> dict[str, int]:
    result = docker("ps", "-aq", "--filter", "label=open-grokbot.sandbox=true", check=False)
    removed = 0
    for name in result.stdout.splitlines():
        if name:
            docker("rm", "-f", name, check=False)
            removed += 1
    return {"removed": removed}


@app.get("/v1/viewer/{session_id}")
def viewer_entry(session_id: str, token: str = Query()) -> RedirectResponse:
    name = container_name(session_id)
    claims = validate_viewer_token(token, name)
    view_only = "0" if claims.get("can_control") is True else "1"
    response = RedirectResponse(
        f"/v1/viewer/{name}/vnc.html?autoconnect=1&resize=scale&view_only={view_only}"
        f"&path=v1/viewer/{name}/websockify"
    )
    response.set_cookie(
        "grokbot_viewer",
        token,
        max_age=300,
        httponly=True,
        samesite="strict",
        path=f"/v1/viewer/{name}",
    )
    return response


@app.get("/v1/viewer/{session_id}/{asset_path:path}")
async def viewer_asset(
    session_id: str,
    asset_path: str,
    request: Request,
    grokbot_viewer: Annotated[str | None, Cookie()] = None,
) -> Response:
    name = container_name(session_id)
    validate_viewer_token(grokbot_viewer or request.query_params.get("token"), name)
    if asset_path == "websockify":
        raise HTTPException(426, "WebSocket upgrade required")
    target = f"http://{container_ip(name)}:6080/{asset_path or 'vnc.html'}"
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(3):
            try:
                upstream = await client.get(target, params=request.query_params)
                break
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise HTTPException(502, "Sandbox viewer temporarily unavailable") from exc
                await asyncio.sleep(0.1 * (attempt + 1))
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={"Cache-Control": "no-store"},
    )


@app.websocket("/v1/viewer/{session_id}/websockify")
async def viewer_socket(websocket: WebSocket, session_id: str) -> None:
    name = container_name(session_id)
    token = websocket.cookies.get("grokbot_viewer") or websocket.query_params.get("token")
    try:
        validate_viewer_token(token, name)
    except HTTPException:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        async with websockets.connect(f"ws://{container_ip(name)}:6080/websockify") as upstream:

            async def browser_to_sandbox() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("bytes") is not None:
                        await upstream.send(message["bytes"])
                    elif message.get("text") is not None:
                        await upstream.send(message["text"])
                    else:
                        return

            async def sandbox_to_browser() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            await asyncio.gather(browser_to_sandbox(), sandbox_to_browser())
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        return
