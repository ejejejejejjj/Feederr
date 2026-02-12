from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import Response
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime, timezone
import logging
import json
from pathlib import Path

from app.config import settings, BASE_DIR
from app.indexer_config import indexer_config
from app.models import SearchRequest, Torrent
from app.scrapers.unit3d import TorrentlandScraper, XBytesV2Scraper
from app.dependencies import get_auth_manager

router = APIRouter()
logger = logging.getLogger(__name__)

CONFIG_FILE = BASE_DIR / "data" / "indexers_config.json"


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


def create_torznab_xml(torrents: list[Torrent], offset: int = 0, search_type: str = 'search') -> str:
    """Create Torznab XML response"""
    rss = Element('rss', version="2.0")
    rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
    rss.set('xmlns:torznab', 'http://torznab.com/schemas/2015/feed')
    
    channel = SubElement(rss, 'channel')
    SubElement(channel, 'title').text = settings.app_name
    SubElement(channel, 'description').text = f"{settings.app_name} - Unit3D Bridge"
    SubElement(channel, 'link').text = "http://feederr:9797"
    
    # Add response attributes
    response_elem = SubElement(channel, 'torznab:response')
    response_elem.set('offset', str(offset))
    response_elem.set('total', str(len(torrents)))
    
    # Add items
    for torrent in torrents:
        item = SubElement(channel, 'item')
        
        # Use title with language prefix for *arr compatibility
        is_tv_search = search_type == 'tvsearch'
        title_with_lang = torrent.get_title_with_languages(is_tv_search=is_tv_search)
        SubElement(item, 'title').text = title_with_lang
        SubElement(item, 'guid', isPermaLink='false').text = torrent.guid
        
        # Use our own download endpoint instead of direct tracker URL
        torrent_id = torrent.guid.split('-')[-1]  # Extract ID from guid like "xbytesv2-39637"
        download_url = f"http://feederr:9797/api/v1/download/{torrent.indexer}/{torrent_id}"
        
        SubElement(item, 'link').text = download_url
        SubElement(item, 'comments').text = torrent.info_url
        # Ensure pubDate is in GMT (UTC)
        pubdate_utc = torrent.publish_date.replace(tzinfo=timezone.utc) if torrent.publish_date.tzinfo is None else torrent.publish_date.astimezone(timezone.utc)
        SubElement(item, 'pubDate').text = pubdate_utc.strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        # Size
        size_attr = SubElement(item, 'torznab:attr')
        size_attr.set('name', 'size')
        size_attr.set('value', str(torrent.size))
        
        # Seeders
        seeders_attr = SubElement(item, 'torznab:attr')
        seeders_attr.set('name', 'seeders')
        seeders_attr.set('value', str(torrent.seeders))
        
        # Peers (seeders + leechers)
        peers_attr = SubElement(item, 'torznab:attr')
        peers_attr.set('name', 'peers')
        peers_attr.set('value', str(torrent.seeders + torrent.leechers))
        
        # Category
        category_attr = SubElement(item, 'torznab:attr')
        category_attr.set('name', 'category')
        category_attr.set('value', torrent.category)
        
        # Parse season and episode from title
        season, episode = torrent.parse_season_episode()
        if season is not None and episode is not None:
            season_attr = SubElement(item, 'torznab:attr')
            season_attr.set('name', 'season')
            season_attr.set('value', str(season))
            
            episode_attr = SubElement(item, 'torznab:attr')
            episode_attr.set('name', 'episode')
            episode_attr.set('value', str(episode))
        elif season is None:
            # Try to get just the season (for full season packs)
            season_only = torrent.parse_season_only()
            if season_only is not None:
                season_attr = SubElement(item, 'torznab:attr')
                season_attr.set('name', 'season')
                season_attr.set('value', str(season_only))
        
        # Download URL
        download_attr = SubElement(item, 'torznab:attr')
        download_attr.set('name', 'downloadvolumefactor')
        download_attr.set('value', '1')
        
        upload_attr = SubElement(item, 'torznab:attr')
        upload_attr.set('name', 'uploadvolumefactor')
        upload_attr.set('value', '1')
        
        # IMDB if available
        if torrent.imdb_id:
            imdb_attr = SubElement(item, 'torznab:attr')
            imdb_attr.set('name', 'imdbid')
            imdb_attr.set('value', torrent.imdb_id)
        
        # TMDB if available
        if torrent.tmdb_id:
            tmdb_attr = SubElement(item, 'torznab:attr')
            tmdb_attr.set('name', 'tmdbid')
            tmdb_attr.set('value', torrent.tmdb_id)
        
        # TVDB if available  
        if torrent.tvdb_id:
            tvdb_attr = SubElement(item, 'torznab:attr')
            tvdb_attr.set('name', 'tvdbid')
            tvdb_attr.set('value', torrent.tvdb_id)
        
        # Enclosure for download
        enclosure = SubElement(item, 'enclosure')
        enclosure.set('url', download_url)
        enclosure.set('length', str(torrent.size))
        enclosure.set('type', 'application/x-bittorrent')
        enclosure.set('length', str(torrent.size))
        enclosure.set('type', 'application/x-bittorrent')
    
    return tostring(rss, encoding='unicode', method='xml')


