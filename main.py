from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
import random
from datetime import datetime, timedelta, timezone

from database import get_db
import models
import schemas
import auth

app = FastAPI(title="Home Services API")

# -------------------------------
# 1. SEND OTP
# -------------------------------
@app.post("/api/auth/send-otp")
async def send_otp(data: schemas.SendOTP, db: AsyncSession = Depends(get_db)):
    otp_code = str(random.randint(1000, 9999))
# New line: We add .replace(tzinfo=None) to make it naive
    expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)

    await db.execute(
        update(models.OTP).where(models.OTP.phone == data.phone).values(is_used=True)
    )

    new_otp = models.OTP(phone=data.phone, otp=otp_code, expires_at=expires, is_used=False)
    db.add(new_otp)
    await db.commit()

    print(f"OTP for {data.phone}: {otp_code}") # Replace with SMS gateway later
    return {"message": "OTP sent successfully"}

# -------------------------------
# 2. VERIFY OTP & LOGIN
# -------------------------------
@app.post("/api/auth/verify-otp", response_model=schemas.Token)
async def verify_otp(data: schemas.VerifyOTP, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.OTP)
        .where((models.OTP.phone == data.phone) & (models.OTP.is_used == False))
        .order_by(models.OTP.id.desc())
    )
    record = result.scalars().first()

    if not record:
        raise HTTPException(status_code=400, detail="OTP not found or already used")
    
    if datetime.now(timezone.utc) > record.expires_at.replace(tzinfo=timezone.utc):
        record.is_used = True
        await db.commit()
        raise HTTPException(status_code=400, detail="OTP expired")

    if record.otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    record.is_used = True
    
    # Check if user exists
    user_result = await db.execute(select(models.User).where(models.User.phone == data.phone))
    user = user_result.scalars().first()

    is_new_user = False
    if not user:
        # Create brand new user with just phone number
        user = models.User(phone=data.phone)
        db.add(user)
        await db.flush()
        is_new_user = True

    await db.commit()
    await db.refresh(user)

    # If the user has no name in the database, their profile is incomplete
    profile_complete = bool(user.name)

    access_token = auth.create_access_token(
        data={"sub": str(user.id), "role": user.role.value, "phone": user.phone}
    )

    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "is_profile_complete": profile_complete
    }

# -------------------------------
# 3. COMPLETE PROFILE
# -------------------------------
@app.put("/api/users/profile", response_model=schemas.UserResponse)
async def update_profile(
    profile_data: schemas.ProfileUpdate, 
    current_user: models.User = Depends(auth.get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    # Update the user's base data
    current_user.name = profile_data.name
    current_user.email = profile_data.email
    current_user.role = profile_data.role

    # If they selected worker or both, ensure they have a worker_profile row
    if profile_data.role in [models.UserRole.worker, models.UserRole.both]:
        profile_check = await db.execute(
            select(models.WorkerProfile).where(models.WorkerProfile.user_id == current_user.id)
        )
        if not profile_check.scalars().first():
            new_profile = models.WorkerProfile(user_id=current_user.id)
            db.add(new_profile)

    await db.commit()
    await db.refresh(current_user)
    return current_user
# Add this import at the top if you don't have it for returning lists
from typing import List

# -------------------------------
# 4. LOCATIONS
# -------------------------------
@app.post("/api/users/locations", response_model=schemas.LocationResponse)
async def add_location(
    location_data: schemas.LocationCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Create the new location attached to the logged-in user
    new_location = models.Location(
        user_id=current_user.id,
        label=location_data.label,
        address=location_data.address,
        latitude=location_data.latitude,
        longitude=location_data.longitude,
        is_default=location_data.is_default
    )
    db.add(new_location)
    await db.commit()
    await db.refresh(new_location)
    return new_location

@app.get("/api/users/locations", response_model=List[schemas.LocationResponse])
async def get_my_locations(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Fetch all locations belonging to this specific user
    result = await db.execute(
        select(models.Location).where(models.Location.user_id == current_user.id)
    )
    return result.scalars().all()
# -------------------------------
# 5. SERVICES
# -------------------------------
@app.get("/api/services", response_model=List[schemas.ServiceResponse])
async def get_all_services(db: AsyncSession = Depends(get_db)):
    """
    Public endpoint to fetch all available services for the home screen.
    Does not require a JWT token (no current_user dependency).
    """
    result = await db.execute(select(models.Service))
    return result.scalars().all()

@app.put("/api/workers/services")
async def update_worker_services(
    service_data: schemas.WorkerServiceUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Protected endpoint for workers to select which services they offer.
    """
    # 1. Ensure the user is actually a worker or both
    if current_user.role == models.UserRole.customer:
        raise HTTPException(status_code=403, detail="Customers cannot provide services")

    # 2. Delete their old service list (so we can cleanly replace it)
    await db.execute(
        models.WorkerService.__table__.delete().where(
            models.WorkerService.worker_id == current_user.id
        )
    )

    # 3. Insert the new list of service IDs
    new_services = [
        models.WorkerService(worker_id=current_user.id, service_id=s_id) 
        for s_id in service_data.service_ids
    ]
    
    db.add_all(new_services)
    await db.commit()
    
    return {"message": "Worker services updated successfully"}