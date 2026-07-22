from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from database import get_db
import models
import schemas
import auth
from uuid import UUID
from fastapi import File, Form, UploadFile
import magic
import shutil # Used for saving the file locally
import os

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


# -------------------------------
# 6. JOBS
# -------------------------------
@app.post("/api/jobs", response_model=schemas.JobResponse)
async def create_job(
    job_data: schemas.JobCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    naive_scheduled_time = None
    if job_data.scheduled_time:
        naive_scheduled_time = job_data.scheduled_time.replace(tzinfo=None)
    # 1. Map the validated Pydantic schema to our SQLAlchemy Database Model
    new_job = models.Job(
        customer_id=current_user.id, # Securely pulled from the JWT token
        service_id=job_data.service_id,
        description=job_data.description,
        scheduled_time=naive_scheduled_time,
        
        # Location data
        location_id=job_data.location_id,
        address=job_data.address,
        latitude=job_data.latitude,
        longitude=job_data.longitude,
        
        # Default starting status
        status=models.JobStatus.requested
    )
    
    # 2. Save it to the database
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    
    return new_job


@app.get("/api/jobs", response_model=List[schemas.JobResponse])
async def get_my_jobs(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns jobs belonging to the logged-in user (either as a customer or assigned worker)."""
    if current_user.role == models.UserRole.customer:
        # Customers see jobs they requested
        query = select(models.Job).where(models.Job.customer_id == current_user.id)
    else:
        # Workers see jobs they are officially assigned to
        query = select(models.Job).where(models.Job.worker_id == current_user.id)
        
    result = await db.execute(query)
    return result.scalars().all()

@app.get("/api/jobs/available", response_model=List[schemas.JobResponse])
async def get_available_jobs(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Workers use this to find jobs that are looking for someone."""
    if current_user.role == models.UserRole.customer:
        raise HTTPException(status_code=403, detail="Customers cannot view available jobs pool")
        
    # Find all jobs that are still 'requested' and have no worker yet
    query = select(models.Job).where(
        models.Job.status == models.JobStatus.requested,
        models.Job.worker_id.is_(None)
    )
    result = await db.execute(query)
    return result.scalars().all()

@app.patch("/api/jobs/{job_id}/status", response_model=schemas.JobResponse)
async def update_job_status(
    job_id: UUID,
    status_data: schemas.JobStatusUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Workers use this to accept a job or mark it completed. Customers can cancel requested jobs."""
    # Find the job
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Assuming job.status and status_data.status can be treated as strings
    current_status = str(job.status.value if hasattr(job.status, 'value') else job.status)
    new_status = str(status_data.status.value if hasattr(status_data.status, 'value') else status_data.status)

    # --- CUSTOMER LOGIC ---
    if current_user.role == models.UserRole.customer:
        if new_status == "cancelled":
            if current_status != "requested":
                raise HTTPException(status_code=403, detail="Customers can only cancel jobs that are still in the 'requested' stage.")
            
            # Ensure we do not cancel if it has been 48 hours
            # (Assuming job.created_at is stored in UTC)
            if job.created_at and (datetime.utcnow() - job.created_at > timedelta(hours=48)):
                raise HTTPException(status_code=403, detail="Cannot manually cancel the job after 48 hours.")

            job.status = status_data.status
            await db.commit()
            await db.refresh(job)
            return job
        else:
            raise HTTPException(status_code=403, detail="Customers can only cancel jobs. You cannot change the status to anything else.")

    # --- WORKER LOGIC ---
    # --- FIX 1: Worker Skill Check ---
    if new_status == "assigned" and current_status == "requested":
        # Check the worker_services table to ensure they offer this service
        service_check = await db.execute(
            select(models.WorkerService).where(
                models.WorkerService.worker_id == current_user.id,
                models.WorkerService.service_id == job.service_id
            )
        )
        if not service_check.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="You do not offer the required service to accept this job.")
        
        job.worker_id = current_user.id

    # --- FIX 2: Strict State Machine ---
    # Define exactly which status transitions are legally allowed
    valid_transitions = {
        "requested": ["assigned", "cancelled"],
        "assigned": ["in_progress", "cancelled"],
        "in_progress": ["completed"],
        "completed": [], # Cannot change once completed
        "cancelled": []  # Cannot change once cancelled
    }
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(status_code=400, detail=f"Invalid action: Cannot change job from {current_status} to {new_status}")

    # Security check: If it's already assigned, only the assigned worker can update it
    if job.worker_id and job.worker_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this job")

    # Update status and save
    job.status = status_data.status
    await db.commit()
    await db.refresh(job)
    
    return job
# -------------------------------
# MODULE 3.5: IMAGES & DISPUTES ENDPOINTS
# -------------------------------



@app.post("/api/jobs/{job_id}/images", response_model=schemas.JobImageResponse, tags=["Jobs"])
async def upload_job_image(
    job_id: UUID,
    # We use File and Form here to accept multipart/form-data
    file: UploadFile = File(...),
    image_type: schemas.ImageTypeEnum = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Upload a before/after/proof image for a specific job with strict security and validation."""
    
    # -----------------------------------------
    # 1. VERIFY JOB & AUTHORIZATION
    # -----------------------------------------
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if current_user.id not in [job.customer_id, job.worker_id]:
        raise HTTPException(status_code=403, detail="You are not authorized to upload images for this job.")

    # Automatically determine who is uploading based on their ID
    if current_user.id == job.customer_id:
        uploader_type = models.UploaderTypeEnum.customer
    else:
       uploader_type = models.UploaderType.worker

    # -----------------------------------------
    # 2. VALIDATE REAL IMAGE (MAGIC BYTES)
    # -----------------------------------------
    # Read the first 2048 bytes to determine the true file signature
    file_bytes = await file.read(2048)
    mime_type = magic.from_buffer(file_bytes, mime=True)
    
    if not mime_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only real images are allowed.")
    
    # Reset file pointer to the beginning after reading bytes
    await file.seek(0) 

    # -----------------------------------------
    # 3. SAVE THE FILE
    # -----------------------------------------
    # Ensure an upload directory exists
    os.makedirs("uploads", exist_ok=True)
    
    # Create a unique file path (In production, upload this to AWS S3 or Cloudinary instead)
    file_location = f"uploads/{job_id}_{file.filename}"
    
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # -----------------------------------------
    # 4. SAVE TO DATABASE
    # -----------------------------------------
    new_image = models.JobImage(
        job_id=job.id,
        image_url=file_location, # Save the path or S3 URL here
        uploaded_by=uploader_type,
        type=image_type
    )
    
    db.add(new_image)
    await db.commit()
    await db.refresh(new_image)
    
    return new_image


@app.post("/api/jobs/{job_id}/disputes", response_model=schemas.DisputeResponse, tags=["Jobs"])
async def create_dispute(
    job_id: UUID,
    dispute_data: schemas.DisputeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """File a dispute for a job."""
    
    # 1. Verify the job exists
    result = await db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # 2. Securely create the dispute using the logged-in user's ID
    new_dispute = models.Dispute(
        job_id=job.id,
        raised_by=current_user.id,
        reason=dispute_data.reason,
        description=dispute_data.description,
        status=models.DisputeStatus.open
    )
    
    db.add(new_dispute)
    await db.commit()
    await db.refresh(new_dispute)
    
    return new_dispute
@app.patch("/api/disputes/{dispute_id}/status", response_model=schemas.DisputeResponse, tags=["Jobs"])
async def update_dispute_status(
    dispute_id: int,
    status_data: schemas.DisputeStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Admin ONLY: Update the status of an existing dispute (e.g., mark as resolved)."""
    
    # SECURITY CHECK: Ensure only admins can judge disputes
    if current_user.role != "admin": 
        raise HTTPException(status_code=403, detail="Only admins can update dispute statuses")

    # 1. Find the dispute in the database
    result = await db.execute(select(models.Dispute).where(models.Dispute.id == dispute_id))
    dispute = result.scalars().first()
    
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    # 2. Update the status and save to database
    dispute.status = status_data.status
    
    db.add(dispute)
    await db.commit()
    await db.refresh(dispute)
    
    return dispute

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
from uuid import UUID

# -------------------------------
# MODULE 4: WEBSOCKETS (REAL-TIME)
# -------------------------------

class ConnectionManager:
    def __init__(self):
        # This dictionary will map a worker's UUID to their active WebSocket connection
        self.active_workers: Dict[UUID, WebSocket] = {}

    async def connect(self, websocket: WebSocket, worker_id: UUID):
        """Accept the connection and store the worker in memory."""
        await websocket.accept()
        self.active_workers[worker_id] = websocket
        print(f"Worker {worker_id} connected. Total online: {len(self.active_workers)}")

    def disconnect(self, worker_id: UUID):
        """Remove the worker when they close the app or lose signal."""
        if worker_id in self.active_workers:
            del self.active_workers[worker_id]
            print(f"Worker {worker_id} disconnected.")

    async def send_job_alert(self, worker_id: UUID, job_data: dict):
        """Push a new job notification instantly to a specific worker."""
        if worker_id in self.active_workers:
            websocket = self.active_workers[worker_id]
            await websocket.send_json(job_data)

    async def broadcast_to_all(self, message: dict):
        """Push a message to every single online worker."""
        for connection in self.active_workers.values():
            await connection.send_json(message)

# Initialize a single global instance of the manager
ws_manager = ConnectionManager()

@app.websocket("/ws/workers/{worker_id}")
async def worker_websocket_endpoint(websocket: WebSocket, worker_id: UUID):
    # 1. Open the connection
    await ws_manager.connect(websocket, worker_id)
    
    try:
        # 2. Keep the connection open forever in a loop
        while True:
            # We wait for the worker's phone to send us JSON data
            data = await websocket.receive_json()
            
            # 3. Check what action the phone is trying to perform
            action = data.get("action")
            
            if action == "update_location":
                lat = data.get("latitude")
                lng = data.get("longitude")
                
                print(f"📍 Worker {worker_id} moved to -> Lat: {lat}, Lng: {lng}")
                
                # IN THE NEXT STEP: 
                # We will route these coordinates directly to the customer 
                # who is waiting for this specific worker!
                
            elif action == "accept_job":
                # The worker tapped "Accept" on a job broadcast
                job_id = data.get("job_id")
                print(f"✅ Worker {worker_id} is trying to accept job {job_id}")
                
            else:
                print(f"Unknown action received from {worker_id}: {data}")
            
    except WebSocketDisconnect:
        # 4. If the worker closes the app, clean up their connection
        ws_manager.disconnect(worker_id)