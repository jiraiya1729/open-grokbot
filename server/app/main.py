from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from inngest.fast_api import serve
from sqlalchemy import text

from app.agents.runtime import INNGEST_FUNCTIONS, inngest_client, recover_stranded_runs
from app.api import router
from app.core.config import get_settings
from app.core.context import ensure_local_context
from app.core.database import SessionLocal
from app.services.integrations import ensure_builtin_definitions
from app.services.templates import ensure_curated_templates

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with SessionLocal() as db:
        ensure_local_context(db, settings)
        ensure_builtin_definitions(db)
        ensure_curated_templates(db)
    recover_stranded_runs()
    # Run watchdog to recover stalled runs from previous sessions
    try:
        from app.services.recovery import RecoveryService

        with SessionLocal() as db:
            svc = RecoveryService(db)
            svc.watchdog_sweep()
    except Exception:
        pass  # Non-fatal: recovery is best-effort on startup
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok", "model_provider": settings.model_provider}


@app.get("/health/providers")
def provider_status() -> dict[str, object]:
    """Report status of optional providers for first-run diagnostics."""
    providers: dict[str, dict[str, str]] = {}

    # Database
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        providers["database"] = {"status": "ok"}
    except Exception as exc:
        providers["database"] = {"status": "error", "detail": str(exc)}

    # Model provider
    model_provider = settings.model_provider
    if model_provider == "bedrock":
        if not settings.bedrock_model_id:
            providers["model"] = {
                "status": "degraded",
                "provider": model_provider,
                "detail": "BEDROCK_MODEL_ID not configured",
            }
        else:
            providers["model"] = {"status": "ok", "provider": model_provider}
    elif model_provider == "deterministic":
        providers["model"] = {
            "status": "ok",
            "provider": model_provider,
            "detail": "deterministic test provider",
        }
    else:
        providers["model"] = {"status": "ok", "provider": model_provider}

    # Computer provider (optional)
    computer_provider = settings.computer_provider
    providers["computer"] = {"status": "ok", "provider": computer_provider}

    # Inngest
    providers["inngest"] = {"status": "ok", "url": settings.inngest_event_url}

    overall = "ok" if all(p["status"] == "ok" for p in providers.values()) else "degraded"
    return {"status": overall, "providers": providers}


@app.get("/health/detailed")
def detailed_health() -> dict[str, object]:
    """Detailed health for observability diagnostics."""
    return provider_status()


serve(
    app,
    inngest_client,
    INNGEST_FUNCTIONS,  # type: ignore[arg-type]
    serve_path="/api/inngest",
    enable_unauthed_sync=settings.environment != "production",
)
