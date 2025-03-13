"""
Status endpoints for monitoring system health.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.api.models import StatusResponse

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def status():
    """
    Status endpoint to verify the API is running.

    Returns:
        JSON response with status information
    """
    return JSONResponse(content={"status": "success"})


@router.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.

    Returns:
        JSON response with health check information
    """
    return {
        "status": "healthy",
        "services": {
            "api": "online",
            "document_processing": "online"
        }
    }