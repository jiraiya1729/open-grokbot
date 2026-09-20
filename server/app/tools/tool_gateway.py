from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from app.infrastructure.computer import (
    ComputerObservation,
    ComputerProvider,
    normalized_workspace_path,
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    required: tuple[str, ...]


class ToolGateway:
    def __init__(
        self,
        provider: ComputerProvider,
        *,
        timeout: int = 30,
        output_bytes: int = 65536,
        control_guard: Callable[[], bool] | None = None,
    ) -> None:
        self.provider = provider
        self.timeout = timeout
        self.output_bytes = output_bytes
        self.control_guard = control_guard
        self.registry = {
            "shell.run": ToolSpec(
                "shell.run", "Run an argv command in the workspace", ("command",)
            ),
            "filesystem.read": ToolSpec("filesystem.read", "Read a workspace file", ("path",)),
            "filesystem.write": ToolSpec(
                "filesystem.write", "Write a UTF-8 workspace file", ("path", "content")
            ),
            "filesystem.list": ToolSpec("filesystem.list", "List a workspace directory", ("path",)),
            "code.run": ToolSpec("code.run", "Run Python or Node code", ("language", "code")),
            "browser.navigate": ToolSpec(
                "browser.navigate", "Open a URL in headless Chromium", ("url",)
            ),
            "browser.screenshot": ToolSpec(
                "browser.screenshot", "Capture the current page", ("url", "path")
            ),
        }

    def invoke(self, session_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = self.registry.get(name)
        if spec is None:
            raise ValueError(f"Unknown tool: {name}")
        missing = [key for key in spec.required if key not in arguments]
        if missing:
            raise ValueError(f"Missing tool arguments: {', '.join(missing)}")
        if (
            self.control_guard
            and name
            in {
                "shell.run",
                "filesystem.write",
                "code.run",
                "browser.navigate",
                "browser.screenshot",
            }
            and not self.control_guard()
        ):
            observation = ComputerObservation(
                False, stderr="Agent input is paused while a user controls the computer"
            )
            return asdict(observation)
        try:
            observation = self._invoke(session_id, name, arguments)
        except TimeoutError:
            observation = ComputerObservation(False, stderr="Tool timed out", timed_out=True)
        except Exception as exc:
            observation = ComputerObservation(False, stderr=str(exc)[:1000])
        return asdict(self._truncate(observation))

    def _invoke(self, session_id: str, name: str, args: dict[str, Any]) -> ComputerObservation:
        if name == "filesystem.read":
            content = self.provider.read_file(
                session_id, normalized_workspace_path(str(args["path"]))
            )
            return ComputerObservation(
                True, stdout=content.decode("utf-8", errors="replace"), data=content
            )
        if name == "filesystem.write":
            self.provider.write_file(
                session_id,
                normalized_workspace_path(str(args["path"])),
                str(args["content"]).encode(),
            )
            return ComputerObservation(True, stdout="File written", exit_code=0)
        if name == "filesystem.list":
            path = normalized_workspace_path(str(args["path"]))
            return self.provider.execute(
                session_id,
                ["find", f"/workspace/{path}", "-maxdepth", "1", "-printf", "%f\\n"],
                self.timeout,
            )
        if name == "shell.run":
            command = args["command"]
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(part, str) for part in command)
            ):
                raise ValueError("command must be a non-empty argv array")
            return self.provider.execute(session_id, command, self.timeout)
        if name == "code.run":
            language = str(args["language"])
            executable = {"python": "python3", "node": "node"}.get(language)
            if executable is None:
                raise ValueError("language must be python or node")
            return self.provider.execute(
                session_id, [executable, "-c", str(args["code"])], self.timeout
            )
        if name == "browser.navigate":
            return self.provider.execute(
                session_id,
                [
                    "env",
                    "-u",
                    "DISPLAY",
                    "chromium",
                    "--headless",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--dump-dom",
                    str(args["url"]),
                ],
                self.timeout,
            )
        path = normalized_workspace_path(str(args["path"]))
        return self.provider.execute(
            session_id,
            [
                "env",
                "-u",
                "DISPLAY",
                "chromium",
                "--headless",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                f"--screenshot=/workspace/{path}",
                str(args["url"]),
            ],
            self.timeout,
        )

    def invoke_hierarchy(
        self,
        name: str,
        arguments: dict[str, Any],
        session: Any,
        workspace_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Invoke hierarchy-plane tools (create_child_bot, delegate_task, spawn_subagent).

        These are separate from computer tools and operate on product state.
        Returns a result dict with ok/result/error keys.
        """
        from app.services.collaboration import (
            MAX_SUBAGENTS_PER_RUN,
            ChildBotService,
            CollaborationService,
            DelegationRepository,
            PolicyDeniedError,
            TaskRepository,
        )

        if name == "create_child_bot":
            required: tuple[str, ...] = ("name", "primary_job", "idempotency_key")
            missing = [k for k in required if k not in arguments]
            if missing:
                return {"ok": False, "error": f"Missing arguments: {', '.join(missing)}"}
            svc = ChildBotService(session)
            try:
                req, mode = svc.request_create(
                    workspace_id=workspace_id,
                    parent_bot_id=uuid.UUID(str(arguments["parent_bot_id"]))
                    if "parent_bot_id" in arguments
                    else workspace_id,
                    idempotency_key=str(arguments["idempotency_key"]),
                    child_name=str(arguments["name"]),
                    child_system_instructions=str(arguments.get("system_instructions", "")),
                    child_role_title=str(arguments["primary_job"]),
                    child_description=str(arguments.get("description", "")),
                    requested_relationship_label=arguments.get("relationship_label"),
                    starter_config={},
                    requested_by_run_id=uuid.UUID(str(arguments["run_id"]))
                    if "run_id" in arguments
                    else None,
                )
            except PolicyDeniedError as e:
                return {"ok": False, "error": str(e), "policy_denied": True}
            except KeyError as e:
                return {"ok": False, "error": str(e)}
            result: dict[str, Any] = {
                "ok": True,
                "request_id": str(req.id),
                "status": req.status,
                "policy_mode": mode,
            }
            if mode == "allow" and req.status == "approved":
                try:
                    req, child = svc.materialize_child(req.id)
                    result["created_bot_id"] = str(child.id)
                    result["status"] = req.status
                except Exception as e:
                    result["materialization_error"] = str(e)
            return result

        if name == "delegate_task":
            required = ("title", "assignee_bot_id", "requester_bot_id")
            missing = [k for k in required if k not in arguments]
            if missing:
                return {"ok": False, "error": f"Missing arguments: {', '.join(missing)}"}
            collab = CollaborationService(
                TaskRepository(session), DelegationRepository(session), session
            )
            hop_depth = int(arguments.get("hop_depth", 1))
            try:
                task = collab.create_task(
                    workspace_id=workspace_id,
                    title=str(arguments["title"]),
                    description=str(arguments.get("description", "")),
                    created_by_type="bot",
                    created_by_id=uuid.UUID(str(arguments["requester_bot_id"])),
                    assigned_to_type="bot",
                    assigned_to_id=uuid.UUID(str(arguments["assignee_bot_id"])),
                    budget=arguments.get("budget", {}),
                )
                corr_id = (
                    uuid.UUID(str(arguments["correlation_id"]))
                    if "correlation_id" in arguments
                    else uuid.uuid4()
                )
                delegation = collab.create_delegation(
                    workspace_id=workspace_id,
                    task_id=task.id,
                    requester_bot_id=uuid.UUID(str(arguments["requester_bot_id"])),
                    assignee_bot_id=uuid.UUID(str(arguments["assignee_bot_id"])),
                    hop_depth=hop_depth,
                    requester_run_id=uuid.UUID(str(arguments["requester_run_id"]))
                    if "requester_run_id" in arguments
                    else None,
                    correlation_id=corr_id,
                )
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return {
                "ok": True,
                "task_id": str(task.id),
                "delegation_id": str(delegation.id),
                "correlation_id": str(delegation.correlation_id),
                "status": delegation.status,
            }

        if name == "spawn_subagent":
            required = ("parent_run_id",)
            missing = [k for k in required if k not in arguments]
            if missing:
                return {"ok": False, "error": f"Missing arguments: {', '.join(missing)}"}
            collab = CollaborationService(
                TaskRepository(session), DelegationRepository(session), session
            )
            try:
                sa = collab.spawn_subagent(
                    workspace_id=workspace_id,
                    parent_run_id=uuid.UUID(str(arguments["parent_run_id"])),
                    kind=str(arguments.get("kind", "general")),
                    purpose=arguments.get("purpose"),
                    token_budget=int(arguments["token_budget"])
                    if "token_budget" in arguments
                    else None,
                )
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return {
                "ok": True,
                "subagent_id": str(sa.id),
                "kind": sa.kind,
                "purpose": sa.purpose,
                "max_per_run": MAX_SUBAGENTS_PER_RUN,
            }

        return {"ok": False, "error": f"Unknown hierarchy tool: {name}"}

    def _truncate(self, observation: ComputerObservation) -> ComputerObservation:
        stdout = observation.stdout.encode()[: self.output_bytes].decode(errors="replace")
        remaining = max(0, self.output_bytes - len(stdout.encode()))
        stderr = observation.stderr.encode()[:remaining].decode(errors="replace")
        truncated = (
            observation.truncated or stdout != observation.stdout or stderr != observation.stderr
        )
        data = observation.data[: self.output_bytes] if observation.data else None
        return ComputerObservation(
            observation.ok,
            stdout,
            stderr,
            observation.exit_code,
            observation.timed_out,
            truncated,
            data,
        )
