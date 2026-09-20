from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class ComputerLimits:
    memory_mb: int = 1024
    cpus: float = 1.0
    pids: int = 256

    def validate(self) -> None:
        if not 128 <= self.memory_mb <= 8192:
            raise ValueError("memory_mb must be between 128 and 8192")
        if not 0.1 <= self.cpus <= 8:
            raise ValueError("cpus must be between 0.1 and 8")
        if not 32 <= self.pids <= 2048:
            raise ValueError("pids must be between 32 and 2048")


@dataclass(frozen=True)
class ComputerInstance:
    provider_session_id: str
    status: str
    viewer_url: str | None = None
    capabilities: tuple[str, ...] = (
        "terminal",
        "files",
        "python",
        "node",
        "browser",
        "viewer",
        "takeover",
    )


@dataclass(frozen=True)
class ComputerObservation:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    truncated: bool = False
    data: bytes | None = None


class ComputerProvider(ABC):
    name: str

    @abstractmethod
    def provision(self, workspace_key: str, limits: ComputerLimits) -> ComputerInstance: ...

    @abstractmethod
    def status(self, provider_session_id: str) -> ComputerInstance: ...

    @abstractmethod
    def destroy(self, provider_session_id: str) -> None: ...

    @abstractmethod
    def execute(
        self, provider_session_id: str, command: list[str], timeout: int
    ) -> ComputerObservation: ...

    @abstractmethod
    def write_file(self, provider_session_id: str, path: str, content: bytes) -> None: ...

    @abstractmethod
    def read_file(self, provider_session_id: str, path: str) -> bytes: ...


class DockerComputerProvider(ComputerProvider):
    name = "docker"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = settings.computer_daemon_url.rstrip("/")
        self.token = settings.computer_daemon_token
        self.image = settings.computer_image
        self.transport = transport

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(base_url=self.base_url, transport=self.transport, timeout=45) as client:
            response = client.request(
                method, path, headers={"Authorization": f"Bearer {self.token}"}, **kwargs
            )
        response.raise_for_status()
        return response

    def provision(self, workspace_key: str, limits: ComputerLimits) -> ComputerInstance:
        limits.validate()
        payload = {"workspace_key": workspace_key, "image": self.image, "limits": limits.__dict__}
        data = self._request("POST", "/v1/sessions", json=payload).json()
        return ComputerInstance(
            data["id"], data["status"], data.get("viewer_url"), tuple(data.get("capabilities", ()))
        )

    def status(self, provider_session_id: str) -> ComputerInstance:
        data = self._request("GET", f"/v1/sessions/{provider_session_id}").json()
        return ComputerInstance(
            data["id"], data["status"], data.get("viewer_url"), tuple(data.get("capabilities", ()))
        )

    def destroy(self, provider_session_id: str) -> None:
        self._request("DELETE", f"/v1/sessions/{provider_session_id}")

    def execute(
        self, provider_session_id: str, command: list[str], timeout: int
    ) -> ComputerObservation:
        data = self._request(
            "POST",
            f"/v1/sessions/{provider_session_id}/exec",
            json={"command": command, "timeout": timeout},
        ).json()
        return ComputerObservation(**data)

    def write_file(self, provider_session_id: str, path: str, content: bytes) -> None:
        self._request(
            "PUT",
            f"/v1/sessions/{provider_session_id}/files",
            json={"path": path, "content": base64.b64encode(content).decode()},
        )

    def read_file(self, provider_session_id: str, path: str) -> bytes:
        data = self._request(
            "GET", f"/v1/sessions/{provider_session_id}/files", params={"path": path}
        ).json()
        return base64.b64decode(data["content"], validate=True)


class FakeComputerProvider(ComputerProvider):
    name = "fake"

    def __init__(
        self, command_handler: Callable[[list[str]], ComputerObservation] | None = None
    ) -> None:
        self.instances: dict[str, ComputerInstance] = {}
        self.files: dict[tuple[str, str], bytes] = {}
        self.command_handler = command_handler or (
            lambda command: ComputerObservation(True, stdout=" ".join(command), exit_code=0)
        )

    def provision(self, workspace_key: str, limits: ComputerLimits) -> ComputerInstance:
        limits.validate()
        instance = ComputerInstance(f"fake-{workspace_key}", "running")
        self.instances[instance.provider_session_id] = instance
        return instance

    def status(self, provider_session_id: str) -> ComputerInstance:
        return self.instances[provider_session_id]

    def destroy(self, provider_session_id: str) -> None:
        current = self.instances[provider_session_id]
        self.instances[provider_session_id] = ComputerInstance(
            current.provider_session_id, "destroyed", capabilities=current.capabilities
        )

    def execute(
        self, provider_session_id: str, command: list[str], timeout: int
    ) -> ComputerObservation:
        del timeout
        if self.status(provider_session_id).status != "running":
            return ComputerObservation(False, stderr="computer is not running")
        return self.command_handler(command)

    def write_file(self, provider_session_id: str, path: str, content: bytes) -> None:
        self.files[(provider_session_id, normalized_workspace_path(path))] = content

    def read_file(self, provider_session_id: str, path: str) -> bytes:
        return self.files[(provider_session_id, normalized_workspace_path(path))]


def normalized_workspace_path(path: str) -> str:
    pure = PurePosixPath(path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("Path must stay within the computer workspace")
    return pure.as_posix()


def provider_from_settings(settings: Settings) -> ComputerProvider:
    if settings.computer_provider == "docker":
        return DockerComputerProvider(settings)
    if settings.computer_provider == "fake":
        return FakeComputerProvider()
    raise ValueError(f"Unsupported computer provider: {settings.computer_provider}")
