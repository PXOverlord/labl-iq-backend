
"""
Analysis API routes with database integration
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
import uuid
import os
import logging
import math
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from app.core.database import get_db
from app.core.security import get_current_active_user, get_current_user_optional
from app.schemas.auth import UserResponse
from app.schemas.analysis import (
    AnalysisCreate, AnalysisUpdate, AnalysisMetadataUpdate, AnalysisResponse, 
    ColumnProfileCreate, ColumnProfileUpdate, ColumnProfileResponse,
    FileUploadResponse, RateCalculationRequest, RateCalculationResponse
)
from app.core.config import settings
from app.services.processor import process_data, calculate_rates, suggest_column_mapping
from app.utils.json_sanitize import deep_clean_json_safe
from app.services.results_visualization import generate_all_visualizations
from app.services.download import to_csv, to_excel, to_pdf
# Prisma Python client expects JSON columns as serialized strings
import json

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


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_results(payload: Any, limit: int = 1000) -> List[Dict[str, Any]]:
    if not payload:
        return []
    rows: List[Dict[str, Any]] = []
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
            if isinstance(data, list):
                rows = data
        except json.JSONDecodeError:
            rows = []
    elif isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        inner = payload.get("results")
        if isinstance(inner, list):
            rows = inner
    if len(rows) > limit:
        return rows[:limit]
    return rows


def _weight_bucket(weight_value: float) -> str:
    if weight_value is None or math.isnan(weight_value):
        return "Unknown"
    if weight_value < 1:
        return "<1 lb"
    if weight_value < 5:
        return "1-4 lb"
    if weight_value < 10:
        return "5-9 lb"
    if weight_value < 20:
        return "10-19 lb"
    if weight_value < 50:
        return "20-49 lb"
    return "50+ lb"


@router.get("/compare")
async def compare_analyses(
    ids: str = Query(..., description="Comma-separated list of analysis IDs to compare"),
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Compare multiple analyses and return aggregated metrics."""
    id_list = [identifier.strip() for identifier in (ids or "").split(",") if identifier.strip()]
    if not id_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one analysis ID"
        )

    analyses = await db.analysis.find_many(
        where={
            "AND": [
                {"id": {"in": id_list}},
                {"userId": current_user.id},
            ]
        },
        order={"createdAt": "desc"},
    )

    found_map = {analysis.id: analysis for analysis in analyses}

    items: List[Dict[str, Any]] = []
    trend_points: List[Dict[str, Any]] = []
    zone_counts: Dict[int, int] = defaultdict(int)
    weight_counts: Dict[str, int] = defaultdict(int)
    merchant_aggregate: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "analyses": 0,
        "totalSavings": 0.0,
        "totalShipments": 0,
    })

    total_shipments = 0
    total_savings = 0.0
    total_current_cost = 0.0
    total_amazon_cost = 0.0

    for analysis_id in id_list:
        analysis = found_map.get(analysis_id)
        if not analysis:
            items.append({"id": analysis_id, "error": "Analysis not found"})
            continue

        data = analysis.model_dump()
        results_payload = data.get("results")
        rows = _parse_results(results_payload)

        shipments = data.get("totalPackages") or len(rows)
        shipments = int(shipments) if shipments else 0

        savings = _to_float(data.get("totalSavings"))
        current_cost = _to_float(data.get("totalCurrentCost"))
        amazon_cost = _to_float(data.get("totalAmazonCost"))
        percent_savings = _to_float(data.get("percentSavings"))
        avg_savings = savings / shipments if shipments else 0.0

        total_shipments += shipments
        total_savings += savings
        total_current_cost += current_cost
        total_amazon_cost += amazon_cost

        created_at = data.get("createdAt")
        if isinstance(created_at, datetime):
            created_iso = created_at.isoformat()
        else:
            created_iso = str(created_at) if created_at else None

        trend_points.append({
            "date": created_iso or analysis_id,
            "savings": round(savings, 2),
            "shipments": shipments,
        })

        merchant_label = data.get("merchant") or "Unassigned"
        merchant_bucket = merchant_aggregate[merchant_label]
        merchant_bucket["analyses"] += 1
        merchant_bucket["totalSavings"] += savings
        merchant_bucket["totalShipments"] += shipments

        for row in rows:
            zone_value = row.get("zone") or row.get("Zone")
            if zone_value is not None:
                try:
                    zone_int = int(zone_value)
                    zone_counts[zone_int] += 1
                except (TypeError, ValueError):
                    pass

            weight_value = row.get("weight_lbs") or row.get("weight") or row.get("Weight")
            if weight_value is not None:
                try:
                    bucket = _weight_bucket(_to_float(weight_value))
                except (TypeError, ValueError):
                    bucket = "Unknown"
            else:
                bucket = "Unknown"
            weight_counts[bucket] += 1

        items.append({
            "id": analysis.id,
            "filename": data.get("fileName") or data.get("filename"),
            "title": data.get("title"),
            "merchant": data.get("merchant"),
            "notes": data.get("notes"),
            "timestamp": created_iso,
            "totalSavings": round(savings, 2),
            "totalShipments": shipments,
            "avgSavingsPerShipment": round(avg_savings, 2),
            "percentSavings": percent_savings,
            "totalCurrentCost": round(current_cost, 2),
            "totalAmazonCost": round(amazon_cost, 2),
        })

    avg_savings_per_shipment = (
        round(total_savings / total_shipments, 2) if total_shipments else 0.0
    )

    summary = {
        "totalSavings": round(total_savings, 2),
        "totalShipments": total_shipments,
        "avgSavingsPerShipment": avg_savings_per_shipment,
        "totalCurrentCost": round(total_current_cost, 2),
        "totalAmazonCost": round(total_amazon_cost, 2),
        "trend": sorted(trend_points, key=lambda point: point["date"]),
        "zones": [
            {"zone": zone, "count": count}
            for zone, count in sorted(zone_counts.items(), key=lambda item: item[0])
        ],
        "weights": [
            {"bucket": bucket, "count": count}
            for bucket, count in sorted(weight_counts.items(), key=lambda item: item[0])
        ],
        "merchants": [
            {
                "merchant": merchant,
                "analyses": values["analyses"],
                "totalSavings": round(values["totalSavings"], 2),
                "totalShipments": values["totalShipments"],
                "avgSavingsPerShipment": (
                    round(values["totalSavings"] / values["totalShipments"], 2)
                    if values["totalShipments"]
                    else 0.0
                ),
            }
            for merchant, values in sorted(
                merchant_aggregate.items(),
                key=lambda item: item[1]["totalSavings"],
                reverse=True,
            )
        ],
    }

    payload = {"items": items, "summary": summary}
    return deep_clean_json_safe(payload)


