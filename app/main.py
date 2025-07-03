import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
import argparse
import sys
import logging

from app.core.config import settings
from app.core.database import connect_db, disconnect_db
from app.api.routes import router as legacy_router
from app.api.auth import router as auth_router
from app.api.analysis import router as analysis_router
from app.api.admin import router as admin_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting up Labl IQ Rate Analyzer API...")
    try:
        await connect_db()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.warning("Continuing without database connection - some features may be limited")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Labl IQ Rate Analyzer API...")
    try:
        await disconnect_db()
        logger.info("Database disconnected successfully")
    except Exception as e:
        logger.error(f"Failed to disconnect from database: {e}")

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Amazon shipping rate analysis API with authentication and database integration",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Add CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(analysis_router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

# Include health check router
from app.api.health import router as health_router
app.include_router(health_router, prefix="/api", tags=["Health"])

# Include legacy routes for backward compatibility
app.include_router(legacy_router, prefix="/api", tags=["Legacy"])

# Root route
@app.get("/", tags=["Root"])
async def root():
    return {
        "message": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs"
    }

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "ok", 
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Labl IQ Rate Analyzer API")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the server on")
    
    args = parser.parse_args()
    
    # Run the application
    logger.info(f"Starting {settings.APP_NAME} on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, reload=settings.DEBUG)
