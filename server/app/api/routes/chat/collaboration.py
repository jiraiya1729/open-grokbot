"""Collaboration HTTP routes for –: tasks, delegations, hierarchy, groups."""

from __future__ import annotations

import contextlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.runtime import inngest_client
from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.schemas import (
    BotHierarchyView,
    BotInboxItemView,
    BotRelationshipView,
    ChildBotRequestCreate,
    ChildBotRequestDecision,
    ChildBotRequestView,
    DelegationAtomicCreate,
    DelegationCreate,
    DelegationView,
    GroupCreate,
    GroupMemberAdd,
    GroupMessageCreate,
    GroupUpdate,
    GroupView,
    MessageReactionView,
    TaskCreate,
    TaskUpdate,
    TaskView,
    UpdateRelationshipBody,
)
from app.services.collaboration import (
    ChildBotService,
    CollaborationService,
    DelegationRepository,
    GroupDispatcher,
    PolicyDeniedError,
    TaskRepository,
)

router = APIRouter(tags=["collaboration"])


def _svc(session: Session = Depends(get_db)) -> CollaborationService:
    return CollaborationService(TaskRepository(session), DelegationRepository(session), session)


# ── Tasks ──────────────────────────────────────────────────────────────────


@router.get("/tasks", response_model=list[TaskView])
def list_tasks(
    assigned_to_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> list[TaskView]:
    items, _ = svc.list_tasks(
        ctx.workspace_id,
        assigned_to_id=assigned_to_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [TaskView.model_validate(t) for t in items]


@router.post("/tasks", response_model=TaskView, status_code=201)
def create_task(
    body: TaskCreate,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> TaskView:
    t = svc.create_task(
        workspace_id=ctx.workspace_id,
        title=body.title,
        description=body.description,
        created_by_type="user",
        created_by_id=ctx.user_id,
        assigned_to_type=body.assigned_to_type,
        assigned_to_id=body.assigned_to_id,
        priority=body.priority,
        deadline=body.deadline,
        budget=body.budget,
    )
    return TaskView.model_validate(t)


@router.get("/tasks/{task_id}", response_model=TaskView)
def get_task(
    task_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> TaskView:
    try:
        t = svc.get_task(task_id)
    except KeyError:
        raise HTTPException(404, "Task not found") from None
    if t.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Task not found") from None
    return TaskView.model_validate(t)


@router.patch("/tasks/{task_id}", response_model=TaskView)
def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> TaskView:
    try:
        t = svc.get_task(task_id)
    except KeyError:
        raise HTTPException(404, "Task not found") from None
    if t.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Task not found") from None
    updates = body.model_dump(exclude_none=True)
    if updates:
        t = svc.update_task(task_id, **updates)
    return TaskView.model_validate(t)


# ── Delegations ────────────────────────────────────────────────────────────


@router.post("/tasks/{task_id}/delegations", response_model=DelegationView, status_code=201)
def create_delegation(
    task_id: uuid.UUID,
    body: DelegationCreate,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> DelegationView:
    try:
        svc.get_task(task_id)
    except KeyError:
        raise HTTPException(404, "Task not found") from None
    try:
        d = svc.create_delegation(
            workspace_id=ctx.workspace_id,
            task_id=task_id,
            requester_bot_id=body.requester_bot_id,
            assignee_bot_id=body.assignee_bot_id,
            hop_depth=body.hop_depth,
            requester_run_id=body.requester_run_id,
            correlation_id=body.correlation_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return DelegationView.model_validate(d)


@router.patch("/delegations/{delegation_id}", response_model=DelegationView)
def transition_delegation(
    delegation_id: uuid.UUID,
    status: str = Query(...),
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> DelegationView:
    try:
        svc.get_delegation(delegation_id)
    except KeyError:
        raise HTTPException(404, "Delegation not found") from None
    d = svc.transition_delegation(delegation_id, status)
    return DelegationView.model_validate(d)


# ── Reactions ──────────────────────────────────────────────────────────────


@router.get("/messages/{message_id}/reactions", response_model=list[MessageReactionView])
def list_reactions(
    message_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> list[MessageReactionView]:
    reactions = svc.list_reactions(message_id)
    return [MessageReactionView.model_validate(r) for r in reactions]


@router.post(
    "/messages/{message_id}/reactions", response_model=MessageReactionView, status_code=201
)
def add_reaction(
    message_id: uuid.UUID,
    emoji: str = Query(...),
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> MessageReactionView:
    r = svc.add_reaction(
        message_id=message_id,
        actor_type="user",
        actor_id=ctx.user_id,
        emoji=emoji,
    )
    return MessageReactionView.model_validate(r)


@router.delete("/messages/{message_id}/reactions", status_code=204)
def remove_reaction(
    message_id: uuid.UUID,
    emoji: str = Query(...),
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> None:
    svc.remove_reaction(
        message_id=message_id,
        actor_type="user",
        actor_id=ctx.user_id,
        emoji=emoji,
    )


# ── Bot relationships ──────────────────────────────────────────────────────


@router.get("/bots/{bot_id}/relationships", response_model=list[BotRelationshipView])
def list_bot_relationships(
    bot_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> list[BotRelationshipView]:
    rels = svc.list_bot_relationships(bot_id)
    return [BotRelationshipView.model_validate(r) for r in rels]


@router.put("/bots/{bot_id}/relationships/{rel_id}", response_model=BotRelationshipView)
def update_bot_relationship(
    bot_id: uuid.UUID,
    rel_id: uuid.UUID,
    body: UpdateRelationshipBody,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> BotRelationshipView:
    valid_types = {"created", "manages", "reports_to", "peer", "specialist_for"}
    if body.relationship_type not in valid_types:
        raise HTTPException(400, f"Invalid relationship_type: {body.relationship_type!r}")
    try:
        rel = svc.update_relationship(rel_id, body.relationship_type)
    except KeyError:
        raise HTTPException(404, "Relationship not found") from None
    if rel.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Relationship not found")
    return BotRelationshipView.model_validate(rel)


@router.get("/bots/{bot_id}/hierarchy", response_model=BotHierarchyView)
def get_bot_hierarchy(
    bot_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> BotHierarchyView:
    from app.domain.models import Bot  # noqa: PLC0415

    db = svc._s
    bot = db.get(Bot, bot_id)
    if bot is None or bot.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Bot not found")
    children = svc.list_children(bot_id)
    rels = svc.list_bot_relationships(bot_id)
    return BotHierarchyView(
        bot_id=bot_id,
        parent_bot_id=bot.creator_bot_id,
        direct_children=[c.id for c in children],
        relationships=[BotRelationshipView.model_validate(r) for r in rels],
    )


# ── Child bot creation requests ──────────────────────────────────────────


def _child_svc(session: Session = Depends(get_db)) -> ChildBotService:
    return ChildBotService(session)


@router.post(
    "/bots/{bot_id}/child-creation-requests",
    response_model=ChildBotRequestView,
    status_code=201,
)
def create_child_request(
    bot_id: uuid.UUID,
    body: ChildBotRequestCreate,
    ctx: RequestContext = Depends(local_context),
    child_svc: ChildBotService = Depends(_child_svc),
) -> ChildBotRequestView:
    try:
        req, mode = child_svc.request_create(
            workspace_id=ctx.workspace_id,
            parent_bot_id=bot_id,
            idempotency_key=body.idempotency_key,
            child_name=body.child_name,
            child_system_instructions=body.child_system_instructions,
            child_role_title=body.child_role_title,
            child_description=body.child_description,
            requested_relationship_label=body.requested_relationship_label,
            starter_config=body.starter_config,
            requested_by_run_id=body.requested_by_run_id,
        )
    except KeyError as e:
        raise HTTPException(404, str(e)) from None
    except PolicyDeniedError as e:
        raise HTTPException(403, str(e)) from None
    # If policy is allow, automatically materialize
    if mode == "allow" and req.status == "approved":
        with contextlib.suppress(Exception):
            req, _ = child_svc.materialize_child(req.id)
    return ChildBotRequestView.model_validate(req)


@router.get(
    "/bots/{bot_id}/child-creation-requests",
    response_model=list[ChildBotRequestView],
)
def list_child_requests(
    bot_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    child_svc: ChildBotService = Depends(_child_svc),
) -> list[ChildBotRequestView]:
    reqs = child_svc.list_requests(bot_id)
    return [ChildBotRequestView.model_validate(r) for r in reqs]


@router.post(
    "/bots/{bot_id}/child-creation-requests/{req_id}/approve",
    response_model=ChildBotRequestView,
)
def approve_child_request(
    bot_id: uuid.UUID,
    req_id: uuid.UUID,
    body: ChildBotRequestDecision | None = None,
    ctx: RequestContext = Depends(local_context),
    child_svc: ChildBotService = Depends(_child_svc),
) -> ChildBotRequestView:
    try:
        req = child_svc.approve(req_id, reason=body.reason if body else None)
    except KeyError:
        raise HTTPException(404, "Request not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if req.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Request not found")
    try:
        req, _ = child_svc.materialize_child(req.id)
    except Exception as e:
        raise HTTPException(500, f"Materialization failed: {e}") from e
    return ChildBotRequestView.model_validate(req)


@router.post(
    "/bots/{bot_id}/child-creation-requests/{req_id}/deny",
    response_model=ChildBotRequestView,
)
def deny_child_request(
    bot_id: uuid.UUID,
    req_id: uuid.UUID,
    body: ChildBotRequestDecision | None = None,
    ctx: RequestContext = Depends(local_context),
    child_svc: ChildBotService = Depends(_child_svc),
) -> ChildBotRequestView:
    try:
        req = child_svc.deny(req_id, reason=body.reason if body else None)
    except KeyError:
        raise HTTPException(404, "Request not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if req.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Request not found")
    return ChildBotRequestView.model_validate(req)


# ── Groups ─────────────────────────────────────────────────────────────────────


def _group_dispatcher(session: Session = Depends(get_db)) -> GroupDispatcher:
    return GroupDispatcher(session)


@router.post("/groups", response_model=GroupView, status_code=201)
def create_group(
    body: GroupCreate,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> GroupView:

    _conv, group = svc.create_group_conversation(
        workspace_id=ctx.workspace_id,
        title=body.title,
        topic=body.topic,
        member_bot_ids=body.member_bot_ids,
        coordinator_bot_id=body.coordinator_bot_id,
        autonomy_policy=body.autonomy_policy,
        created_by_id=ctx.user_id,
    )
    return GroupView.model_validate(group)


@router.get("/groups/{conversation_id}", response_model=GroupView)
def get_group(
    conversation_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> GroupView:
    group = svc.get_group(conversation_id)
    if group is None:
        raise HTTPException(404, "Group not found")
    return GroupView.model_validate(group)


@router.patch("/groups/{conversation_id}", response_model=GroupView)
def update_group(
    conversation_id: uuid.UUID,
    body: GroupUpdate,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> GroupView:
    group = svc.get_group(conversation_id)
    if group is None:
        raise HTTPException(404, "Group not found")
    updates = body.model_dump(exclude_none=True)
    for k, v in updates.items():
        setattr(group, k, v)
    svc._s.commit()
    svc._s.refresh(group)
    return GroupView.model_validate(group)


@router.post("/groups/{conversation_id}/archive", status_code=204)
def archive_group(
    conversation_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> None:
    from datetime import UTC, datetime  # noqa: PLC0415

    from app.domain.models import Conversation  # noqa: PLC0415

    conv = svc._s.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Group not found")
    conv.archived_at = datetime.now(UTC)
    svc._s.commit()


@router.post("/groups/{conversation_id}/members", status_code=201)
def add_group_member(
    conversation_id: uuid.UUID,
    body: GroupMemberAdd,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> dict[str, str]:
    svc.add_group_member(
        conversation_id=conversation_id,
        participant_type=body.participant_type,
        participant_id=body.participant_id,
        role=body.role,
    )
    return {"status": "added"}


@router.delete("/groups/{conversation_id}/members/{participant_id}", status_code=204)
def remove_group_member(
    conversation_id: uuid.UUID,
    participant_id: uuid.UUID,
    participant_type: str = Query(default="bot"),
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> None:
    svc.remove_group_member(
        conversation_id=conversation_id,
        participant_type=participant_type,
        participant_id=participant_id,
    )


@router.post("/groups/{conversation_id}/messages", status_code=201)
def send_group_message(
    conversation_id: uuid.UUID,
    body: GroupMessageCreate,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
    dispatcher: GroupDispatcher = Depends(_group_dispatcher),
) -> dict[str, str]:
    from contextlib import suppress  # noqa: PLC0415

    from app.domain.models import Conversation, Message  # noqa: PLC0415

    conv = svc._s.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Group not found")
    group = svc.get_group(conversation_id)
    if group is None:
        raise HTTPException(404, "Group record not found")

    msg = Message(
        workspace_id=ctx.workspace_id,
        conversation_id=conversation_id,
        sender_type="user",
        sender_id=ctx.user_id,
        kind="text",
        text_content=body.text,
        reply_to_message_id=body.reply_to_message_id,
    )
    svc._s.add(msg)
    svc._s.flush()

    from app.services.collaboration import _MENTION_RE  # noqa: PLC0415

    mention_tokens = [m.group(1) for m in _MENTION_RE.finditer(body.text)]
    inbox_items = dispatcher.dispatch(
        workspace_id=ctx.workspace_id,
        message=msg,
        group=group,
        mention_tokens=mention_tokens,
    )

    # Emit Inngest wakeup events after commit
    import inngest  # noqa: PLC0415

    for item in inbox_items:
        with suppress(Exception):
            inngest_client.send_sync(
                inngest.Event(
                    name="grokbot/message.delivery.requested",
                    data={
                        "bot_id": str(item.bot_id),
                        "inbox_item_id": str(item.id),
                    },
                )
            )
    return {"message_id": str(msg.id), "woken_bots": str(len(inbox_items))}


@router.get("/groups/{conversation_id}/mentions/autocomplete")
def autocomplete_mentions(
    conversation_id: uuid.UUID,
    q: str = Query(default=""),
    ctx: RequestContext = Depends(local_context),
    dispatcher: GroupDispatcher = Depends(_group_dispatcher),
) -> list[dict[str, str]]:
    return dispatcher.autocomplete_mentions(ctx.workspace_id, conversation_id, q)


# ── Bot inbox ──────────────────────────────────────────────────────────────────


@router.get("/bots/{bot_id}/inbox", response_model=list[BotInboxItemView])
def get_bot_inbox(
    bot_id: uuid.UUID,
    status: str = Query(default="pending"),
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> list[BotInboxItemView]:
    items = svc.get_bot_inbox(bot_id, status=status)
    return [BotInboxItemView.model_validate(i) for i in items]


# ── Atomic delegation ──────────────────────────────────────────────────────────


@router.post("/delegations/atomic", status_code=201)
def create_delegation_atomic(
    body: DelegationAtomicCreate,
    ctx: RequestContext = Depends(local_context),
    svc: CollaborationService = Depends(_svc),
) -> dict[str, str]:
    from contextlib import suppress  # noqa: PLC0415

    try:
        task, delegation, msg, _delivery, inbox_item = svc.create_delegation_atomic(
            workspace_id=ctx.workspace_id,
            requester_bot_id=body.requester_bot_id,
            assignee_bot_id=body.assignee_bot_id,
            title=body.title,
            description=body.description,
            requester_run_id=body.requester_run_id,
            hop_depth=body.hop_depth,
            correlation_id=body.correlation_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    import inngest  # noqa: PLC0415

    with suppress(Exception):
        inngest_client.send_sync(
            inngest.Event(
                name="grokbot/delegation.created",
                data={
                    "delegation_id": str(delegation.id),
                    "assignee_bot_id": str(delegation.assignee_bot_id),
                    "inbox_item_id": str(inbox_item.id),
                },
            )
        )
    return {
        "task_id": str(task.id),
        "delegation_id": str(delegation.id),
        "message_id": str(msg.id),
        "inbox_item_id": str(inbox_item.id),
    }
