from __future__ import annotations

import json
import threading
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import inngest
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.agents.graph import BotGraphState, build_graph, make_graph_state
from app.agents.run_states import transition_run
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.product_events import validate_product_event
from app.domain.models import (
    Approval,
    Artifact,
    ArtifactLink,
    Bot,
    ComputerSession,
    ComputerWorkspace,
    Conversation,
    File,
    Message,
    Routine,
    Run,
    RunEvent,
    WorkspaceMember,
)
from app.infrastructure.blob_store import LocalBlobStore
from app.infrastructure.computer import ComputerLimits, ComputerProvider, provider_from_settings
from app.infrastructure.providers import ModelRouter
from app.tools.safety import (
    acquire_control,
    action_digest,
    active_control,
    create_approval,
    execute_once,
    policy_effect,
)
from app.tools.tool_gateway import ToolGateway

settings = get_settings()
model_router = ModelRouter(settings)
checkpoint_database_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
checkpoint_database_url += (
    "&options=-csearch_path%3Dlanggraph"
    if "?" in checkpoint_database_url
    else "?options=-csearch_path%3Dlanggraph"
)
inngest_client = inngest.Inngest(
    app_id="open-grokbot",
    event_api_base_url=settings.inngest_event_url.rsplit("/e/", 1)[0],
    event_key=settings.inngest_event_key,
    signing_key=settings.inngest_signing_key or None,
    is_production=False,
    request_timeout=2,
)


def append_event(db: Session, run: Run, event_type: str, payload: dict[str, object]) -> RunEvent:
    validated = validate_product_event(event_type, payload)
    sequence = (
        db.scalar(
            select(func.coalesce(func.max(RunEvent.sequence), 0)).where(RunEvent.run_id == run.id)
        )
        or 0
    )
    event = RunEvent(
        workspace_id=run.workspace_id,
        run_id=run.id,
        sequence=sequence + 1,
        event_type=event_type,
        event_version=1,
        payload=validated,
    )
    db.add(event)
    db.flush()
    return event


def _attached_files(db: Session, message: Message | None) -> list[File]:
    if message is None:
        return []
    raw_ids = message.structured_content.get("file_ids", [])
    try:
        ids = [uuid.UUID(str(value)) for value in raw_ids]
    except ValueError:
        return []
    if not ids:
        return []
    records = list(
        db.scalars(
            select(File).where(
                File.id.in_(ids), File.workspace_id == message.workspace_id, File.status == "ready"
            )
        )
    )
    by_id = {record.id: record for record in records}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


def _start_run_computer(db: Session, run: Run) -> tuple[ComputerProvider, ComputerSession]:
    workspace = db.scalar(
        select(ComputerWorkspace).where(
            ComputerWorkspace.workspace_id == run.workspace_id,
            ComputerWorkspace.bot_id == run.bot_id,
            ComputerWorkspace.state == "active",
        )
    )
    if workspace is None:
        workspace = ComputerWorkspace(
            workspace_id=run.workspace_id,
            bot_id=run.bot_id,
            project_key=f"bot-{run.bot_id}",
            state="active",
        )
        db.add(workspace)
        db.flush()
    provider = provider_from_settings(settings)
    session = db.scalar(
        select(ComputerSession)
        .where(
            ComputerSession.computer_workspace_id == workspace.id,
            ComputerSession.status.in_(["starting", "running"]),
        )
        .order_by(ComputerSession.started_at.desc())
        .limit(1)
    )
    if session and session.provider_session_id:
        remote = provider.status(session.provider_session_id)
        session.status = remote.status
    else:
        session = ComputerSession(
            workspace_id=run.workspace_id,
            computer_workspace_id=workspace.id,
            provider=provider.name,
            status="starting",
            started_at=datetime.now(UTC),
            metadata_={},
        )
        db.add(session)
        db.flush()
        append_event(
            db, run, "computer_activity", {"status": "starting", "label": "Starting computer"}
        )
        remote = provider.provision(
            str(workspace.id),
            ComputerLimits(
                settings.computer_memory_mb, settings.computer_cpus, settings.computer_pids_limit
            ),
        )
        session.provider_session_id = remote.provider_session_id
        session.status = remote.status
        session.viewer_url = remote.viewer_url
        session.metadata_ = {"capabilities": list(remote.capabilities)}
    if not session.provider_session_id or session.status != "running":
        raise RuntimeError("Computer did not reach running state")
    lease = active_control(db, session.id)
    if lease is None:
        acquire_control(db, session, owner_type="agent", owner_id=run.bot_id, ttl_seconds=86400)
    elif lease.owner_type == "user":
        transition_run(run, "waiting_takeover")
        append_event(
            db,
            run,
            "run_status",
            {"status": "waiting_takeover", "label": "Waiting for you to return control"},
        )
        db.commit()
        raise RuntimeError("Agent input is paused while a user controls the computer")
    append_event(db, run, "computer_activity", {"status": "running", "label": "Computer ready"})
    db.commit()
    return provider, session


