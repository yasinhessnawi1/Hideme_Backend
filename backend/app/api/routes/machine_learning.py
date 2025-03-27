import time
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.machine_learning_service import MashinLearningService
from backend.app.utils.logging.logger import log_info, log_warning
from backend.app.utils.memory_management import memory_optimized, memory_monitor

# Configure rate limiter and router
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


# Router endpoints for Presidio and GLiNER

@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def presidio_detect_sensitive(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using Microsoft Presidio NER with enhanced security.
    """
    operation_id = f"presidio_detect_{int(time.time())}"
    log_info(f"[ML] Starting Presidio detection processing [operation_id={operation_id}]")
    service = MashinLearningService(detector_type="presidio")
    return await service.detect(file, requested_entities, operation_id)


@router.post("/gl_detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=200)  # GLiNER requires more memory
async def gliner_detect_sensitive_entities(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None)
):
    """
    Detect sensitive information using GLiNER with enhanced security and specialized entity recognition.
    """
    operation_id = f"gliner_detect_{int(time.time())}"
    log_info(f"[ML] Starting GLiNER detection processing [operation_id={operation_id}]")
    current_memory_usage = memory_monitor.get_memory_usage()
    if current_memory_usage > 85:
        log_warning(f"[ML] High memory pressure ({current_memory_usage:.1f}%), may impact GLiNER performance [operation_id={operation_id}]")
    service = MashinLearningService(detector_type="gliner")
    return await service.detect(file, requested_entities, operation_id)
