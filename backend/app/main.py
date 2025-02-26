import uvicorn
from fastapi import FastAPI

from backend.app.routes import ai_routes, presidio_routes, pdf_routes
from backend.app.utils.logger import default_logger as logger


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    """
    app_api = FastAPI(
        title="Sensitive Data Detection and Redaction API",
        version="1.0",
        description="API for detecting and redacting sensitive information from documents."
    )

    # Include route modules.
    app_api.include_router(ai_routes.router, prefix="/ai", tags=["AI Detection"])
    app_api.include_router(presidio_routes.router, prefix="/ml", tags=["Machine Learning Detection"])
    app_api.include_router(pdf_routes.router, prefix="/pdf", tags=["PDF Redaction"])

    return app_api


app = create_app()

if __name__ == "__main__":
    # Configure logging if needed.
    logger.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
