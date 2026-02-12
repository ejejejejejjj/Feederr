"""Network request logger for debugging"""
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque
import json


class NetworkLogger:
    """Singleton class to log HTTP requests made by scrapers"""
    
    _instance = None
    _logs: deque = deque(maxlen=100)  # Keep last 100 requests
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def log_request(
        cls,
        method: str,
        url: str,
        request_type: str,  # "tracker" or "internal"
        indexer: Optional[str] = None,
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        request_headers: Optional[Dict] = None,
        response_headers: Optional[Dict] = None,
        request_body: Optional[str] = None,
        response_body: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Log a network request"""
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "method": method,
            "url": url,
            "type": request_type,
            "indexer": indexer,
            "status": status_code,
            "duration": duration_ms,
            "request_headers": request_headers or {},
            "response_headers": response_headers or {},
            "request_body": request_body,
            "response_body": response_body,
            "error": error
        }
        
        instance = cls()
        instance._logs.appendleft(log_entry)
    
    @classmethod
    def get_logs(cls, limit: int = 50) -> List[Dict]:
        """Get recent network logs"""
        instance = cls()
        logs = list(instance._logs)[:limit]
        return logs
    
    @classmethod
    def clear_logs(cls):
        """Clear all logs"""
        instance = cls()
        instance._logs.clear()


# Global singleton instance
network_logger = NetworkLogger()
