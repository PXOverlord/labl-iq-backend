from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import pandas as pd
import uuid
import os
import json
from typing import List, Dict, Optional
import logging

from app.core.config import settings
from app.services.processor import process_data, calculate_rates, suggest_column_mapping
from app.services.results_visualization import generate_all_visualizations
from app.services.profiles import save_profile, load_profile, list_profiles, delete_profile

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

# Store session data (in a real app, use a proper database)
sessions = {}

@router.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
):
    """Handle file upload and return column mapping interface"""
    # Validate file extension
    file_ext = file.filename.split(".")[-1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Use {', '.join(settings.ALLOWED_EXTENSIONS)}")
    
    # Create session ID
    session_id = str(uuid.uuid4())
    
    # Save file
    file_path = settings.UPLOAD_DIR / f"{session_id}.{file_ext}"
    with open(file_path, "wb") as f:
        contents = await file.read()
        f.write(contents)
    
    # Read file to get columns
    try:
        if file_ext == "csv":
            # Try with different encodings and delimiters
            try:
                # First try standard CSV
                df = pd.read_csv(file_path, encoding='utf-8')
            except Exception as e:
                logger = logging.getLogger("labl_iq.routes")
                logger.warning(f"Error reading CSV with default settings: {str(e)}")
                
                # If standard fails, try with different encodings and delimiters
                try:
                    df = pd.read_csv(file_path, encoding='latin1')
                except Exception:
                    try:
                        # Try with explicit delimiter
                        df = pd.read_csv(file_path, encoding='utf-8', delimiter=',', skipinitialspace=True)
                    except Exception:
                        # Last resort - very flexible reading
                        df = pd.read_csv(file_path, encoding='cp1252', sep=None, engine='python')
            
            # Log the columns for debugging
            logger = logging.getLogger("labl_iq.routes")
            logger.info(f"Successfully read CSV with columns: {df.columns.tolist()}")
        else:
            df = pd.read_excel(file_path)
        
        columns = df.columns.tolist()
        
        # Generate suggested column mappings
        suggested_mappings = suggest_column_mapping(df)
        
        # Store session data
        sessions[session_id] = {
            "file_path": str(file_path),
            "columns": columns,
            "mapped_columns": {},
            "suggested_mappings": suggested_mappings,
            "data": None
        }
        
        # Get saved profiles
        profiles = list_profiles()
        
        # Return column mapping interface
        return templates.TemplateResponse(
            "mapping.html", 
            {
                "request": request,
                "columns": columns,
                "session_id": session_id,
                "required_fields": [
                    "weight", "length", "width", "height", 
                    "from_zip", "to_zip", "carrier", "rate"
                ],
                "suggested_mappings": suggested_mappings,
                "profiles": profiles
            }
        )
    except Exception as e:
        # Clean up file on error
        if file_path.exists():
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@router.get("/profiles", response_class=HTMLResponse)
async def get_profiles(request: Request):
    """Get list of saved column mapping profiles"""
    profiles = list_profiles()
    return templates.TemplateResponse(
        "profiles.html",
        {
            "request": request,
            "profiles": profiles
        }
    )

@router.post("/profiles/save")
async def save_mapping_profile(
    profile_name: str = Form(...),
    mapping: str = Form(...)
):
    """Save a column mapping profile"""
    try:
        # Parse mapping JSON
        mapped_columns = json.loads(mapping)
        
        # Save profile
        success = save_profile(profile_name, mapped_columns)
        
        if success:
            return {"status": "success", "message": f"Profile '{profile_name}' saved successfully"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to save profile '{profile_name}'")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving profile: {str(e)}")

@router.get("/profiles/list")
async def list_mapping_profiles():
    """List all saved column mapping profiles"""
    profiles = list_profiles()
    return {"profiles": profiles}

@router.get("/profiles/{profile_name}")
async def get_mapping_profile(profile_name: str):
    """Get a specific column mapping profile"""
    mapping = load_profile(profile_name)
    
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    
    return {"name": profile_name, "mapping": mapping}

@router.delete("/profiles/{profile_name}")
async def delete_mapping_profile(profile_name: str):
    """Delete a column mapping profile"""
    success = delete_profile(profile_name)
    
    if success:
        return {"status": "success", "message": f"Profile '{profile_name}' deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")

@router.post("/map-columns", response_class=HTMLResponse)
async def map_columns(
    request: Request,
    session_id: str = Form(...),
    mapping: str = Form(...),
    save_as_profile: Optional[str] = Form(None)
):
    """Process column mapping and return rate calculation interface"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Parse mapping JSON
    try:
        # Check if mapping string is empty or malformed
        if not mapping or mapping.isspace():
            logger = logging.getLogger("labl_iq.routes")
            logger.error(f"Empty mapping provided for session {session_id}")
            
            # Provide a default mapping for weight if we know the columns
            columns = sessions[session_id].get("columns", [])
            suggested_mappings = sessions[session_id].get("suggested_mappings", {})
            
            # Look for weight column as a fallback
            default_mapping = {}
            if "weight" in suggested_mappings:
                default_mapping["weight"] = suggested_mappings["weight"]
            elif "Weight (lbs)" in columns:
                default_mapping["weight"] = "Weight (lbs)"
            elif any(c.lower().startswith("weight") for c in columns):
                # Find first column that starts with 'weight'
                for col in columns:
                    if col.lower().startswith("weight"):
                        default_mapping["weight"] = col
                        break
            
            if default_mapping:
                logger.info(f"Using default mapping for session {session_id}: {default_mapping}")
                mapping = json.dumps(default_mapping)
            else:
                raise ValueError("Empty mapping provided and no default mapping could be determined")
            
        mapped_columns = json.loads(mapping)
        if not mapped_columns:
            logger = logging.getLogger("labl_iq.routes")
            logger.error(f"No column mappings provided for session {session_id}")
            
            # If we still have an empty mapping, use the same default logic as above
            columns = sessions[session_id].get("columns", [])
            suggested_mappings = sessions[session_id].get("suggested_mappings", {})
            
            # Look for weight column as a fallback
            default_mapping = {}
            if "weight" in suggested_mappings:
                default_mapping["weight"] = suggested_mappings["weight"]
            elif "Weight (lbs)" in columns:
                default_mapping["weight"] = "Weight (lbs)"
            elif any(c.lower().startswith("weight") for c in columns):
                # Find first column that starts with 'weight'
                for col in columns:
                    if col.lower().startswith("weight"):
                        default_mapping["weight"] = col
                        break
            
            if default_mapping:
                logger.info(f"Using default mapping for session {session_id}: {default_mapping}")
                mapped_columns = default_mapping
            else:
                raise ValueError("No column mappings provided and no default mapping could be determined")
            
        sessions[session_id]["mapped_columns"] = mapped_columns
        
        # Save as profile if requested
        if save_as_profile:
            save_profile(save_as_profile, mapped_columns)
        
        # Process data with mapped columns
        file_path = sessions[session_id]["file_path"]
        data = process_data(file_path, mapped_columns)
        sessions[session_id]["data"] = data
        
        # Return rate calculation interface
        return templates.TemplateResponse(
            "calculate.html", 
            {
                "request": request,
                "session_id": session_id,
                "sample_data": data.head(5).to_dict('records') if len(data) > 0 else [],
                "row_count": len(data)
            }
        )
    except json.JSONDecodeError as e:
        # Return to mapping page with error
        columns = sessions[session_id].get("columns", [])
        suggested_mappings = sessions[session_id].get("suggested_mappings", {})
        
        return templates.TemplateResponse(
            "mapping.html", 
            {
                "request": request,
                "columns": columns,
                "session_id": session_id,
                "required_fields": [
                    "weight", "length", "width", "height", 
                    "from_zip", "to_zip", "carrier", "rate"
                ],
                "suggested_mappings": suggested_mappings,
                "profiles": list_profiles(),
                "error": f"Error parsing column mapping data: {str(e)}"
            },
            status_code=400
        )
    except Exception as e:
        # Log the error for debugging
        logger = logging.getLogger("labl_iq.routes")
        logger.error(f"Error in map-columns: {str(e)}", exc_info=True)
        
        # Return to mapping page with error
        columns = sessions[session_id].get("columns", [])
        suggested_mappings = sessions[session_id].get("suggested_mappings", {})
        
        return templates.TemplateResponse(
            "mapping.html", 
            {
                "request": request,
                "columns": columns,
                "session_id": session_id,
                "required_fields": [
                    "weight", "length", "width", "height", 
                    "from_zip", "to_zip", "carrier", "rate"
                ],
                "suggested_mappings": suggested_mappings,
                "profiles": list_profiles(),
                "error": f"Error mapping columns: {str(e)}"
            },
            status_code=400
        )

@router.post("/calculate-rates", response_class=HTMLResponse)
async def calculate_rate_analysis(
    request: Request,
    session_id: str = Form(...),
    amazon_rate: float = Form(settings.DEFAULT_AMAZON_RATE),
    fuel_surcharge: float = Form(settings.DEFAULT_FUEL_SURCHARGE),
    service_level: str = Form("standard"),
    markup_percent: float = Form(None),
    use_advanced_settings: bool = Form(True)
):
    """Calculate Amazon rates and compare with current rates"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if sessions[session_id].get("data") is None:
        logger = logging.getLogger("labl_iq.routes")
        logger.error(f"Session {session_id} has no data")
        # Create error message to display to user
        error_message = "No data found in session. Please go back and map your columns properly."
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_title": "Missing Data",
                "error_message": error_message,
                "back_url": "/"
            }
        )
    
    try:
        # Get data from session
        data = sessions[session_id]["data"]
        logger = logging.getLogger("labl_iq.routes")
        logger.info(f"Calculating rates for session {session_id}, data shape: {data.shape}")
        
        # Check if we have any data
        if data.empty:
            logger.error(f"Empty data frame for session {session_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error_title": "Empty Dataset",
                    "error_message": "The processed dataset is empty. Please check your file and column mappings.",
                    "back_url": "/"
                }
            )
        
        # Log available columns
        logger.info(f"Available columns in data: {data.columns.tolist()}")
        
        # Use advanced settings if requested
        if use_advanced_settings:
            # Import global settings from main
            from main import global_settings
            
            # Create calculation criteria from global settings
            calculation_criteria = {
                'markup_percentage': global_settings.markup_percentage if markup_percent is None else markup_percent,
                'fuel_surcharge_percentage': global_settings.fuel_surcharge_percentage,
                'das_surcharge': global_settings.das_surcharge,
                'edas_surcharge': global_settings.edas_surcharge,
                'remote_surcharge': global_settings.remote_surcharge,
                'dim_divisor': global_settings.dim_divisor,
                'service_level_markups': global_settings.service_level_markups
            }
        else:
            # Use basic settings
            calculation_criteria = {
                'markup_percentage': markup_percent if markup_percent is not None else 10.0,
                'fuel_surcharge_percentage': fuel_surcharge * 100,  # Convert decimal to percentage
                'das_surcharge': 1.98,
                'edas_surcharge': 3.92,
                'remote_surcharge': 14.15,
                'dim_divisor': 139.0
            }
        
        # Calculate rates with criteria
        results = calculate_rates(
            data, 
            amazon_rate, 
            fuel_surcharge,
            calculation_criteria.get('markup_percentage', 10.0), 
            service_level,
            calculation_criteria
        )
        
        # Check if results are empty (should never happen with our fixes)
        if not results:
            logger.error(f"No results returned for session {session_id}")
            results = [{
                "package_id": "ERROR",
                "error_message": "No results were calculated. Please try again with different settings.",
                "weight": 0,
                "dimensions": "0x0x0",
                "from_zip": "N/A",
                "to_zip": "N/A",
                "carrier": "Unknown",
                "current_rate": 0,
                "amazon_rate": 0,
                "billable_weight": 0,
                "zone": "Unknown",
                "savings": 0,
                "savings_percent": 0,
                "errors": "No results calculated"
            }]

        # Calculate summary stats, handling case where errors might be present
        total_current = sum(r.get("current_rate", 0) or 0 for r in results)
        total_amazon = sum(r.get("amazon_rate", 0) or 0 for r in results)
        total_savings = sum(r.get("savings", 0) or 0 for r in results)
        
        # Calculate percent savings safely
        percent_savings = 0
        if total_current > 0:
            percent_savings = round((total_savings / total_current) * 100, 2)
        
        # Generate visualizations (if we have results with no major errors)
        if results and "error_message" not in results[0]:
            try:
                visualizations = generate_all_visualizations(results)
            except Exception as e:
                logger.error(f"Error generating visualizations: {str(e)}", exc_info=True)
                visualizations = {}
        else:
            visualizations = {}
        
        # Store results in session for later download
        sessions[session_id]["results"] = results
        
        # Return results visualization
        return templates.TemplateResponse(
            "results.html", 
            {
                "request": request,
                "session_id": session_id,
                "results": results,
                "summary": {
                    "total_packages": len(results),
                    "total_current_cost": total_current,
                    "total_amazon_cost": total_amazon,
                    "total_savings": total_savings,
                    "percent_savings": percent_savings
                },
                # Add visualization data
                "zone_fig": visualizations.get('zone_fig'),
                "zone_table": visualizations.get('zone_table'),
                "weight_fig": visualizations.get('weight_fig'),
                "weight_table": visualizations.get('weight_table'),
                "surcharge_fig": visualizations.get('surcharge_fig'),
                "surcharge_table": visualizations.get('surcharge_table')
            }
        )
    except Exception as e:
        logger = logging.getLogger("labl_iq.routes")
        logger.error(f"Error calculating rates: {str(e)}", exc_info=True)
        
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_title": "Rate Calculation Error",
                "error_message": f"An error occurred during rate calculation: {str(e)}",
                "back_url": "/"
            }
        )

