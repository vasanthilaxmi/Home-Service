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