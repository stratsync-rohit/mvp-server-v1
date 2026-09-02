import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from app.api.client import router as clients_router
from app.api.dashboard import router as dashboard_router
from app.api.industries import router as industries_router
from app.api.notifications import router as notifications_router
from app.api.risks import router as risks_router
from app.api.slack_destinations import router as slack_destinations_router
from app.api.slack_interactions import router as slack_interactions_router
from app.api.teams_channels import router as teams_channels_router

from app.config import get_settings
from app.database import close_mongo_connection, connect_to_mongo, get_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "Backend test for the MS teams(expandale)V1 notification integration system. "
        
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    async def health():
        try:
            database = get_database()
            con = await database.command("ping")

            print("Database Connected =", con)
            
        except (PyMongoError, RuntimeError):
            logger.exception("health_check_database_unavailable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            )

        return {"status": "ok", "database": "connected"}



    app.include_router(clients_router)
    app.include_router(teams_channels_router)
    app.include_router(slack_destinations_router)
    app.include_router(slack_interactions_router)
    app.include_router(industries_router)
    app.include_router(risks_router)
    app.include_router(notifications_router)
    app.include_router(dashboard_router)
    return app


app = create_app()
