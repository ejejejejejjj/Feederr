from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import secrets
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent

def generate_api_key() -> str:
    """Generate a secure random API key (hex format, 32 chars)"""
    return secrets.token_hex(16)  # 16 bytes = 32 hex chars


def get_or_create_api_key() -> str:
    """Get existing API key or create new one"""
    key_file = Path("/app/data/api_key.txt")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    
    if key_file.exists():
        return key_file.read_text().strip()
    
    new_key = generate_api_key()
    key_file.write_text(new_key)
    return new_key


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # General
    app_name: str = Field(default="Feederr", alias="APP_NAME")
    api_key: str = Field(default_factory=get_or_create_api_key, alias="API_KEY")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=9797, alias="PORT")
    
    # Browser
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")
    browser_timeout: int = Field(default=30000, alias="BROWSER_TIMEOUT")
    session_refresh_hours: int = Field(default=24, alias="SESSION_REFRESH_HOURS")
    
    class Config:
        # NOTE: Indexer configuration (URLs, credentials, etc.) is now managed
        # via /app/config/indexers.json and the UI - NOT from .env
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
