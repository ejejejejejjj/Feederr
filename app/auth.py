import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.config import settings
from app.indexer_config import indexer_config

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages authentication sessions for Unit3D indexers using Playwright"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.cookies_dir = Path("/app/cookies")
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
    
    async def _get_browser(self) -> Browser:
        """Get or create browser instance"""
        if not self.browser:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=settings.browser_headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
        return self.browser
    
    async def _load_cookies(self, indexer: str) -> Optional[list]:
        """Load cookies from file"""
        cookie_file = self.cookies_dir / f"{indexer}_cookies.json"
        if cookie_file.exists():
            try:
                with open(cookie_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cookies for {indexer}: {e}")
        return None
    
    async def _save_cookies(self, indexer: str, cookies: list):
        """Save cookies to file"""
        cookie_file = self.cookies_dir / f"{indexer}_cookies.json"
        try:
            with open(cookie_file, 'w') as f:
                json.dump(cookies, f)
            logger.info(f"Saved cookies for {indexer}")
        except Exception as e:
            logger.error(f"Failed to save cookies for {indexer}: {e}")
    
    async def _login_generic(self, page: Page, indexer_id: str, url: str, username: str, password: str) -> bool:
        """Generic login for Unit3D sites"""
        try:
            logger.info(f"Logging into {indexer_id}")
            await page.goto(f"{url}/login", timeout=60000)
            
            # Wait for login form
            try:
                await page.wait_for_selector('input[name="username"], input[name="email"], input[id="username"]', timeout=15000)
            except Exception as e:
                logger.error(f"Login form not found for {indexer_id}: {e}")
                return False
            
            # Fill credentials
            username_filled = False
            for selector in ['input[name="username"]', 'input[name="email"]', 'input[id="username"]']:
                try:
                    if await page.locator(selector).count() > 0:
                        await page.fill(selector, username)
                        username_filled = True
                        break
                except:
                    continue
            
            if not username_filled:
                logger.error(f"Could not fill username field for {indexer_id}")
                return False
            
            # Fill password
            for selector in ['input[name="password"]', 'input[id="password"]', 'input[type="password"]']:
                try:
                    if await page.locator(selector).count() > 0:
                        await page.fill(selector, password)
                        break
                except:
                    continue
            
            # Submit form
            try:
                submit_selector = 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign in")'
                if await page.locator(submit_selector).count() > 0:
                    async with page.expect_navigation(timeout=45000, wait_until='domcontentloaded'):
                        await page.click(submit_selector)
                else:
                    await page.keyboard.press('Enter')
                    await page.wait_for_url(lambda url: '/login' not in url, timeout=30000)
            except Exception as submit_error:
                logger.warning(f"Submit/navigation issue for {indexer_id}: {submit_error}")
                await page.wait_for_timeout(3000)
            
            # Check success
            success_indicators = [
                'a[href*="/profile"]',
                '.user-menu',
                'a[href*="/logout"]',
                '.navbar .dropdown',
                '#account-dropdown',
                '[data-user]'
            ]
            
            for indicator in success_indicators:
                if await page.locator(indicator).count() > 0:
                    logger.info(f"Login successful for {indexer_id}")
                    return True
            
            logger.error(f"Login failed for {indexer_id} - no success indicators found")
            return False
            
        except Exception as e:
            logger.error(f"Error logging into {indexer_id}: {e}")
            return False
    
    async def validate_credentials(self, indexer_id: str, url: str, username: str, password: str) -> tuple[bool, str]:
        """Validate credentials without saving to config. Returns (success, message)"""
        browser = await self._get_browser()
        context = await browser.new_context()
        
        try:
            page = await context.new_page()
            success = await self._login_generic(page, indexer_id, url, username, password)
            
            if success:
                # Save cookies for this indexer
                cookies = await context.cookies()
                await self._save_cookies(indexer_id, cookies)
                
                # Update session info
                self.sessions[indexer_id] = {
                    "authenticated": True,
                    "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "expires": (datetime.now() + timedelta(hours=settings.session_refresh_hours)).isoformat()
                }
                
                return True, "Credentials validated successfully"
            else:
                return False, "Invalid credentials - login failed"
            
        except Exception as e:
            logger.error(f"Credential validation failed for {indexer_id}: {e}")
            return False, f"Validation error: {str(e)}"
        finally:
            await context.close()
    
    async def _perform_login(self, indexer: str) -> bool:
        """Perform login for specified indexer"""
        browser = await self._get_browser()
        context = await browser.new_context()
        
        try:
            # Get credentials from config
            indexer_cfg = indexer_config.get_indexer(indexer)
            if not indexer_cfg:
                logger.error(f"Indexer {indexer} not found in config")
                return False
            
            url = indexer_cfg.get("url")
            username = indexer_cfg.get("username")
            password = indexer_cfg.get("password")
            
            if not all([url, username, password]):
                logger.error(f"Incomplete configuration for {indexer}")
                return False
            
            page = await context.new_page()
            success = await self._login_generic(page, indexer, url, username, password)
            
            if success:
                # Save cookies
                cookies = await context.cookies()
                await self._save_cookies(indexer, cookies)
                
                # Update session info
                self.sessions[indexer] = {
                    "authenticated": True,
                    "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "expires": (datetime.now() + timedelta(hours=settings.session_refresh_hours)).isoformat()
                }
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Login failed for {indexer}: {e}")
            return False
        finally:
            await context.close()
    
    async def ensure_session(self, indexer: str) -> bool:
        """Ensure valid session exists for indexer"""
        async with self._lock:
            # Check if we have recent valid session
            session_info = self.sessions.get(indexer, {})
            if session_info.get("authenticated"):
                expires = datetime.fromisoformat(session_info.get("expires"))
                if datetime.now() < expires:
                    logger.info(f"Using existing session for {indexer}")
                    return True
            
            # Try to load cookies
            cookies = await self._load_cookies(indexer)
            if cookies:
                # TODO: Validate cookies are still valid
                # For now, assume they are and update session info
                self.sessions[indexer] = {
                    "authenticated": True,
                    "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "expires": (datetime.now() + timedelta(hours=settings.session_refresh_hours)).isoformat()
                }
                logger.info(f"Loaded existing cookies for {indexer}")
                return True
            
            # Need to perform fresh login
            logger.info(f"No valid session found for {indexer}, performing login")
            return await self._perform_login(indexer)
    
    async def get_cookies(self, indexer: str) -> Optional[list]:
        """Get cookies for indexer, ensuring session is valid"""
        await self.ensure_session(indexer)
        return await self._load_cookies(indexer)
    
    async def check_session_status(self, indexer: str) -> Dict[str, Any]:
        """Check session status without refreshing"""
        session_info = self.sessions.get(indexer, {})
        return {
            "authenticated": session_info.get("authenticated", False),
            "last_check": session_info.get("last_check"),
            "expires": session_info.get("expires")
        }
    
    async def refresh_session(self, indexer: str) -> bool:
        """Force refresh session for indexer"""
        async with self._lock:
            logger.info(f"Force refreshing session for {indexer}")
            return await self._perform_login(indexer)
    
    def delete_cookies(self, indexer: str) -> bool:
        """Delete cookies file for indexer"""
        cookie_file = self.cookies_dir / f"{indexer}_cookies.json"
        try:
            if cookie_file.exists():
                cookie_file.unlink()
                logger.info(f"Deleted cookies for {indexer}")
                
                # Remove from sessions
                if indexer in self.sessions:
                    del self.sessions[indexer]
                
                return True
            else:
                logger.warning(f"No cookies file found for {indexer}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete cookies for {indexer}: {e}")
            return False
    
    async def close(self):
        """Cleanup resources"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
