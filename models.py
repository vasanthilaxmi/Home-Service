import uuid
import enum
from sqlalchemy import Column, String, Boolean, DateTime, Float, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy import CheckConstraint

class UserRole(enum.Enum):
    customer = "customer"
    worker = "worker"
    both = "both"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=True) # Now optional
    email = Column(String, unique=True, nullable=True) # Now optional
    phone = Column(String, unique=True, nullable=False)
    role = Column(SQLEnum(UserRole, name="user_role"), default=UserRole.customer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    worker_profile = relationship("WorkerProfile", back_populates="user", uselist=False)
    locations = relationship("Location", back_populates="user", cascade="all, delete-orphan")
class WorkerProfile(Base):
    __tablename__ = "worker_profile"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    experience = Column(Integer, default=0) # in years
    is_online = Column(Boolean, default=False)
    is_busy = Column(Boolean, default=False)
    rating = Column(Float, default=0)
    total_jobs = Column(Integer, default=0)
    last_active_at = Column(DateTime)

    user = relationship("User", back_populates="worker_profile")

class OTP(Base):
    # 1. Change the table name to match your PostgreSQL database exactly
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, index=True, nullable=False)
    otp = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    
    # 2. Add the created_at column that exists in your pgAdmin table
    created_at = Column(DateTime, server_default=func.now())
# Add this import at the top of models.py if not already there:
# from sqlalchemy import CheckConstraint

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    
    # We can enforce the regex at the database level directly through SQLAlchemy
    # __table_args__ = (
    #     CheckConstraint("name ~ '^[A-Za-z ]+$'", name="services_name_check"),
    # )

class WorkerService(Base):
    __tablename__ = "worker_services"

    # Composite Primary Key mapping workers to the services they provide
    worker_id = Column(UUID(as_uuid=True), ForeignKey("worker_profile.user_id", ondelete="CASCADE"), primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)

class Location(Base):
    __tablename__ = "locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    label = Column(String, nullable=True) # e.g., "Home", "Office"
    address = Column(String, nullable=False)
    
    # Stored as standard floats for basic distance calculations later
    latitude = Column(Float)
    longitude = Column(Float)
    
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    # Establish relationship back to the user
    user = relationship("User", back_populates="locations")   

class JobStatus(enum.Enum):
    requested = "requested"       
    assigned = "assigned"         
    in_progress = "in_progress"   
    completed = "completed"       
    cancelled = "cancelled"       
    disputed = "disputed"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    worker_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    
    # Text fields for job details
    description = Column(String, nullable=True)
    updated_description = Column(String, nullable=True) 
    
    # Pricing and Scheduling
    status = Column(SQLEnum(JobStatus, name="job_status"), default=JobStatus.requested)
    scheduled_time = Column(DateTime, nullable=True)
    service_charge = Column(Float, nullable=True) # Maps to PostgreSQL numeric
    final_price = Column(Float, nullable=True)
    revision_count = Column(Integer, default=0)
    
    # Location details
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True) # Maps to PostgreSQL double precision
    longitude = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    customer = relationship("User", foreign_keys=[customer_id], backref="jobs_requested")
    worker = relationship("User", foreign_keys=[worker_id], backref="jobs_assigned")
    service = relationship("Service")
    location = relationship("Location")