def _import_files(
    db: Session, run: Run, provider: ComputerProvider, session: ComputerSession, files: list[File]
) -> str:
    assert session.provider_session_id
    store = LocalBlobStore(Path(settings.data_root) / "blob-store")
    gateway = ToolGateway(
        provider,
        timeout=settings.computer_tool_timeout_seconds,
        output_bytes=settings.computer_tool_output_bytes,
        control_guard=lambda: (
            (lease := active_control(db, session.id)) is None or lease.owner_type == "agent"
        ),
    )
    context_parts: list[str] = []
    for record in files:
        with store.open(record.blob_key) as source:
            content = source.read()
        workspace_path = f"uploads/{record.id}-{record.safe_name}"
        observation = gateway.invoke(
            session.provider_session_id,
            "filesystem.write",
            {"path": workspace_path, "content": content.decode("utf-8", errors="replace")},
        )
        if not observation["ok"]:
            raise RuntimeError(str(observation["stderr"]))
        append_event(
            db,
            run,
            "computer_activity",
            {"status": "running", "label": f"Reading {record.safe_name}"},
        )
        if (record.mime_type or "").startswith("text/") and len(content) <= 65536:
            decoded = content.decode("utf-8", errors="replace")
            context_parts.append(
                f"\n\nAttached file `{record.original_name}`:\n```\n{decoded}\n```"
            )
    db.commit()
    return "".join(context_parts)


def _export_result(
    db: Session,
    run: Run,
    message: Message,
    provider: ComputerProvider,
    session: ComputerSession,
    output: str,
) -> Artifact:
    assert run.conversation_id and session.provider_session_id
    gateway = ToolGateway(
        provider,
        timeout=settings.computer_tool_timeout_seconds,
        output_bytes=settings.computer_tool_output_bytes,
        control_guard=lambda: (
            (lease := active_control(db, session.id)) is None or lease.owner_type == "agent"
        ),
    )
    workspace_path = f"outputs/{run.id}-result.md"
    content = f"# Result\n\n{output}\n".encode()
    written = gateway.invoke(
        session.provider_session_id,
        "filesystem.write",
        {"path": workspace_path, "content": content.decode()},
    )
    if not written["ok"]:
        raise RuntimeError(str(written["stderr"]))
    exported = gateway.invoke(
        session.provider_session_id, "filesystem.read", {"path": workspace_path}
    )
    if not exported["ok"]:
        raise RuntimeError(str(exported["stderr"]))
    exported_bytes = exported["data"] or content
    if isinstance(exported_bytes, str):
        exported_bytes = exported_bytes.encode()
    store = LocalBlobStore(Path(settings.data_root) / "blob-store")
    key = store.generated_key("artifacts")
    info = store.put(key, BytesIO(exported_bytes))
    try:
        artifact = Artifact(
            workspace_id=run.workspace_id,
            created_by_bot_id=run.bot_id,
            run_id=run.id,
            name="Result.md",
            blob_key=key,
            mime_type="text/markdown",
            byte_size=info.byte_size,
            sha256=info.sha256,
            artifact_type="document",
            revision=1,
            metadata_={
                "workspace_path": workspace_path,
                "source_file_ids": message.structured_content.get("file_ids", []),
            },
        )
        db.add(artifact)
        db.flush()
        db.add_all(
            [
                ArtifactLink(
                    artifact_id=artifact.id,
                    entity_type="conversation",
                    entity_id=run.conversation_id,
                    relation="output",
                ),
                ArtifactLink(
                    artifact_id=artifact.id, entity_type="run", entity_id=run.id, relation="output"
                ),
                ArtifactLink(
                    artifact_id=artifact.id,
                    entity_type="message",
                    entity_id=message.id,
                    relation="output",
                ),
            ]
        )
        message.structured_content = {
            **message.structured_content,
            "artifacts": [
                {
                    "id": str(artifact.id),
                    "name": artifact.name,
                    "mime_type": artifact.mime_type,
                    "byte_size": artifact.byte_size,
                }
            ],
        }
        append_event(
            db, run, "artifact_created", {"artifact_id": str(artifact.id), "name": artifact.name}
        )
        return artifact
    except BaseException:
        store.delete(key)
        raise


