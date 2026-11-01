import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from backend.config import APP_TITLE, APP_VERSION
from backend.database import engine, Base, SessionLocal
from backend.services import get_or_create_settings
from backend.routers import (
    overview,
    analytics,
    forecasting,
    recommendations,
    buildings,
    readings,
    quality,
    reports,
    settings,
    alerts,
    seed_router,
)

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    Base.metadata.create_all(bind=engine)
    # Ensure default settings row exists
    db = SessionLocal()
    try:
        get_or_create_settings(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="Backend API and Database for CampusWatt - Campus Energy Load Forecasting and Peak Reduction System",
    lifespan=lifespan,
)

# Enable CORS for all origins so that frontend served from file:// or any local port works
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers under /api
app.include_router(overview.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(forecasting.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(buildings.router, prefix="/api")
app.include_router(readings.router, prefix="/api")
app.include_router(quality.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(seed_router.router, prefix="/api")


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok", "app": APP_TITLE, "version": APP_VERSION}


# Serve frontend directly from backend server if accessed via browser
@app.get("/", include_in_schema=False)
def index_redirect():
    frtnd_path = BASE_DIR / "frtnd.html"
    if frtnd_path.exists():
        return FileResponse(str(frtnd_path))
    return RedirectResponse(url="/docs")


@app.get("/frtnd.html", include_in_schema=False)
def serve_frtnd():
    frtnd_path = BASE_DIR / "frtnd.html"
    return FileResponse(str(frtnd_path))
