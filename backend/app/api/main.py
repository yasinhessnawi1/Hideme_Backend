"""
Main entry point for the Sensitive Data Detection and Redaction API.

This module initializes and configures the FastAPI application with security,
error handling, and middleware essential for processing sensitive data securely.
It ensures compliance with GDPR and provides modular routing for various services.
"""

import time
import atexit  # Ensure resources are cleaned up when the program exits.
import os
import json  # Used for serializing error responses.

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Importing the API routers for various modules.
from backend.app.api.routes import (
    status_router,
    pdf_router,
    gemini_router,
    presidio_router,
    metadata_router,
    batch_router,
)
# Service that initializes detectors and related components.
from backend.app.services.initialization_service import initialization_service
# Constants for allowed origins and JSON media type.
from backend.app.utils.constant.constant import ALLOWED_ORIGINS, JSON_MEDIA_TYPE
# Logging functions for information and error logging.
from backend.app.utils.logging.logger import log_info, log_error
# Caching middleware to cache responses on specific paths.
from backend.app.utils.security.caching_middleware import CacheMiddleware
# Manager for data retention and cleanup.
from backend.app.utils.security.retention_management import retention_manager
# Rate limiting middleware and configuration retrieval.
from backend.app.utils.security.rate_limiting import RateLimitingMiddleware, get_rate_limit_config
# Security-aware error handling for safely processing exceptions.
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler


