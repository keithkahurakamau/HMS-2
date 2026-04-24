from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from typing import List, Optional
import re

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role_id: int
    
    # Optional clinical fields for Doctors/Lab Techs
    specialization: Optional[str] = None
    license_number: Optional[str] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r"[A-Z]", v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r"[a-z]", v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r"\d", v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('Password must contain at least one special character')
        return v

class UserResponse(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: str
    permissions: List[str]
    
    # Added fields to match the final database model
    is_active: bool
    specialization: Optional[str] = None
    license_number: Optional[str] = None

    # Modern Pydantic V2 syntax (replaces 'class Config:')
    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str