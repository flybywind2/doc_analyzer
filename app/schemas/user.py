"""
User schemas
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """Base user schema"""
    username: str = Field(..., min_length=3, max_length=50)
    name: Optional[str] = Field(None, max_length=100)
    role: str = Field(default="reviewer", pattern="^(admin|reviewer)$")
    department_id: Optional[int] = None
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for creating user"""
    password: Optional[str] = Field(None, min_length=8)


class UserUpdate(BaseModel):
    """Schema for updating user"""
    name: Optional[str] = Field(None, max_length=100)
    role: Optional[str] = Field(None, pattern="^(admin|reviewer)$")
    department_id: Optional[int] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    """Schema for password change"""
    old_password: Optional[str] = None
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    """Schema for user response"""
    id: int
    is_first_login: bool
    created_at: datetime
    updated_at: Optional[datetime]
    last_login_at: Optional[datetime]
    department_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for login"""
    username: str
    password: str


class Token(BaseModel):
    """Schema for token response"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for token data"""
    username: Optional[str] = None
    role: Optional[str] = None
