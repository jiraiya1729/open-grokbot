from fastapi import APIRouter, Depends

from app.api.dependencies import local_context
from app.api.routes.automation import integrations, routines, webhooks
from app.api.routes.bots import bots, lifecycle, skills, teaching, templates
from app.api.routes.chat import collaboration, conversations, notifications, runs
from app.api.routes.computer import computers, files, safety
from app.api.routes.knowledge import memories, search
from app.api.routes.system import recovery, usage
from app.core.context import RequestContext
from app.domain.schemas import LocalContext

router = APIRouter(prefix="/api/v1")
router.include_router(bots.router)
router.include_router(conversations.router)
router.include_router(runs.router)
router.include_router(files.router)
router.include_router(computers.router)
router.include_router(safety.router)
router.include_router(memories.router)
router.include_router(skills.router)
router.include_router(routines.router)
router.include_router(notifications.router)
router.include_router(collaboration.router)
router.include_router(templates.router)
router.include_router(integrations.router)
router.include_router(webhooks.router)
router.include_router(search.router)
router.include_router(teaching.router)
router.include_router(usage.router)
router.include_router(recovery.router)
router.include_router(lifecycle.router)


@router.get("/context", response_model=LocalContext, tags=["local-mode"])
def get_context(ctx: RequestContext = Depends(local_context)) -> LocalContext:
    return LocalContext(**ctx.__dict__)
