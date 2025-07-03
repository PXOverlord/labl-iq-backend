
"""
Analysis-related Pydantic schemas
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class AnalysisStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class AnalysisCreate(BaseModel):
    fileName: str
    fileSize: int
    columnMapping: Optional[Dict[str, Any]] = None

class AnalysisUpdate(BaseModel):
    status: Optional[AnalysisStatus] = None
    columnMapping: Optional[Dict[str, Any]] = None
    amazonRate: Optional[float] = None
    fuelSurcharge: Optional[float] = None
    serviceLevel: Optional[str] = None
    markupPercent: Optional[float] = None
    totalPackages: Optional[int] = None
    totalCurrentCost: Optional[float] = None
    totalAmazonCost: Optional[float] = None
    totalSavings: Optional[float] = None
    percentSavings: Optional[float] = None
    errorMessage: Optional[str] = None

class AnalysisResponse(BaseModel):
    id: str
    userId: str
    fileName: str
    fileSize: int
    filePath: Optional[str] = None
    status: AnalysisStatus
    columnMapping: Optional[Dict[str, Any]] = None
    amazonRate: Optional[float] = None
    fuelSurcharge: Optional[float] = None
    serviceLevel: Optional[str] = None
    markupPercent: Optional[float] = None
    totalPackages: Optional[int] = None
    totalCurrentCost: Optional[float] = None
    totalAmazonCost: Optional[float] = None
    totalSavings: Optional[float] = None
    percentSavings: Optional[float] = None
    errorMessage: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    completedAt: Optional[datetime] = None

    class Config:
        from_attributes = True

class ColumnProfileCreate(BaseModel):
    name: str
    description: Optional[str] = None
    mapping: Dict[str, Any]
    isPublic: bool = False

class ColumnProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    mapping: Optional[Dict[str, Any]] = None
    isPublic: Optional[bool] = None

class ColumnProfileResponse(BaseModel):
    id: str
    userId: str
    name: str
    description: Optional[str] = None
    mapping: Dict[str, Any]
    isPublic: bool
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True

class FileUploadResponse(BaseModel):
    analysisId: str
    fileName: str
    fileSize: int
    columns: List[str]
    suggestedMappings: Dict[str, str]
    message: str

class RateCalculationRequest(BaseModel):
    analysisId: str
    amazonRate: float = 0.50
    fuelSurcharge: float = 16.0
    serviceLevel: str = "standard"
    markupPercent: Optional[float] = None
    useAdvancedSettings: bool = True

class RateCalculationResponse(BaseModel):
    analysisId: str
    results: List[Dict[str, Any]]
    summary: Dict[str, Any]
    visualizations: Optional[Dict[str, Any]] = None
