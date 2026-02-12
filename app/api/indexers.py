from fastapi import APIRouter, HTTPException, Depends
from typing import List
import logging
import json
from pathlib import Path

from app.config import settings
from app.indexer_config import indexer_config
from app.models import SearchRequest, Torrent
from app.scrapers.unit3d import TorrentlandScraper, XBytesV2Scraper
from app.dependencies import get_auth_manager

router = APIRouter()
logger = logging.getLogger(__name__)

CONFIG_FILE = Path("/app/data/indexers_config.json")


def load_indexer_config(indexer_name: str) -> dict:
    """Load configuration for a specific indexer"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                all_config = json.load(f)
                return all_config.get(indexer_name, {})
    except Exception as e:
        logger.error(f"Failed to load config for {indexer_name}: {e}")
    return {}


@router.get("/list")
async def list_indexers():
    """List all configured indexers (enabled and disabled)"""
    indexers = []
    
    # Mostrar TODOS los indexers, no solo los enabled
    for indexer_id, config in indexer_config.get_all_indexers().items():
        indexers.append({
            "id": indexer_id,
            "name": config.get("name", indexer_id),
            "url": config.get("url"),
            "enabled": config.get("enabled", False)
        })
    
    return {"indexers": indexers}


@router.post("/{indexer}/search")
async def search_indexer(
    indexer: str,
    request: SearchRequest,
    auth_manager = Depends(get_auth_manager)
) -> List[Torrent]:
    """Search a specific indexer"""
    
    # Check if indexer exists
    indexer_cfg = indexer_config.get_indexer(indexer)
    if not indexer_cfg:
        raise HTTPException(status_code=404, detail=f"Indexer {indexer} not found")
    
    # Check if can search (enabled + within time restrictions)
    if not indexer_config.can_search(indexer):
        # Return empty results if disabled or outside time restrictions
        logger.info(f"Indexer {indexer} cannot search (disabled or outside time restrictions)")
        return []
    
    if indexer == "torrentland":
        scraper = TorrentlandScraper(auth_manager, indexer_cfg)
    elif indexer == "xbytesv2":
        scraper = XBytesV2Scraper(auth_manager, indexer_cfg)
    else:
        raise HTTPException(status_code=404, detail=f"Indexer {indexer} not found")
    
    try:
        torrents = await scraper.search(request)
        return torrents
    except Exception as e:
        logger.error(f"Search failed on {indexer}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{indexer}/refresh-session")
async def refresh_session(indexer: str, auth_manager = Depends(get_auth_manager)):
    """Force refresh authentication session for an indexer"""
    
    if indexer not in ["torrentland", "xbytesv2"]:
        raise HTTPException(status_code=404, detail=f"Indexer {indexer} not found")
    
    try:
        success = await auth_manager.refresh_session(indexer)
        return {
            "indexer": indexer,
            "success": success,
            "message": "Session refreshed successfully" if success else "Failed to refresh session"
        }
    except Exception as e:
        logger.error(f"Failed to refresh session for {indexer}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
