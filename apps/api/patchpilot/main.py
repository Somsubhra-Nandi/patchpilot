from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from patchpilot.api.router import api_router
from patchpilot.caspian.runtime import get_gateway
from patchpilot.core.config import get_settings
from patchpilot.core.logging import configure_logging
from patchpilot.db.base import Base
from patchpilot.db.session import engine
from patchpilot.demo.seed import seed_database

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_schema:
        Base.metadata.create_all(engine)
    if settings.seed_demo_data:
        seed_database()
    if settings.caspian_enabled:
        get_gateway().start()
    yield
    gateway = get_gateway()
    if gateway.client:
        gateway.client.close()


app = FastAPI(
    title="PatchPilot API",
    version="0.1.0",
    description="Traceable maintainer workflows from issue intake to draft pull request.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.effective_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

