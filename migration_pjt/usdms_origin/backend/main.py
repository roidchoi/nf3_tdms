from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import os
from backend.routers import data

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("US-DMS Backend Starting...")
    # Initialize DB connection pool here if needed
    yield
    # Shutdown
    logger.info("US-DMS Backend Shutting Down...")

app = FastAPI(
    title="US-DMS API",
    description="US Data Management System Backend",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {"message": "US-DMS Backend is running"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "db": "unknown"}
