
"""
Analysis API routes with database integration
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
import pandas as pd
import uuid
import os
import json
import logging

from app.core.database import get_db
from app.core.security import get_current_active_user, get_current_user_optional
from app.schemas.auth import UserResponse
from app.schemas.analysis import (
    AnalysisCreate, AnalysisUpdate, AnalysisResponse, 
    ColumnProfileCreate, ColumnProfileUpdate, ColumnProfileResponse,
    FileUploadResponse, RateCalculationRequest, RateCalculationResponse
)
from app.core.config import settings
from app.services.processor import process_data, calculate_rates, suggest_column_mapping
from app.services.results_visualization import generate_all_visualizations
from app.services.download import to_csv, to_excel, to_pdf

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Upload a file for analysis"""
    try:
        # Validate file extension
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Use {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )
        
        # Create analysis record
        analysis = await db.analysis.create(
            data={
                "userId": current_user.id,
                "fileName": file.filename,
                "fileSize": 0,  # Will update after saving
                "status": "PENDING"
            }
        )
        
        # Save file
        file_path = settings.UPLOAD_DIR / f"{analysis.id}.{file_ext}"
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Update analysis with file info
        file_size = len(contents)
        analysis = await db.analysis.update(
            where={"id": analysis.id},
            data={
                "fileSize": file_size,
                "filePath": str(file_path)
            }
        )
        
        # Read file to get columns
        try:
            if file_ext == "csv":
                df = pd.read_csv(file_path, encoding='utf-8')
            else:
                df = pd.read_excel(file_path)
            
            columns = df.columns.tolist()
            suggested_mappings = suggest_column_mapping(df)
            
            # Log file upload
            await db.auditlog.create(
                data={
                    "userId": current_user.id,
                    "action": "FILE_UPLOADED",
                    "details": json.dumps({
                        "analysisId": analysis.id,
                        "fileName": file.filename,
                        "fileSize": file_size
                    })
                }
            )
            
            logger.info(f"File uploaded by user {current_user.email}: {file.filename}")
            
            return FileUploadResponse(
                analysisId=analysis.id,
                fileName=file.filename,
                fileSize=file_size,
                columns=columns,
                suggestedMappings=suggested_mappings,
                message="File uploaded successfully"
            )
            
        except Exception as e:
            # Clean up file and analysis on error
            if file_path.exists():
                os.remove(file_path)
            await db.analysis.delete(where={"id": analysis.id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/map-columns/{analysis_id}")
async def map_columns(
    analysis_id: str,
    column_mapping: Dict[str, str],
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Map columns for an analysis"""
    try:
        # Get analysis
        analysis = await db.analysis.find_unique(
            where={"id": analysis_id, "userId": current_user.id}
        )
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        # Update analysis with column mapping
        analysis = await db.analysis.update(
            where={"id": analysis_id},
            data={
                "columnMapping": json.dumps(column_mapping),
                "status": "PROCESSING"
            }
        )
        
        # Process data with mapped columns
        if analysis.filePath:
            try:
                data = process_data(analysis.filePath, column_mapping)
                
                # Update status to completed
                await db.analysis.update(
                    where={"id": analysis_id},
                    data={"status": "COMPLETED"}
                )
                
                logger.info(f"Columns mapped for analysis {analysis_id}")
                return {"message": "Columns mapped successfully", "rowCount": len(data)}
                
            except Exception as e:
                # Update status to failed
                await db.analysis.update(
                    where={"id": analysis_id},
                    data={
                        "status": "FAILED",
                        "errorMessage": str(e)
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error processing data: {str(e)}"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file found for analysis"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error mapping columns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/process", response_model=RateCalculationResponse)
async def process_analysis(
    request: RateCalculationRequest,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Process rate calculation for an analysis"""
    try:
        # Get analysis
        analysis = await db.analysis.find_unique(
            where={"id": request.analysisId, "userId": current_user.id}
        )
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        if not analysis.filePath or not analysis.columnMapping:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Analysis not ready for processing"
            )
        
        # Get user settings for advanced calculation
        user_settings = await db.usersettings.find_unique(where={"userId": current_user.id})
        
        # Process data
        column_mapping = json.loads(analysis.columnMapping) if analysis.columnMapping else {}
        data = process_data(analysis.filePath, column_mapping)
        
        # Prepare calculation criteria
        if request.useAdvancedSettings and user_settings:
            calculation_criteria = {
                'markup_percentage': request.markupPercent or user_settings.defaultMarkup,
                'fuel_surcharge_percentage': user_settings.fuelSurcharge,
                'das_surcharge': user_settings.dasSurcharge,
                'edas_surcharge': user_settings.edasSurcharge,
                'remote_surcharge': user_settings.remoteSurcharge,
                'dim_divisor': user_settings.dimDivisor,
                'service_level_markups': {
                    "standard": user_settings.standardMarkup,
                    "expedited": user_settings.expeditedMarkup,
                    "priority": user_settings.priorityMarkup,
                    "next_day": user_settings.nextDayMarkup
                }
            }
        else:
            calculation_criteria = {
                'markup_percentage': request.markupPercent or 10.0,
                'fuel_surcharge_percentage': request.fuelSurcharge,
                'das_surcharge': 1.98,
                'edas_surcharge': 3.92,
                'remote_surcharge': 14.15,
                'dim_divisor': 139.0
            }
        
        # Calculate rates
        results = calculate_rates(
            data,
            request.amazonRate,
            request.fuelSurcharge / 100,  # Convert to decimal
            calculation_criteria.get('markup_percentage', 10.0),
            request.serviceLevel,
            calculation_criteria
        )
        
        # Calculate summary
        total_current = sum(r.get("current_rate", 0) or 0 for r in results)
        total_amazon = sum(r.get("amazon_rate", 0) or 0 for r in results)
        total_savings = sum(r.get("savings", 0) or 0 for r in results)
        percent_savings = 0
        if total_current > 0:
            percent_savings = round((total_savings / total_current) * 100, 2)
        
        summary = {
            "total_packages": len(results),
            "total_current_cost": total_current,
            "total_amazon_cost": total_amazon,
            "total_savings": total_savings,
            "percent_savings": percent_savings
        }
        
        # Generate visualizations
        visualizations = None
        if results and "error_message" not in results[0]:
            try:
                visualizations = generate_all_visualizations(results)
            except Exception as e:
                logger.warning(f"Error generating visualizations: {e}")
        
        # Update analysis with results
        await db.analysis.update(
            where={"id": request.analysisId},
            data={
                "amazonRate": request.amazonRate,
                "fuelSurcharge": request.fuelSurcharge,
                "serviceLevel": request.serviceLevel,
                "markupPercent": request.markupPercent,
                "totalPackages": summary["total_packages"],
                "totalCurrentCost": summary["total_current_cost"],
                "totalAmazonCost": summary["total_amazon_cost"],
                "totalSavings": summary["total_savings"],
                "percentSavings": summary["percent_savings"],
                "status": "COMPLETED",
                "completedAt": "now()"
            }
        )
        
        # Log analysis completion
        await db.auditlog.create(
            data={
                "userId": current_user.id,
                "action": "ANALYSIS_COMPLETED",
                "details": json.dumps({
                    "analysisId": request.analysisId,
                    "totalSavings": summary["total_savings"],
                    "percentSavings": summary["percent_savings"]
                })
            }
        )
        
        logger.info(f"Analysis completed for user {current_user.email}: {request.analysisId}")
        
        return RateCalculationResponse(
            analysisId=request.analysisId,
            results=results,
            summary=summary,
            visualizations=visualizations
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing analysis: {e}")
        # Update analysis status to failed
        try:
            await db.analysis.update(
                where={"id": request.analysisId},
                data={
                    "status": "FAILED",
                    "errorMessage": str(e)
                }
            )
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/results/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis_results(
    analysis_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Get analysis results"""
    try:
        analysis = await db.analysis.find_unique(
            where={"id": analysis_id, "userId": current_user.id}
        )
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        return AnalysisResponse.model_validate(analysis)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/export/{analysis_id}/{format}")
async def export_analysis(
    analysis_id: str,
    format: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Export analysis results"""
    try:
        # Get analysis
        analysis = await db.analysis.find_unique(
            where={"id": analysis_id, "userId": current_user.id}
        )
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        if analysis.status != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Analysis not completed"
            )
        
        # Re-process data to get results for export
        if not analysis.filePath or not analysis.columnMapping:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Analysis data not available"
            )
        
        # Get user settings
        user_settings = await db.usersettings.find_unique(where={"userId": current_user.id})
        
        # Re-calculate results
        data = process_data(analysis.filePath, analysis.columnMapping)
        
        calculation_criteria = {
            'markup_percentage': analysis.markupPercent or (user_settings.defaultMarkup if user_settings else 10.0),
            'fuel_surcharge_percentage': analysis.fuelSurcharge or (user_settings.fuelSurcharge if user_settings else 16.0),
            'das_surcharge': user_settings.dasSurcharge if user_settings else 1.98,
            'edas_surcharge': user_settings.edasSurcharge if user_settings else 3.92,
            'remote_surcharge': user_settings.remoteSurcharge if user_settings else 14.15,
            'dim_divisor': user_settings.dimDivisor if user_settings else 139.0
        }
        
        results = calculate_rates(
            data,
            analysis.amazonRate or 0.50,
            (analysis.fuelSurcharge or 16.0) / 100,
            calculation_criteria['markup_percentage'],
            analysis.serviceLevel or "standard",
            calculation_criteria
        )
        
        # Export based on format
        if format.lower() == "csv":
            output, media_type, filename = to_csv(results)
        elif format.lower() == "excel":
            output, media_type, filename = to_excel(results)
        elif format.lower() == "pdf":
            output, media_type, filename = to_pdf(results)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format: {format}"
            )
        
        # Log export
        await db.auditlog.create(
            data={
                "userId": current_user.id,
                "action": "ANALYSIS_EXPORTED",
                "details": json.dumps({
                    "analysisId": analysis_id,
                    "format": format
                })
            }
        )
        
        return StreamingResponse(
            output,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/", response_model=List[AnalysisResponse])
async def get_user_analyses(
    skip: int = 0,
    limit: int = 100,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Get user's analysis history"""
    try:
        analyses = await db.analysis.find_many(
            where={"userId": current_user.id},
            skip=skip,
            take=limit,
            order_by={"createdAt": "desc"}
        )
        
        return [AnalysisResponse.model_validate(analysis) for analysis in analyses]
        
    except Exception as e:
        logger.error(f"Error getting user analyses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

# Column Profile endpoints
@router.post("/profiles", response_model=ColumnProfileResponse)
async def create_column_profile(
    profile_data: ColumnProfileCreate,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Create a new column profile"""
    try:
        profile = await db.columnprofile.create(
            data={
                "userId": current_user.id,
                "name": profile_data.name,
                "description": profile_data.description,
                "mapping": json.dumps(profile_data.mapping),
                "isPublic": profile_data.isPublic
            }
        )
        
        logger.info(f"Column profile created by user {current_user.email}: {profile_data.name}")
        return ColumnProfileResponse.model_validate(profile)
        
    except Exception as e:
        logger.error(f"Error creating column profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/profiles", response_model=List[ColumnProfileResponse])
async def get_column_profiles(
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Get user's column profiles"""
    try:
        profiles = await db.columnprofile.find_many(
            where={
                "OR": [
                    {"userId": current_user.id},
                    {"isPublic": True}
                ]
            },
            order_by={"createdAt": "desc"}
        )
        
        return [ColumnProfileResponse.model_validate(profile) for profile in profiles]
        
    except Exception as e:
        logger.error(f"Error getting column profiles: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/profiles/{profile_id}", response_model=ColumnProfileResponse)
async def get_column_profile(
    profile_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Get a specific column profile"""
    try:
        profile = await db.columnprofile.find_unique(
            where={
                "id": profile_id,
                "OR": [
                    {"userId": current_user.id},
                    {"isPublic": True}
                ]
            }
        )
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Column profile not found"
            )
        
        return ColumnProfileResponse.model_validate(profile)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting column profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.put("/profiles/{profile_id}", response_model=ColumnProfileResponse)
async def update_column_profile(
    profile_id: str,
    profile_data: ColumnProfileUpdate,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Update a column profile"""
    try:
        # Check if profile exists and belongs to user
        existing_profile = await db.columnprofile.find_unique(
            where={"id": profile_id, "userId": current_user.id}
        )
        
        if not existing_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Column profile not found"
            )
        
        profile = await db.columnprofile.update(
            where={"id": profile_id},
            data=profile_data.model_dump(exclude_unset=True)
        )
        
        logger.info(f"Column profile updated by user {current_user.email}: {profile_id}")
        return ColumnProfileResponse.model_validate(profile)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating column profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.delete("/profiles/{profile_id}")
async def delete_column_profile(
    profile_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Delete a column profile"""
    try:
        # Check if profile exists and belongs to user
        existing_profile = await db.columnprofile.find_unique(
            where={"id": profile_id, "userId": current_user.id}
        )
        
        if not existing_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Column profile not found"
            )
        
        await db.columnprofile.delete(where={"id": profile_id})
        
        logger.info(f"Column profile deleted by user {current_user.email}: {profile_id}")
        return {"message": "Column profile deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting column profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
