"""
Main API module for document processing system.

This module creates and configures the FastAPI application.
"""
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from backend.app.api.routes import (
    status_router,
    pdf_router,
    gemini_router,
    presidio_router,
    metadata_router,
    hybrid_router,
)
from backend.app.api.routes.hybrid_routes import hybrid_detect_sensitive

from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logger import log_info, log_error


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Sensitive Data Detection and Redaction API",
        version="1.0",
        description="API for detecting and redacting sensitive information from documents."
    )

    # Add CORS middleware to allow all origins for now
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict this to allowed origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes with appropriate prefixes and tags
    app.include_router(status_router, tags=["Status"])
    app.include_router(pdf_router, prefix="/pdf", tags=["PDF Processing"])
    app.include_router(gemini_router, prefix="/ai", tags=["AI Detection"])
    app.include_router(presidio_router, prefix="/ml", tags=["Machine Learning Detection"])
    app.include_router(metadata_router, prefix="/help", tags=["System Metadata"])
    app.include_router(hybrid_router, prefix="/hybrid", tags=["Hybrid Detection"])

    # Customize OpenAPI schema
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title="Sensitive Data Detection and Redaction API",
            version="1.0",
            description="API for detecting and redacting sensitive information from various document formats.",
            routes=app.routes,
        )

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    @app.on_event("startup")
    def startup_event():
        """
        Initialize all entity detectors on application startup.

        This ensures that models are downloaded once when the server starts
        and cached for future use.
        """
        start_time = time.time()
        log_info("[STARTUP] Pre-initializing entity detectors...")

        try:
            # Initialize all detectors including GLiNER model
            initialization_service.initialize_detectors()

            # Get initialization status
            status = initialization_service.get_initialization_status()

            # Log status details
            log_info(f"[STARTUP] Presidio initialized: {status['presidio']}")
            log_info(f"[STARTUP] Gemini initialized: {status['gemini']}")
            log_info(f"[STARTUP] GLiNER initialized: {status.get('gliner', False)}")

            # Run health check
            health = initialization_service.check_health()
            log_info(f"[STARTUP] Health check: {health['status']}")

            total_time = time.time() - start_time
            log_info(f"[STARTUP] Entity detectors pre-initialization complete in {total_time:.2f}s")

        except Exception as e:
            log_error(f"[STARTUP] Error initializing entity detectors: {e}")

    # Use the safe logger function to avoid encoding issues
    log_info("[OK] API application created and configured successfully")
    return app