def execute_bot_run(run_id: uuid.UUID) -> dict[str, str]:
    """Idempotent run worker used by both Inngest and the deterministic inline runner."""
    with SessionLocal() as db:
        claimed = db.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "queued")
            .values(status="running", started_at=datetime.now(UTC))
            .returning(Run.id)
        ).scalar_one_or_none()
        if claimed is None:
            existing = db.get(Run, run_id)
            return {"run_id": str(run_id), "status": existing.status if existing else "missing"}
        run = db.get(Run, run_id)
        assert run is not None
        append_event(db, run, "run_status", {"status": "running"})
        db.commit()

    try:
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            assert run and run.conversation_id
            bot = db.get(Bot, run.bot_id)
            assert bot
            history = list(
                db.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == run.conversation_id, Message.deleted_at.is_(None)
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(settings.recent_message_limit)
                )
            )
            history.reverse()
            trigger_message = (
                db.get(Message, run.trigger_message_id) if run.trigger_message_id else None
            )
            action_request = _action_request(trigger_message)
            approved_action_output: str | None = None
            if action_request:
                action_type, action_payload = action_request
                effect = policy_effect(
                    db, run.workspace_id, run.bot_id, "demo.external", action_type
                )
                if effect == "deny":
                    transition_run(run, "failed")
                    run.error_code = "PolicyDenied"
                    run.error_message = "Policy denied the requested consequential action."
                    append_event(
                        db,
                        run,
                        "run_error",
                        {
                            "code": "policy_denied",
                            "message": run.error_message,
                            "recoverable": False,
                        },
                    )
                    append_event(db, run, "run_status", {"status": "failed"})
                    db.commit()
                    return {"run_id": str(run.id), "status": run.status}
                approval: Approval | None = None
                if effect == "ask":
                    approval = create_approval(db, run, action_type, action_payload)
                    if approval.status == "pending":
                        transition_run(run, "waiting_approval")
                        metadata = dict(run.metadata_)
                        metadata["approval_checkpoint"] = {
                            "approval_id": str(approval.id),
                            "action_digest": approval.action_digest,
                            "langgraph_thread_id": run.langgraph_thread_id,
                        }
                        run.metadata_ = metadata
                        append_event(
                            db,
                            run,
                            "approval_requested",
                            {
                                "approval_id": str(approval.id),
                                "action_type": approval.action_type,
                                "action_payload": approval.action_payload,
                                "action_digest": approval.action_digest,
                                "status": "pending",
                            },
                        )
                        append_event(
                            db,
                            run,
                            "run_status",
                            {"status": "waiting_approval", "label": "Waiting for approval"},
                        )
                        db.commit()
                        return {"run_id": str(run.id), "status": run.status}
                execution = execute_once(
                    db,
                    run=run,
                    approval=approval,
                    idempotency_key=f"run:{run.id}:{action_digest(action_type, action_payload)}",
                    provider="deterministic-local",
                    action_type=action_type,
                    payload=action_payload,
                    executor=lambda: {
                        "result": "completed",
                        "action_type": action_type,
                        "request": action_payload["request"],
                    },
                )
                approved_action_output = (
                    f"The approved `{action_type}` action completed once. "
                    f"Request: {action_payload['request']}"
                )
                append_event(
                    db,
                    run,
                    "tool_activity",
                    {
                        "tool": "demo.external",
                        "status": "completed",
                        "label": f"Completed {action_type} action ({execution.status})",
                    },
                )
                db.commit()
            attached_files = _attached_files(db, trigger_message)
            computer_provider: ComputerProvider | None = None
            computer_session: ComputerSession | None = None
            attachment_context = ""
            if attached_files:
                computer_provider, computer_session = _start_run_computer(db, run)
                attachment_context = _import_files(
                    db, run, computer_provider, computer_session, attached_files
                )
            prompt_messages: list[tuple[str, str]] = []
            for history_message in history:
                content = history_message.text_content or ""
                if trigger_message and history_message.id == trigger_message.id:
                    content += attachment_context
                prompt_messages.append(
                    ("assistant" if history_message.sender_type == "bot" else "user", content)
                )
            from app.agents.context_builder import ContextBuilder

            user_query = (trigger_message.text_content or "") if trigger_message else ""
            enriched_instructions, _memory_meta = ContextBuilder(db).build(
                workspace_id=run.workspace_id,
                bot_id=run.bot_id,
                base_instructions=bot.system_instructions,
                user_message=user_query,
            )
            graph_state: BotGraphState = make_graph_state(
                bot_id=str(run.bot_id),
                bot_name=bot.name,
                role_title=bot.role_title or "teammate",
                instructions=enriched_instructions,
                workspace_id=str(run.workspace_id),
                run_id=str(run.id),
                messages=prompt_messages,
            )
            provider = model_router.route("general")
            graph_gateway = ToolGateway(
                provider_from_settings(settings),
                timeout=settings.computer_tool_timeout_seconds,
                output_bytes=settings.computer_tool_output_bytes,
                control_guard=None,
            )
            graph_configurable: dict[str, object] = {
                "thread_id": run.langgraph_thread_id or str(run.id),
                "db": db,
                "tool_gateway": graph_gateway,
            }
            graph = None
            if approved_action_output is None:
                with PostgresSaver.from_conn_string(checkpoint_database_url) as checkpointer:
                    graph = build_graph(provider, checkpointer)
                    completed_state = graph.invoke(
                        graph_state,
                        {"configurable": graph_configurable},
                    )
                response_words = completed_state["response"].split(" ")
            else:
                response_words = approved_action_output.split(" ")
            output = ""
            index = 0
            consumed_steering: set[str] = set(run.metadata_.get("consumed_steering_ids", []))
            while index < len(response_words):
                word = response_words[index]
                delta = word + ("" if index == len(response_words) - 1 else " ")
                db.refresh(run)
                if run.status in {"cancel_requested", "cancelled"}:
                    transition_run(run, "cancelled")
                    append_event(db, run, "run_status", {"status": "cancelled"})
                    db.commit()
                    return {"run_id": str(run_id), "status": "cancelled"}
                if run.status == "waiting_takeover":
                    append_event(
                        db,
                        run,
                        "run_status",
                        {
                            "status": "waiting_takeover",
                            "label": "Waiting for you to return control",
                        },
                    )
                    db.commit()
                    return {"run_id": str(run_id), "status": "waiting_takeover"}
                steering_ids = [
                    str(value) for value in run.metadata_.get("steering_message_ids", [])
                ]
                pending_steering = [
                    value for value in steering_ids if value not in consumed_steering
                ]
                if pending_steering and graph is not None:
                    steering_messages = list(
                        db.scalars(
                            select(Message).where(
                                Message.id.in_([uuid.UUID(value) for value in pending_steering])
                            )
                        )
                    )
                    steering_text = "\n".join(
                        item.text_content or "" for item in steering_messages if item.text_content
                    )
                    if steering_text:
                        prompt_messages.append(("user", f"Steering: {steering_text}"))
                        graph_state["messages"] = prompt_messages
                        with PostgresSaver.from_conn_string(
                            checkpoint_database_url
                        ) as checkpointer:
                            steered_graph = build_graph(provider, checkpointer)
                            completed_state = steered_graph.invoke(
                                graph_state,
                                {"configurable": graph_configurable},
                            )
                        response_words = completed_state["response"].split(" ")
                        output = ""
                        index = 0
                        consumed_steering.update(pending_steering)
                        metadata = dict(run.metadata_)
                        metadata["consumed_steering_ids"] = sorted(consumed_steering)
                        run.metadata_ = metadata
                        for steering_message in steering_messages:
                            append_event(
                                db,
                                run,
                                "steering",
                                {
                                    "message_id": str(steering_message.id),
                                    "text": steering_message.text_content or "",
                                    "status": "applied",
                                },
                            )
                        db.commit()
                        continue
                output += delta
                append_event(db, run, "message_delta", {"delta": delta})
                db.commit()
                index += 1
            db.refresh(run)
            if run.status != "running":
                return {"run_id": str(run_id), "status": run.status}
            message = Message(
                workspace_id=run.workspace_id,
                conversation_id=run.conversation_id,
                sender_type="bot",
                sender_id=run.bot_id,
                kind="text",
                text_content=output,
                structured_content={"provider": provider.name, "run_id": str(run.id)},
                correlation_id=run.correlation_id,
            )
            db.add(message)
            db.flush()
            if attached_files and computer_provider and computer_session:
                _export_result(db, run, message, computer_provider, computer_session, output)
            run.result_message_id = message.id
            transition_run(run, "completed")
            conversation = db.get(Conversation, run.conversation_id)
            if conversation:
                conversation.last_message_at = message.created_at or datetime.now(UTC)
            append_event(
                db, run, "message_created", {"message_id": str(message.id), "text": output}
            )
            append_event(db, run, "run_status", {"status": "completed"})
            db.commit()
            with suppress(Exception):
                inngest_client.send_sync(
                    inngest.Event(
                        name="grokbot/run.completed",
                        data={
                            "workspace_id": str(run.workspace_id),
                            "bot_id": str(run.bot_id),
                            "run_id": str(run_id),
                            "conversation_id": str(run.conversation_id),
                        },
                    )
                )
            return {"run_id": str(run_id), "status": "completed"}
    except Exception as exc:
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if run and run.status == "running":
                transition_run(run, "failed")
                run.error_code = type(exc).__name__
                run.error_message = str(exc)[:2000]
                append_event(
                    db, run, "run_status", {"status": "failed", "message": "The run failed."}
                )
                db.commit()
        raise


