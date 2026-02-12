from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging
import json
from datetime import datetime

from app.config import settings
from app.indexer_config import indexer_config
from app.dependencies import get_auth_manager
from app.network_logger import network_logger

router = APIRouter()
templates = Jinja2Templates(directory="/app/app/templates")
logger = logging.getLogger(__name__)


@router.get("/home", response_class=HTMLResponse)
async def ui_home(request: Request, auth_manager = Depends(get_auth_manager)):
    """Web UI home page"""
    
    # Get indexer statuses - TODOS los indexers, enabled y disabled
    indexers_status = []
    
    for indexer_id, config in indexer_config.get_all_indexers().items():
        status = await auth_manager.check_session_status(indexer_id)
        indexers_status.append({
            "id": indexer_id,
            "name": config.get("name", indexer_id),
            "url": config.get("url"),
            "authenticated": status.get("authenticated", False),
            "last_check": status.get("last_check"),
            "enabled": config.get("enabled", False)
        })
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "app_name": settings.app_name,
        "indexers": indexers_status,
        "api_key": settings.api_key
    })


@router.get("/home/logs", response_class=HTMLResponse)
async def ui_logs(request: Request):
    """View logs page"""
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "app_name": settings.app_name
    })


@router.get("/home/query-builder", response_class=HTMLResponse)
async def ui_query_builder(request: Request, auth_manager = Depends(get_auth_manager)):
    """Query builder page"""
    indexers_status = []
    
    # Mostrar todos los indexers
    for indexer_id, config in indexer_config.get_all_indexers().items():
        indexers_status.append({
            "id": indexer_id,
            "name": config.get("name", indexer_id),
            "enabled": config.get("enabled", False)
        })
    
    return templates.TemplateResponse("query_builder.html", {
        "request": request,
        "app_name": settings.app_name,
        "indexers": indexers_status,
        "api_key": settings.api_key
    })


@router.get("/home/api-status", response_class=HTMLResponse)
async def ui_api_status(request: Request):
    """API Status page"""
    return templates.TemplateResponse("api_status.html", {
        "request": request,
        "app_name": settings.app_name
    })


@router.get("/home/api-docs", response_class=HTMLResponse)
async def ui_api_docs(request: Request):
    """API Documentation page"""
    return templates.TemplateResponse("api_docs.html", {
        "request": request,
        "app_name": settings.app_name
    })


@router.post("/api/regenerate-key")
async def api_regenerate_key():
    """Regenerate API key"""
    try:
        from app.config import generate_api_key
        
        new_key = generate_api_key()
        key_file = Path("/app/data/api_key.txt")
        key_file.write_text(new_key)
        
        # Update settings
        settings.api_key = new_key
        
        logger.info("API key regenerated")
        return {"success": True, "api_key": new_key}
        
    except Exception as e:
        logger.error(f"Failed to regenerate API key: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to regenerate API key: {e}"}
        )


@router.get("/api/logs")
async def api_get_logs(lines: int = 100):
    """API endpoint to get logs"""
    log_file = Path("/app/logs/app.log")
    logs = []
    
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                logs = [line.strip() for line in all_lines[-lines:]]
        except Exception as e:
            logger.error(f"Failed to read logs: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to read logs: {e}"}
            )
    
    return {"logs": logs, "total": len(logs)}


@router.delete("/api/logs")
async def api_clear_logs():
    """API endpoint to clear logs"""
    log_file = Path("/app/logs/app.log")
    
    try:
        if log_file.exists():
            with open(log_file, 'w') as f:
                f.write("")
            logger.info("Logs cleared via web UI")
        return {"success": True, "message": "Logs cleared"}
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to clear logs: {e}"}
        )


