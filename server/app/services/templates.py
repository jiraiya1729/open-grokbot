"""Template repository and service."""

from __future__ import annotations

import re
import uuid
from builtins import list as builtin_list
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    Bot,
    BotSkill,
    MarketplaceEntry,
    Memory,
    Skill,
    SkillVersion,
    Template,
    TemplateInstall,
    TemplateVersion,
)

_CREDENTIAL_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|credential|private_key|access_key|auth_key)",
    re.IGNORECASE,
)

_CURATED_TEMPLATES = (
    (
        "Research Assistant",
        "Finds, compares, and cites reliable information.",
        "research",
        ["research", "sources"],
        True,
    ),
    (
        "Code Reviewer",
        "Reviews code changes for correctness, safety, and clarity.",
        "code",
        ["code", "review"],
        True,
    ),
    (
        "Writing Assistant",
        "Helps draft and refine clear, useful writing.",
        "writing",
        ["writing", "editing"],
        False,
    ),
    (
        "Personal Planner",
        "Turns goals into practical, well-prioritized plans.",
        "planning",
        ["planning", "tasks"],
        False,
    ),
    (
        "Data Analyst",
        "Explores data and explains useful findings.",
        "data",
        ["data", "analysis"],
        False,
    ),
)


def ensure_curated_templates(session: Session) -> None:
    """Install the local Marketplace catalog once, without copying user data."""
    existing_names = set(
        session.scalars(select(Template.name).where(Template.visibility == "curated"))
    )
    changed = False
    for name, description, category, tags, featured in _CURATED_TEMPLATES:
        if name in existing_names:
            continue
        template = Template(
            workspace_id=None,
            owner_type="system",
            owner_id=None,
            name=name,
            description=description,
            visibility="curated",
            latest_version=1,
        )
        session.add(template)
        session.flush()
        session.add(
            TemplateVersion(
                template_id=template.id,
                version=1,
                manifest={
                    "name": name,
                    "role_title": name,
                    "description": description,
                    "avatar_value": "✦",
                },
                included_instructions=f"You are a {name}. {description}",
                included_memory_ids=[],
                included_skill_versions=[],
                required_integrations=[],
                security_review={"passed": True, "redacted_fields": []},
            )
        )
        session.add(
            MarketplaceEntry(
                template_id=template.id,
                category=category,
                tags=tags,
                featured=featured,
                ranking_weight=2.0 if featured else 1.0,
            )
        )
        changed = True
    if changed:
        session.commit()


class ImmutableError(ValueError):
    """Raised when a caller tries to mutate an immutable resource."""


def _redact_credentials(manifest: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in manifest.items() if not _CREDENTIAL_PATTERNS.search(k)}


class TemplateRepository:
    def __init__(self, s: Session) -> None:
        self._s = s

    def create(self, **kwargs: Any) -> Template:
        t = Template(**kwargs)
        self._s.add(t)
        self._s.commit()
        self._s.refresh(t)
        return t

    def create_version(self, **kwargs: Any) -> TemplateVersion:
        tv = TemplateVersion(**kwargs)
        self._s.add(tv)
        self._s.commit()
        self._s.refresh(tv)
        return tv

    def get(self, template_id: uuid.UUID) -> Template | None:
        return self._s.scalar(select(Template).where(Template.id == template_id))

    def list(self, workspace_id: uuid.UUID) -> list[Template]:
        return list(
            self._s.scalars(
                select(Template)
                .where((Template.workspace_id == workspace_id) | (Template.visibility == "curated"))
                .order_by(Template.created_at.desc())
            )
        )

    def get_version(self, template_id: uuid.UUID, version: int) -> TemplateVersion | None:
        return self._s.scalar(
            select(TemplateVersion).where(
                TemplateVersion.template_id == template_id,
                TemplateVersion.version == version,
            )
        )

    def update_version(self, version_id: uuid.UUID, **kwargs: Any) -> TemplateVersion:
        raise ImmutableError("Template versions are immutable after creation.")

    def list_installs(self, template_id: uuid.UUID) -> builtin_list[TemplateInstall]:
        return builtin_list(
            self._s.scalars(
                select(TemplateInstall).where(TemplateInstall.template_id == template_id)
            )
        )

    def add_marketplace_entry(self, **kwargs: Any) -> MarketplaceEntry:
        me = MarketplaceEntry(**kwargs)
        self._s.add(me)
        self._s.commit()
        self._s.refresh(me)
        return me

    def search_marketplace(
        self,
        query: str | None = None,
        category: str | None = None,
        featured: bool | None = None,
    ) -> builtin_list[tuple[Template, MarketplaceEntry]]:
        stmt = select(Template, MarketplaceEntry).join(
            MarketplaceEntry, MarketplaceEntry.template_id == Template.id
        )
        if category:
            stmt = stmt.where(MarketplaceEntry.category == category)
        if featured is not None:
            stmt = stmt.where(MarketplaceEntry.featured == featured)
        rows = cast(
            builtin_list[tuple[Template, MarketplaceEntry]],
            self._s.execute(stmt.order_by(MarketplaceEntry.ranking_weight.desc())).all(),
        )
        if query:
            q = query.lower()
            rows = [
                (t, me)
                for t, me in rows
                if q in (t.name or "").lower()
                or q in (t.description or "").lower()
                or any(q in tag.lower() for tag in (me.tags or []))
            ]
        return rows


