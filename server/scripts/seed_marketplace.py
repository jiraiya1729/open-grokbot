"""Seed curated marketplace templates.

Run with: uv run python scripts/seed_marketplace.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.services.templates import TemplateRepository, TemplateService

CURATED_TEMPLATES = [
    {
        "name": "Research Assistant",
        "description": "A Bot for deep research tasks: gathering sources, summarising findings, and producing structured reports.",
        "category": "research",
        "tags": ["research", "summarise", "analysis"],
        "featured": True,
        "ranking_weight": 5.0,
        "instructions": "You are a thorough research assistant. When given a topic, gather information methodically, evaluate sources critically, and produce clear structured summaries with citations.",
    },
    {
        "name": "Code Reviewer",
        "description": "Performs detailed code reviews: correctness, security, style, and maintainability.",
        "category": "code",
        "tags": ["code-review", "security", "engineering"],
        "featured": True,
        "ranking_weight": 4.5,
        "instructions": "You are a senior code reviewer. Analyse code for correctness, security vulnerabilities, style issues, and maintainability. Provide actionable, specific feedback with examples.",
    },
    {
        "name": "Writing Assistant",
        "description": "Helps draft, edit, and refine written content — emails, documents, proposals, and more.",
        "category": "writing",
        "tags": ["writing", "editing", "content"],
        "featured": False,
        "ranking_weight": 4.0,
        "instructions": "You are a skilled writing assistant. Help users draft and refine written content. Match the requested tone and format. Offer concrete improvements rather than vague suggestions.",
    },
    {
        "name": "Personal Planner",
        "description": "Organises tasks, sets priorities, and tracks progress on personal and professional goals.",
        "category": "planning",
        "tags": ["planning", "productivity", "goals"],
        "featured": False,
        "ranking_weight": 3.5,
        "instructions": "You are a helpful personal planner. Help users break down goals into actionable tasks, set realistic deadlines, and track progress. Be encouraging and practical.",
    },
    {
        "name": "Data Analyst",
        "description": "Explores data, identifies patterns, and produces clear analytical insights.",
        "category": "data",
        "tags": ["data", "analysis", "insights"],
        "featured": False,
        "ranking_weight": 3.0,
        "instructions": "You are a data analyst. When given datasets or data descriptions, identify key patterns and anomalies, compute relevant statistics, and explain findings clearly in plain language.",
    },
]


def main() -> None:
    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)

        for spec in CURATED_TEMPLATES:
            # Check if already seeded
            existing = repo.search_marketplace(query=spec["name"])
            if any(t.name == spec["name"] for t, _ in existing):
                print(f"Already seeded: {spec['name']}")
                continue

            template = repo.create(
                workspace_id=None,
                owner_type="system",
                owner_id=None,
                name=spec["name"],
                description=spec["description"],
                visibility="curated",
                latest_version=1,
            )
            repo.create_version(
                template_id=template.id,
                version=1,
                manifest={"name": spec["name"], "role_title": spec["category"].title() + " Bot"},
                included_instructions=spec["instructions"],
                included_memory_ids=[],
                included_skill_versions=[],
                required_integrations=[],
                security_review={"passed": True, "redacted_fields": []},
            )
            repo.add_marketplace_entry(
                template_id=template.id,
                category=spec["category"],
                tags=spec["tags"],
                featured=spec["featured"],
                ranking_weight=spec["ranking_weight"],
            )
            print(f"Seeded: {spec['name']}")

    print("Done.")


if __name__ == "__main__":
    main()
