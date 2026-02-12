from abc import ABC, abstractmethod
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin, quote_plus
from datetime import datetime, timezone, timedelta
import pytz
import re
import random
import asyncio
import time

from app.models import Torrent, SearchRequest
from app.auth import AuthManager
from app.network_logger import network_logger

logger = logging.getLogger(__name__)

# User agents realistas para rotar
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]


def is_login_page(url: str, html: str) -> bool:
    """Detect if we got redirected to login page"""
    # Check URL
    if '/login' in url.lower():
        return True
    
    # Check HTML content for login indicators
    html_lower = html.lower()
    login_indicators = [
        'name="username"',
        'name="password"',
        'id="username"',
        'id="password"',
        'type="password"',
        'login-form',
        'signin-form'
    ]
    
    # Count how many indicators are present
    matches = sum(1 for indicator in login_indicators if indicator in html_lower)
    
    # If we have at least 2 login indicators, it's likely a login page
    return matches >= 2


def validate_custom_user_agent(ua: str) -> bool:
    """Validate custom user agent string"""
    if not ua or len(ua) < 50 or len(ua) > 300:
        return False
    
    # Must contain Mozilla
    if 'Mozilla' not in ua:
        return False
    
    # Must contain a browser indicator
    browsers = ['Chrome', 'Firefox', 'Safari', 'Edge', 'Gecko', 'AppleWebKit']
    if not any(browser in ua for browser in browsers):
        return False
    
    # Must contain platform indicator
    platforms = ['Windows', 'Linux', 'Mac', 'Android', 'X11']
    if not any(platform in ua for platform in platforms):
        return False
    
    # No script tags or dangerous chars
    forbidden = ['<', '>', 'script', '\n', '\r', '\0']
    if any(char in ua for char in forbidden):
        return False
    
    return True


def get_user_agent_from_config(indexer_name: str, config: dict) -> str:
    """Get user agent based on indexer configuration"""
    ua_config = config.get("user_agent", {})
    mode = ua_config.get("mode", "random")
    
    if mode == "custom":
        custom_ua = ua_config.get("custom_value", "")
        if validate_custom_user_agent(custom_ua):
            return custom_ua
        else:
            logger.warning(f"Invalid custom user agent for {indexer_name}, falling back to random")
            return random.choice(USER_AGENTS)
    
    elif mode == "list":
        list_index = ua_config.get("list_index", 0)
        # Ensure list_index is an integer
        try:
            list_index = int(list_index)
        except (ValueError, TypeError):
            list_index = 0
        
        if 0 <= list_index < len(USER_AGENTS):
            return USER_AGENTS[list_index]
        else:
            logger.warning(f"Invalid user agent index {list_index} for {indexer_name}, falling back to random")
            return random.choice(USER_AGENTS)
    
    else:  # random (default)
        return random.choice(USER_AGENTS)


def map_category_to_torznab_id(category_text: str, title: str = "") -> str:
    """Map Unit3D category name to Torznab category ID"""
    category_lower = category_text.lower().strip()
    title_upper = title.upper()
    
    # Detect quality from title for subcategories
    is_sd = bool(re.search(r'\b(SD|480P|576P)\b', title_upper))
    is_hd = bool(re.search(r'\b(HD|720P|1080P)\b', title_upper))
    is_uhd = bool(re.search(r'\b(UHD|2160P|4K)\b', title_upper))
    
    # Movies
    if any(word in category_lower for word in ['película', 'movie', 'film', 'cine']):
        if is_uhd:
            return '2050'  # Movies/UHD
        elif is_hd:
            return '2040'  # Movies/HD
        elif is_sd:
            return '2030'  # Movies/SD
        else:
            return '2000'  # Movies (general)
    
    # TV/Series
    elif any(word in category_lower for word in ['serie', 'tv', 'television', 'temporada']):
        if is_uhd:
            return '5050'  # TV/UHD
        elif is_hd:
            return '5040'  # TV/HD
        elif is_sd:
            return '5030'  # TV/SD
        else:
            return '5000'  # TV (general)
    
    # Anime
    elif 'anime' in category_lower:
        if 'serie' in category_lower or 'tv' in category_lower:
            return '5070'  # TV/Anime
        else:
            return '2060'  # Movies/Other (anime movies)
    
    # Default to Movies
    else:
        return '2000'


