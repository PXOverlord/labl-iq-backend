from pydantic import BaseModel, Field
from typing import Dict, Optional

class AdvancedSettings(BaseModel):
    """Schema for advanced rate calculation settings"""
    # General markup
    markup_percentage: float = Field(10.0, ge=0, description="Default markup percentage")
    
    # Service level specific markups
    service_level_markups: Dict[str, float] = Field(
        default_factory=lambda: {
            "standard": 0.0,
            "expedited": 10.0,
            "priority": 15.0,
            "next_day": 25.0
        },
        description="Service level specific markup percentages"
    )
    
    # Surcharge settings
    das_surcharge: float = Field(1.98, ge=0, description="Delivery Area Surcharge amount")
    edas_surcharge: float = Field(3.92, ge=0, description="Extended Delivery Area Surcharge amount")
    remote_surcharge: float = Field(14.15, ge=0, description="Remote Area Surcharge amount")
    fuel_surcharge_percentage: float = Field(16.0, ge=0, description="Fuel surcharge percentage")
    
    # Dimensional weight settings
    dim_divisor: float = Field(139.0, gt=0, description="Dimensional weight divisor")

class SettingsResponse(BaseModel):
    """Schema for settings response"""
    settings: AdvancedSettings
    message: str = "Settings retrieved successfully"