@inngest_client.create_function(
    fn_id="execute-bot-run",
    name="Execute Bot run",
    trigger=inngest.TriggerEvent(event="grokbot/bot.run.requested"),
    concurrency=[inngest.Concurrency(limit=1, key="event.data.bot_id")],
    cancel=[
        inngest.Cancel(
            event="grokbot/run.cancel.requested", match="async.data.run_id == event.data.run_id"
        )
    ],
    retries=3,
)
def execute_bot_run_function(ctx: inngest.ContextSync) -> dict[str, str]:
    return execute_bot_run(uuid.UUID(str(ctx.event.data["run_id"])))


@inngest_client.create_function(
    fn_id="resume-bot-run",
    name="Resume Bot run after approval",
    trigger=inngest.TriggerEvent(event="grokbot/bot.resume.requested"),
    concurrency=[inngest.Concurrency(limit=1, key="event.data.bot_id")],
    retries=3,
)
def resume_bot_run_function(ctx: inngest.ContextSync) -> dict[str, str]:
    return execute_bot_run(uuid.UUID(str(ctx.event.data["run_id"])))


@inngest_client.create_function(
    fn_id="resume-bot-run-after-takeover",
    name="Resume Bot run after takeover",
    trigger=inngest.TriggerEvent(event="grokbot/takeover.resolved"),
    concurrency=[inngest.Concurrency(limit=1, key="event.data.bot_id")],
    retries=3,
)
def takeover_resume_function(ctx: inngest.ContextSync) -> dict[str, str]:
    return execute_bot_run(uuid.UUID(str(ctx.event.data["run_id"])))