class Unit3DScraper(ABC):
    """Base scraper for Unit3D trackers"""
    
    def __init__(self, name: str, base_url: str, auth_manager: AuthManager, config: dict = None):
        self.name = name
        self.base_url = base_url
        self.auth_manager = auth_manager
        self.config = config or {}
    
    async def _get_client_with_cookies(self) -> httpx.AsyncClient:
        """Create HTTP client with cookies and realistic headers"""
        cookies = await self.auth_manager.get_cookies(self.name)
        
        if not cookies:
            raise Exception(f"No valid session for {self.name}")
        
        # Convert playwright cookies to httpx format
        cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
        
        # Get user agent from config
        user_agent = get_user_agent_from_config(self.name, self.config)
        
        # Headers realistas que imitan Firefox
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'DNT': '1',
            'Sec-GPC': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        client = httpx.AsyncClient(
            cookies=cookie_dict,
            follow_redirects=True,
            timeout=30.0,
            headers=headers,
            http2=True  # HTTP/2 como navegadores modernos
        )
        
        return client
    
    async def _random_delay(self, min_ms: int = 200, max_ms: int = 800):
        """Añade un delay aleatorio para imitar comportamiento humano"""
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string to bytes"""
        size_str = size_str.strip().upper()
        
        # Match number and unit (supports both "GB" and "GiB" format)
        match = re.match(r'([\d.]+)\s*([KMGT]?I?B)', size_str)
        if not match:
            return 0
        
        value = float(match.group(1))
        unit = match.group(2)
        
        multipliers = {
            'B': 1,
            'KB': 1024,
            'KIB': 1024,
            'MB': 1024 ** 2,
            'MIB': 1024 ** 2,
            'GB': 1024 ** 3,
            'GIB': 1024 ** 3,
            'TB': 1024 ** 4,
            'TIB': 1024 ** 4
        }
        
        return int(value * multipliers.get(unit, 1))
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime"""
        # Unit3D typically uses format like "2024-01-15 12:30:45" or relative times
        try:
            # Try absolute format first
            return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            # Handle relative times (e.g., "2 hours ago", "1 day ago")
            # For now, return current time - in production you'd parse this properly
            return datetime.now()
    
    def _parse_relative_date(self, relative_str: str) -> datetime:
        """Parse Spanish relative date strings like 'hace 1 día', 'hace 2 horas'"""
        # Torrentland is GMT+1 (Europe/Madrid), convert to UTC
        madrid_tz = pytz.timezone('Europe/Madrid')
        now_madrid = datetime.now(madrid_tz)
        
        # Extract number and unit
        if 'minuto' in relative_str or 'min' in relative_str:
            match = re.search(r'(\d+)', relative_str)
            if match:
                minutes = int(match.group(1))
                result = now_madrid - timedelta(minutes=minutes)
            else:
                result = now_madrid
        elif 'hora' in relative_str:
            match = re.search(r'(\d+)', relative_str)
            if match:
                hours = int(match.group(1))
                result = now_madrid - timedelta(hours=hours)
            else:
                result = now_madrid
        elif 'día' in relative_str or 'dia' in relative_str:
            match = re.search(r'(\d+)', relative_str)
            if match:
                days = int(match.group(1))
                result = now_madrid - timedelta(days=days)
            else:
                result = now_madrid
        elif 'semana' in relative_str:
            match = re.search(r'(\d+)', relative_str)
            if match:
                weeks = int(match.group(1))
                result = now_madrid - timedelta(weeks=weeks)
            else:
                result = now_madrid
        elif 'mes' in relative_str:
            match = re.search(r'(\d+)', relative_str)
            if match:
                months = int(match.group(1))
                result = now_madrid - timedelta(days=months * 30)  # Approximate
            else:
                result = now_madrid
        elif 'año' in relative_str:
            match = re.search(r'(\d+)', relative_str)
            if match:
                years = int(match.group(1))
                result = now_madrid - timedelta(days=years * 365)  # Approximate
            else:
                result = now_madrid
        else:
            result = now_madrid
        
        # Convert to UTC
        return result.astimezone(pytz.UTC)
    
    @abstractmethod
    async def search(self, request: SearchRequest) -> List[Torrent]:
        """Search for torrents"""
        pass
    
    def _extract_torrent_id(self, url: str) -> Optional[str]:
        """Extract torrent ID from URL"""
        match = re.search(r'/torrents/(\d+)', url)
        return match.group(1) if match else None
    
    def _map_torznab_categories(self, cat_str: str) -> List[str]:
        """
        Map Torznab categories to xBytesV2 categories
        
        Torznab -> xBytesV2:
        - 2000 (Movies) -> 1
        - 5000 (TV) -> 2
        - 5030,5040,5050 (TV/SD/HD/UHD) -> 2
        - 2030,2040,2050 (Movies/SD/HD/UHD) -> 1
        """
        torznab_cats = cat_str.split(',')
        xbytes_cats = set()
        
        for cat in torznab_cats:
            cat = cat.strip()
            # Movies categories -> 1
            if cat.startswith('2'):
                xbytes_cats.add('1')
            # TV categories -> 2  
            elif cat.startswith('5'):
                xbytes_cats.add('2')
            # Anime categories
            elif cat == '5070':  # Anime
                xbytes_cats.add('3')  # Anime Movies
                xbytes_cats.add('4')  # Anime TV
        
        return list(xbytes_cats) if xbytes_cats else ['1', '2']  # Default: Movies + TV


