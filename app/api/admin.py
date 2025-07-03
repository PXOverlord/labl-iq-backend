
"""
Admin API routes for user management and system administration
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import json

from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.schemas.auth import UserResponse, UserRole
from app.schemas.analysis import AnalysisResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Get all users (admin only)"""
    try:
        where_clause = {}
        if role:
            where_clause["role"] = role
        if is_active is not None:
            where_clause["isActive"] = is_active
        
        users = await db.user.find_many(
            where=where_clause,
            skip=skip,
            take=limit,
            order_by={"createdAt": "desc"},
            include={"settings": True}
        )
        
        return [UserResponse.model_validate(user) for user in users]
        
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: str,
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Get user by ID (admin only)"""
    try:
        user = await db.user.find_unique(
            where={"id": user_id},
            include={"settings": True, "children": True, "parent": True}
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse.model_validate(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by ID: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    new_role: UserRole,
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Update user role (admin only)"""
    try:
        # Check if user exists
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent admin from demoting themselves
        if user_id == current_admin.id and new_role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own admin role"
            )
        
        # Update user role
        updated_user = await db.user.update(
            where={"id": user_id},
            data={"role": new_role}
        )
        
        # Log the role change
        await db.auditlog.create(
            data={
                "userId": current_admin.id,
                "action": "USER_ROLE_CHANGED",
                "details": json.dumps({
                    "targetUserId": user_id,
                    "targetUserEmail": user.email,
                    "oldRole": user.role,
                    "newRole": new_role
                })
            }
        )
        
        logger.info(f"User role changed by admin {current_admin.email}: {user.email} -> {new_role}")
        return {"message": f"User role updated to {new_role}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    is_active: bool,
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Update user active status (admin only)"""
    try:
        # Check if user exists
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent admin from deactivating themselves
        if user_id == current_admin.id and not is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account"
            )
        
        # Update user status
        updated_user = await db.user.update(
            where={"id": user_id},
            data={"isActive": is_active}
        )
        
        # Log the status change
        await db.auditlog.create(
            data={
                "userId": current_admin.id,
                "action": "USER_STATUS_CHANGED",
                "details": json.dumps({
                    "targetUserId": user_id,
                    "targetUserEmail": user.email,
                    "oldStatus": user.isActive,
                    "newStatus": is_active
                })
            }
        )
        
        status_text = "activated" if is_active else "deactivated"
        logger.info(f"User {status_text} by admin {current_admin.email}: {user.email}")
        return {"message": f"User {status_text} successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/analyses", response_model=List[AnalysisResponse])
async def get_all_analyses(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Get all analyses (admin only)"""
    try:
        where_clause = {}
        if user_id:
            where_clause["userId"] = user_id
        if status:
            where_clause["status"] = status
        
        analyses = await db.analysis.find_many(
            where=where_clause,
            skip=skip,
            take=limit,
            order_by={"createdAt": "desc"},
            include={"user": True}
        )
        
        return [AnalysisResponse.model_validate(analysis) for analysis in analyses]
        
    except Exception as e:
        logger.error(f"Error getting all analyses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/analytics/dashboard")
async def get_admin_dashboard(
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Get admin dashboard analytics"""
    try:
        # Get user statistics
        total_users = await db.user.count()
        active_users = await db.user.count(where={"isActive": True})
        admin_users = await db.user.count(where={"role": "ADMIN"})
        
        # Get analysis statistics
        total_analyses = await db.analysis.count()
        completed_analyses = await db.analysis.count(where={"status": "COMPLETED"})
        failed_analyses = await db.analysis.count(where={"status": "FAILED"})
        
        # Get recent activity (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_users = await db.user.count(
            where={"createdAt": {"gte": thirty_days_ago}}
        )
        recent_analyses = await db.analysis.count(
            where={"createdAt": {"gte": thirty_days_ago}}
        )
        
        # Get top users by analysis count
        top_users = await db.user.find_many(
            include={
                "_count": {
                    "select": {"analyses": True}
                }
            },
            order_by={"analyses": {"_count": "desc"}},
            take=10
        )
        
        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "admins": admin_users,
                "recent": recent_users
            },
            "analyses": {
                "total": total_analyses,
                "completed": completed_analyses,
                "failed": failed_analyses,
                "recent": recent_analyses
            },
            "topUsers": [
                {
                    "id": user.id,
                    "email": user.email,
                    "firstName": user.firstName,
                    "lastName": user.lastName,
                    "analysisCount": user._count.analyses
                }
                for user in top_users
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting admin dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/audit-logs")
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Get audit logs (admin only)"""
    try:
        where_clause = {}
        if user_id:
            where_clause["userId"] = user_id
        if action:
            where_clause["action"] = action
        
        logs = await db.auditlog.find_many(
            where=where_clause,
            skip=skip,
            take=limit,
            order_by={"createdAt": "desc"}
        )
        
        return logs
        
    except Exception as e:
        logger.error(f"Error getting audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_admin: UserResponse = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Delete a user (admin only)"""
    try:
        # Check if user exists
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent admin from deleting themselves
        if user_id == current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Delete user (cascade will handle related records)
        await db.user.delete(where={"id": user_id})
        
        # Log the deletion
        await db.auditlog.create(
            data={
                "userId": current_admin.id,
                "action": "USER_DELETED",
                "details": json.dumps({
                    "deletedUserId": user_id,
                    "deletedUserEmail": user.email
                })
            }
        )
        
        logger.info(f"User deleted by admin {current_admin.email}: {user.email}")
        return {"message": "User deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