@inngest_client.create_function(
    fn_id="extract-memories",
    name="Extract memories from completed run",
    trigger=inngest.TriggerEvent(event="grokbot/run.completed"),
    retries=2,
)
def extract_memories_function(ctx: inngest.ContextSync) -> dict[str, str]:
    """Failure-isolated background memory extraction.

    Any exception is caught and logged; it must never affect the completed run.
    """
    run_id_str = str(ctx.event.data.get("run_id", ""))
    workspace_id_str = str(ctx.event.data.get("workspace_id", ""))
    bot_id_str = str(ctx.event.data.get("bot_id", ""))
    conversation_id_str = str(ctx.event.data.get("conversation_id", ""))
    try:
        from app.core.database import SessionLocal
        from app.domain.models import Conversation, Message
        from app.services.memory import MemoryRepository, MemoryService

        with SessionLocal() as db:
            conversation_id = uuid.UUID(conversation_id_str)
            conversation = db.get(Conversation, conversation_id)
            if conversation is None:
                return {"status": "skipped", "reason": "conversation not found"}
            recent_msgs = list(
                db.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.sender_type.in_(["user", "bot"]),
                    )
                    .order_by(Message.created_at.desc())
                    .limit(10)
                )
            )
            if not recent_msgs:
                return {"status": "skipped", "reason": "no messages"}
            svc = MemoryService(MemoryRepository(db))
            extracted = 0
            for msg in recent_msgs:
                if msg.sender_type != "user":
                    continue
                text_content = (msg.text_content or "").strip()
                if len(text_content) < 20:
                    continue
                import asyncio

                asyncio.run(
                    svc.create_memory(
                        workspace_id=uuid.UUID(workspace_id_str),
                        content=text_content[:500],
                        scope_type="bot",
                        scope_id=uuid.UUID(bot_id_str),
                        memory_type="episodic",
                        importance=0.3,
                        confidence=0.4,
                        source_type="run",
                        source_id=uuid.UUID(run_id_str),
                        source_excerpt=text_content[:200],
                    )
                )
                db.commit()
                extracted += 1
            return {"status": "ok", "extracted": str(extracted)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:500]}


