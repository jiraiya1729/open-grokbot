"""Skills repository and service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.domain.models import BotSkill, Skill, SkillVersion


class SkillRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create_skill(self, **kwargs: Any) -> Skill:
        sk = Skill(**kwargs)
        self._s.add(sk)
        self._s.commit()
        self._s.refresh(sk)
        return sk

    def get_skill(self, skill_id: uuid.UUID) -> Skill | None:
        return self._s.get(Skill, skill_id)

    def get_skill_required(self, skill_id: uuid.UUID) -> Skill:
        sk = self.get_skill(skill_id)
        if sk is None:
            raise KeyError(f"Skill {skill_id} not found")
        return sk

    def list_skills(
        self,
        workspace_id: uuid.UUID,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Skill], int]:
        base = select(Skill).where(Skill.workspace_id == workspace_id)
        if not include_archived:
            base = base.where(Skill.lifecycle_status != "archived")
        count_q = select(func.count()).select_from(base.subquery())
        total: int = self._s.execute(count_q).scalar_one()
        items = list(
            self._s.scalars(base.order_by(Skill.updated_at.desc()).limit(limit).offset(offset))
        )
        return items, total

    def update_skill(self, skill: Skill, **kwargs: Any) -> Skill:
        for k, v in kwargs.items():
            setattr(skill, k, v)
        self._s.commit()
        self._s.refresh(skill)
        return skill

    def create_skill_version(
        self, skill_id: uuid.UUID, version: int, **kwargs: Any
    ) -> SkillVersion:
        sv = SkillVersion(skill_id=skill_id, version=version, **kwargs)
        self._s.add(sv)
        self._s.commit()
        self._s.refresh(sv)
        return sv

    def get_skill_version(self, skill_id: uuid.UUID, version: int) -> SkillVersion | None:
        return self._s.scalars(
            select(SkillVersion).where(
                and_(SkillVersion.skill_id == skill_id, SkillVersion.version == version)
            )
        ).first()

    def list_skill_versions(self, skill_id: uuid.UUID) -> list[SkillVersion]:
        return list(
            self._s.scalars(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill_id)
                .order_by(SkillVersion.version.desc())
            )
        )

    def get_bot_skill(self, bot_id: uuid.UUID, skill_id: uuid.UUID) -> BotSkill | None:
        return self._s.get(BotSkill, (bot_id, skill_id))

    def list_bot_skills(self, bot_id: uuid.UUID) -> list[BotSkill]:
        return list(self._s.scalars(select(BotSkill).where(BotSkill.bot_id == bot_id)))

    def upsert_bot_skill(
        self,
        bot_id: uuid.UUID,
        skill_id: uuid.UUID,
        enabled: bool = True,
        pinned_version: int | None = None,
        config: dict[str, Any] | None = None,
    ) -> BotSkill:
        bs = self.get_bot_skill(bot_id, skill_id)
        if bs is None:
            bs = BotSkill(
                bot_id=bot_id,
                skill_id=skill_id,
                enabled=enabled,
                pinned_version=pinned_version,
                config=config or {},
            )
            self._s.add(bs)
        else:
            bs.enabled = enabled
            if pinned_version is not None:
                bs.pinned_version = pinned_version
            if config is not None:
                bs.config = config
        self._s.commit()
        self._s.refresh(bs)
        return bs

    def remove_bot_skill(self, bot_id: uuid.UUID, skill_id: uuid.UUID) -> None:
        bs = self.get_bot_skill(bot_id, skill_id)
        if bs:
            self._s.delete(bs)
            self._s.commit()


class SkillService:
    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    def create_skill(
        self,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        owner_type: str = "workspace",
        owner_id: uuid.UUID | None = None,
        steps: list[Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        trigger_conditions: dict[str, Any] | None = None,
        created_by_type: str | None = None,
        created_by_id: uuid.UUID | None = None,
    ) -> tuple[Skill, SkillVersion]:
        sk = self._repo.create_skill(
            workspace_id=workspace_id,
            name=name,
            description=description,
            owner_type=owner_type,
            owner_id=owner_id,
            latest_version=1,
        )
        sv = self._repo.create_skill_version(
            skill_id=sk.id,
            version=1,
            steps=steps or [],
            input_schema=input_schema,
            output_schema=output_schema,
            trigger_conditions=trigger_conditions,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
        )
        return sk, sv

    def add_version(
        self,
        skill_id: uuid.UUID,
        steps: list[Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        trigger_conditions: dict[str, Any] | None = None,
        decision_rules: dict[str, Any] | None = None,
        validation_rules: dict[str, Any] | None = None,
        required_tools: list[Any] | None = None,
        approval_requirements: dict[str, Any] | None = None,
        created_by_type: str | None = None,
        created_by_id: uuid.UUID | None = None,
    ) -> SkillVersion:
        sk = self._repo.get_skill_required(skill_id)
        new_version = sk.latest_version + 1
        sv = self._repo.create_skill_version(
            skill_id=skill_id,
            version=new_version,
            steps=steps or [],
            input_schema=input_schema,
            output_schema=output_schema,
            trigger_conditions=trigger_conditions,
            decision_rules=decision_rules,
            validation_rules=validation_rules,
            required_tools=required_tools,
            approval_requirements=approval_requirements,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
        )
        self._repo.update_skill(sk, latest_version=new_version)
        return sv

    def update_skill(self, skill_id: uuid.UUID, **kwargs: Any) -> Skill:
        sk = self._repo.get_skill_required(skill_id)
        return self._repo.update_skill(sk, **kwargs)

    def get_skill(self, skill_id: uuid.UUID) -> Skill:
        return self._repo.get_skill_required(skill_id)

    def list_skills(
        self,
        workspace_id: uuid.UUID,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Skill], int]:
        return self._repo.list_skills(workspace_id, include_archived, limit, offset)

    def list_versions(self, skill_id: uuid.UUID) -> list[SkillVersion]:
        return self._repo.list_skill_versions(skill_id)

    def get_version(self, skill_id: uuid.UUID, version: int) -> SkillVersion:
        sv = self._repo.get_skill_version(skill_id, version)
        if sv is None:
            raise KeyError(f"SkillVersion {skill_id}:{version} not found")
        return sv

    def enable_for_bot(
        self,
        bot_id: uuid.UUID,
        skill_id: uuid.UUID,
        pinned_version: int | None = None,
        config: dict[str, Any] | None = None,
    ) -> BotSkill:
        return self._repo.upsert_bot_skill(
            bot_id, skill_id, enabled=True, pinned_version=pinned_version, config=config
        )

    def disable_for_bot(self, bot_id: uuid.UUID, skill_id: uuid.UUID) -> BotSkill:
        return self._repo.upsert_bot_skill(bot_id, skill_id, enabled=False)

    def list_bot_skills(self, bot_id: uuid.UUID) -> list[BotSkill]:
        return self._repo.list_bot_skills(bot_id)
