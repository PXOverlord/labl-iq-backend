from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Union
import re

class ColumnMapping(BaseModel):
    """Schema for column mapping data"""
    weight: str
    length: str
    width: str
    height: str
    from_zip: str
    to_zip: str
    carrier: str
    rate: str
    service_level: Optional[str] = None
    package_type: Optional[str] = None

class RateParameters(BaseModel):
    """Schema for Amazon rate calculation parameters"""
    amazon_rate: float = Field(..., gt=0, description="Base Amazon rate per pound")
    fuel_surcharge: float = Field(..., ge=0, lt=1, description="Fuel surcharge as decimal (e.g., 0.05 for 5%)")
    service_level: str = Field("standard", description="Service level (standard, expedited, priority, next_day)")
    markup_percent: float = Field(10.0, ge=0, description="Markup percentage")

class ShippingPackage(BaseModel):
    """Schema for a shipping package"""
    weight: Optional[float] = None
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    from_zip: Optional[str] = None
    to_zip: Optional[str] = None
    carrier: Optional[str] = None
    rate: Optional[float] = None
    service_level: Optional[str] = "standard"
    package_type: Optional[str] = "box"
    
    @validator('from_zip', 'to_zip')
    def validate_zip(cls, v):
        if v is None:
            return v
        
        # Remove any non-numeric characters
        zip_code = re.sub(r'[^0-9]', '', str(v))
        
        # Check if it's a valid US ZIP code format
        if len(zip_code) not in [5, 9]:
            raise ValueError('ZIP code must be 5 or 9 digits')
        
        return zip_code
    
    @validator('service_level')
    def validate_service_level(cls, v):
        if v is None:
            return "standard"
        
        valid_levels = ["standard", "expedited", "priority", "next_day"]
        v_lower = v.lower()
        
        if v_lower not in valid_levels:
            # Map common variations
            if v_lower in ["ground", "regular", "std"]:
                return "standard"
            elif v_lower in ["express", "2day", "2-day"]:
                return "expedited"
            elif v_lower in ["prio", "3day"]:
                return "priority"
            elif v_lower in ["overnight", "1day", "nextday"]:
                return "next_day"
            else:
                return "standard"
        
        return v_lower
    
    @validator('package_type')
    def validate_package_type(cls, v):
        if v is None:
            return "box"
        
        valid_types = ["box", "envelope", "pak", "custom"]
        v_lower = v.lower()
        
        if v_lower not in valid_types:
            # Map common variations
            if v_lower in ["parcel", "carton"]:
                return "box"
            elif v_lower in ["env", "flat"]:
                return "envelope"
            elif v_lower in ["poly", "polybag", "bag"]:
                return "pak"
            else:
                return "box"
        
        return v_lower

class RateResult(BaseModel):
    """Schema for rate calculation result"""
    package_id: str
    weight: Optional[float] = None
    dimensions: str
    from_zip: Optional[str] = None
    to_zip: Optional[str] = None
    carrier: Optional[str] = None
    current_rate: float
    amazon_rate: float
    billable_weight: float
    zone: str = "Unknown"
    base_rate: float = 0.0
    fuel_surcharge: float = 0.0
    das_surcharge: float = 0.0
    edas_surcharge: float = 0.0
    remote_surcharge: float = 0.0
    total_surcharges: float = 0.0
    markup_amount: float = 0.0
    markup_percentage: float = 0.0
    savings: float
    savings_percent: float
    service_level: str = "standard"
    package_type: str = "box"
    errors: str = ""

class AnalysisSummary(BaseModel):
    """Schema for analysis summary"""
    total_packages: int
    total_current_cost: float
    total_amazon_cost: float
    total_savings: float
    percent_savings: float
