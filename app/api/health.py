
from fastapi import APIRouter
from app.core.config import settings
from app.core.database import get_db_status
import time

router = APIRouter()

@router.get("/health")
async def health_check():
    """Enhanced health check endpoint for production monitoring"""
    
    start_time = time.time()
    
    # Check database connectivity
    db_status = await get_db_status()
    
    response_time = round((time.time() - start_time) * 1000, 2)  # ms
    
    health_data = {
        "status": "ok" if db_status["connected"] else "error",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": int(time.time()),
        "response_time_ms": response_time,
        "database": db_status,
        "services": {
            "api": "ok",
            "file_upload": "ok",
            "authentication": "ok"
        }
    }
    
    # Import sanitization utilities
    from app.utils.json_sanitize import deep_clean_json_safe, contains_nan_inf
    
    # Sanitize the response
    health_data = deep_clean_json_safe(health_data)
    if contains_nan_inf(health_data):
        logger.error("NaN/Inf detected in response content after cleaning")
    
    return health_data

@router.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check for debugging"""
    
    import psutil
    import os
    
    # System metrics
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Build the response content
    content = {
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": memory.percent,
            "memory_available_mb": round(memory.available / 1024 / 1024, 2),
            "disk_percent": round((disk.used / disk.total) * 100, 2),
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 2)
        },
        "environment": {
            "python_version": os.sys.version,
            "environment": settings.ENVIRONMENT,
            "debug_mode": settings.DEBUG
        },
        "database": await get_db_status(),
        "upload_directory": {
            "exists": settings.UPLOAD_DIR.exists(),
            "writable": os.access(settings.UPLOAD_DIR, os.W_OK)
        }
    }
    
    # Import sanitization utilities
    from app.utils.json_sanitize import deep_clean_json_safe, contains_nan_inf
    
    # Sanitize the response
    content = deep_clean_json_safe(content)
    if contains_nan_inf(content):
        logger.error("NaN/Inf detected in response content after cleaning")
    
    return content
