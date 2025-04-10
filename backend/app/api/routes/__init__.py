"""
Routes package for API endpoints.

This module exports all route collections for the API.
"""
from backend.app.api.routes.status_routes import router as status_router
from backend.app.api.routes.pdf_routes import router as pdf_router
from backend.app.api.routes.ai_routes import router as gemini_router
from backend.app.api.routes.machine_learning import router as presidio_router
from backend.app.api.routes.metadata_routes import router as metadata_router
from backend.app.api.routes.batch_routes import router as batch_router

# Export all routers
__all__ = [
    "status_router",
    "pdf_router",
    "gemini_router",
    "presidio_router",
    "metadata_router",
    "batch_router"
]
