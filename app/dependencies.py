"""Dependencies for FastAPI dependency injection"""
from typing import Optional
from app.auth import AuthManager

# Global auth manager instance
_auth_manager: Optional[AuthManager] = None


def set_auth_manager(manager: AuthManager):
    """Set the global auth manager instance"""
    global _auth_manager
    _auth_manager = manager


def get_auth_manager() -> AuthManager:
    """Get the global auth manager instance"""
    if _auth_manager is None:
        raise RuntimeError("AuthManager not initialized")
    return _auth_manager
