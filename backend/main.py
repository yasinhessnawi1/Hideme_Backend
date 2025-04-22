"""
Main entry point for the document processing API application.
This module initializes the FastAPI application by creating an app instance from the API factory,
loads configuration parameters using the configuration singleton,
and starts the Uvicorn server with the specified host, port, and debug settings.
It serves as the primary launcher for the application and supports development (with auto-reload)
or production mode depending on the configuration.
"""

import uvicorn
from backend.app.api.main import create_app
from backend.app.utils.logging.logger import log_info
from backend.app.configs.config_singleton import get_config

# Create the FastAPI application instance using the factory function.
app = create_app()

# Load the API port from the configuration; default to 8000 if not specified.
port = get_config("api_port", 8000)
# Load the API host from the configuration; default to "0.0.0.0" to listen on all interfaces.
host = get_config("api_host", "0.0.0.0")
# Load the debug flag from the configuration; default to False.
debug = get_config("debug", False)

if __name__ == "__main__":
    # Log the startup information with host, port, and debug mode.
    log_info(f"[OK] Starting server on {host}:{port} (debug={debug})")
    # Start the Uvicorn server with the application specified by its import path.
    uvicorn.run(
        "backend.main:app",          # Path to the ASGI application.
        host=host,                   # Bind the server to the specified host.
        port=port,                   # Bind the server to the specified port.
        reload=debug,                # Enable automatic reload if in debug mode.
        log_level="info",            # Set the log level to "info" for server logs.
        workers=1,                   # Run with a single worker process.
        limit_concurrency=100,       # Limit the number of concurrent requests.
        timeout_keep_alive=600       # Set the keep-alive timeout for connections (in seconds).
    )
