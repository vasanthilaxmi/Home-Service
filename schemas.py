from typing import Annotated, Optional
from pydantic import BaseModel, EmailStr, StringConstraints, Field, model_validator
from uuid import UUID
from typing import Optional
from datetime import datetime
from models import UserRole
from enum import Enum
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


# -------------------------------
# MODULE 3: JOBS SCHEMAS
# -------------------------------

# We recreate the Enum here for Pydantic to use for validation
class JobStatusEnum(str, Enum):
    requested = "requested"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    disputed = "disputed"

class JobCreate(BaseModel):
    service_id: int
    description: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    
    # All location fields remain optional individually...
    location_id: Optional[UUID] = None
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    # ...but we validate them together here!
    @model_validator(mode='after')
    def check_location_provided(self) -> 'JobCreate':
        has_saved_location = self.location_id is not None
        has_raw_location = (self.address is not None and 
                            self.latitude is not None and 
                            self.longitude is not None)
        
        if not has_saved_location and not has_raw_location:
            raise ValueError(
                "Location is mandatory. You must provide either a 'location_id' "
                "OR a complete 'address', 'latitude', and 'longitude'."
            )
        
        return self

class JobResponse(BaseModel):
    id: UUID
    customer_id: UUID
    worker_id: Optional[UUID] = None
    service_id: int
    
    description: Optional[str]
    updated_description: Optional[str]
    
    status: JobStatusEnum
    scheduled_time: Optional[datetime]
    service_charge: Optional[float]
    final_price: Optional[float]
    revision_count: int
    
    location_id: Optional[UUID]
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class JobStatusUpdate(BaseModel):
    status: JobStatusEnum


# -------------------------------
# MODULE 3.5: JOB IMAGES & DISPUTES SCHEMAS
# -------------------------------

class ImageTypeEnum(str, Enum):
    before = "before"
    after = "after"
    proof = "proof"

class UploaderTypeEnum(str, Enum):
    worker = "worker"
    customer = "customer"

class DisputeStatusEnum(str, Enum):
    open = "open"
    resolved = "resolved"
    rejected = "rejected"

# --- Job Images ---
class JobImageCreate(BaseModel):
    image_url: str
    uploaded_by: UploaderTypeEnum
    type: ImageTypeEnum

class JobImageResponse(BaseModel):
    id: int
    job_id: UUID
    image_url: str
    uploaded_by: UploaderTypeEnum
    type: ImageTypeEnum
    created_at: datetime

    class Config:
        from_attributes = True

# --- Disputes ---
class DisputeCreate(BaseModel):
    reason: str
    description: str

class DisputeResponse(BaseModel):
    id: int
    job_id: UUID
    raised_by: UUID
    reason: str
    description: str
    status: DisputeStatusEnum
    created_at: datetime

    class Config:
        from_attributes = True
class DisputeStatusUpdate(BaseModel):
    status: DisputeStatusEnum        