class TorrentlandScraper(Unit3DScraper):
    """Scraper for Torrentland"""
    
    def __init__(self, auth_manager: AuthManager, config: dict = None):
        super().__init__("torrentland", "https://torrentland.li", auth_manager, config)
    
    async def search(self, request: SearchRequest) -> List[Torrent]:
        """Search Torrentland using Playwright (Brotli compression issue)"""
        try:
            # Delay aleatorio antes de la búsqueda
            await self._random_delay(300, 1000)
            
            # Build search URL
            search_url = f"{self.base_url}/torrents"
            params = ['alive=true']
            
            # Priorizar búsqueda por IDs
            if request.tmdb_id:
                params.append(f'tmdbId={request.tmdb_id}')
            elif request.imdb_id:
                imdb_clean = request.imdb_id.replace('tt', '') if request.imdb_id.startswith('tt') else request.imdb_id
                params.append(f'imdbId={imdb_clean}')
            elif request.tvdb_id:
                params.append(f'tvdbId={request.tvdb_id}')
            elif request.query:
                params.append(f'name={request.query}')
            
            # Mapear categorías
            if request.category:
                xbytes_cats = self._map_torznab_categories(request.category)
                for idx, cat in enumerate(xbytes_cats):
                    params.append(f'categories[{idx}]={cat}')
            
            full_url = f"{search_url}?{'&'.join(params)}"
            
            logger.info(f"Searching Torrentland with Playwright: {full_url}")
            
            # Log request start
            start_time = time.time()
            
            # Get browser and create context with cookies
            browser = await self.auth_manager._get_browser()
            cookies = await self.auth_manager._load_cookies(self.name)
            
            # Get user agent from config
            user_agent = get_user_agent_from_config(self.name, self.config)
            
            context = await browser.new_context(user_agent=user_agent)
            if cookies:
                await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            try:
                response = await page.goto(full_url, wait_until='networkidle', timeout=30000)
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Get HTML content
                html = await page.content()
                current_url = page.url
                
                # Check if we got redirected to login
                if is_login_page(current_url, html):
                    logger.warning(f"Session expired for {self.name}, detected login page. Auto-renewing session...")
                    await page.close()
                    await context.close()
                    
                    # Renew session
                    renewal_success = await self.auth_manager.refresh_session(self.name)
                    if not renewal_success:
                        logger.error(f"Failed to renew session for {self.name}")
                        return []
                    
                    logger.info(f"Session renewed for {self.name}, retrying search...")
                    
                    # Retry the search with new session
                    cookies = await self.auth_manager._load_cookies(self.name)
                    context = await browser.new_context(user_agent=user_agent)
                    if cookies:
                        await context.add_cookies(cookies)
                    page = await context.new_page()
                    response = await page.goto(full_url, wait_until='networkidle', timeout=30000)
                    html = await page.content()
                    current_url = page.url
                
                # Extract relevant part (around torrent table) for logging
                table_start = html.find('modern-data-table')
                if table_start == -1:
                    table_start = html.find('<table')
                if table_start == -1:
                    table_start = 0
                
                # Get context around table (1000 chars before, 3000 after)
                start_pos = max(0, table_start - 1000)
                end_pos = min(len(html), table_start + 3000)
                html_snippet = html[start_pos:end_pos]
                if start_pos > 0:
                    html_snippet = '...' + html_snippet
                if end_pos < len(html):
                    html_snippet = html_snippet + '...'
                
                # Get all request headers (Firefox-like)
                req_headers = {
                    "User-Agent": user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "DNT": "1",
                    "Sec-GPC": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Priority": "u=0, i",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache"
                }
                
                # Get response headers
                resp_headers = await response.all_headers() if response else {}
                
                # Log successful request
                network_logger.log_request(
                    method="GET",
                    url=full_url,
                    request_type="tracker",
                    indexer="torrentland",
                    status_code=response.status if response else None,
                    duration_ms=duration_ms,
                    request_headers=req_headers,
                    response_headers=resp_headers,
                    response_body=html_snippet
                )
                
                # Wait for content to load
                try:
                    await page.wait_for_selector('table.modern-data-table', timeout=5000)
                except:
                    logger.warning("No results table found for Torrentland")
                    return []
                
            except Exception as page_error:
                duration_ms = int((time.time() - start_time) * 1000)
                network_logger.log_request(
                    method="GET",
                    url=full_url,
                    request_type="tracker",
                    indexer="torrentland",
                    duration_ms=duration_ms,
                    error=str(page_error)
                )
                raise
            finally:
                await page.close()
                await context.close()
            
            # Parse HTML
            soup = BeautifulSoup(html, 'html.parser')
            
            torrents = []
            
            # Torrentland uses table.modern-data-table
            torrent_rows = soup.select('table.modern-data-table tbody tr')
            
            logger.info(f"Found {len(torrent_rows)} rows in HTML for Torrentland")
            
            for row in torrent_rows[:request.limit]:
                try:
                    torrent = self._parse_torrent_row(row)
                    if torrent:
                        torrents.append(torrent)
                except Exception as e:
                    logger.error(f"Failed to parse torrent row: {e}")
                    continue
            
            logger.info(f"Found {len(torrents)} torrents on Torrentland")
            return torrents
            
        except Exception as e:
            logger.error(f"Search failed on Torrentland: {e}")
            return []
    
    def _parse_torrent_row(self, row) -> Optional[Torrent]:
        """Parse a torrent row from HTML - Torrentland specific structure"""
        try:
            # Title and link
            title_elem = row.select_one('a.view-torrent.torrent-listings-name')
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            info_url = urljoin(self.base_url, title_elem['href'])
            torrent_id = self._extract_torrent_id(info_url)
            
            if not torrent_id:
                return None
            
            # Download URL
            download_url = f"{self.base_url}/torrents/download/{torrent_id}"
            
            # Size - in td.torrent-listings-size span.badge-extra
            size_elem = row.select_one('td.torrent-listings-size span.badge-extra')
            size_text = size_elem.get_text(strip=True).replace('&nbsp;', ' ') if size_elem else '0 B'
            size = self._parse_size(size_text)
            
            # Seeders - in td.torrent-listings-seeders span.badge-extra
            seeders_elem = row.select_one('td.torrent-listings-seeders span.badge-extra')
            seeders = int(seeders_elem.get_text(strip=True)) if seeders_elem else 0
            
            # Leechers - in td.torrent-listings-leechers span.badge-extra
            leechers_elem = row.select_one('td.torrent-listings-leechers span.badge-extra')
            leechers = int(leechers_elem.get_text(strip=True)) if leechers_elem else 0
            
            # Date - relative format "hace 1 día", "hace 2 horas"
            date_elem = row.select_one('td.torrent-listings-age span.badge-extra')
            if date_elem:
                date_text = date_elem.get_text(strip=True).lower()
                publish_date = self._parse_relative_date(date_text)
            else:
                publish_date = datetime.now(pytz.UTC)
            
            # Category - from span label
            category_elem = row.select_one('span.label[data-original-title="Categoria"]')
            category_text = category_elem.get_text(strip=True) if category_elem else "Unknown"
            # Map to Torznab ID
            category = map_category_to_torznab_id(category_text, title)
            
            # IMDB ID - from hidden div
            imdb_elem = row.select_one('div#imdb_id')
            imdb_id = imdb_elem.get_text(strip=True) if imdb_elem else None
            
            # TMDB ID - from similar link: /torrents/similar/1.175 -> 175
            tmdb_id = None
            tmdb_link = row.select_one('a[href*="/torrents/similar/"]')
            if tmdb_link:
                href = tmdb_link.get('href', '')
                match = re.search(r'/torrents/similar/\d+\.(\d+)', href)
                if match:
                    tmdb_id = match.group(1)
            
            return Torrent(
                title=title,
                guid=f"torrentland-{torrent_id}",
                indexer="torrentland",
                download_url=download_url,
                info_url=info_url,
                publish_date=publish_date,
                size=size,
                seeders=seeders,
                leechers=leechers,
                category=category,
                imdb_id=imdb_id,
                tmdb_id=tmdb_id
            )
            
        except Exception as e:
            logger.error(f"Failed to parse torrent row: {e}")
            return None