def create_caps_xml() -> str:
    """Create capabilities XML for Prowlarr"""
    rss = Element('caps')
    
    # Server info
    server = SubElement(rss, 'server')
    server.set('title', settings.app_name)
    server.set('version', '1.0.0')
    
    # Limits
    limits = SubElement(rss, 'limits')
    limits.set('max', '100')
    limits.set('default', '100')
    
    # Searching capabilities
    searching = SubElement(rss, 'searching')
    
    search = SubElement(searching, 'search')
    search.set('available', 'yes')
    search.set('supportedParams', 'q')
    
    tv_search = SubElement(searching, 'tv-search')
    tv_search.set('available', 'yes')
    tv_search.set('supportedParams', 'q,season,ep,imdbid,tvdbid,tmdbid')
    
    movie_search = SubElement(searching, 'movie-search')
    movie_search.set('available', 'yes')
    movie_search.set('supportedParams', 'q,imdbid,tmdbid')
    
    # Categorías reales de xBytesV2
    categories = SubElement(rss, 'categories')
    
    categories_list = [
        ('2000', 'Movies'),
        ('5000', 'TV'),
        ('5030', 'TV/SD'),
        ('5040', 'TV/HD'),
        ('5050', 'TV/UHD'),
        ('2030', 'Movies/SD'),
        ('2040', 'Movies/HD'),
        ('2050', 'Movies/UHD'),
    ]
    
    for cat_id, cat_name in categories_list:
        category = SubElement(categories, 'category')
        category.set('id', cat_id)
        category.set('name', cat_name)
    
    return tostring(rss, encoding='unicode', method='xml')


def create_fake_torrent(indexer: str, category: Optional[str] = None) -> Torrent:
    """Create a fake torrent to indicate indexer is disabled or outside time restrictions"""
    # Use first category from request, or default to 2000 (Movies)
    cat_id = category.split(',')[0] if category else '2000'
    
    # Get indexer config for time restriction info
    indexer_cfg = indexer_config.get_indexer(indexer)
    time_restrictions = indexer_cfg.get('time_restrictions', {}) if indexer_cfg else {}
    
    # Build informative title
    if not indexer_cfg.get('enabled', True):
        reason = "Indexer temporalmente deshabilitado"
    elif time_restrictions.get('enabled', False):
        start = time_restrictions.get('start_time', '10:00')
        end = time_restrictions.get('end_time', '23:59')
        reason = f"Fuera de horario de funcionamiento ({start}-{end})"
    else:
        reason = "Indexer no disponible"
    
    fake_torrent = Torrent(
        title=f"[INFO] {reason} - {indexer}",
        guid=f"{indexer}-disabled-info",
        indexer=indexer,
        download_url="http://feederr:9797/api/v1/status",  # Non-functional but valid URL
        info_url="http://feederr:9797/home",
        publish_date=datetime.now(timezone.utc),
        size=1024,  # 1KB
        seeders=0,
        leechers=0,
        category=cat_id
    )
    
    return fake_torrent


