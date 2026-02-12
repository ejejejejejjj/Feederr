from fastapi import APIRouter, Depends
from app.dependencies import get_auth_manager
from app.config import settings
from app.indexer_config import indexer_config
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": "1.0.0"
    }


@router.get("/status")
async def status_check(auth_manager=Depends(get_auth_manager)):
    """Detailed status of all indexers (enabled and disabled)"""
    status = {
        "name": settings.app_name,
        "version": "1.0.0",
        "status": "running",
        "indexers": {}
    }
    
    # Mostrar TODOS los indexers, no solo los enabled
    for indexer_id, config in indexer_config.get_all_indexers().items():
        indexer_status = await auth_manager.check_session_status(indexer_id)
        status["indexers"][indexer_id] = {
            "enabled": config.get("enabled", False),
            "authenticated": indexer_status.get("authenticated", False),
            "last_check": indexer_status.get("last_check"),
            "url": config.get("url")
        }
    
    return status