@inngest_client.create_function(
    fn_id="check-due-routines",
    name="Check and trigger due routines",
    trigger=inngest.TriggerCron(cron="* * * * *"),
    retries=0,
)
def check_due_routines_function(ctx: inngest.ContextSync) -> dict[str, int]:
    """Every minute: find enabled routines whose next_expected_run_at has passed."""
    from app.domain.models import Routine

    now = datetime.now(UTC)
    triggered = 0
    with suppress(Exception), SessionLocal() as db:
        due = list(
            db.scalars(
                select(Routine).where(
                    Routine.enabled.is_(True),
                    Routine.next_expected_run_at.isnot(None),
                    Routine.next_expected_run_at <= now,
                )
            )
        )
        for r in due:
            with suppress(Exception):
                inngest_client.send_sync(
                    inngest.Event(
                        name="grokbot/routine.trigger",
                        data={"routine_id": str(r.id)},
                    )
                )
                triggered += 1
    return {"triggered": triggered}


@inngest_client.create_function(
    fn_id="execute-routine-run",
    name="Execute routine run",
    trigger=inngest.TriggerEvent(event="grokbot/routine.trigger"),
    retries=2,
)
def execute_routine_run_function(ctx: inngest.ContextSync) -> dict[str, str]:
    """Create a RoutineRun and advance routine scheduling on trigger."""
    routine_id_str = str(ctx.event.data.get("routine_id", ""))
    try:
        from app.services.routines import (
            NotificationRepository,
            NotificationService,
            RoutineRepository,
            RoutineService,
            _compute_next_run,
        )

        with SessionLocal() as db:
            svc = RoutineService(RoutineRepository(db))
            routine_id = uuid.UUID(routine_id_str)
            r = db.get(Routine, routine_id)
            if r is None:
                return {"status": "skipped", "reason": "routine not found"}
            if not r.enabled:
                return {"status": "skipped", "reason": "routine disabled"}
            rr = svc.create_run(routine_id, status="running")
            next_run = _compute_next_run(r.trigger_type, r.schedule_expression, r.timezone)
            svc._repo.update(r, next_expected_run_at=next_run)
            members = list(
                db.scalars(
                    select(WorkspaceMember).where(WorkspaceMember.workspace_id == r.workspace_id)
                )
            )
            n_svc = NotificationService(NotificationRepository(db))
            for member in members:
                with suppress(Exception):
                    n_svc.create(
                        workspace_id=r.workspace_id,
                        user_id=member.user_id,
                        type="routine_completed",
                        title=f"Routine '{r.name}' ran",
                        body="Your scheduled routine executed successfully.",
                        entity_type="routine_run",
                        entity_id=rr.id,
                    )
            svc._repo.update_run(rr, status="completed", completed_at=datetime.now(UTC))
            return {"status": "ok", "routine_run_id": str(rr.id)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:500]}