@router.get("/download-results/{session_id}/{format}")
async def download_results(session_id: str, format: str):
    """
    Generate and download results in the specified format
    
    Args:
        session_id: Session ID to identify the data
        format: Format to download (csv, excel, pdf)
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Import the download service
    from app.services.download import to_csv, to_excel, to_pdf
    
    # Get results from session
    results = sessions.get(session_id, {}).get("results", [])
    
    if not results:
        raise HTTPException(status_code=404, detail="No results found for this session")
    
    try:
        # Generate the appropriate file based on the requested format
        if format.lower() == "csv":
            output, media_type, filename = to_csv(results)
            return StreamingResponse(output, media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})
        
        elif format.lower() == "excel":
            output, media_type, filename = to_excel(results)
            return StreamingResponse(output, media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})
        
        elif format.lower() == "pdf":
            output, media_type, filename = to_pdf(results)
            return StreamingResponse(output, media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating download: {str(e)}")



# Import the advanced settings models
from app.models.advanced_settings import AdvancedSettings, SettingsResponse

# Global settings store (in a real app, use a database)
# Initialize with default values
global_settings = AdvancedSettings(
    markup_percentage=10.0,
    service_level_markups={
        "standard": 0.0,
        "expedited": 10.0,
        "priority": 15.0,
        "next_day": 25.0
    },
    das_surcharge=1.98,
    edas_surcharge=3.92,
    remote_surcharge=14.15,
    fuel_surcharge_percentage=16.0,
    dim_divisor=139.0
)

@router.get("/api/settings", response_model=SettingsResponse)
async def get_settings():
    """Get the current advanced settings"""
    return SettingsResponse(settings=global_settings)

@router.post("/api/settings", response_model=SettingsResponse)
async def update_settings(settings: AdvancedSettings):
    """Update the advanced settings"""
    global global_settings
    global_settings = settings
    return SettingsResponse(
        settings=global_settings,
        message="Settings updated successfully"
    )

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Render the settings configuration page"""
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": global_settings.model_dump()
        }
    )
