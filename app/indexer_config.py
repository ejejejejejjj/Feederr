"""
Indexer Configuration Manager
Loads and manages indexer configurations from indexers.json
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, time

logger = logging.getLogger(__name__)

INDEXERS_CONFIG_FILE = Path("/app/config/indexers.json")


class IndexerConfig:
    """Manages indexer configurations"""
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load indexers configuration from JSON file"""
        if INDEXERS_CONFIG_FILE.exists():
            try:
                with open(INDEXERS_CONFIG_FILE, 'r') as f:
                    self._config = json.load(f)
                logger.info(f"Loaded {len(self._config)} indexers from config")
            except Exception as e:
                logger.error(f"Failed to load indexers config: {e}")
                self._config = {}
        else:
            logger.warning(f"Indexers config file not found: {INDEXERS_CONFIG_FILE}")
            self._config = {}
    
    def save_config(self):
        """Save configuration to JSON file"""
        try:
            INDEXERS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(INDEXERS_CONFIG_FILE, 'w') as f:
                json.dump(self._config, f, indent=2)
            logger.info("Saved indexers configuration")
        except Exception as e:
            logger.error(f"Failed to save indexers config: {e}")
    
    def create_indexer(self, indexer_id: str, name: str, url: str, username: str, password: str) -> bool:
        """Create a new indexer configuration"""
        if indexer_id in self._config:
            logger.error(f"Indexer {indexer_id} already exists")
            return False
        
        self._config[indexer_id] = {
            "id": indexer_id,
            "name": name,
            "url": url,
            "username": username,
            "password": password,
            "enabled": True,
            "indexer_type": "unit3d",
            "auto_thanks": True,
            "time_restrictions": {
                "enabled": False,
                "start_time": "10:00",
                "end_time": "23:59"
            },
            "user_agent": {
                "mode": "random",
                "list_index": 0,
                "custom_value": ""
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        self.save_config()
        logger.info(f"Created new indexer: {indexer_id}")
        return True
    
    def delete_indexer(self, indexer_id: str) -> bool:
        """Delete an indexer configuration"""
        if indexer_id not in self._config:
            logger.error(f"Indexer {indexer_id} not found in config")
            return False
        
        del self._config[indexer_id]
        self.save_config()
        logger.info(f"Deleted indexer: {indexer_id}")
        return True
    
    def update_indexer(self, indexer_id: str, config: Dict[str, Any]):
        """Update configuration for a specific indexer"""
        if indexer_id in self._config:
            self._config[indexer_id].update(config)
            self._config[indexer_id]["updated_at"] = datetime.now().isoformat()
            self.save_config()
        else:
            logger.error(f"Indexer {indexer_id} not found in config")
    
    def reload(self):
        """Reload configuration from file"""
        self._load_config()
    
    def get_indexer(self, indexer_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific indexer"""
        return self._config.get(indexer_id)
    
    def get_all_indexers(self) -> Dict[str, Any]:
        """Get all indexer configurations"""
        return self._config
    
    def get_enabled_indexers(self) -> Dict[str, Any]:
        """Get only enabled indexers - estos pueden comunicarse con el tracker"""
        return {
            key: value for key, value in self._config.items()
            if value.get("enabled", False)
        }
    
    def is_enabled(self, indexer_id: str) -> bool:
        """Check if indexer is enabled for tracker communication"""
        indexer = self.get_indexer(indexer_id)
        return indexer.get("enabled", False) if indexer else False
    
    def is_within_time_restrictions(self, indexer_id: str) -> bool:
        """Check if current time is within allowed time restrictions"""
        indexer = self.get_indexer(indexer_id)
        if not indexer:
            return False
        
        time_restrictions = indexer.get("time_restrictions", {})
        if not time_restrictions.get("enabled", False):
            return True  # No restrictions, always allowed
        
        try:
            now = datetime.now().time()
            start_str = time_restrictions.get("start_time", "10:00")
            end_str = time_restrictions.get("end_time", "23:59")
            
            start = datetime.strptime(start_str, "%H:%M").time()
            end = datetime.strptime(end_str, "%H:%M").time()
            
            # Handle cases where end time is before start time (crosses midnight)
            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end
        except Exception as e:
            logger.error(f"Error checking time restrictions for {indexer_id}: {e}")
            return True  # Default to allowed on error
    
    def can_search(self, indexer_id: str) -> bool:
        """Check if indexer can perform searches (enabled + within time restrictions)"""
        return self.is_enabled(indexer_id) and self.is_within_time_restrictions(indexer_id)
    
    def get_url(self, indexer_id: str) -> Optional[str]:
        """Get URL for indexer"""
        indexer = self.get_indexer(indexer_id)
        return indexer.get("url") if indexer else None
    
    def get_credentials(self, indexer_id: str) -> Optional[Dict[str, str]]:
        """Get credentials (username, password) for indexer"""
        indexer = self.get_indexer(indexer_id)
        if indexer:
            return {
                "username": indexer.get("username"),
                "password": indexer.get("password")
            }
        return None


# Global instance
indexer_config = IndexerConfig()