@inngest_client.create_function(
    fn_id="bot-message-delivery",
    name="Deliver Bot-to-Bot message and wake recipient",
    trigger=inngest.TriggerEvent(event="grokbot/message.delivery.requested"),
    concurrency=[inngest.Concurrency(limit=1, key="event.data.bot_id")],
    retries=3,
)
def bot_message_delivery_function(ctx: inngest.ContextSync) -> dict[str, str]:
    """Triggered after send_bot_message() commit. Wakes the recipient Bot."""
    inbox_item_id_str = str(ctx.event.data.get("inbox_item_id", ""))
    bot_id_str = str(ctx.event.data.get("bot_id", ""))
    try:
        from app.domain.models import Bot, BotInboxItem, Message, Run

        with SessionLocal() as db:
            inbox_item = (
                db.get(BotInboxItem, uuid.UUID(inbox_item_id_str)) if inbox_item_id_str else None
            )
            if inbox_item is None or inbox_item.status != "pending":
                return {"status": "skipped", "reason": "inbox item already processed or not found"}
            bot = db.get(Bot, uuid.UUID(bot_id_str))
            if bot is None:
                return {"status": "error", "reason": "bot not found"}
            # Mark in_progress
            inbox_item.status = "in_progress"
            db.flush()

            # Find the source message to use as trigger
            source_message: Message | None = None
            source_conversation_id: uuid.UUID | None = None
            if inbox_item.source_type == "dm":
                source_message = db.get(Message, inbox_item.source_id)
                if source_message:
                    source_conversation_id = source_message.conversation_id

            # Create a new Run for the recipient bot
            run = Run(
                workspace_id=bot.workspace_id,
                bot_id=bot.id,
                conversation_id=source_conversation_id,
                trigger_message_id=source_message.id if source_message else None,
                source="agent",
                status="queued",
                priority=inbox_item.priority * 10,
            )
            db.add(run)
            db.flush()
            append_event(
                db, run, "run_status", {"status": "queued", "label": "Bot message received"}
            )
            db.commit()
            run_id = run.id

        return execute_bot_run(run_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:500]}


@inngest_client.create_function(
    fn_id="delegation-created",
    name="Handle delegation created — wake assignee Bot",
    trigger=inngest.TriggerEvent(event="grokbot/delegation.created"),
    concurrency=[inngest.Concurrency(limit=1, key="event.data.assignee_bot_id")],
    retries=3,
)
def delegation_created_function(ctx: inngest.ContextSync) -> dict[str, str]:
    """Triggered after atomic delegation transaction commits. Wakes the assignee Bot."""
    delegation_id_str = str(ctx.event.data.get("delegation_id", ""))
    inbox_item_id_str = str(ctx.event.data.get("inbox_item_id", ""))
    try:
        from app.domain.models import BotInboxItem, Delegation, Message, Run

        with SessionLocal() as db:
            delegation = db.get(Delegation, uuid.UUID(delegation_id_str))
            if delegation is None:
                return {"status": "skipped", "reason": "delegation not found"}
            if delegation.status not in {"requested", "accepted"}:
                return {"status": "skipped", "reason": f"delegation already {delegation.status}"}
            inbox_item = (
                db.get(BotInboxItem, uuid.UUID(inbox_item_id_str)) if inbox_item_id_str else None
            )
            if inbox_item and inbox_item.status != "pending":
                return {"status": "skipped", "reason": "inbox item already processed"}
            # Accept delegation
            delegation.status = "accepted"
            delegation.accepted_at = datetime.now(UTC)
            if inbox_item:
                inbox_item.status = "in_progress"
            db.flush()

            # Find handoff message
            source_message: Message | None = None
            if delegation.result_message_id:
                source_message = db.get(Message, delegation.result_message_id)

            run = Run(
                workspace_id=delegation.workspace_id,
                bot_id=delegation.assignee_bot_id,
                conversation_id=source_message.conversation_id if source_message else None,
                trigger_message_id=source_message.id if source_message else None,
                source="agent",
                status="queued",
                priority=700,
                metadata_={"delegation_id": delegation_id_str},
            )
            db.add(run)
            db.flush()
            append_event(
                db, run, "run_status", {"status": "queued", "label": "Delegation received"}
            )
            db.commit()
            run_id = run.id

        return execute_bot_run(run_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:500]}


