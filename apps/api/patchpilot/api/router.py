from fastapi import APIRouter

from patchpilot.api import channels, decisions, health, repositories, tasks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(repositories.router)
api_router.include_router(tasks.router)
api_router.include_router(decisions.router)
api_router.include_router(channels.router)
