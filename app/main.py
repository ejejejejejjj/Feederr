from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from app.config import settings, BASE_DIR
from app.indexer_config import indexer_config
from app.api import torznab, indexers, health, download
from app.web import ui
from app.auth import AuthManager
from app.dependencies import set_auth_manager
from app.session_scheduler import get_session_scheduler

# Configure logging
log_dir = BASE_DIR / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "app.log"

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler(log_file, mode='a')  # File output
    ]
)
logger = logging.getLogger(__name__)

# Initialize auth manager
auth_manager = None
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global auth_manager, scheduler
    
    # Startup
    logger.info(f"Starting {settings.app_name}")
    auth_manager = AuthManager()
    set_auth_manager(auth_manager)  # Set global instance for dependencies
    
    # Initialize sessions ONLY for enabled indexers from indexers.json
    for indexer_id in indexer_config.get_enabled_indexers().keys():
        logger.info(f"Initializing {indexer_id} session")
        try:
            await auth_manager.ensure_session(indexer_id)
        except Exception as e:
            logger.error(f"Failed to initialize {indexer_id}: {e}")
    
    # Initialize session scheduler
    scheduler = get_session_scheduler(auth_manager, indexer_config)
    if scheduler:
        scheduler.start()
        logger.info("Session scheduler started - daily auto-renewal enabled")
    
    yield
    
    # Shutdown
    logger.info("Shutting down")
    
    # Stop scheduler
    if scheduler:
        await scheduler.stop()
        logger.info("Session scheduler stopped")
    
    # Close auth manager
    await auth_manager.close()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Bridge between Sonarr/Radarr/Prowlarr and Unit3D indexers",
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "defaultModelsExpandDepth": -1
    }
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(torznab.router, prefix="/api/v1", tags=["torznab"])
app.include_router(download.router, prefix="/api/v1", tags=["download"])
app.include_router(indexers.router, prefix="/api/indexers", tags=["indexers"])
app.include_router(ui.router, prefix="", tags=["ui"])


@app.get("/")
async def root():
    """Root endpoint - redirect to home"""
    return RedirectResponse(url="/home")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