@router.post("/api/indexers")
async def api_create_indexer(request: Request, auth_manager = Depends(get_auth_manager)):
    """Create a new indexer"""
    try:
        data = await request.json()
        
        # Validate required fields
        required = ["indexer_type", "username", "password"]
        if not all(field in data for field in required):
            return JSONResponse(
                status_code=400,
                content={"error": "Missing required fields: indexer_type, username, password"}
            )
        
        indexer_type = data["indexer_type"]
        username = data["username"]
        password = data["password"]
        
        # Extract additional config
        config_enabled = data.get("enabled", True)
        config_auto_thanks = data.get("auto_thanks", True)
        config_time_enabled = data.get("time_restrictions_enabled", False)
        config_start_time = data.get("start_time", "10:00")
        config_end_time = data.get("end_time", "23:59")
        
        # Mapping de tipos a URLs y IDs
        indexer_mappings = {
            "xbytesv2": {
                "id": "xbytesv2",
                "name": "xBytesV2",
                "url": "https://xbytesv2.li"
            },
            "torrentland": {
                "id": "torrentland",
                "name": "Torrentland",
                "url": "https://torrentland.li"
            }
        }
        
        if indexer_type not in indexer_mappings:
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid indexer type: {indexer_type}. Must be 'xbytesv2' or 'torrentland'"}
            )
        
        mapping = indexer_mappings[indexer_type]
        
        # Check if indexer already exists
        if indexer_config.get_indexer(mapping["id"]):
            return JSONResponse(
                status_code=409,
                content={"error": f"Indexer {mapping['name']} already exists"}
            )
        
        # VALIDATE CREDENTIALS FIRST
        logger.info(f"Validating credentials for {mapping['name']}...")
        is_valid, message = await auth_manager.validate_credentials(
            indexer_id=mapping["id"],
            url=mapping["url"],
            username=username,
            password=password
        )
        
        if not is_valid:
            logger.warning(f"Invalid credentials for {mapping['name']}: {message}")
            return JSONResponse(
                status_code=401,
                content={"error": f"Credenciales inválidas: {message}"}
            )
        
        # Credentials are valid - create indexer with config
        success = indexer_config.create_indexer(
            indexer_id=mapping["id"],
            name=mapping["name"],
            url=mapping["url"],
            username=username,
            password=password
        )
        
        if success:
            # Apply additional config
            indexer_config.update_indexer(mapping["id"], {
                "enabled": config_enabled,
                "auto_thanks": config_auto_thanks,
                "time_restrictions": {
                    "enabled": config_time_enabled,
                    "start_time": config_start_time,
                    "end_time": config_end_time
                }
            })
            logger.info(f"Created new indexer via UI: {mapping['id']} with validated credentials")
            return {"success": True, "message": f"Indexer {mapping['name']} created successfully"}
        else:
            # If failed to create, delete the cookies we just created
            auth_manager.delete_cookies(mapping["id"])
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to create indexer configuration"}
            )
        
    except Exception as e:
        logger.error(f"Failed to create indexer: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to create indexer: {e}"}
        )


@router.delete("/api/indexers/{indexer_id}")
async def api_delete_indexer(indexer_id: str, auth_manager = Depends(get_auth_manager)):
    """Delete an indexer"""
    try:
        # Check if indexer exists
        if not indexer_config.get_indexer(indexer_id):
            return JSONResponse(
                status_code=404,
                content={"error": f"Indexer {indexer_id} not found"}
            )
        
        # Delete cookies first
        auth_manager.delete_cookies(indexer_id)
        
        # Delete indexer from config
        success = indexer_config.delete_indexer(indexer_id)
        
        if success:
            logger.info(f"Deleted indexer and cookies via UI: {indexer_id}")
            return {"success": True, "message": f"Indexer {indexer_id} deleted successfully"}
        else:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to delete indexer"}
            )
        
    except Exception as e:
        logger.error(f"Failed to delete indexer: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to delete indexer: {e}"}
        )


