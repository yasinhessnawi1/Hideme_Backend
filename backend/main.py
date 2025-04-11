"""
Main entry point for the document processing API application.
"""
import uvicorn
from backend.app.api.main import create_app
from backend.app.utils.logging.logger import log_info
from backend.app.configs.config_singleton import get_config

# Create the application
app = create_app()

# Load configuration
port = get_config("api_port", 8000)
host = get_config("api_host", "0.0.0.0")
debug = get_config("debug", False)

if __name__ == "__main__":
    log_info(f"[OK] Starting server on {host}:{port} (debug={debug})")
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info",
        workers=1,
        limit_concurrency=100,
        timeout_keep_alive=600
    )