@router.get("/torznab/{indexer}")
async def torznab_api(
    indexer: str,
    t: str = Query(..., description="Torznab action (caps, search, tvsearch, movie)"),
    q: Optional[str] = Query(None, description="Search query"),
    cat: Optional[str] = Query(None, description="Category"),
    imdbid: Optional[str] = Query(None, description="IMDB ID"),
    tvdbid: Optional[str] = Query(None, description="TVDB ID"),
    tmdbid: Optional[str] = Query(None, description="TMDB ID"),
    season: Optional[int] = Query(None, description="Season number"),
    ep: Optional[int] = Query(None, description="Episode number"),
    limit: int = Query(100, description="Result limit"),
    offset: int = Query(0, description="Result offset"),
    apikey: Optional[str] = Query(None, description="API key"),
    auth_manager = Depends(get_auth_manager)
):
    """
    Torznab API endpoint compatible with Prowlarr/Sonarr/Radarr
    
    Usage in Prowlarr:
    - Add as "Generic Torznab" indexer
    - URL: http://feederr:9797/api/v1/torznab/torrentland or .../xbytesv2
    - API Key: (from .env)
    """
    
    # Validate API key
    if apikey != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Validate indexer - debe existir, pero no necesita estar enabled para caps
    indexer_cfg = indexer_config.get_indexer(indexer)
    if not indexer_cfg:
        raise HTTPException(status_code=404, detail=f"Indexer {indexer} not found")
    
    # Handle capabilities request - SIEMPRE responder, aunque esté disabled
    if t == 'caps':
        xml_response = create_caps_xml()
        return Response(content=xml_response, media_type='application/xml')
    
    # Handle search requests
    if t in ['search', 'tvsearch', 'movie']:
        # Check if can search (enabled + within time restrictions)
        if not indexer_config.can_search(indexer):
            # Return fake torrent so *arr apps don't complain about no results
            logger.info(f"Indexer {indexer} cannot search (disabled or outside time restrictions) - returning fake result")
            fake_torrent = create_fake_torrent(indexer, cat)
            xml_response = create_torznab_xml([fake_torrent], offset, search_type=t)
            return Response(content=xml_response, media_type='application/xml')
        
        # Create search request - priorizar IDs sobre texto
        search_request = SearchRequest(
            query=q if not (tmdbid or imdbid or tvdbid) else None,  # Solo si no hay IDs
            category=cat,
            imdb_id=imdbid,
            tvdb_id=tvdbid,
            tmdb_id=tmdbid,
            season=season,
            limit=limit,
            offset=offset
        )
        
        # Get appropriate scraper
        if indexer == 'torrentland':
            scraper = TorrentlandScraper(auth_manager, indexer_cfg)
        elif indexer == 'xbytesv2':  # xbytesv2
            scraper = XBytesV2Scraper(indexer_cfg.get("url"), auth_manager, indexer_cfg)
        else:
            # For any other indexers configured in indexers.json
            scraper = XBytesV2Scraper(indexer_cfg.get("url"), auth_manager, indexer_cfg)
        
        # Perform search
        try:
            torrents = await scraper.search(search_request)
            
            # Filter by season/episode if requested (for TV searches)
            if season is not None and t in ['tvsearch', 'search']:
                filtered_torrents = []
                for torrent in torrents:
                    # Try to extract season and episode from torrent title
                    torrent_season, torrent_episode = torrent.parse_season_episode()
                    
                    # If no episode found, check if it's a season pack
                    is_season_pack = False
                    if torrent_season is None:
                        # Try season-only pattern (for full season packs)
                        torrent_season = torrent.parse_season_only()
                        is_season_pack = True if torrent_season is not None else False
                    
                    # Skip if season doesn't match
                    if torrent_season != season:
                        continue
                    
                    # If searching for specific episode
                    if ep is not None:
                        # Keep only if matches exact episode
                        if torrent_episode == ep:
                            filtered_torrents.append(torrent)
                    else:
                        # Searching for season without specific episode = want season packs only
                        # Exclude individual episodes (S01E01), keep only full season packs (S01)
                        if is_season_pack:
                            filtered_torrents.append(torrent)
                
                if ep is not None:
                    logger.info(f"Season/Episode filter: {len(torrents)} results → {len(filtered_torrents)} after filtering for S{season:02d}E{ep:02d}")
                else:
                    logger.info(f"Season pack filter: {len(torrents)} results → {len(filtered_torrents)} after filtering for S{season:02d} (packs only)")
                    
                torrents = filtered_torrents
            
            xml_response = create_torznab_xml(torrents, offset, search_type=t)
            
            return Response(content=xml_response, media_type='application/xml')
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    
    raise HTTPException(status_code=400, detail=f"Unknown action: {t}")