def _init_middlewares(app: FastAPI) -> None:
    """
    Initialize and add middleware components to the FastAPI application.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    try:
        # Add custom middleware to set security headers on all responses.
        app.add_middleware(
            BaseHTTPMiddleware,
            dispatch=SecurityHeadersMiddleware(app=app).dispatch
        )
        # Add validation middleware to prevent suspicious URL patterns.
        app.add_middleware(
            BaseHTTPMiddleware,
            dispatch=ValidationMiddleware(app=app).dispatch
        )
        # Add middleware to enforce a maximum request body size.
        app.add_middleware(
            BaseHTTPMiddleware,
            dispatch=RequestSizeMiddleware(max_content_length=25 * 1024 * 1024, app=app).dispatch
        )
        # Add GZip middleware to compress responses larger than 1KB.
        app.add_middleware(GZipMiddleware, minimum_size=1000)
        # Add rate limiting middleware using centralized configuration.
        app.add_middleware(RateLimitingMiddleware, config=get_rate_limit_config())

        # Set up CORS (Cross-Origin Resource Sharing) configuration.
        cors_config = {
            "allow_origins": ALLOWED_ORIGINS,  # Allowed origins from constant.
            "allow_credentials": True,
            "allow_methods": ["POST", "GET"],
            "allow_headers": ["*"],
            "max_age": 600,  # Cache preflight requests for 10 minutes.
        }
        # In production, filter out localhost origins.
        if os.environ.get("ENVIRONMENT") == "production":
            cors_config["allow_origins"] = [
                origin for origin in ALLOWED_ORIGINS if not origin.startswith("http://localhost")
            ]
        # Apply the CORS configuration.
        app.add_middleware(CORSMiddleware, **cors_config)
    except Exception as e:
        # Log any errors during middleware initialization securely.
        SecurityAwareErrorHandler.log_processing_error(e, "init_middlewares")


def _init_rate_limiting(app: FastAPI) -> None:
    """
    (Optional) Additional rate limiting configuration can be done here if needed.
    The primary rate limiter is applied via RateLimitingMiddleware.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    try:
        # Currently, additional rate limiting logic is not needed.
        pass
    except Exception as e:
        # Log any errors during rate limiting initialization.
        SecurityAwareErrorHandler.log_processing_error(e, "init_rate_limiting")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    SecurityHeadersMiddleware is an ASGI middleware that adds essential security-related HTTP headers to every response.

    This middleware ensures that security measures such as preventing content type sniffing,
    XSS protection, strict transport security, and content security policies are applied consistently.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Add security-related HTTP headers to every response.

        Args:
            request (Request): The incoming HTTP request.
            call_next (Callable): Function to execute the next middleware or route handler.

        Returns:
            Response: The modified HTTP response with additional security headers.
        """
        try:
            # Process the request through the next middleware/route handler.
            response = await call_next(request)
            # Set HTTP header to prevent MIME type sniffing.
            response.headers["X-Content-Type-Options"] = "nosniff"
            # Deny framing of the content.
            response.headers["X-Frame-Options"] = "DENY"
            # Enable XSS protection in browsers.
            response.headers["X-XSS-Protection"] = "1; mode=block"
            # Set strict transport security header.
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
            # Determine the environment to set the appropriate Content-Security-Policy.
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
            # Set additional security-related headers.
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
            # Return the modified response.
            return response
        except Exception as e:
            # On error, create a secure error response using SecurityAwareErrorHandler.
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_dispatch_main", endpoint=str(request.url)
            )
            status = error_info.get("status_code", 500)
            return Response(
                content=error_info,
                status_code=status,
                media_type=JSON_MEDIA_TYPE
            )


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """
    RequestSizeMiddleware is an ASGI middleware that enforces a maximum request body size.

    It checks the 'content-length' header of incoming HTTP requests and returns a 413 error response
    if the request body size exceeds the configured limit.
    """

    def __init__(self, app, max_content_length: int = 10 * 1024 * 1024):
        """
        Initialize the middleware to enforce a maximum request body size.

        Args:
            app: The ASGI application.
            max_content_length (int): Maximum allowed size of the request body in bytes.
        """
        super().__init__(app)
        # Set the maximum allowed content length.
        self.max_content_length = max_content_length

    async def dispatch(self, request: Request, call_next):
        """
        Check the request's content length and return a 413 error response if it exceeds the limit.

        Args:
            request (Request): The incoming HTTP request.
            call_next (Callable): Function to execute the next middleware/route handler.

        Returns:
            Response: Either the original response if within limit, or a 413 error response.
        """
        try:
            # Retrieve the 'content-length' header from the request.
            content_length = request.headers.get("content-length")
            # If the content length is provided and exceeds the maximum allowed, return a 413 response.
            if content_length is not None and int(content_length) > self.max_content_length:
                return Response(
                    status_code=413,
                    content=json.dumps({"detail": "Request body too large"}),
                    media_type=JSON_MEDIA_TYPE
                )
            # Otherwise, continue processing the request.
            return await call_next(request)
        except Exception as e:
            # Handle any errors and create a safe error response.
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_dispatch_request", endpoint=str(request.url)
            )
            status = error_info.get("status_code", 500)
            return Response(
                content=error_info,
                status_code=status,
                media_type=JSON_MEDIA_TYPE
            )


class ValidationMiddleware(BaseHTTPMiddleware):
    """
    ValidationMiddleware is an ASGI middleware that validates incoming request paths.

    It checks for suspicious patterns in the URL to prevent potential security risks and returns
    a 400 error response if an invalid path is detected.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Validate the incoming request path for suspicious patterns.

        Args:
            request (Request): The incoming HTTP request.
            call_next (Callable): Function to execute the next middleware/route handler.

        Returns:
            Response: The original response if the path is valid, otherwise a 400 error response.
        """
        try:
            # Retrieve the URL path from the request.
            path = request.url.path
            # Define a list of suspicious patterns that should not be in the path.
            suspicious_patterns = ["../", "..\\", ";", "&&", "|", "eval("]
            # Check each pattern to see if it appears in the path.
            for pattern in suspicious_patterns:
                if pattern in path:
                    # If a suspicious pattern is found, return a 400 error response.
                    return Response(
                        status_code=400,
                        content=json.dumps({"detail": "Invalid request path"}),
                        media_type=JSON_MEDIA_TYPE
                    )
            # Proceed with processing if the path is valid.
            return await call_next(request)
        except Exception as e:
            # Handle errors during path validation securely.
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_validationMiddleware", endpoint=str(request.url)
            )
            status = error_info.get("status_code", 500)
            return Response(
                content=error_info,
                status_code=status,
                media_type=JSON_MEDIA_TYPE
            )


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with enhanced security, error handling, and modular middleware.

    Returns:
        FastAPI: The fully configured FastAPI application instance.
    """
    try:
        # Initialize the FastAPI application with metadata and custom documentation URLs.
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

        # Initialize and add the necessary middlewares.
        _init_middlewares(app)
        _init_rate_limiting(app)

        # Add caching middleware for specific paths to improve performance.
        app.add_middleware(
            CacheMiddleware,
            paths=[
                "/ai", "/ml", "/batch", "/pdf", "/status", "/help",
                "/readiness", "/metrics", "/health"
            ],
            ttl=600
        )

        # Include routers for various API endpoints.
        app.include_router(status_router, tags=["Status"])
        app.include_router(pdf_router, prefix="/pdf", tags=["PDF Processing"])
        app.include_router(gemini_router, prefix="/ai", tags=["AI Detection"])
        app.include_router(presidio_router, prefix="/ml", tags=["Machine Learning Detection"])
        app.include_router(metadata_router, prefix="/help", tags=["System Metadata"])
        app.include_router(batch_router, prefix="/batch", tags=["Batch Processing"])

        def custom_openapi():
            """
            Generate a custom OpenAPI schema including security schemes.

            Returns:
                dict: The generated OpenAPI schema.
            """
            # Return the schema if it has already been generated.
            if app.openapi_schema:
                return app.openapi_schema
            # Generate the OpenAPI schema using current routes and metadata.
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
            # Add security schemes to the OpenAPI schema for API key authentication.
            openapi_schema["components"] = openapi_schema.get("components", {})
            openapi_schema["components"]["securitySchemes"] = {
                "apiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key"
                }
            }
            app.openapi_schema = openapi_schema
            # Return the completed OpenAPI schema.
            return app.openapi_schema

        # Set the custom OpenAPI schema for the application.
        app.openapi = custom_openapi

        @app.middleware("http")
        async def add_process_time_header(request: Request, call_next):
            """
            Middleware to add processing time and request ID headers to every response.

            Args:
                request (Request): The incoming HTTP request.
                call_next (Callable): The next middleware/route handler.

            Returns:
                Response: The HTTP response with additional custom headers.
            """
            # Generate a unique request ID using current time and random bytes.
            request_id = f"req_{time.time()}_{os.urandom(4).hex()}"
            # Attach the request ID to the request state.
            request.state.request_id = request_id
            # Record the start time for processing.
            start_time = time.time()
            try:
                # Process the request with the next middleware/route handler.
                response = await call_next(request)
            except Exception as exp:
                # On error, handle securely using SecurityAwareErrorHandler.
                error_info = SecurityAwareErrorHandler.handle_safe_error(
                    exp, "api_process_time_header", endpoint=str(request.url)
                )
                status = error_info.get("status_code", 500)
                return Response(
                    content=error_info,
                    status_code=status,
                    media_type=JSON_MEDIA_TYPE
                )
            # Calculate the total processing time.
            process_time = time.time() - start_time
            # Add custom headers with processing time and request ID.
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Request-ID"] = request_id
            log_info(
                f"[REQUEST] {request.method} {request.url.path} completed in {process_time:.4f}s [ID: {request_id}]")
            # Return the modified response.
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
                # Begin lazy initialization of detectors.
                await initialization_service.initialize_detectors_lazy()
                # Retrieve the current initialization status.
                status = initialization_service.get_initialization_status()
                log_info(f"[STARTUP] Presidio initialized: {status.get('presidio', False)}")
                log_info(f"[STARTUP] Gemini initialized: {status.get('gemini', False)}")
                log_info(f"[STARTUP] GLiNER initialized: {status.get('gliner', False)}")
                # Perform a health check of the service.
                health = initialization_service.check_health()
                log_info(f"[STARTUP] Health check: {health.get('status', 'unknown')}")
                # Start the retention manager for data cleanup.
                retention_manager.start()
                total_time = time.time() - start_time
                log_info(f"[STARTUP] Lazy initialization complete in {total_time:.2f}s")
            except Exception as exp:
                # Log any errors during startup but allow the application to continue.
                log_error(f"[STARTUP] Error during detector lazy initialization: {exp}")

        @app.on_event("shutdown")
        async def shutdown_event():
            """
            Clean up resources on application shutdown.
            """
            log_info("[SHUTDOWN] Cleaning up resources...")
            # Shut down the retention manager.
            retention_manager.shutdown()
            try:
                # Attempt asynchronous shutdown of the initialization service.
                await initialization_service.shutdown_async()
            except Exception as exp:
                log_error(f"[SHUTDOWN] Error during shutdown: {exp}")
            try:
                # Perform garbage collection to free memory.
                import gc
                gc.collect()
                # Invalidate any cached responses.
                from backend.app.utils.security.caching_middleware import invalidate_cache
                invalidate_cache()
                log_info("[SHUTDOWN] Additional cleanup completed successfully")
            except Exception as exp:
                log_error(f"[SHUTDOWN] Error during additional cleanup: {exp}")
            log_info("[SHUTDOWN] Cleanup complete")

        # Register atexit handler to ensure retention manager is shut down on exit.
        atexit.register(lambda: retention_manager.shutdown())
        log_info("[OK] API application created and configured successfully")
        # Return the fully configured FastAPI application.
        return app
    except Exception as e:
        # Log and re-raise any errors during application creation.
        SecurityAwareErrorHandler.log_processing_error(e, "create_app")
        raise


# Create the FastAPI app.
app = create_app()