@router.post("/api/indexers/{indexer_id}/config")
async def api_save_indexer_config(indexer_id: str, request: Request, auth_manager = Depends(get_auth_manager)):
    """Save indexer configuration to indexers.json"""
    try:
        data = await request.json()
        
        # Get current indexer config
        current_config = indexer_config.get_indexer(indexer_id)
        if not current_config:
            return JSONResponse(
                status_code=404,
                content={"error": f"Indexer {indexer_id} not found"}
            )
        
        # Check if credentials are being updated
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        
        if username or password:
            # If only one is provided, use current value for the other
            if not username:
                username = current_config.get("username")
            if not password:
                password = current_config.get("password")
            
            # Validate new credentials
            logger.info(f"Validating updated credentials for {indexer_id}...")
            is_valid, message = await auth_manager.validate_credentials(
                indexer_id=indexer_id,
                url=current_config.get("url"),
                username=username,
                password=password
            )
            
            if not is_valid:
                logger.warning(f"Invalid credentials for {indexer_id}: {message}")
                return JSONResponse(
                    status_code=401,
                    content={"error": f"Credenciales inválidas: {message}"}
                )
        
        # Update fields
        update_data = {}
        
        # Update credentials if provided
        if username:
            update_data["username"] = username
        if password:
            update_data["password"] = password
        
        # Enabled state
        if "enabled" in data:
            update_data["enabled"] = data["enabled"]
        
        # Auto thanks
        if "auto_thanks" in data:
            update_data["auto_thanks"] = data["auto_thanks"]
        
        # Time restrictions
        if any(k in data for k in ["time_restrictions_enabled", "start_time", "end_time"]):
            update_data["time_restrictions"] = {
                "enabled": data.get("time_restrictions_enabled", False),
                "start_time": data.get("start_time", "10:00"),
                "end_time": data.get("end_time", "23:59")
            }
        
        # User agent
        if any(k in data for k in ["user_agent_mode", "user_agent_list_index", "user_agent_custom_value"]):
            update_data["user_agent"] = {
                "mode": data.get("user_agent_mode", "random"),
                "list_index": int(data.get("user_agent_list_index", 0)),
                "custom_value": data.get("user_agent_custom_value", "")
            }
        
        # Update configuration
        indexer_config.update_indexer(indexer_id, update_data)
        
        logger.info(f"Saved configuration for indexer: {indexer_id}")
        return {"success": True, "message": "Configuration saved"}
        
    except Exception as e:
        logger.error(f"Failed to save indexer config: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to save configuration: {e}"}
        )


@router.get("/api/indexers/{indexer_id}/config")
async def api_get_indexer_config(indexer_id: str):
    """Get indexer configuration from indexers.json"""
    try:
        config = indexer_config.get_indexer(indexer_id)
        
        if not config:
            return JSONResponse(
                status_code=404,
                content={"error": f"Indexer {indexer_id} not found"}
            )
        
        # Return configuration WITHOUT credentials (no se pueden editar, solo al crear)
        return {
            "success": True,
            "config": {
                "enabled": config.get("enabled", False),
                "auto_thanks": config.get("auto_thanks", True),
                "time_restrictions_enabled": config.get("time_restrictions", {}).get("enabled", False),
                "start_time": config.get("time_restrictions", {}).get("start_time", "10:00"),
                "end_time": config.get("time_restrictions", {}).get("end_time", "23:59"),
                "user_agent_mode": config.get("user_agent", {}).get("mode", "random"),
                "user_agent_list_index": config.get("user_agent", {}).get("list_index", 0),
                "user_agent_custom_value": config.get("user_agent", {}).get("custom_value", "")
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get indexer config: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get configuration: {e}"}
        )


@router.get("/api/network-logs")
async def get_network_logs(limit: int = 50):
    """Get network request logs for debugging"""
    try:
        logs = network_logger.get_logs(limit=limit)
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Failed to get network logs: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get logs: {e}"}
        )


@router.delete("/api/network-logs")
async def clear_network_logs():
    """Clear network request logs"""
    try:
        network_logger.clear_logs()
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to clear network logs: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to clear logs: {e}"}
        )
