
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.ai_detect_service import AIDetectService
from backend.app.utils.system_utils.memory_management import memory_optimized

# Configure rate limiter and router
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Router: The endpoint just calls the service.
@router.post("/detect")
@limiter.limit("10/minute")
@memory_optimized(threshold_mb=75)
async def ai_detect_sensitive(
    request: Request,
    file: UploadFile = File(...),
    requested_entities: Optional[str] = Form(None),
    remove_words: Optional[str] = Form(None)  # New parameter for comma-separated words
):
    """
    Minimal endpoint that delegates document processing to AIDetectService.
    """
    service = AIDetectService()
    return await service.detect(file, requested_entities, remove_words)
