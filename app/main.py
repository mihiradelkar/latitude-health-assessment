# app/main.py
# Updated version with MCP support

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import clinical_notes, prior_auth, fhir_resources
from app.utils.config import settings

# NEW: Import MCP server
from app.services.mcp_server import add_mcp_routes

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("Starting Latitude Health API...")
    print("MCP Server initializing...")
    yield
    print("Shutting down...")

app = FastAPI(
    title="Latitude Health Prior Auth API",
    description="prior authorization system using FHIR and MCP",
    version="2.0.0",  # Bumped: MCP support
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(clinical_notes.router, prefix="/api/v1/clinical-notes", tags=["Clinical Notes"])
app.include_router(prior_auth.router, prefix="/api/v1/prior-auth", tags=["Prior Authorization"])
app.include_router(fhir_resources.router, prefix="/api/v1/fhir", tags=["FHIR Resources"])

# MCP protocol routes
add_mcp_routes(app)

@app.get("/")
async def root():
    return {
        "message": "Latitude Health Prior Auth API",
        "version": "2.0.0",
        "status": "running",
        "mcp_enabled": True
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "mcp_server": "active"
    }

# MCP-specific health check
@app.get("/mcp/health")
async def mcp_health():
    """Check MCP server status"""
    from app.services.mcp_server import mcp_server
    
    tools_count = len(mcp_server.list_tools())
    
    return {
        "status": "healthy",
        "tools_available": tools_count,
        "version": "1.0.0",
        "protocol": "MCP"
    }