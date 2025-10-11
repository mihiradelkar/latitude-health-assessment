from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import clinical_notes, prior_auth, fhir_resources
from app.utils.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("🚀 Starting Latitude Health API...")
    yield
    print("👋 Shutting down...")

app = FastAPI(
    title="Latitude Health Prior Auth API",
    description="AI-powered prior authorization system using FHIR and MCP",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(clinical_notes.router, prefix="/api/v1/clinical-notes", tags=["Clinical Notes"])
app.include_router(prior_auth.router, prefix="/api/v1/prior-auth", tags=["Prior Authorization"])
app.include_router(fhir_resources.router, prefix="/api/v1/fhir", tags=["FHIR Resources"])

@app.get("/")
async def root():
    return {
        "message": "Latitude Health Prior Auth API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}