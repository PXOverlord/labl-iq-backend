
import logging
from typing import Dict, Any
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Global database instance
db = None
_connection_retry_count = 0
_max_retries = 3

# Try to import Prisma, but don't fail if it's not available
try:
    from prisma import Prisma
    PRISMA_AVAILABLE = True
except Exception as e:
    logger.warning(f"Prisma not available: {e}")
    PRISMA_AVAILABLE = False

from app.core.config import settings

async def connect_db():
    """Connect to the database with retry logic"""
    global db, _connection_retry_count
    
    # Check if Prisma is available
    if not PRISMA_AVAILABLE:
        logger.warning("Prisma not available - skipping database connection")
        return
    
    # Check if DATABASE_URL is available
    database_url = settings.DATABASE_URL
    if not database_url:
        logger.warning("DATABASE_URL not found - skipping database connection")
        return
    
    # Retry logic for database connection
    for attempt in range(_max_retries):
        try:
            logger.info(f"Attempting database connection (attempt {attempt + 1}/{_max_retries})")
            
            db = Prisma()
            await db.connect()
            
            # Test the connection
            await db.query_raw("SELECT 1 as test")
            
            logger.info("Database connected successfully")
            _connection_retry_count = 0  # Reset retry count on success
            return
            
        except Exception as e:
            _connection_retry_count += 1
            logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
            
            if attempt < _max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.error("All database connection attempts failed")
                logger.warning("Continuing without database connection - some features may be limited")
                db = None

async def disconnect_db():
    """Disconnect from the database"""
    global db
    
    if db is None:
        logger.info("No database connection to disconnect")
        return
        
    try:
        await db.disconnect()
        logger.info("Database disconnected successfully")
        db = None
    except Exception as e:
        logger.error(f"Failed to disconnect from database: {e}")

async def get_db_status() -> Dict[str, Any]:
    """Get database connection status and basic info"""
    if db is None:
        return {
            "connected": False,
            "error": "No database connection available",
            "retry_count": _connection_retry_count
        }
        
    try:
        # Try a simple query to test connectivity
        result = await db.query_raw("SELECT 1 as test")
        
        # Get basic database info
        try:
            user_count = await db.user.count()
            analysis_count = await db.analysis.count()
            
            stats = {
                "total_users": user_count,
                "total_analyses": analysis_count
            }
        except Exception as e:
            logger.warning(f"Could not get database stats: {e}")
            stats = {"error": "Could not retrieve statistics"}
        
        return {
            "connected": True,
            "query_test": result[0]["test"] == 1,
            "stats": stats,
            "retry_count": _connection_retry_count
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "connected": False,
            "error": str(e),
            "retry_count": _connection_retry_count
        }

def get_db():
    """Get database instance for dependency injection"""
    if db is None:
        raise Exception("Database not connected")
    return db

@asynccontextmanager
async def get_db_context():
    """Context manager for database operations"""
    if db is None:
        raise Exception("Database not connected")
    
    try:
        yield db
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        raise

async def ensure_db_connection():
    """Ensure database connection is available"""
    if db is None:
        await connect_db()
    
    if db is None:
        raise Exception("Could not establish database connection")

# Health check function
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check for the database"""
    status = await get_db_status()
    
    if status["connected"]:
        return {
            "status": "healthy",
            "database": "connected",
            "details": status
        }
    else:
        return {
            "status": "degraded",
            "database": "disconnected",
            "details": status
        }
