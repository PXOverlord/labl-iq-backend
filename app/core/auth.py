
"""
Authentication utilities for JWT token handling and password management
"""
import os
from datetime import datetime, timedelta
from typing import Union, Any, Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create an access token"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a refresh token"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    encoded_jwt = jwt.encode(to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str, secret_key: str) -> Optional[dict]:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

def decode_access_token(token: str) -> Optional[dict]:
    """Decode an access token"""
    return verify_token(token, settings.SECRET_KEY)

def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode a refresh token"""
    return verify_token(token, settings.REFRESH_SECRET_KEY)
