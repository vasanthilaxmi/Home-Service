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


from pydantic import Field
from typing import List

# -------------------------------
# SERVICES SCHEMAS
# -------------------------------

class ServiceResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class WorkerServiceUpdate(BaseModel):
    """
    Used when a worker selects the services they provide.
    Instead of sending one at a time, they send a list of service IDs.
    """
    service_ids: List[int]


# -------------------------------
# LOCATIONS SCHEMAS
# -------------------------------

class LocationCreate(BaseModel):
    label: Optional[str] = None  # e.g., "Home", "Office"
    address: str
    
    # We use Field to strictly validate real-world coordinates
    latitude: float = Field(..., ge=-90, le=90, description="Valid latitude between -90 and 90")
    longitude: float = Field(..., ge=-180, le=180, description="Valid longitude between -180 and 180")
    
    is_default: bool = False

class LocationResponse(BaseModel):
    id: UUID
    user_id: UUID
    label: Optional[str]
    address: str
    latitude: float
    longitude: float
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True