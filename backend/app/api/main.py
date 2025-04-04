import time
import atexit
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.api.routes import (
    status_router,
    pdf_router,
    gemini_router,
    presidio_router,
    metadata_router,
    batch_router,
)
from backend.app.services.initialization_service import initialization_service
from backend.app.utils.logging.logger import log_info, log_error
from backend.app.utils.security.caching_middleware import CacheMiddleware
from backend.app.utils.security.retention_management import retention_manager
from backend.app.utils.security.rate_limiting import RateLimitingMiddleware, get_rate_limit_config

# Allowed origins from environment or default
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,https://www.hidemeai.com,http://localhost:5173"
).split(",")


def _init_middlewares(app: FastAPI) -> None:
    """Initialize and add middleware components to the app."""
    app.add_middleware(BaseHTTPMiddleware, dispatch=SecurityHeadersMiddleware(app=app).dispatch)
    app.add_middleware(BaseHTTPMiddleware, dispatch=ValidationMiddleware(app=app).dispatch)
    app.add_middleware(BaseHTTPMiddleware, dispatch=RequestSizeMiddleware(max_content_length=25 * 1024 * 1024, app=app).dispatch)
    app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses >1KB

    # Add the custom rate limiting middleware using the centralized configuration
    app.add_middleware(RateLimitingMiddleware, config=get_rate_limit_config())

    # Configure CORS
    cors_config = {
        "allow_origins": ALLOWED_ORIGINS,
        "allow_credentials": True,
        "allow_methods": ["POST", "GET"],
        "allow_headers": ["*"],
        "max_age": 1800,  # Cache preflight for 10 minutes
    }
    if os.environ.get("ENVIRONMENT") == "production":
        cors_config["allow_origins"] = [origin for origin in ALLOWED_ORIGINS if
                                        not origin.startswith("http://localhost")]
    app.add_middleware(CORSMiddleware, **cors_config)


def _init_rate_limiting(app: FastAPI) -> None:
    """
    (Optional) Additional rate limiting configuration can be done here if needed.
    The primary rate limiter is applied via RateLimitingMiddleware.
    """
    pass  # Rate limiting is handled by the middleware added in _init_middlewares


# Custom middleware classes (unchanged)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; script-src 'self'; connect-src 'self'; img-src 'self'; "
                "style-src 'self'; frame-ancestors 'none'; form-action 'self'; block-all-mixed-content; "
                "upgrade-insecure-requests"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                "img-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
            )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response


class RequestSizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_content_length: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_content_length = max_content_length

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > self.max_content_length:
            return Response(
                status_code=413,
                content={"detail": "Request body too large"},
                media_type="application/json"
            )
        return await call_next(request)


class ValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        suspicious_patterns = ["../", "..\\", ";", "&&", "|", "eval("]
        for pattern in suspicious_patterns:
            if pattern in path:
                return Response(
                    status_code=400,
                    content={"detail": "Invalid request path"},
                    media_type="application/json"
                )
        return await call_next(request)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with enhanced security and modular middleware.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Sensitive Data Detection and Redaction API",
        version="1.0",
        description="""
        API for detecting and redacting sensitive information from documents with GDPR compliance.
        Processing is performed in-memory where possible, with strict data minimization and security controls.
        """,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    _init_middlewares(app)
    _init_rate_limiting(app)

    # Add the caching middleware for specific paths, now handling POST as well
    app.add_middleware(CacheMiddleware, paths=["/ai", "/ml", "/batch", "/pdf"], ttl=300)

    app.include_router(status_router, tags=["Status"])
    app.include_router(pdf_router, prefix="/pdf", tags=["PDF Processing"])
    app.include_router(gemini_router, prefix="/ai", tags=["AI Detection"])
    app.include_router(presidio_router, prefix="/ml", tags=["Machine Learning Detection"])
    app.include_router(metadata_router, prefix="/help", tags=["System Metadata"])
    app.include_router(batch_router, prefix="/batch", tags=["Batch Processing"])

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title="Sensitive Data Detection and Redaction API",
            version="1.0",
            description="""
            API for detecting and redacting sensitive information from various document formats.

            GDPR Compliance:
            - Processing is performed under GDPR Article 6(1)(f).
            - Data is processed in-memory where possible and temporary files are securely deleted.
            - Data minimization principles are applied throughout the pipeline.

            Security:
            - Endpoints enforce rate limiting.
            - Files are validated before processing.
            - Processing results are sanitized to remove sensitive details.
            - TLS is used for secure transmission.
            """,
            routes=app.routes,
        )

        openapi_schema["components"] = openapi_schema.get("components", {})
        openapi_schema["components"]["securitySchemes"] = {
            "apiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key"
            }
        }

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        request_id = f"req_{time.time()}_{os.urandom(4).hex()}"
        request.state.request_id = request_id
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = request_id
        log_info(f"[REQUEST] {request.method} {request.url.path} completed in {process_time:.4f}s [ID: {request_id}]")
        return response

    @app.on_event("startup")
    async def startup_event():
        """
        Perform lazy initialization of detectors and other services on startup.
        Detector initialization is deferred until first use.
        """
        start_time = time.time()
        log_info("[STARTUP] Starting lazy initialization of detectors...")
        try:
            await initialization_service.initialize_detectors_lazy()
            status = initialization_service.get_initialization_status()
            log_info(f"[STARTUP] Presidio initialized: {status.get('presidio', False)}")
            log_info(f"[STARTUP] Gemini initialized: {status.get('gemini', False)}")
            log_info(f"[STARTUP] GLiNER initialized: {status.get('gliner', False)}")
            health = initialization_service.check_health()
            log_info(f"[STARTUP] Health check: {health.get('status', 'unknown')}")
            retention_manager.start()
            total_time = time.time() - start_time
            log_info(f"[STARTUP] Lazy initialization complete in {total_time:.2f}s")
        except Exception as e:
            log_error(f"[STARTUP] Error during detector lazy initialization: {e}")
            # Continue startup; detectors will initialize on demand.

    @app.on_event("shutdown")
    async def shutdown_event():
        log_info("[SHUTDOWN] Cleaning up resources...")
        retention_manager.shutdown()
        try:
            await initialization_service.shutdown_async()
        except Exception as e:
            log_error(f"[SHUTDOWN] Error during shutdown: {e}")
        try:
            import gc
            gc.collect()
            from backend.app.utils.security.caching_middleware import invalidate_cache
            invalidate_cache()
            log_info("[SHUTDOWN] Additional cleanup completed successfully")
        except Exception as e:
            log_error(f"[SHUTDOWN] Error during additional cleanup: {e}")
        log_info("[SHUTDOWN] Cleanup complete")

    atexit.register(lambda: retention_manager.shutdown())
    log_info("[OK] API application created and configured successfully")
    return app

app = create_app()
