from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import re


class Torrent(BaseModel):
    """Torrent model"""
    title: str
    guid: str
    indexer: str
    download_url: str
    info_url: str
    publish_date: datetime
    size: int  # bytes
    seeders: int
    leechers: int
    category: str
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    resolution: Optional[str] = None
    codec: Optional[str] = None
    languages: Optional[List[str]] = None  # ISO 639-1 codes
    
    def parse_languages(self) -> List[str]:
        """Parse languages from title"""
        title_upper = self.title.upper()
        detected_langs = []
        
        # Language mappings (Spanish tracker typical format)
        lang_patterns = {
            'Spanish': [r'\bESP\b', r'\bSPA\b', r'\bCAST\b', r'\bESPAÑOL\b'],
            'English': [r'\bING\b', r'\bENG\b', r'\bINGLES\b', r'\bINGLÉS\b'],
            'Latino': [r'\bLAT\b', r'\bLATINO\b'],
            'French': [r'\bFRA\b', r'\bFRE\b', r'\bFRANCES\b', r'\bFRANCÉS\b'],
            'German': [r'\bGER\b', r'\bALE\b', r'\bALEMAN\b', r'\bALEMÁN\b'],
            'Italian': [r'\bITA\b', r'\bITALIANO\b'],
            'Portuguese': [r'\bPOR\b', r'\bPORT\b', r'\bPORTUGUES\b', r'\bPORTUGUÉS\b'],
            'Japanese': [r'\bJAP\b', r'\bJPN\b', r'\bJAPONES\b', r'\bJAPONÉS\b'],
            'Korean': [r'\bKOR\b', r'\bCOREANO\b'],
            'Chinese': [r'\bCHI\b', r'\bCHN\b', r'\bCHINO\b'],
            'Russian': [r'\bRUS\b', r'\bRUSO\b'],
        }
        
        # Check for DUAL/MULTI first
        if re.search(r'\bDUAL\b', title_upper):
            # DUAL typically means Spanish + English in Spanish trackers
            detected_langs.extend(['Spanish', 'English'])
        elif re.search(r'\bMULTI\b', title_upper):
            # MULTI could be several languages
            detected_langs.extend(['Spanish', 'English'])
        else:
            # Check each language pattern
            for lang_name, patterns in lang_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, title_upper):
                        if lang_name not in detected_langs:
                            detected_langs.append(lang_name)
                        break
        
        # Default to Spanish if nothing detected (Spanish tracker)
        if not detected_langs:
            detected_langs = ['Spanish']
        
        return detected_langs
    
    def _remove_year_parentheses(self, title: str) -> str:
        """Remove year parentheses from TV series titles.
        - If only one (YYYY) found: removes it
        - If multiple found: removes only the last one
        """
        pattern = r'\(\d{4}\)'
        matches = list(re.finditer(pattern, title))
        
        if len(matches) == 0:
            return title
        elif len(matches) == 1:
            # One match: remove it
            result = re.sub(pattern, '', title, count=1).strip()
        else:
            # Multiple matches: remove only the last one
            last_match = matches[-1]
            result = (title[:last_match.start()] + title[last_match.end():]).strip()
        
        # Clean up multiple spaces
        result = re.sub(r'\s+', ' ', result)
        return result
    
    def get_title_with_languages(self, is_tv_search: bool = False) -> str:
        """Get title with language substitutions for *arr compatibility"""
        modified_title = self.title
        
        # Transform Spanish season format to *arr format
        # Examples:
        # "Serie - Segunda temporada (2023/info)" -> "Serie (2023) - S02 [info]"
        # "Serie - Temporada 2 (2020) info" -> "Serie (2020) - S02 [info]"
        modified_title = self._transform_season_format(modified_title)
        
        # Remove year parentheses for TV series
        if is_tv_search:
            modified_title = self._remove_year_parentheses(modified_title)
        
        # Replace ESP/SPA/CAST with SPANiSH
        modified_title = re.sub(r'\b(ESP|SPA|CAST)\b', 'SPANiSH', modified_title, flags=re.IGNORECASE)
        
        # Remove ING/ENG (and one trailing slash if present)
        modified_title = re.sub(r'(ING|ENG)/?', '', modified_title, flags=re.IGNORECASE)
        
        # Fix /S01/E13/ format to /S01E13/ (remove middle slash)
        modified_title = re.sub(r'/S(\d{1,2})/E(\d{1,2})/', r'/S\1E\2/', modified_title, flags=re.IGNORECASE)
        
        # Clean up double slashes that may result from removals
        modified_title = re.sub(r'/+', '/', modified_title)
        
        # Clean up trailing/leading slashes in parentheses like (2025//)
        modified_title = re.sub(r'/+\)', ')', modified_title)
        modified_title = re.sub(r'\(/+', '(', modified_title)
        
        return modified_title
    
    def _transform_season_format(self, title: str) -> str:
        """Transform Spanish season format to *arr compatible format"""
        # Ordinals mapping
        ordinals = {
            'primera': '01', 'segunda': '02', 'tercera': '03', 'cuarta': '04',
            'quinta': '05', 'sexta': '06', 'séptima': '07', 'septima': '07',
            'octava': '08', 'novena': '09', 'décima': '10', 'decima': '10'
        }
        
        # Pattern 1: "Serie - [Ordinal] temporada (año/info)"
        # Example: "30 Monedas - Segunda temporada (2023/HMAX/WEB-DL/...)"
        pattern1 = r'^(.+?)\s*-\s*(primera|segunda|tercera|cuarta|quinta|sexta|s[eé]ptima|octava|novena|d[eé]cima)\s+temporada\s*\((\d{4})/(.*?)\)$'
        match = re.match(pattern1, title, re.IGNORECASE)
        if match:
            series_name = match.group(1).strip()
            ordinal = match.group(2).lower()
            year = match.group(3)
            info = match.group(4).strip()
            season_num = ordinals.get(ordinal, '01')
            return f"{series_name} S{season_num} [{info}]"
        
        # Pattern 2: "Serie - Temporada N (año/info)"
        # Example: "Serie - Temporada 2 (2023/WEB-DL/...)"
        pattern2 = r'^(.+?)\s*-\s*temporada\s+(\d{1,2})\s*\((\d{4})/(.*?)\)$'
        match = re.match(pattern2, title, re.IGNORECASE)
        if match:
            series_name = match.group(1).strip()
            season_num = match.group(2).zfill(2)
            year = match.group(3)
            info = match.group(4).strip()
            return f"{series_name} S{season_num} [{info}]"
        
        # Pattern 3: "Serie - [Ordinal] temporada (año) info sin slash"
        # Example: "30 monedas - Temporada 2 (2020) Full BluRay..."
        pattern3 = r'^(.+?)\s*-\s*(primera|segunda|tercera|cuarta|quinta|sexta|s[eé]ptima|octava|novena|d[eé]cima)\s+temporada\s*\((\d{4})\)\s+(.+)$'
        match = re.match(pattern3, title, re.IGNORECASE)
        if match:
            series_name = match.group(1).strip()
            ordinal = match.group(2).lower()
            year = match.group(3)
            info = match.group(4).strip()
            season_num = ordinals.get(ordinal, '01')
            return f"{series_name} S{season_num} [{info}]"
        
        # Pattern 4: "Serie - Temporada N (año) info sin slash"
        # Example: "30 monedas - Temporada 2 (2020) Full BluRay..."
        pattern4 = r'^(.+?)\s*-\s*temporada\s+(\d{1,2})\s*\((\d{4})\)\s+(.+)$'
        match = re.match(pattern4, title, re.IGNORECASE)
        if match:
            series_name = match.group(1).strip()
            season_num = match.group(2).zfill(2)
            year = match.group(3)
            info = match.group(4).strip()
            return f"{series_name} S{season_num} [{info}]"
        
        # No match, return original
        return title
    
    def parse_season_episode(self) -> tuple[Optional[int], Optional[int]]:
        """Parse season and episode from title"""
        title_upper = self.title.upper()
        
        # Patterns: S01E01, /S01/E01/, 1x01, Season 1 Episode 1
        patterns = [
            r'/S(\d{1,2})/E(\d{1,2})/',  # /S01/E01/ (xBytesV2 format)
            r'S(\d{1,2})E(\d{1,2})',  # S01E01
            r'(\d{1,2})X(\d{1,2})',   # 1x01
            r'SEASON[\s]+(\d{1,2})[\s]+EPISODE[\s]+(\d{1,2})',  # Season 1 Episode 1
            r'TEMPORADA[\s]+(\d{1,2})[\s]+CAPITULO[\s]+(\d{1,2})',  # Temporada 1 Capitulo 1
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title_upper)
            if match:
                return int(match.group(1)), int(match.group(2))
        
        return None, None
    
    def parse_season_only(self) -> Optional[int]:
        """Parse season from title (for full season packs)"""
        title_upper = self.title.upper()
        
        # Handle Spanish ordinals first (más específico)
        ordinals = {
            'PRIMERA': 1, 'SEGUNDA': 2, 'TERCERA': 3, 'CUARTA': 4,
            'QUINTA': 5, 'SEXTA': 6, 'SEPTIMA': 7, 'OCTAVA': 8,
            'NOVENA': 9, 'DECIMA': 10
        }
        
        for ordinal, num in ordinals.items():
            if f'{ordinal} TEMPORADA' in title_upper:
                return num
        
        # Numeric patterns
        patterns = [
            r'/S(\d{1,2})/',  # /S01/ (xBytesV2 format)
            r'S(\d{1,2})(?:[^E\d]|$)',  # S01 followed by non-digit/non-E or end
            r'SEASON[\s]+(\d{1,2})',  # Season 1
            r'TEMPORADA[\s]+(\d{1,2})',  # Temporada 1
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title_upper)
            if match:
                return int(match.group(1))
        
        return None


class SearchRequest(BaseModel):
    """Search request model"""
    query: Optional[str] = None
    category: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    season: Optional[int] = None
    limit: int = 100
    offset: int = 0
