import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
import argparse
import sys
import logging

from .core.config import settings
from .core.database import connect_db, disconnect_db
from .api.routes import router as legacy_router
from .api.auth import router as auth_router
from .api.analysis import router as analysis_router
from .api.admin import router as admin_router
from .api.assistant import router as assistant_router

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

# Add CORS middleware for frontend
# Force permissive CORS to unblock browser calls in hosted environments.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(analysis_router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(assistant_router, prefix="/api/assistant", tags=["Assistant"])

# Include health check router
from .api.health import router as health_router
app.include_router(health_router, prefix="/api", tags=["Health"])

# Include legacy routes for backward compatibility
app.include_router(legacy_router, prefix="/api", tags=["Legacy"])

# New endpoint for frontend-controlled rate calculations
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
from fastapi import HTTPException

class ShipmentData(BaseModel):
    weight: float
    zone: Optional[int] = None
    origin_zip: Optional[str] = None
    destination_zip: Optional[str] = None
    package_type: str = "box"
    service_level: str = "standard"
    carrier_rate: float

class AnalysisRequest(BaseModel):
    shipments: List[ShipmentData]
    discount_percent: Optional[float] = 0.0
    markup_percent: Optional[float] = 0.0
    fuel_surcharge_percent: Optional[float] = 0.0
    
    # Frontend-controlled surcharge settings
    das_surcharge: Optional[float] = 1.98
    edas_surcharge: Optional[float] = 3.92
    remote_surcharge: Optional[float] = 14.15
    dim_divisor: Optional[float] = 139.0
    origin_zip: Optional[str] = "46307"

class AnalysisResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    summary: Dict[str, Any]
    message: Optional[str] = None

@app.post("/api/calculate-rates", response_model=AnalysisResponse)
async def calculate_shipment_rates(request: AnalysisRequest):
    """Calculate rates for a list of shipments using frontend-controlled settings."""
    try:
        # Import the rate calculator here to avoid circular imports
        from .services.calc_engine import AmazonRateCalculator
        
        # Initialize rate calculator
        rate_calculator = AmazonRateCalculator()
        rate_calculator.load_reference_data()
        
        # Store original settings to restore later
        original_settings = {
            'das_surcharge': rate_calculator.criteria_values.get('das_surcharge'),
            'edas_surcharge': rate_calculator.criteria_values.get('edas_surcharge'),
            'remote_surcharge': rate_calculator.criteria_values.get('remote_surcharge'),
            'dim_divisor': rate_calculator.criteria_values.get('dim_divisor'),
            'origin_zip': rate_calculator.criteria_values.get('origin_zip'),
            'markup_percentage': rate_calculator.criteria_values.get('markup_percentage'),
            'fuel_surcharge_percentage': rate_calculator.criteria_values.get('fuel_surcharge_percentage'),
        }
        
        # Temporarily override settings with frontend values
        if request.das_surcharge is not None:
            rate_calculator.criteria_values['das_surcharge'] = request.das_surcharge
        if request.edas_surcharge is not None:
            rate_calculator.criteria_values['edas_surcharge'] = request.edas_surcharge
        if request.remote_surcharge is not None:
            rate_calculator.criteria_values['remote_surcharge'] = request.remote_surcharge
        if request.dim_divisor is not None:
            rate_calculator.criteria_values['dim_divisor'] = request.dim_divisor
        if request.origin_zip is not None:
            rate_calculator.criteria_values['origin_zip'] = request.origin_zip
        if request.markup_percent is not None:
            rate_calculator.criteria_values['markup_percentage'] = request.markup_percent
        if request.fuel_surcharge_percent is not None:
            rate_calculator.criteria_values['fuel_surcharge_percentage'] = request.fuel_surcharge_percent
        
        # Convert to the format expected by the rate calculator
        shipments = []
        for shipment in request.shipments:
            shipment_dict = {
                'shipment_id': f"shipment_{len(shipments)}",
                'weight': shipment.weight,
                'package_type': shipment.package_type,
                'service_level': shipment.service_level,
                'carrier_rate': shipment.carrier_rate
            }
            
            # Always add ZIP codes for surcharge calculations, regardless of zone
            if shipment.origin_zip:
                shipment_dict['origin_zip'] = shipment.origin_zip
            if shipment.destination_zip:
                shipment_dict['destination_zip'] = shipment.destination_zip
            
            # If zone is provided, use it directly (don't calculate from ZIP)
            if shipment.zone is not None and shipment.zone > 0:
                shipment_dict['zone'] = shipment.zone
            
            shipments.append(shipment_dict)
        
        # Calculate rates using the initialized rate calculator
        results = rate_calculator.calculate_rates(
            shipments=shipments,
            discount_percent=request.discount_percent,
            markup_percent=request.markup_percent
        )
        summary = rate_calculator.get_summary_stats(results)
        
        # Restore original settings
        rate_calculator.criteria_values.update(original_settings)

        # Import sanitization utilities
        from .utils.json_sanitize import deep_clean_json_safe, contains_nan_inf

        # Sanitize the response data
        sanitized_results = deep_clean_json_safe(results)
        sanitized_summary = deep_clean_json_safe(summary)

        # Create the response content
        content = {
            "success": True,
            "results": sanitized_results,
            "summary": sanitized_summary,
            "message": "Rates calculated successfully using frontend settings"
        }

        # Final sanitization pass
        content = deep_clean_json_safe(content)
        if contains_nan_inf(content):
            logger.error("NaN/Inf detected in response content after cleaning; stripping results to avoid 500")
            content.pop("results", None)
            content.pop("summary", None)

        return content
        
    except Exception as e:
        logger.error(f"Error calculating rates: {e}")
        raise HTTPException(status_code=500, detail=f"Rate calculation failed: {str(e)}")
    finally:
        # Always restore original settings, even if there was an error
        if 'original_settings' in locals():
            rate_calculator.criteria_values.update(original_settings)

# Root route
@app.get("/", tags=["Root"])
async def root():
    # Import sanitization utilities
    from .utils.json_sanitize import deep_clean_json_safe, contains_nan_inf
    
    # Build the response content
    content = {
        "message": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs"
    }
    
    # Sanitize the response
    content = deep_clean_json_safe(content)
    if contains_nan_inf(content):
        logger.error("NaN/Inf detected in response content after cleaning")
    
    return content

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health():
    # Import sanitization utilities
    from .utils.json_sanitize import deep_clean_json_safe, contains_nan_inf
    
    # Build the response content
    content = {
        "status": "ok", 
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }
    
    # Sanitize the response
    content = deep_clean_json_safe(content)
    if contains_nan_inf(content):
        logger.error("NaN/Inf detected in response content after cleaning")
    
    return content

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Labl IQ Rate Analyzer API")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the server on")
    
    args = parser.parse_args()
    
    # Run the application
    logger.info(f"Starting {settings.APP_NAME} on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, reload=settings.DEBUG)
