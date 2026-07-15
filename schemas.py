from typing import Annotated, Optional
from pydantic import BaseModel, EmailStr, StringConstraints
from uuid import UUID
from datetime import datetime
from models import UserRole

# Define reusable, modern Pydantic V2 constraints
PhoneNumber = Annotated[str, StringConstraints(pattern=r'^\d{10}$')]
OTPCode = Annotated[str, StringConstraints(pattern=r'^\d{4}$')]

class SendOTP(BaseModel):
    phone: PhoneNumber

class VerifyOTP(BaseModel):
    phone: PhoneNumber
    otp: OTPCode
    
class ProfileUpdate(BaseModel):
    name: str
    email: EmailStr
    role: UserRole

class UserResponse(BaseModel):
    id: UUID
    name: Optional[str]
    email: Optional[EmailStr]
    phone: str
    role: UserRole
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# The missing Token schema!
class Token(BaseModel):
    access_token: str
    token_type: str
    is_profile_complete: bool