import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the routers from your routes modules.
from backend.app.routes import ai_routes, presidio_routes, pdf_routes, status_routes

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

    # --- Security and Middleware Setup ---
    # Add CORS middleware to allow all origins for now.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict this to your allowed origins.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # (Optional) You can add more security middleware here (e.g., HTTPSRedirectMiddleware,
    # custom error handlers, security headers, etc.)

    # --- Include Routes ---
    app.include_router(ai_routes.router, prefix="/ai", tags=["AI Detection"])
    app.include_router(presidio_routes.router, prefix="/ml", tags=["Machine Learning Detection"])
    app.include_router(pdf_routes.router, prefix="/pdf", tags=["PDF Redaction"])
    app.include_router(status_routes.router, tags=["Status"])




app = create_app()

if __name__ == "__main__":
    logger.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
