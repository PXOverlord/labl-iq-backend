
"""
Security dependencies for FastAPI routes
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.auth import decode_access_token
from app.core.database import get_db
from app.schemas.auth import UserResponse
import logging

logger = logging.getLogger(__name__)

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    scheme_name="JWT"
)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db = Depends(get_db)
) -> UserResponse:
    """Get the current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode the token
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    # Extract user ID from token
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    # Get user from database
    try:
        user = await db.user.find_unique(
            where={"id": user_id},
            include={"settings": True}
        )
        if user is None:
            raise credentials_exception
        
        if not user.isActive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        return UserResponse.model_validate(user)
    except Exception as e:
        logger.error(f"Error fetching user: {e}")
        raise credentials_exception

async def get_current_active_user(
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """Get the current active user"""
    if not current_user.isActive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def get_current_admin_user(
    current_user: UserResponse = Depends(get_current_active_user)
) -> UserResponse:
    """Get the current admin user"""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

# Optional authentication (for endpoints that work with or without auth)
async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db = Depends(get_db)
) -> Optional[UserResponse]:
    """Get the current user if authenticated, None otherwise"""
    if not token:
        return None
    
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None
