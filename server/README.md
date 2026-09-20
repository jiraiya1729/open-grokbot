# Open-GrokBot API

FastAPI control plane and durable Bot runtime.

## Architecture

- `app/api/` owns FastAPI transport. `router.py` composes routes, `dependencies.py` holds shared request dependencies, and `routes/` groups endpoint modules by product area (`bots`, `chat`, `computer`, `knowledge`, `automation`, and `system`).
- `app/agents/` owns LangGraph state/graph/runtime orchestration and the explicit run state machine.
- `app/core/` owns configuration, database/session setup, request context, and typed product-event contracts.
- `app/domain/` owns SQLAlchemy product models, API schemas, and workspace-scoped repositories. LangGraph keeps checkpoint tables in the separate `langgraph` schema.
- `app/infrastructure/` owns replaceable BlobStore, computer, embedding, and model-provider adapters.
- `app/services/` owns product capabilities such as collaboration, memory, skills, routines, integrations, lifecycle, recovery, teaching, templates, usage, and webhooks.
- `app/tools/` owns the safety-policy and Tool Gateway boundary, including approvals, audit, idempotent actions, and computer leases.
- `app/main.py` is the single API entry point. Imports use the package paths above; duplicate root-level forwarding modules have been removed.
- `alembic/` contains schema migrations. Never create product schema from test setup.

PostgreSQL stores product truth. Inngest schedules durable work. LangGraph defines one Bot run. Blob storage owns bytes, while logical computer workspaces survive disposable sandbox sessions. These identities are intentionally separate.

## Run locally

For the supported local stack, start services from the repository root; migrations run in the API container against the Compose PostgreSQL host:

```bash
docker compose up -d --build
docker compose exec api .venv/bin/alembic upgrade head
```

For an API process on the host, set `DATABASE_URL` to `postgresql+psycopg://grokbot:grokbot@localhost:5432/grokbot` before invoking Alembic or Uvicorn. The API container must never mount the Docker socket.

## Quality gates

```bash
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app computer_daemon
uv run pytest
```

Tests use a separate `grokbot_test` database by default, apply the real migration, and cover domain rules, database constraints, API behavior, BlobStore safety, file authorization, computer lifecycle, takeover fencing, approval tamper rejection, ambiguous side-effect replay, audit redaction, tool normalization, artifact export, checkpoint persistence, event ordering, cancellation, and workspace isolation.

Tests are grouped under `tests/agents`, `tests/api`, `tests/collaboration`, `tests/computer`, `tests/core`, and `tests/services`. Shared fixtures live in `tests/conftest.py`; reusable HTTP setup lives in `tests/factories.py`. Run `uv run pytest` to discover every group.