class XBytesV2Scraper(Unit3DScraper):
    """Scraper for xBytesV2"""
    
    def __init__(self, base_url: str, auth_manager: AuthManager, config: dict = None):
        super().__init__("xbytesv2", base_url, auth_manager, config)
    
    async def search(self, request: SearchRequest) -> List[Torrent]:
        """Search xBytesV2 - similar to Torrentland but with different base URL"""
        try:
            # Delay aleatorio antes de la búsqueda
            await self._random_delay(300, 1000)
            
            client = await self._get_client_with_cookies()
            
            # Build search URL and params for xBytesV2
            search_url = f"{self.base_url}/torrents/"
            params = {
                'alive': 'true',  # Solo torrents vivos
            }
            
            # Priorizar búsqueda por IDs (tmdbid > imdbid > tvdbid)
            if request.tmdb_id:
                params['tmdbId'] = request.tmdb_id
            elif request.imdb_id:
                # xBytesV2 usa imdbId sin el 'tt'
                imdb_clean = request.imdb_id.replace('tt', '') if request.imdb_id.startswith('tt') else request.imdb_id
                params['imdbId'] = imdb_clean
            elif request.tvdb_id:
                params['tvdbId'] = request.tvdb_id
            elif request.query:
                # Solo usamos query textual si no hay IDs
                params['name'] = request.query
            
            # Mapear categorías de Torznab a xBytesV2
            if request.category:
                xbytes_cats = self._map_torznab_categories(request.category)
                for idx, cat in enumerate(xbytes_cats):
                    params[f'categories[{idx}]'] = cat
            
            # Añadir Referer header
            headers = {'Referer': f"{self.base_url}/torrents"}
            
            logger.info(f"Searching xBytesV2: {search_url} with params {params}")
            
            # Log request start
            start_time = time.time()
            full_url = f"{search_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
            
            # Get all headers that will be sent (client base headers + custom Referer)
            all_req_headers = dict(client.headers)
            all_req_headers.update(headers)
            
            try:
                response = await client.get(search_url, params=params, headers=headers)
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Extract HTML response
                html = response.text
                
                # Check if we got redirected to login
                if is_login_page(str(response.url), html) or response.status_code == 401 or response.status_code == 403:
                    logger.warning(f"Session expired for {self.name}, detected login page or auth error. Auto-renewing session...")
                    await client.aclose()
                    
                    # Renew session
                    renewal_success = await self.auth_manager.refresh_session(self.name)
                    if not renewal_success:
                        logger.error(f"Failed to renew session for {self.name}")
                        return []
                    
                    logger.info(f"Session renewed for {self.name}, retrying search...")
                    
                    # Retry with new session
                    client = await self._get_client_with_cookies()
                    response = await client.get(search_url, params=params, headers=headers)
                    html = response.text
                
                # Extract relevant part of HTML response
                table_start = html.find('<table')
                if table_start == -1:
                    table_start = html.find('torrent-search--list')
                if table_start == -1:
                    table_start = 0
                
                # Get context around table (1000 chars before, 3000 after)
                start_pos = max(0, table_start - 1000)
                end_pos = min(len(html), table_start + 3000)
                html_snippet = html[start_pos:end_pos]
                if start_pos > 0:
                    html_snippet = '...' + html_snippet
                if end_pos < len(html):
                    html_snippet = html_snippet + '...'
                
                # Log successful request
                network_logger.log_request(
                    method="GET",
                    url=full_url,
                    request_type="tracker",
                    indexer="xbytesv2",
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    request_headers=all_req_headers,
                    response_headers=dict(response.headers),
                    response_body=html_snippet
                )
                
                response.raise_for_status()
            except Exception as req_error:
                duration_ms = int((time.time() - start_time) * 1000)
                network_logger.log_request(
                    method="GET",
                    url=full_url,
                    request_type="tracker",
                    indexer="xbytesv2",
                    status_code=getattr(req_error.response, 'status_code', None) if hasattr(req_error, 'response') else None,
                    duration_ms=duration_ms,
                    request_headers=dict(headers),
                    error=str(req_error)
                )
                raise
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            torrents = []
            # xBytesV2 usa 'table.data-table' en lugar de 'table.table'
            torrent_rows = soup.select('table.data-table tbody tr.torrent-search--list__row')
            
            for row in torrent_rows[:request.limit]:
                try:
                    torrent = self._parse_torrent_row(row)
                    if torrent:
                        torrents.append(torrent)
                except Exception as e:
                    logger.error(f"Failed to parse torrent row: {e}")
                    continue
            
            await client.aclose()
            
            logger.info(f"Found {len(torrents)} torrents on xBytesV2")
            return torrents
            
        except Exception as e:
            logger.error(f"Search failed on xBytesV2: {e}")
            return []
    
    def _parse_torrent_row(self, row) -> Optional[Torrent]:
        """Parse torrent row - xBytesV2 specific structure"""
        try:
            # xBytesV2 usa clases específicas
            title_elem = row.select_one('a.torrent-search--list__name')
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            info_url = urljoin(self.base_url, title_elem['href'])
            
            # Get torrent ID from data attribute or URL
            torrent_id = row.get('data-torrent-id') or self._extract_torrent_id(info_url)
            if not torrent_id:
                return None
            
            download_url = f"{self.base_url}/torrents/download/{torrent_id}"
            
            # Size
            size_elem = row.select_one('td.torrent-search--list__size span')
            size = self._parse_size(size_elem.get_text(strip=True)) if size_elem else 0
            
            # Seeders/Leechers
            seeders_elem = row.select_one('td.torrent-search--list__seeders span')
            leechers_elem = row.select_one('td.torrent-search--list__leechers span')
            
            seeders = int(seeders_elem.get_text(strip=True)) if seeders_elem else 0
            leechers = int(leechers_elem.get_text(strip=True)) if leechers_elem else 0
            
            # Date - xBytesV2 usa formato datetime="2023-10-07 17:37:29" en Europe/Madrid timezone
            date_elem = row.select_one('td.torrent-search--list__age time')
            date_str = date_elem.get('datetime') if date_elem else None
            if date_str:
                # Parse "2023-10-07 17:37:29" format
                # xBytesV2 stores dates in Europe/Madrid timezone, convert to UTC
                madrid_tz = pytz.timezone('Europe/Madrid')
                naive_dt = datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S")
                madrid_dt = madrid_tz.localize(naive_dt)
                publish_date = madrid_dt.astimezone(pytz.UTC)
            else:
                publish_date = datetime.now(pytz.UTC)
            
            # Category from data attribute
            # Category - map Unit3D category to Torznab ID
            category_id = row.get('data-category-id', 'Unknown')
            category_name_map = {'1': 'Movies', '2': 'TV', '3': 'Anime Movies', '4': 'Anime TV'}
            category_name = category_name_map.get(category_id, 'Movies')
            category = map_category_to_torznab_id(category_name, title)
            
            # Get IDs from data attributes
            imdb_id = row.get('data-imdb-id', '0')
            tmdb_id = row.get('data-tmdb-id', '0')
            tvdb_id = row.get('data-tvdb-id', '0')
            
            # Only set if not 0
            imdb_id = f"tt{imdb_id}" if imdb_id != '0' else None
            tmdb_id = tmdb_id if tmdb_id != '0' else None
            tvdb_id = tvdb_id if tvdb_id != '0' else None
            
            return Torrent(
                title=title,
                guid=f"xbytesv2-{torrent_id}",
                indexer="xbytesv2",
                download_url=download_url,
                info_url=info_url,
                publish_date=publish_date,
                size=size,
                seeders=seeders,
                leechers=leechers,
                category=category,
                imdb_id=imdb_id,
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id
            )
            
        except Exception as e:
            logger.error(f"Failed to parse torrent row: {e}")
            return None
