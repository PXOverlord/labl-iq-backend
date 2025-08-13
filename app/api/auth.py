
"""
Authentication API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import json
from app.core.database import get_db
from app.core.auth import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_refresh_token
from app.core.security import get_current_user, get_current_active_user
from app.schemas.auth import (
    UserCreate, UserResponse, TokenResponse, TokenRefresh, 
    PasswordChange, UserSettingsResponse, UserSettingsUpdate
)
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db = Depends(get_db)
):
    """Register a new user"""
    try:
        # Check if user already exists
        existing_user = await db.user.find_unique(where={"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Validate parent user if provided
        if user_data.parentId:
            parent_user = await db.user.find_unique(where={"id": user_data.parentId})
            if not parent_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parent user not found"
                )
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Create user
        user = await db.user.create(
            data={
                "email": user_data.email,
                "password": hashed_password,
                "firstName": user_data.firstName,
                "lastName": user_data.lastName,
                "parentId": user_data.parentId,
                "role": "USER"  # Default role
            }
        )
        
        # Create default user settings
        await db.usersettings.create(
            data={
                "userId": user.id,
                "defaultMarkup": 10.0,
                "fuelSurcharge": 16.0,
                "dasSurcharge": 1.98,
                "edasSurcharge": 3.92,
                "remoteSurcharge": 14.15,
                "dimDivisor": 139.0,
                "standardMarkup": 0.0,
                "expeditedMarkup": 10.0,
                "priorityMarkup": 15.0,
                "nextDayMarkup": 25.0
            }
        )
        
        # Log the registration
        await db.auditlog.create(
            data={
                "userId": user.id,
                "action": "USER_REGISTERED",
                "details": json.dumps({"email": user.email})
            }
        )
        
        logger.info(f"New user registered: {user.email}")
        return UserResponse.model_validate(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/login", response_model=TokenResponse)
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db = Depends(get_db)
):
    """Authenticate user and return JWT tokens"""
    try:
        # Find user by email
        user = await db.user.find_unique(where={"email": form_data.username})
        
        if not user or not verify_password(form_data.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.isActive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        # Create tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=user.id, expires_delta=access_token_expires
        )
        refresh_token = create_refresh_token(subject=user.id)
        
        # Log the login
        await db.auditlog.create(
            data={
                "userId": user.id,
                "action": "USER_LOGIN",
                "details": json.dumps({"email": user.email})
            }
        )
        
        logger.info(f"User logged in: {user.email}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    token_data: TokenRefresh,
    db = Depends(get_db)
):
    """Refresh access token using refresh token"""
    try:
        # Decode refresh token
        payload = decode_refresh_token(token_data.refresh_token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Verify user exists and is active
        user = await db.user.find_unique(where={"id": user_id})
        if not user or not user.isActive:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=user.id, expires_delta=access_token_expires
        )
        new_refresh_token = create_refresh_token(subject=user.id)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: UserResponse = Depends(get_current_active_user)
):
    """Get current user information"""
    return current_user

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Change user password"""
    try:
        # Get user with password
        user = await db.user.find_unique(where={"id": current_user.id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Verify current password
        if not verify_password(password_data.current_password, user.password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect current password"
            )
        
        # Hash new password
        new_hashed_password = get_password_hash(password_data.new_password)
        
        # Update password
        await db.user.update(
            where={"id": current_user.id},
            data={"password": new_hashed_password}
        )
        
        # Log password change
        await db.auditlog.create(
            data={
                "userId": current_user.id,
                "action": "PASSWORD_CHANGED",
                "details": json.dumps({"email": current_user.email})
            }
        )
        
        logger.info(f"Password changed for user: {current_user.email}")
        
        # Import sanitization utilities
        from app.utils.json_sanitize import deep_clean_json_safe, contains_nan_inf
        
        # Sanitize the response
        content = {"message": "Password changed successfully"}
        content = deep_clean_json_safe(content)
        if contains_nan_inf(content):
            logger.error("NaN/Inf detected in response content after cleaning")
        
        return content
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/settings", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Get user settings"""
    try:
        settings = await db.usersettings.find_unique(where={"userId": current_user.id})
        if not settings:
            # Create default settings if they don't exist
            settings = await db.usersettings.create(
                data={
                    "userId": current_user.id,
                    "defaultMarkup": 10.0,
                    "fuelSurcharge": 16.0,
                    "dasSurcharge": 1.98,
                    "edasSurcharge": 3.92,
                    "remoteSurcharge": 14.15,
                    "dimDivisor": 139.0,
                    "standardMarkup": 0.0,
                    "expeditedMarkup": 10.0,
                    "priorityMarkup": 15.0,
                    "nextDayMarkup": 25.0
                }
            )
        
        return UserSettingsResponse.model_validate(settings)
        
    except Exception as e:
        logger.error(f"Error getting user settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.put("/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    settings_data: UserSettingsUpdate,
    current_user: UserResponse = Depends(get_current_active_user),
    db = Depends(get_db)
):
    """Update user settings"""
    try:
        # Update settings
        settings = await db.usersettings.update(
            where={"userId": current_user.id},
            data=settings_data.model_dump(exclude_unset=True)
        )
        
        # Log settings update
        await db.auditlog.create(
            data={
                "userId": current_user.id,
                "action": "SETTINGS_UPDATED",
                "details": json.dumps(settings_data.model_dump(exclude_unset=True))
            }
        )
        
        logger.info(f"Settings updated for user: {current_user.email}")
        return UserSettingsResponse.model_validate(settings)
        
    except Exception as e:
        logger.error(f"Error updating user settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
