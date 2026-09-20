"""Collaboration service for –: tasks, delegations, groups, subagent runs, hierarchy."""

from __future__ import annotations

import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    Bot,
    BotCreationRequest,
    BotInboxItem,
    BotRelationship,
    Conversation,
    ConversationParticipant,
    Delegation,
    Group,
    GroupRound,
    Message,
    MessageDelivery,
    MessageMention,
    MessageReaction,
    SubagentRun,
    Task,
)

_MENTION_RE = re.compile(r"@(\w+)")

MAX_HOP_DEPTH = 5
MAX_SUBAGENTS_PER_RUN = 3
MAX_DIRECT_CHILDREN = 3
MAX_HIERARCHY_DEPTH = 1


class PolicyDeniedError(ValueError):
    pass


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, **kwargs: Any) -> Task:
        t = Task(**kwargs)
        self._s.add(t)
        self._s.commit()
        self._s.refresh(t)
        return t

    def get(self, task_id: uuid.UUID) -> Task | None:
        return self._s.get(Task, task_id)

    def get_required(self, task_id: uuid.UUID) -> Task:
        t = self.get(task_id)
        if t is None:
            raise KeyError(f"Task {task_id} not found")
        return t

    def list_for_workspace(
        self,
        workspace_id: uuid.UUID,
        assigned_to_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        conditions: list[Any] = [Task.workspace_id == workspace_id]
        if assigned_to_id:
            conditions.append(Task.assigned_to_id == assigned_to_id)
        if status:
            conditions.append(Task.status == status)
        where = and_(*conditions)
        total: int = self._s.execute(select(func.count(Task.id)).where(where)).scalar_one()
        items = list(
            self._s.scalars(
                select(Task)
                .where(where)
                .order_by(Task.priority.desc(), Task.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def update(self, task: Task, **kwargs: Any) -> Task:
        for k, v in kwargs.items():
            setattr(task, k, v)
        self._s.commit()
        self._s.refresh(task)
        return task


class DelegationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, **kwargs: Any) -> Delegation:
        d = Delegation(**kwargs)
        self._s.add(d)
        self._s.commit()
        self._s.refresh(d)
        return d

    def get(self, delegation_id: uuid.UUID) -> Delegation | None:
        return self._s.get(Delegation, delegation_id)

    def get_required(self, delegation_id: uuid.UUID) -> Delegation:
        d = self.get(delegation_id)
        if d is None:
            raise KeyError(f"Delegation {delegation_id} not found")
        return d

    def get_by_correlation(self, correlation_id: uuid.UUID) -> Delegation | None:
        return self._s.scalars(
            select(Delegation).where(Delegation.correlation_id == correlation_id)
        ).first()

    def list_for_assignee(
        self,
        assignee_bot_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Delegation], int]:
        conditions: list[Any] = [Delegation.assignee_bot_id == assignee_bot_id]
        if status:
            conditions.append(Delegation.status == status)
        where = and_(*conditions)
        total: int = self._s.execute(select(func.count(Delegation.id)).where(where)).scalar_one()
        items = list(
            self._s.scalars(
                select(Delegation)
                .where(where)
                .order_by(Delegation.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def update(self, delegation: Delegation, **kwargs: Any) -> Delegation:
        for k, v in kwargs.items():
            setattr(delegation, k, v)
        self._s.commit()
        self._s.refresh(delegation)
        return delegation


class CollaborationService:
    def __init__(
        self,
        tasks: TaskRepository,
        delegations: DelegationRepository,
        session: Session,
    ) -> None:
        self._tasks = tasks
        self._delegations = delegations
        self._s = session

    # ── Tasks ──────────────────────────────────────────────────────────────

    def create_task(
        self,
        workspace_id: uuid.UUID,
        title: str,
        created_by_type: str,
        created_by_id: uuid.UUID | None = None,
        assigned_to_type: str | None = None,
        assigned_to_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> Task:
        return self._tasks.create(
            workspace_id=workspace_id,
            title=title,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
            assigned_to_type=assigned_to_type,
            assigned_to_id=assigned_to_id,
            **kwargs,
        )

    def get_task(self, task_id: uuid.UUID) -> Task:
        return self._tasks.get_required(task_id)

    def update_task(self, task_id: uuid.UUID, **kwargs: Any) -> Task:
        t = self._tasks.get_required(task_id)
        if "status" in kwargs and kwargs["status"] in ("completed", "failed", "cancelled"):
            kwargs.setdefault("completed_at", datetime.now(UTC))
        return self._tasks.update(t, **kwargs)

    def list_tasks(
        self,
        workspace_id: uuid.UUID,
        assigned_to_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        return self._tasks.list_for_workspace(workspace_id, assigned_to_id, status, limit, offset)

    # ── Delegations ────────────────────────────────────────────────────────

    def create_delegation(
        self,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
        requester_bot_id: uuid.UUID,
        assignee_bot_id: uuid.UUID,
        hop_depth: int = 1,
        requester_run_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> Delegation:
        if hop_depth > MAX_HOP_DEPTH:
            raise ValueError(f"Delegation hop_depth {hop_depth} exceeds limit {MAX_HOP_DEPTH}")
        # Idempotency: if correlation_id exists, return existing delegation
        corr_id = correlation_id or uuid.uuid4()
        existing = self._delegations.get_by_correlation(corr_id)
        if existing:
            return existing
        return self._delegations.create(
            workspace_id=workspace_id,
            task_id=task_id,
            requester_bot_id=requester_bot_id,
            assignee_bot_id=assignee_bot_id,
            hop_depth=hop_depth,
            requester_run_id=requester_run_id,
            correlation_id=corr_id,
        )

    def get_delegation(self, delegation_id: uuid.UUID) -> Delegation:
        return self._delegations.get_required(delegation_id)

    def transition_delegation(self, delegation_id: uuid.UUID, new_status: str) -> Delegation:
        d = self._delegations.get_required(delegation_id)
        updates: dict[str, Any] = {"status": new_status}
        if new_status == "accepted":
            updates["accepted_at"] = datetime.now(UTC)
        elif new_status in ("completed", "failed", "cancelled"):
            updates["completed_at"] = datetime.now(UTC)
        return self._delegations.update(d, **updates)

    # ── Group conversations ───────────────────────────────────────────────

    def create_group(
        self,
        conversation_id: uuid.UUID,
        slug: str | None = None,
        topic: str | None = None,
        autonomy_policy: dict[str, Any] | None = None,
    ) -> Group:
        g = Group(
            conversation_id=conversation_id,
            slug=slug,
            topic=topic,
            autonomy_policy=autonomy_policy or {},
        )
        self._s.add(g)
        self._s.commit()
        self._s.refresh(g)
        return g

    def get_group(self, conversation_id: uuid.UUID) -> Group | None:
        return self._s.get(Group, conversation_id)

    # ── Message reactions ─────────────────────────────────────────────────

    def add_reaction(
        self,
        message_id: uuid.UUID,
        actor_type: str,
        actor_id: uuid.UUID,
        emoji: str,
    ) -> MessageReaction:
        existing = self._s.get(MessageReaction, (message_id, actor_type, actor_id, emoji))
        if existing:
            return existing
        r = MessageReaction(
            message_id=message_id,
            actor_type=actor_type,
            actor_id=actor_id,
            emoji=emoji,
        )
        self._s.add(r)
        self._s.commit()
        return r

    def remove_reaction(
        self,
        message_id: uuid.UUID,
        actor_type: str,
        actor_id: uuid.UUID,
        emoji: str,
    ) -> None:
        r = self._s.get(MessageReaction, (message_id, actor_type, actor_id, emoji))
        if r:
            self._s.delete(r)
            self._s.commit()

    def list_reactions(self, message_id: uuid.UUID) -> list[MessageReaction]:
        return list(
            self._s.scalars(select(MessageReaction).where(MessageReaction.message_id == message_id))
        )

    # ── Message deliveries ────────────────────────────────────────────────

    def create_delivery(
        self,
        message_id: uuid.UUID,
        recipient_type: str,
        recipient_id: uuid.UUID,
        wake_requested: bool = False,
    ) -> MessageDelivery:
        delivery_key = f"{message_id}:{recipient_type}:{recipient_id}"
        existing = self._s.scalars(
            select(MessageDelivery).where(MessageDelivery.delivery_key == delivery_key)
        ).first()
        if existing:
            return existing
        d = MessageDelivery(
            message_id=message_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            delivery_key=delivery_key,
            wake_requested=wake_requested,
        )
        self._s.add(d)
        self._s.commit()
        self._s.refresh(d)
        return d

    # ── Subagent runs ─────────────────────────────────────────────────────

    def spawn_subagent(
        self,
        workspace_id: uuid.UUID,
        parent_run_id: uuid.UUID,
        kind: str = "general",
        purpose: str | None = None,
        token_budget: int | None = None,
    ) -> SubagentRun:
        existing_count = self._s.execute(
            select(func.count(SubagentRun.id)).where(
                and_(
                    SubagentRun.parent_run_id == parent_run_id,
                    SubagentRun.status == "running",
                )
            )
        ).scalar_one()
        if existing_count >= MAX_SUBAGENTS_PER_RUN:
            raise ValueError(f"Max {MAX_SUBAGENTS_PER_RUN} concurrent subagents per run exceeded")
        sa = SubagentRun(
            workspace_id=workspace_id,
            parent_run_id=parent_run_id,
            kind=kind,
            purpose=purpose,
            token_budget=token_budget,
        )
        self._s.add(sa)
        self._s.commit()
        self._s.refresh(sa)
        return sa

    def complete_subagent(
        self,
        subagent_id: uuid.UUID,
        status: str = "completed",
        result_summary: str | None = None,
    ) -> SubagentRun:
        sa = self._s.get(SubagentRun, subagent_id)
        if sa is None:
            raise KeyError(f"SubagentRun {subagent_id} not found")
        sa.status = status
        sa.result_summary = result_summary
        sa.completed_at = datetime.now(UTC)
        self._s.commit()
        self._s.refresh(sa)
        return sa

    def cleanup_subagents(self, parent_run_id: uuid.UUID) -> int:
        running = list(
            self._s.scalars(
                select(SubagentRun).where(
                    and_(
                        SubagentRun.parent_run_id == parent_run_id,
                        SubagentRun.status == "running",
                    )
                )
            )
        )
        for sa in running:
            sa.status = "cancelled"
            sa.completed_at = datetime.now(UTC)
        if running:
            self._s.commit()
        return len(running)

    def list_subagents(self, parent_run_id: uuid.UUID) -> list[SubagentRun]:
        return list(
            self._s.scalars(
                select(SubagentRun)
                .where(SubagentRun.parent_run_id == parent_run_id)
                .order_by(SubagentRun.started_at)
            )
        )

    # ── Bot relationships ──────────────────────────────────────────────────

    def create_bot_relationship(
        self,
        workspace_id: uuid.UUID,
        from_bot_id: uuid.UUID,
        to_bot_id: uuid.UUID,
        relationship_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> BotRelationship:
        existing = self._s.scalars(
            select(BotRelationship).where(
                and_(
                    BotRelationship.from_bot_id == from_bot_id,
                    BotRelationship.to_bot_id == to_bot_id,
                    BotRelationship.relationship_type == relationship_type,
                )
            )
        ).first()
        if existing:
            return existing
        rel = BotRelationship(
            workspace_id=workspace_id,
            from_bot_id=from_bot_id,
            to_bot_id=to_bot_id,
            relationship_type=relationship_type,
            metadata_=metadata or {},
        )
        self._s.add(rel)
        self._s.commit()
        self._s.refresh(rel)
        return rel

    def list_bot_relationships(self, from_bot_id: uuid.UUID) -> list[BotRelationship]:
        return list(
            self._s.scalars(
                select(BotRelationship).where(BotRelationship.from_bot_id == from_bot_id)
            )
        )

    def get_relationship(self, rel_id: uuid.UUID) -> BotRelationship | None:
        return self._s.get(BotRelationship, rel_id)

    def update_relationship(self, rel_id: uuid.UUID, relationship_type: str) -> BotRelationship:
        rel = self._s.get(BotRelationship, rel_id)
        if rel is None:
            raise KeyError(f"Relationship {rel_id} not found")
        rel.relationship_type = relationship_type
        self._s.commit()
        self._s.refresh(rel)
        return rel

    def list_children(self, parent_bot_id: uuid.UUID) -> list[Bot]:
        """Return active direct children of a parent bot."""
        return list(
            self._s.scalars(
                select(Bot).where(
                    Bot.creator_bot_id == parent_bot_id,
                    Bot.lifecycle_status == "active",
                )
            )
        )

    # ── Bot-to-Bot DMs ─────────────────────────────────────────────────────

    def create_or_get_bot_dm(
        self,
        workspace_id: uuid.UUID,
        bot_a_id: uuid.UUID,
        bot_b_id: uuid.UUID,
    ) -> Conversation:
        """Find or create a DM conversation between two Bots."""
        # Look for an existing DM where both bots are participants
        a_convs = set(
            r[0]
            for r in self._s.execute(
                select(ConversationParticipant.conversation_id).where(
                    ConversationParticipant.participant_type == "bot",
                    ConversationParticipant.participant_id == bot_a_id,
                )
            ).fetchall()
        )
        b_convs = set(
            r[0]
            for r in self._s.execute(
                select(ConversationParticipant.conversation_id).where(
                    ConversationParticipant.participant_type == "bot",
                    ConversationParticipant.participant_id == bot_b_id,
                )
            ).fetchall()
        )
        shared = a_convs & b_convs
        if shared:
            conv_id = next(iter(shared))
            conv = self._s.get(Conversation, conv_id)
            if conv and conv.type == "dm":
                return conv

        # Create a new DM conversation
        conv = Conversation(
            workspace_id=workspace_id,
            type="dm",
            created_by_type="bot",
            created_by_id=bot_a_id,
        )
        self._s.add(conv)
        self._s.flush()
        for bot_id in (bot_a_id, bot_b_id):
            self._s.add(
                ConversationParticipant(
                    conversation_id=conv.id,
                    participant_type="bot",
                    participant_id=bot_id,
                    role="member",
                )
            )
        self._s.commit()
        self._s.refresh(conv)
        return conv

    def send_bot_message(
        self,
        workspace_id: uuid.UUID,
        sender_bot_id: uuid.UUID,
        conversation_id: uuid.UUID,
        recipient_bot_id: uuid.UUID,
        content: str,
        run_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        priority: int = 5,
        source_type: str = "dm",
    ) -> tuple[Message, MessageDelivery, BotInboxItem]:
        """Persist a Bot message, delivery record, and inbox item."""
        structured: dict[str, Any] = {}
        if run_id:
            structured["run_id"] = str(run_id)
        if task_id:
            structured["task_id"] = str(task_id)

        msg = Message(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            sender_type="bot",
            sender_id=sender_bot_id,
            kind="text",
            text_content=content,
            structured_content=structured,
        )
        self._s.add(msg)
        self._s.flush()

        delivery_key = f"{msg.id}:bot:{recipient_bot_id}"
        existing_delivery = self._s.scalars(
            select(MessageDelivery).where(MessageDelivery.delivery_key == delivery_key)
        ).first()
        if existing_delivery:
            delivery = existing_delivery
        else:
            delivery = MessageDelivery(
                message_id=msg.id,
                recipient_type="bot",
                recipient_id=recipient_bot_id,
                delivery_key=delivery_key,
                wake_requested=True,
            )
            self._s.add(delivery)
            self._s.flush()

        # Idempotent inbox item
        existing_inbox = self._s.scalars(
            select(BotInboxItem).where(
                BotInboxItem.bot_id == recipient_bot_id,
                BotInboxItem.source_type == source_type,
                BotInboxItem.source_id == msg.id,
            )
        ).first()
        if existing_inbox:
            inbox_item = existing_inbox
        else:
            inbox_item = BotInboxItem(
                workspace_id=workspace_id,
                bot_id=recipient_bot_id,
                source_type=source_type,
                source_id=msg.id,
                priority=priority,
            )
            self._s.add(inbox_item)
            self._s.flush()

        self._s.commit()
        return msg, delivery, inbox_item

    def create_delegation_atomic(
        self,
        workspace_id: uuid.UUID,
        requester_bot_id: uuid.UUID,
        assignee_bot_id: uuid.UUID,
        title: str,
        description: str = "",
        requester_run_id: uuid.UUID | None = None,
        hop_depth: int = 1,
        correlation_id: uuid.UUID | None = None,
    ) -> tuple[Task, Delegation, Message, MessageDelivery, BotInboxItem]:
        """Create task + delegation + handoff DM message + inbox item atomically.

        Caller must emit grokbot/delegation.created after commit.
        """
        if hop_depth > MAX_HOP_DEPTH:
            raise ValueError(f"Delegation hop_depth {hop_depth} exceeds limit {MAX_HOP_DEPTH}")
        corr_id = correlation_id or uuid.uuid4()
        # Idempotency: return existing if correlation_id matches
        existing_d = self._delegations.get_by_correlation(corr_id)
        if existing_d:
            existing_t = self._tasks.get(existing_d.task_id)
            # Find existing handoff message
            existing_msg = self._s.scalars(
                select(Message).where(
                    Message.structured_content["delegation_id"].astext == str(existing_d.id)
                )
            ).first()
            if existing_t and existing_msg:
                existing_del = self._s.scalars(
                    select(MessageDelivery).where(
                        MessageDelivery.message_id == existing_msg.id,
                        MessageDelivery.recipient_type == "bot",
                        MessageDelivery.recipient_id == assignee_bot_id,
                    )
                ).first()
                existing_inbox = self._s.scalars(
                    select(BotInboxItem).where(
                        BotInboxItem.source_type == "delegation",
                        BotInboxItem.source_id == existing_d.id,
                        BotInboxItem.bot_id == assignee_bot_id,
                    )
                ).first()
                if existing_del and existing_inbox:
                    return existing_t, existing_d, existing_msg, existing_del, existing_inbox

        task = self._tasks.create(
            workspace_id=workspace_id,
            title=title,
            description=description,
            created_by_type="bot",
            created_by_id=requester_bot_id,
            assigned_to_type="bot",
            assigned_to_id=assignee_bot_id,
        )
        delegation = self._delegations.create(
            workspace_id=workspace_id,
            task_id=task.id,
            requester_bot_id=requester_bot_id,
            assignee_bot_id=assignee_bot_id,
            hop_depth=hop_depth,
            requester_run_id=requester_run_id,
            correlation_id=corr_id,
        )
        dm_conv = self.create_or_get_bot_dm(workspace_id, requester_bot_id, assignee_bot_id)
        handoff_content = f"**Task delegated:** {title}\n\n{description}".strip()
        msg = Message(
            workspace_id=workspace_id,
            conversation_id=dm_conv.id,
            sender_type="bot",
            sender_id=requester_bot_id,
            kind="delegation",
            text_content=handoff_content,
            structured_content={
                "delegation_id": str(delegation.id),
                "task_id": str(task.id),
                "requester_run_id": str(requester_run_id) if requester_run_id else None,
            },
        )
        self._s.add(msg)
        self._s.flush()
        delegation.result_message_id = msg.id
        delivery_key = f"delegation:{delegation.id}:bot:{assignee_bot_id}"
        existing_del = self._s.scalars(
            select(MessageDelivery).where(MessageDelivery.delivery_key == delivery_key)
        ).first()
        if existing_del:
            delivery = existing_del
        else:
            delivery = MessageDelivery(
                message_id=msg.id,
                recipient_type="bot",
                recipient_id=assignee_bot_id,
                delivery_key=delivery_key,
                wake_requested=True,
            )
            self._s.add(delivery)
            self._s.flush()

        existing_inbox = self._s.scalars(
            select(BotInboxItem).where(
                BotInboxItem.bot_id == assignee_bot_id,
                BotInboxItem.source_type == "delegation",
                BotInboxItem.source_id == delegation.id,
            )
        ).first()
        if existing_inbox:
            inbox_item = existing_inbox
        else:
            inbox_item = BotInboxItem(
                workspace_id=workspace_id,
                bot_id=assignee_bot_id,
                source_type="delegation",
                source_id=delegation.id,
                priority=7,  # delegation > group (5) > routine (3)
            )
            self._s.add(inbox_item)
            self._s.flush()

        self._s.commit()
        return task, delegation, msg, delivery, inbox_item

    def complete_delegation(
        self,
        delegation_id: uuid.UUID,
        result: dict[str, Any],
        completing_run_id: uuid.UUID,
        requester_resume_priority: int = 9,
    ) -> Delegation:
        """Complete a delegation idempotently and create requester resume inbox item."""
        delegation = self._delegations.get_required(delegation_id)
        if delegation.status == "completed":
            return delegation  # idempotent

        # Update delegation and task
        delegation.status = "completed"
        delegation.completed_at = datetime.now(UTC)
        task = self._tasks.get(delegation.task_id)
        if task:
            self._tasks.update(task, status="completed", completed_at=datetime.now(UTC))

        # Persist result message in the DM
        dm_conv = self.create_or_get_bot_dm(
            delegation.workspace_id, delegation.requester_bot_id, delegation.assignee_bot_id
        )
        result_text = result.get("summary", result.get("result", "Task completed."))
        result_msg = Message(
            workspace_id=delegation.workspace_id,
            conversation_id=dm_conv.id,
            sender_type="bot",
            sender_id=delegation.assignee_bot_id,
            kind="delegation",
            text_content=str(result_text),
            structured_content={
                "delegation_id": str(delegation_id),
                "result": result,
                "completing_run_id": str(completing_run_id),
            },
        )
        self._s.add(result_msg)
        self._s.flush()

        # Create resume inbox item for requester
        if delegation.requester_run_id:
            existing_resume = self._s.scalars(
                select(BotInboxItem).where(
                    BotInboxItem.bot_id == delegation.requester_bot_id,
                    BotInboxItem.source_type == "resume",
                    BotInboxItem.source_id == delegation_id,
                )
            ).first()
            if not existing_resume:
                inbox_item = BotInboxItem(
                    workspace_id=delegation.workspace_id,
                    bot_id=delegation.requester_bot_id,
                    source_type="resume",
                    source_id=delegation_id,
                    priority=requester_resume_priority,
                )
                self._s.add(inbox_item)
                self._s.flush()

        self._s.commit()
        return delegation

    def get_bot_inbox(
        self,
        bot_id: uuid.UUID,
        status: str = "pending",
        limit: int = 20,
    ) -> list[BotInboxItem]:
        return list(
            self._s.scalars(
                select(BotInboxItem)
                .where(BotInboxItem.bot_id == bot_id, BotInboxItem.status == status)
                .order_by(BotInboxItem.priority.desc(), BotInboxItem.available_at)
                .limit(limit)
            )
        )

    # ── Group management ────────────────────────────────────────────────────

    def create_group_conversation(
        self,
        workspace_id: uuid.UUID,
        title: str,
        topic: str | None = None,
        member_bot_ids: list[uuid.UUID] | None = None,
        coordinator_bot_id: uuid.UUID | None = None,
        autonomy_policy: dict[str, Any] | None = None,
        created_by_id: uuid.UUID | None = None,
    ) -> tuple[Conversation, Group]:
        """Create a group conversation with a Group record."""
        conv = Conversation(
            workspace_id=workspace_id,
            type="group",
            title=title,
            created_by_type="user" if created_by_id else "system",
            created_by_id=created_by_id,
        )
        self._s.add(conv)
        self._s.flush()
        for bot_id in member_bot_ids or []:
            self._s.add(
                ConversationParticipant(
                    conversation_id=conv.id,
                    participant_type="bot",
                    participant_id=bot_id,
                    role="member",
                )
            )
        group = Group(
            conversation_id=conv.id,
            topic=topic,
            autonomy_policy=autonomy_policy or {},
        )
        # Set coordinator and title if columns exist (migration 0016)
        with suppress(Exception):
            group.coordinator_bot_id = coordinator_bot_id
            group.title = title
        self._s.add(group)
        self._s.commit()
        self._s.refresh(conv)
        return conv, group

    def get_group_members(self, conversation_id: uuid.UUID) -> list[ConversationParticipant]:
        return list(
            self._s.scalars(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == conversation_id
                )
            )
        )

    def add_group_member(
        self,
        conversation_id: uuid.UUID,
        participant_type: str,
        participant_id: uuid.UUID,
        role: str = "member",
    ) -> ConversationParticipant:
        existing = self._s.get(
            ConversationParticipant, (conversation_id, participant_type, participant_id)
        )
        if existing:
            return existing
        p = ConversationParticipant(
            conversation_id=conversation_id,
            participant_type=participant_type,
            participant_id=participant_id,
            role=role,
        )
        self._s.add(p)
        self._s.commit()
        return p

    def remove_group_member(
        self,
        conversation_id: uuid.UUID,
        participant_type: str,
        participant_id: uuid.UUID,
    ) -> None:
        existing = self._s.get(
            ConversationParticipant, (conversation_id, participant_type, participant_id)
        )
        if existing:
            self._s.delete(existing)
            self._s.commit()


# ── Group Dispatcher ─────────────────────────────────────────────────────


class GroupDispatcher:
    """Resolves mentions and creates deduplicated inbox items for group messages."""

    MAX_FANOUT = 5

    def __init__(self, session: Session) -> None:
        self._s = session

    def parse_mentions(self, text: str) -> list[str]:
        """Extract @token strings from message text."""
        return [m.group(1) for m in _MENTION_RE.finditer(text)]

    def persist_mentions(
        self,
        workspace_id: uuid.UUID,
        message: Message,
        mentions: list[str],
        bot_name_map: dict[str, uuid.UUID],
        coordinator_bot_id: uuid.UUID | None,
    ) -> list[MessageMention]:
        """Resolve @tokens to mention records and persist them."""
        created: list[MessageMention] = []
        for token in mentions:
            lower = token.lower()
            if lower == "everyone":
                m = MessageMention(
                    workspace_id=workspace_id,
                    message_id=message.id,
                    target_type="everyone",
                    token=f"@{token}",
                )
                self._s.add(m)
                created.append(m)
            elif lower == "coordinator":
                m = MessageMention(
                    workspace_id=workspace_id,
                    message_id=message.id,
                    target_type="coordinator",
                    target_id=coordinator_bot_id,
                    token=f"@{token}",
                )
                self._s.add(m)
                created.append(m)
            elif token in bot_name_map:
                m = MessageMention(
                    workspace_id=workspace_id,
                    message_id=message.id,
                    target_type="bot",
                    target_id=bot_name_map[token],
                    token=f"@{token}",
                )
                self._s.add(m)
                created.append(m)
        if created:
            self._s.flush()
        return created

    def dispatch(
        self,
        workspace_id: uuid.UUID,
        message: Message,
        group: Group,
        mention_tokens: list[str],
    ) -> list[BotInboxItem]:
        """Create deduplicated inbox items for selected recipients."""
        # Build bot name map for this group
        bot_members = list(
            self._s.execute(
                select(ConversationParticipant.participant_id, Bot.name)
                .join(Bot, Bot.id == ConversationParticipant.participant_id)
                .where(
                    ConversationParticipant.conversation_id == group.conversation_id,
                    ConversationParticipant.participant_type == "bot",
                    Bot.lifecycle_status == "active",
                )
            ).fetchall()
        )
        bot_name_map: dict[str, uuid.UUID] = {row[1]: row[0] for row in bot_members}
        all_bot_ids: list[uuid.UUID] = [row[0] for row in bot_members]
        coordinator_bot_id: uuid.UUID | None = getattr(group, "coordinator_bot_id", None)

        # Persist mention records
        self.persist_mentions(
            workspace_id, message, mention_tokens, bot_name_map, coordinator_bot_id
        )

        # Determine which bots to wake
        selected: list[uuid.UUID] = []
        lower_tokens = {t.lower() for t in mention_tokens}
        if "everyone" in lower_tokens:
            selected = all_bot_ids[: self.MAX_FANOUT]
        else:
            for token in mention_tokens:
                if token.lower() == "coordinator" and coordinator_bot_id:
                    if coordinator_bot_id not in selected:
                        selected.append(coordinator_bot_id)
                elif token in bot_name_map:
                    bid = bot_name_map[token]
                    if bid not in selected:
                        selected.append(bid)
            if not selected and coordinator_bot_id:
                selected = [coordinator_bot_id]

        # Get or create group round
        active_round = self._s.scalars(
            select(GroupRound).where(
                GroupRound.conversation_id == group.conversation_id,
                GroupRound.status == "active",
            )
        ).first()
        if active_round:
            # Check limits
            if active_round.message_count >= active_round.max_messages:
                active_round.status = "limit_reached"
                active_round.stop_reason = "max_messages"
                active_round.ended_at = datetime.now(UTC)
                self._s.flush()
                selected = []
            else:
                active_round.message_count += 1
                self._s.flush()
        else:
            last_round = self._s.scalars(
                select(GroupRound)
                .where(GroupRound.conversation_id == group.conversation_id)
                .order_by(GroupRound.round_no.desc())
                .limit(1)
            ).first()
            next_no = (last_round.round_no + 1) if last_round else 1
            active_round = GroupRound(
                workspace_id=workspace_id,
                conversation_id=group.conversation_id,
                trigger_message_id=message.id,
                round_no=next_no,
                message_count=1,
            )
            self._s.add(active_round)
            self._s.flush()

        inbox_items: list[BotInboxItem] = []
        for bot_id in selected[: self.MAX_FANOUT]:
            existing = self._s.scalars(
                select(BotInboxItem).where(
                    BotInboxItem.bot_id == bot_id,
                    BotInboxItem.source_type == "mention",
                    BotInboxItem.source_id == message.id,
                )
            ).first()
            if existing:
                inbox_items.append(existing)
                continue
            item = BotInboxItem(
                workspace_id=workspace_id,
                bot_id=bot_id,
                source_type="mention",
                source_id=message.id,
                priority=5,
            )
            self._s.add(item)
            inbox_items.append(item)

        if inbox_items:
            self._s.flush()
        self._s.commit()
        return inbox_items

    def autocomplete_mentions(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID, query: str
    ) -> list[dict[str, Any]]:
        """Return @autocomplete suggestions: Bot names + @everyone + @coordinator."""
        bots = list(
            self._s.execute(
                select(Bot.id, Bot.name)
                .join(ConversationParticipant, ConversationParticipant.participant_id == Bot.id)
                .where(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.participant_type == "bot",
                    Bot.lifecycle_status == "active",
                )
            ).fetchall()
        )
        lower_q = query.lower()
        results: list[dict[str, Any]] = []
        for bot_id, name in bots:
            if lower_q in name.lower():
                results.append(
                    {"token": f"@{name}", "type": "bot", "id": str(bot_id), "name": name}
                )
        for special in ["everyone", "coordinator"]:
            if lower_q in special:
                results.append({"token": f"@{special}", "type": special})
        return results


# ── Bot creation requests ────────────────────────────────────────────────


class BotCreationPolicy:
    """Evaluate whether a parent bot may create a persistent child bot."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def evaluate(
        self,
        parent: Bot,
        child_name: str,
        child_system_instructions: str,
    ) -> str:
        """Return allowed policy mode: 'allow', 'ask', or raise PolicyDeniedError."""
        if parent.lifecycle_status != "active":
            raise PolicyDeniedError("Parent bot is not active")
        mode: str = str((parent.tool_policy or {}).get("bot_creation", "ask"))
        if mode == "deny":
            raise PolicyDeniedError("Bot creation is denied by policy")
        if mode not in ("allow", "ask"):
            raise PolicyDeniedError(f"Unknown bot_creation policy mode: {mode!r}")
        if not child_name.strip():
            raise PolicyDeniedError("Child bot name must not be blank")
        if len(child_name) > 80:
            raise PolicyDeniedError("Child bot name too long")
        if len(child_system_instructions) > 12000:
            raise PolicyDeniedError("Child system instructions too long")
        # Check max direct children
        active_children = self._s.execute(
            select(func.count(Bot.id)).where(
                Bot.creator_bot_id == parent.id,
                Bot.lifecycle_status == "active",
            )
        ).scalar_one()
        if active_children >= MAX_DIRECT_CHILDREN:
            raise PolicyDeniedError(
                f"Parent has {active_children} children (limit {MAX_DIRECT_CHILDREN})"
            )
        # Check depth: parent must not itself be a child bot (depth 1 limit)
        if parent.creator_bot_id is not None:
            raise PolicyDeniedError(
                "Hierarchy depth limit: a child bot cannot create further children"
            )
        return mode


class ChildBotRequestRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, request_id: uuid.UUID) -> BotCreationRequest | None:
        return self._s.get(BotCreationRequest, request_id)

    def get_required(self, request_id: uuid.UUID) -> BotCreationRequest:
        r = self.get(request_id)
        if r is None:
            raise KeyError(f"BotCreationRequest {request_id} not found")
        return r

    def get_by_idempotency(
        self, workspace_id: uuid.UUID, idempotency_key: str
    ) -> BotCreationRequest | None:
        return self._s.scalars(
            select(BotCreationRequest).where(
                BotCreationRequest.workspace_id == workspace_id,
                BotCreationRequest.idempotency_key == idempotency_key,
            )
        ).first()

    def list_for_parent(self, parent_bot_id: uuid.UUID) -> list[BotCreationRequest]:
        return list(
            self._s.scalars(
                select(BotCreationRequest)
                .where(BotCreationRequest.parent_bot_id == parent_bot_id)
                .order_by(BotCreationRequest.created_at.desc())
            )
        )


class ChildBotService:
    def __init__(self, session: Session) -> None:
        self._s = session
        self._policy = BotCreationPolicy(session)
        self._repo = ChildBotRequestRepository(session)

    def request_create(
        self,
        workspace_id: uuid.UUID,
        parent_bot_id: uuid.UUID,
        idempotency_key: str,
        child_name: str,
        child_system_instructions: str = "",
        child_role_title: str | None = None,
        child_description: str | None = None,
        requested_relationship_label: str | None = None,
        starter_config: dict[str, Any] | None = None,
        requested_by_run_id: uuid.UUID | None = None,
    ) -> tuple[BotCreationRequest, str]:
        """Create a creation request and return (request, policy_mode)."""
        # Idempotency check
        existing = self._repo.get_by_idempotency(workspace_id, idempotency_key)
        if existing:
            mode = (self._s.get(Bot, existing.parent_bot_id) or Bot()).tool_policy.get(
                "bot_creation", "ask"
            )
            return existing, mode

        parent = self._s.get(Bot, parent_bot_id)
        if parent is None or parent.workspace_id != workspace_id:
            raise KeyError("Parent bot not found")
        mode = self._policy.evaluate(parent, child_name, child_system_instructions)

        status = "awaiting_approval" if mode == "ask" else "approved"
        req = BotCreationRequest(
            workspace_id=workspace_id,
            parent_bot_id=parent_bot_id,
            requested_by_run_id=requested_by_run_id,
            idempotency_key=idempotency_key,
            child_name=child_name.strip(),
            child_role_title=child_role_title,
            child_description=child_description,
            child_system_instructions=child_system_instructions,
            requested_relationship_label=requested_relationship_label,
            starter_config=starter_config or {},
            status=status,
        )
        self._s.add(req)
        self._s.commit()
        self._s.refresh(req)
        return req, mode

    def approve(self, request_id: uuid.UUID, reason: str | None = None) -> BotCreationRequest:
        req = self._repo.get_required(request_id)
        if req.status not in ("requested", "awaiting_approval"):
            raise ValueError(f"Cannot approve request in status {req.status!r}")
        req.status = "approved"
        req.decision_reason = reason
        req.updated_at = datetime.now(UTC)
        self._s.commit()
        self._s.refresh(req)
        return req

    def deny(self, request_id: uuid.UUID, reason: str | None = None) -> BotCreationRequest:
        req = self._repo.get_required(request_id)
        if req.status not in ("requested", "awaiting_approval"):
            raise ValueError(f"Cannot deny request in status {req.status!r}")
        req.status = "denied"
        req.decision_reason = reason
        req.updated_at = datetime.now(UTC)
        self._s.commit()
        self._s.refresh(req)
        return req

    def materialize_child(self, request_id: uuid.UUID) -> tuple[BotCreationRequest, Bot]:
        """Idempotently create the child Bot from an approved request."""
        req = self._repo.get_required(request_id)
        if req.created_bot_id is not None:
            child = self._s.get(Bot, req.created_bot_id)
            if child:
                return req, child
        if req.status != "approved":
            raise ValueError(f"Request must be approved before materialization, got {req.status!r}")

        parent = self._s.get(Bot, req.parent_bot_id)
        if parent is None:
            raise KeyError("Parent bot not found")

        child = Bot(
            workspace_id=req.workspace_id,
            creator_bot_id=req.parent_bot_id,
            name=req.child_name,
            role_title=req.child_role_title,
            description=req.child_description,
            system_instructions=req.child_system_instructions,
            avatar_type="emoji",
            avatar_value="✦",
        )
        self._s.add(child)
        self._s.flush()

        # Record relationship
        rel_type = req.requested_relationship_label or "created"
        valid_types = {"created", "manages", "reports_to", "peer", "specialist_for"}
        if rel_type not in valid_types:
            rel_type = "created"
        rel = BotRelationship(
            workspace_id=req.workspace_id,
            from_bot_id=req.parent_bot_id,
            to_bot_id=child.id,
            relationship_type=rel_type,
        )
        self._s.add(rel)

        req.status = "created"
        req.created_bot_id = child.id
        req.updated_at = datetime.now(UTC)
        self._s.commit()
        self._s.refresh(req)
        self._s.refresh(child)
        return req, child

    def list_requests(self, parent_bot_id: uuid.UUID) -> list[BotCreationRequest]:
        return self._repo.list_for_parent(parent_bot_id)
