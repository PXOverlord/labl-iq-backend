
import logging
from typing import Dict, Any
import os

logger = logging.getLogger(__name__)

# Global database instance
db = None

# Try to import Prisma, but don't fail if it's not available
try:
    from prisma import Prisma
    PRISMA_AVAILABLE = True
except Exception as e:
    logger.warning(f"Prisma not available: {e}")
    PRISMA_AVAILABLE = False

async def connect_db():
    """Connect to the database"""
    global db
    
    # Check if Prisma is available
    if not PRISMA_AVAILABLE:
        logger.warning("Prisma not available - skipping database connection")
        return
    
    # Check if DATABASE_URL is available
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL not found - skipping database connection")
        return
    
    try:
        db = Prisma()
        await db.connect()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.warning("Continuing without database connection")
        db = None

async def disconnect_db():
    """Disconnect from the database"""
    if db is None:
        logger.info("No database connection to disconnect")
        return
        
    try:
        await db.disconnect()
        logger.info("Database disconnected successfully")
    except Exception as e:
        logger.error(f"Failed to disconnect from database: {e}")

async def get_db_status() -> Dict[str, Any]:
    """Get database connection status and basic info"""
    if db is None:
        return {
            "connected": False,
            "error": "No database connection available"
        }
        
    try:
        # Try a simple query to test connectivity
        result = await db.query_raw("SELECT 1 as test")
        
        # Get basic database info
        user_count = await db.user.count()
        analysis_count = await db.analysis.count()
        
        return {
            "connected": True,
            "query_test": result[0]["test"] == 1,
            "stats": {
                "total_users": user_count,
                "total_analyses": analysis_count
            }
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "connected": False,
            "error": str(e)
        }

def get_db():
    """Get database instance for dependency injection"""
    if db is None:
        raise Exception("Database not connected")
    return db
