from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Replace with your actual database credentials
# Format: postgresql+asyncpg://user:password@localhost:5432/dbname
DATABASE_URL = "postgresql+asyncpg://postgres:padmachandra@localhost:5432/postgres"

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

# Dependency to inject the database session into our routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session