class TemplateService:
    def __init__(self, repo: TemplateRepository, s: Session) -> None:
        self._repo = repo
        self._s = s

    def create_template_from_bot(
        self,
        bot_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        visibility: str,
        included_memory_ids: list[uuid.UUID] | None = None,
        included_skill_version_ids: list[uuid.UUID] | None = None,
        instructions_override: str | None = None,
    ) -> tuple[Template, TemplateVersion]:
        bot = self._s.get(Bot, bot_id)
        if bot is None:
            raise ValueError(f"Bot {bot_id} not found")

        manifest: dict[str, Any] = {
            "name": bot.name,
            "role_title": bot.role_title,
            "description": bot.description,
            "avatar_value": bot.avatar_value,
        }
        manifest = _redact_credentials(manifest)

        instructions = instructions_override or bot.system_instructions or ""

        safe_memory_ids: list[str] = []
        if included_memory_ids:
            for mid in included_memory_ids:
                mem = self._s.get(Memory, mid)
                if mem is not None and mem.scope_type in ("workspace", "bot"):
                    safe_memory_ids.append(str(mid))

        skill_versions_list: list[dict[str, Any]] = []
        if included_skill_version_ids:
            for svid in included_skill_version_ids:
                sv = self._s.get(SkillVersion, svid)
                if sv is not None:
                    skill = self._s.get(Skill, sv.skill_id)
                    skill_versions_list.append(
                        {
                            "skill_id": str(sv.skill_id),
                            "skill_name": skill.name if skill else None,
                            "version": sv.version,
                            "steps": sv.steps,
                        }
                    )

        template = self._repo.create(
            workspace_id=workspace_id,
            owner_type="user",
            owner_id=user_id,
            name=name,
            description=description,
            visibility=visibility,
            latest_version=1,
        )

        tv = self._repo.create_version(
            template_id=template.id,
            version=1,
            manifest=manifest,
            included_instructions=instructions,
            included_memory_ids=safe_memory_ids,
            included_skill_versions=skill_versions_list,
            required_integrations=[],
            security_review={"passed": True, "redacted_fields": []},
        )

        return template, tv

    def install_template(
        self,
        template_id: uuid.UUID,
        version: int,
        workspace_id: uuid.UUID,
        installed_by_user_id: uuid.UUID,
    ) -> tuple[Bot, TemplateInstall]:
        tv = self._repo.get_version(template_id, version)
        if tv is None:
            raise ValueError(f"Template version {template_id}@{version} not found")

        manifest = tv.manifest or {}
        new_bot = Bot(
            workspace_id=workspace_id,
            created_by_user_id=installed_by_user_id,
            name=manifest.get("name", "Installed Bot"),
            role_title=manifest.get("role_title"),
            description=manifest.get("description"),
            avatar_value=manifest.get("avatar_value"),
            system_instructions=tv.included_instructions or "",
            lifecycle_status="active",
        )
        self._s.add(new_bot)
        self._s.flush()

        for sv_info in tv.included_skill_versions or []:
            skill_id_str = sv_info.get("skill_id")
            if skill_id_str:
                try:
                    skill_id = uuid.UUID(skill_id_str)
                    self._s.add(BotSkill(bot_id=new_bot.id, skill_id=skill_id, enabled=True))
                except Exception:
                    pass

        self._s.flush()

        install = TemplateInstall(
            workspace_id=workspace_id,
            template_id=template_id,
            template_version=version,
            installed_bot_id=new_bot.id,
            installed_by_user_id=installed_by_user_id,
        )
        self._s.add(install)
        self._s.commit()
        self._s.refresh(new_bot)
        self._s.refresh(install)

        return new_bot, install

    def publish_to_marketplace(
        self,
        template_id: uuid.UUID,
        category: str,
        tags: list[str],
        featured: bool = False,
        ranking_weight: float = 1.0,
    ) -> MarketplaceEntry:
        tmpl = self._repo.get(template_id)
        if tmpl is None:
            raise ValueError(f"Template {template_id} not found")
        tmpl.visibility = "curated"
        self._s.flush()
        return self._repo.add_marketplace_entry(
            template_id=template_id,
            category=category,
            tags=tags,
            featured=featured,
            ranking_weight=ranking_weight,
        )

    def search_marketplace(
        self,
        query: str | None = None,
        category: str | None = None,
        featured: bool | None = None,
    ) -> list[tuple[Template, MarketplaceEntry]]:
        return self._repo.search_marketplace(query=query, category=category, featured=featured)
