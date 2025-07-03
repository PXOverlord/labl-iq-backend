
from prisma import Prisma
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Global database instance
db = Prisma()

async def connect_db():
    """Connect to the database"""
    try:
        await db.connect()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

async def disconnect_db():
    """Disconnect from the database"""
    try:
        await db.disconnect()
        logger.info("Database disconnected successfully")
    except Exception as e:
        logger.error(f"Failed to disconnect from database: {e}")
        raise

async def get_db_status() -> Dict[str, Any]:
    """Get database connection status and basic info"""
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
    return db
