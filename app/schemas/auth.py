
"""
Authentication-related Pydantic schemas
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    parentId: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    role: UserRole
    isActive: bool
    createdAt: datetime
    updatedAt: datetime
    parentId: Optional[str] = None

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    isActive: Optional[bool] = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenRefresh(BaseModel):
    refresh_token: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

class UserSettingsResponse(BaseModel):
    id: str
    userId: str
    originZip: Optional[str] = None
    defaultMarkup: float
    fuelSurcharge: float
    dasSurcharge: float
    edasSurcharge: float
    remoteSurcharge: float
    dimDivisor: float
    standardMarkup: float
    expeditedMarkup: float
    priorityMarkup: float
    nextDayMarkup: float
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True

class UserSettingsUpdate(BaseModel):
    originZip: Optional[str] = None
    defaultMarkup: Optional[float] = None
    fuelSurcharge: Optional[float] = None
    dasSurcharge: Optional[float] = None
    edasSurcharge: Optional[float] = None
    remoteSurcharge: Optional[float] = None
    dimDivisor: Optional[float] = None
    standardMarkup: Optional[float] = None
    expeditedMarkup: Optional[float] = None
    priorityMarkup: Optional[float] = None
    nextDayMarkup: Optional[float] = None