@router.get("/upload/{analysis_id}/columns", response_model=FileUploadResponse)
async def get_upload_columns(
    analysis_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Retrieve column metadata and suggested mappings for an uploaded file."""
    try:
        analysis = await db.analysis.find_unique(
            where={"id": analysis_id, "userId": current_user.id}
        )

        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )

        if not analysis.filePath or not os.path.exists(analysis.filePath):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is no longer available"
            )

        # Read the stored upload to extract columns again
        try:
            if analysis.filePath.endswith(".csv"):
                try:
                    df = pd.read_csv(analysis.filePath, encoding="utf-8")
                except UnicodeDecodeError:
                    try:
                        df = pd.read_csv(analysis.filePath, encoding="latin1")
                    except Exception:
                        df = pd.read_csv(analysis.filePath, encoding="cp1252")
            else:
                df = pd.read_excel(analysis.filePath)
        except Exception as exc:
            logger.error("Unable to re-read uploaded file %s: %s", analysis.filePath, exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to read uploaded file"
            )

        columns = df.columns.tolist()
        suggestions = suggest_column_mapping(df)

        payload = deep_clean_json_safe({
            "analysisId": analysis.id,
            "fileName": analysis.fileName,
            "fileSize": analysis.fileSize or 0,
            "columns": columns,
            "suggestedMappings": suggestions,
            "message": "Columns loaded successfully"
        })

        return FileUploadResponse(**payload)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving upload columns: {e}")
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
                
                # Import sanitization utilities
                from app.utils.json_sanitize import deep_clean_json_safe, contains_nan_inf
                
                # Sanitize the response
                content = {"message": "Columns mapped successfully", "rowCount": len(data)}
                content = deep_clean_json_safe(content)
                if contains_nan_inf(content):
                    logger.error("NaN/Inf detected in response content after cleaning")
                
                return content
                
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
                'markup_percentage': request.markupPercent if request.markupPercent is not None else 0.0,
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

        cleaned_summary = deep_clean_json_safe(summary)
        
        # Generate visualizations
        visualizations = None
        if results and "error_message" not in results[0]:
            try:
                visualizations = generate_all_visualizations(results)
            except Exception as e:
                logger.warning(f"Error generating visualizations: {e}")

        # Prepare JSON-safe payloads
        cleaned_results = deep_clean_json_safe(results)
        total_results = len(cleaned_results)
        preview_limit = min(100, total_results)
        preview_results = cleaned_results[:preview_limit]

        cleaned_settings = deep_clean_json_safe({
            'amazon_rate': request.amazonRate,
            'fuel_surcharge': request.fuelSurcharge,
            'service_level': request.serviceLevel,
            'markup_percent': request.markupPercent,
            'use_advanced_settings': request.useAdvancedSettings,
            'das_surcharge': calculation_criteria.get('das_surcharge'),
            'edas_surcharge': calculation_criteria.get('edas_surcharge'),
            'remote_surcharge': calculation_criteria.get('remote_surcharge'),
            'dim_divisor': calculation_criteria.get('dim_divisor'),
            'service_level_markups': calculation_criteria.get('service_level_markups'),
            'calculation_criteria': calculation_criteria,
        })

        cleaned_visualizations = deep_clean_json_safe(visualizations) if visualizations else None

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
                "completedAt": datetime.utcnow(),
                "results": json.dumps(cleaned_results),
                "settings": json.dumps(cleaned_settings),
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
            results=preview_results,
            summary=cleaned_summary,
            visualizations=cleaned_visualizations,
            totalResults=total_results,
            previewCount=preview_limit
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
        
        analysis_data = analysis.dict()
        if isinstance(analysis_data.get("columnMapping"), str):
            try:
                analysis_data["columnMapping"] = json.loads(analysis_data["columnMapping"])
            except json.JSONDecodeError:
                analysis_data["columnMapping"] = None

        if isinstance(analysis_data.get("tags"), str):
            try:
                analysis_data["tags"] = json.loads(analysis_data["tags"])
            except json.JSONDecodeError:
                analysis_data["tags"] = [t.strip() for t in analysis_data["tags"].split(",") if t.strip()]

        return AnalysisResponse.model_validate(analysis_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.delete("/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Delete an analysis and its uploaded file."""
    try:
        analysis = await db.analysis.find_unique(
            where={"id": analysis_id, "userId": current_user.id}
        )
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )

        # Remove uploaded file if it exists
        if analysis.filePath:
            try:
                file_path = Path(analysis.filePath)
                if file_path.exists():
                    file_path.unlink()
            except Exception as file_err:
                logger.warning("Failed to delete file for analysis %s: %s", analysis_id, file_err)

        await db.analysis.delete(where={"id": analysis_id})

        try:
            await db.auditlog.create(
                data={
                    "userId": current_user.id,
                    "action": "ANALYSIS_DELETED",
                    "details": json.dumps({"analysisId": analysis_id})
                }
            )
        except Exception as audit_err:
            logger.warning("Failed to write audit log for deletion of %s: %s", analysis_id, audit_err)

        return {"message": "Analysis deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.patch("/{analysis_id}/meta", response_model=AnalysisResponse)
async def update_analysis_metadata(
    analysis_id: str,
    metadata: AnalysisMetadataUpdate,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Update merchant/title/tag metadata for an analysis."""
    try:
        analysis = await db.analysis.find_unique(
            where={"id": analysis_id, "userId": current_user.id}
        )

        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )

        payload = {}
        if metadata.merchant is not None:
            payload["merchant"] = metadata.merchant.strip() or None
        if metadata.title is not None:
            payload["title"] = metadata.title.strip() or None
        if metadata.tags is not None:
            cleaned_tags = [tag.strip() for tag in metadata.tags if tag and tag.strip()]
            payload["tags"] = cleaned_tags or None
        if metadata.notes is not None:
            notes = metadata.notes.strip()
            payload["notes"] = notes or None

        if payload:
            try:
                updated = await db.analysis.update(
                    where={"id": analysis_id},
                    data=payload
                )

                audit_details = deep_clean_json_safe({"analysisId": analysis_id, **payload})

                await db.auditlog.create(
                    data={
                        "userId": current_user.id,
                        "action": "ANALYSIS_METADATA_UPDATED",
                        "details": json.dumps(audit_details)
                    }
                )
            except Exception as err:
                logger.warning("Failed to update analysis metadata for %s: %s", analysis_id, err)
                updated = analysis
        else:
            updated = analysis

        analysis_data = updated.dict()
        if isinstance(analysis_data.get("columnMapping"), str):
            try:
                analysis_data["columnMapping"] = json.loads(analysis_data["columnMapping"])
            except json.JSONDecodeError:
                analysis_data["columnMapping"] = None

        # Ensure tags is always a list when present
        tags = analysis_data.get("tags")
        if isinstance(tags, str):
            try:
                analysis_data["tags"] = json.loads(tags)
            except json.JSONDecodeError:
                analysis_data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        return AnalysisResponse.model_validate(analysis_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating analysis metadata: {e}")
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
        column_mapping = analysis.columnMapping
        if isinstance(column_mapping, str):
            try:
                column_mapping = json.loads(column_mapping)
            except json.JSONDecodeError:
                column_mapping = {}
        column_mapping = column_mapping or {}

        data = process_data(analysis.filePath, column_mapping)
        
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
            order={"createdAt": "desc"},
        )

        mapped = []
        for analysis in analyses:
            analysis_data = analysis.model_dump()
            analysis_data.pop("user", None)
            if isinstance(analysis_data.get("columnMapping"), str):
                try:
                    analysis_data["columnMapping"] = json.loads(analysis_data["columnMapping"])
                except json.JSONDecodeError:
                    analysis_data["columnMapping"] = None

            if isinstance(analysis_data.get("tags"), str):
                try:
                    analysis_data["tags"] = json.loads(analysis_data["tags"])
                except json.JSONDecodeError:
                    analysis_data["tags"] = [
                        tag.strip()
                        for tag in analysis_data["tags"].split(",")
                        if tag and tag.strip()
                    ]

            if isinstance(analysis_data.get("settings"), str):
                try:
                    analysis_data["settings"] = json.loads(analysis_data["settings"])
                except json.JSONDecodeError:
                    analysis_data["settings"] = None
            mapped.append(AnalysisResponse.model_validate(analysis_data))

        return mapped
        
    except Exception as e:
        logger.error(f"Error getting user analyses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

# Column Profile endpoints
# Helpers
def _normalize_profile(profile: Any) -> ColumnProfileResponse:
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column profile not found")

    if hasattr(profile, "dict"):
        data = profile.dict()
    else:
        data = dict(profile)

    raw_mapping = data.get("mapping")
    if isinstance(raw_mapping, str):
        try:
            data["mapping"] = json.loads(raw_mapping)
        except json.JSONDecodeError:
            data["mapping"] = None

    return ColumnProfileResponse.model_validate(data)


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
        return _normalize_profile(profile)
        
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
            order={"createdAt": "desc"}
        )

        return [_normalize_profile(profile) for profile in profiles]
        
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
        
        return _normalize_profile(profile)
        
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
        
        # Import sanitization utilities
        from app.utils.json_sanitize import deep_clean_json_safe, contains_nan_inf
        
        # Sanitize the response
        content = {"message": "Column profile deleted successfully"}
        content = deep_clean_json_safe(content)
        if contains_nan_inf(content):
            logger.error("NaN/Inf detected in response content after cleaning")
        
        return content
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting column profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