@inngest_client.create_function(
    fn_id="delegation-completed-resume",
    name="Resume requester Bot after delegation completes",
    trigger=inngest.TriggerEvent(event="grokbot/delegation.completed"),
    concurrency=[inngest.Concurrency(limit=1, key="event.data.requester_bot_id")],
    retries=3,
)
def delegation_completed_function(ctx: inngest.ContextSync) -> dict[str, str]:
    """Resumes the requester Bot run with the delegation result as an observation."""
    requester_run_id_str = str(ctx.event.data.get("requester_run_id", ""))
    delegation_id_str = str(ctx.event.data.get("delegation_id", ""))
    result = ctx.event.data.get("result", {})
    try:
        from app.domain.models import Delegation, Run

        with SessionLocal() as db:
            requester_run = db.get(Run, uuid.UUID(requester_run_id_str))
            if requester_run is None:
                return {"status": "skipped", "reason": "requester run not found"}
            delegation = db.get(Delegation, uuid.UUID(delegation_id_str))
            # Inject delegation result into run metadata for next invocation
            meta = dict(requester_run.metadata_)
            meta["delegation_results"] = meta.get("delegation_results", [])
            meta["delegation_results"].append(
                {
                    "delegation_id": delegation_id_str,
                    "status": delegation.status if delegation else "completed",
                    "result": result,
                }
            )
            requester_run.metadata_ = meta
            if requester_run.status == "waiting_agent":
                from app.agents.run_states import transition_run

                transition_run(requester_run, "queued")
                append_event(
                    db,
                    requester_run,
                    "run_status",
                    {"status": "queued", "label": "Delegation result received"},
                )
            db.commit()
            run_id = requester_run.id

        return execute_bot_run(run_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:500]}


INNGEST_FUNCTIONS = [
    execute_bot_run_function,
    resume_bot_run_function,
    takeover_resume_function,
    extract_memories_function,
    check_due_routines_function,
    execute_routine_run_function,
    bot_message_delivery_function,
    delegation_created_function,
    delegation_completed_function,
]


def dispatch_run(run: Run, event_name: str = "grokbot/bot.run.requested") -> None:
    event = inngest.Event(
        name=event_name,
        id=f"{event_name}:{run.id}",
        data={
            "workspace_id": str(run.workspace_id),
            "bot_id": str(run.bot_id),
            "run_id": str(run.id),
            "message_id": str(run.trigger_message_id),
        },
    )
    try:
        event_ids = inngest_client.send_sync(event)
        if event_ids:
            with SessionLocal() as db:
                persisted = db.get(Run, run.id)
                if persisted:
                    persisted.inngest_event_id = event_ids[0]
                    db.commit()
    except Exception:
        # The durable queued row remains truth when local delivery is unavailable.
        pass
    if settings.enable_inline_worker:
        threading.Thread(
            target=execute_bot_run, args=(run.id,), daemon=True, name=f"run-{run.id}"
        ).start()


def _action_request(message: Message | None) -> tuple[str, dict[str, str]] | None:
    if message is None or not message.text_content:
        return None
    text = message.text_content.strip()
    if not text.startswith("/action "):
        return None
    remainder = text.removeprefix("/action ").strip()
    action_type, separator, request = remainder.partition(" ")
    if not separator or not action_type or not request:
        return None
    return action_type, {"request": request}


def request_cancel(db: Session, run: Run) -> Run:
    if run.status in {"queued", "running"}:
        transition_run(run, "cancel_requested" if run.status == "running" else "cancelled")
        append_event(db, run, "run_status", {"status": run.status})
        db.commit()
        with suppress(Exception):
            inngest_client.send_sync(
                inngest.Event(
                    name="grokbot/run.cancel.requested",
                    id=f"cancel:{run.id}",
                    data={"run_id": str(run.id), "bot_id": str(run.bot_id)},
                )
            )
    return run


def recover_stranded_runs() -> int:
    with SessionLocal() as db:
        runs = list(
            db.scalars(select(Run).where(Run.status.in_(["queued", "running", "cancel_requested"])))
        )
        count = 0
        for run in runs:
            if run.status == "running":
                transition_run(run, "queued")
                append_event(db, run, "run_status", {"status": "queued", "recovered": True})
            elif run.status == "cancel_requested":
                transition_run(run, "cancelled")
                append_event(db, run, "run_status", {"status": "cancelled", "recovered": True})
            count += 1
        db.commit()
        for run in runs:
            if run.status == "queued" and settings.enable_inline_worker:
                threading.Thread(target=execute_bot_run, args=(run.id,), daemon=True).start()
        return count


def event_to_sse(event: RunEvent) -> str:
    payload = {
        "id": event.id,
        "run_id": str(event.run_id),
        "sequence": event.sequence,
        "event_type": event.event_type,
        "created_at": event.created_at.isoformat(),
        **event.payload,
    }
    return f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(payload)}\n\n"
