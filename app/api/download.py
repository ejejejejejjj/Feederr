from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pathlib import Path
import logging
import tempfile
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import asyncio

from app.config import settings
from app.indexer_config import indexer_config
from app.dependencies import get_auth_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# Directory to store downloaded torrents (cross-platform temp dir)
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "Feederr_torrents"
DOWNLOAD_DIR.mkdir(exist_ok=True)


async def download_torrent_file(indexer: str, torrent_id: str, give_thanks: bool = True) -> Path:
    """
    Download a torrent file using Playwright
    
    Args:
        indexer: Indexer name (torrentland, xbytesv2)
        torrent_id: Torrent ID
        give_thanks: Whether to click the thank button after download
        
    Returns:
        Path to downloaded torrent file
    """
    auth_manager = get_auth_manager()
    
    # Check if indexer exists
    indexer_cfg = indexer_config.get_indexer(indexer)
    if not indexer_cfg:
        raise HTTPException(status_code=404, detail=f"Indexer {indexer} not found")
    
    # Check if can search (enabled + within time restrictions)
    if not indexer_config.can_search(indexer):
        raise HTTPException(status_code=403, detail=f"Indexer {indexer} is disabled or outside allowed time")
    
    # Get indexer URL from config
    base_url = indexer_config.get_url(indexer)
    if not base_url:
        raise HTTPException(status_code=404, detail=f"No URL configured for {indexer}")
    
    # Get cookies for this indexer
    cookies = await auth_manager.get_cookies(indexer)
    if not cookies:
        raise HTTPException(status_code=401, detail=f"No valid session for {indexer}")
    
    torrent_url = f"{base_url}/torrents/{torrent_id}"
    download_path = DOWNLOAD_DIR / f"{indexer}_{torrent_id}.torrent"
    
    logger.info(f"Downloading torrent from {torrent_url}")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            # Add cookies
            await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            # Set up download handler
            download_info = None
            
            async def handle_download(download):
                nonlocal download_info
                download_info = download
                await download.save_as(download_path)
                logger.info(f"Torrent saved to {download_path}")
            
            page.on("download", handle_download)
            
            # Navigate to torrent page
            await page.goto(torrent_url, wait_until="domcontentloaded", timeout=30000)
            
            # Find and click download button
            # Unit3D uses fa-download icon
            download_button = None
            selectors = [
                'a[href*="/download"] i.fa-download',
                'a[title*="Descargar"] i.fa-download',
                'button:has(i.fa-download)',
            ]
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        download_button = element
                        break
                except:
                    continue
            
            if not download_button:
                # Try clicking the parent anchor
                download_link = await page.query_selector('a[href*="/download"]')
                if download_link:
                    await download_link.click()
                else:
                    raise Exception("Download button not found")
            else:
                # Click the icon's parent (the anchor)
                parent = await download_button.evaluate_handle('element => element.closest("a")')
                await parent.as_element().click()
            
            # Wait for download to complete
            await asyncio.sleep(2)
            
            if not download_path.exists():
                raise Exception("Download failed - file not created")
            
            # Give thanks if enabled
            if give_thanks:
                try:
                    logger.info(f"Attempting to give thanks for torrent {torrent_id}")
                    
                    # Find thank button with fa-heart
                    thank_selectors = [
                        'button:has(i.fa-heart)',
                        'button[wire\\:click*="store"]',
                        'button:has(i.text-pink)',
                    ]
                    
                    thank_button = None
                    for selector in thank_selectors:
                        try:
                            thank_button = await page.wait_for_selector(selector, timeout=3000)
                            if thank_button:
                                break
                        except:
                            continue
                    
                    if thank_button:
                        await thank_button.click()
                        await asyncio.sleep(1)
                        logger.info(f"Thanks given for torrent {torrent_id}")
                    else:
                        logger.warning(f"Thank button not found for torrent {torrent_id}")
                
                except Exception as e:
                    logger.warning(f"Failed to give thanks: {e}")
            
            await browser.close()
            
            return download_path
            
    except Exception as e:
        logger.error(f"Failed to download torrent {torrent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/download/{indexer}/{torrent_id}")
async def download_torrent(
    indexer: str,
    torrent_id: str,
    thanks: bool = True
):
    """
    Download a torrent file and serve it to the client
    
    This endpoint:
    1. Navigates to the torrent page using Playwright
    2. Downloads the .torrent file
    3. Optionally gives thanks (clicks fa-heart button)
    4. Serves the file to the client
    
    Usage:
    GET /api/v1/download/xbytesv2/39637?thanks=true
    """
    try:
        torrent_path = await download_torrent_file(indexer, torrent_id, give_thanks=thanks)
        
        if not torrent_path.exists():
            raise HTTPException(status_code=404, detail="Torrent file not found")
        
        # Serve the file
        return FileResponse(
            path=torrent_path,
            media_type="application/x-bittorrent",
            filename=f"{indexer}_{torrent_id}.torrent",
            headers={
                "Content-Disposition": f'attachment; filename="{indexer}_{torrent_id}.torrent"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
