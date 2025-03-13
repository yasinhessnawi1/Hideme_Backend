"""
API models for document processing endpoints.

This module contains Pydantic models for API request and response validation.
"""
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel


class StatusResponse(BaseModel):
    """Response model for status endpoint."""
    status: str


class PerformanceMetrics(BaseModel):
    """Model for performance metrics data."""
    extraction_time: Optional[float] = None
    detection_time: Optional[float] = None
    redaction_time: Optional[float] = None
    total_time: Optional[float] = None


class ProcessingResult(BaseModel):
    """Response model for document processing endpoints."""
    status: str
    input_file: str
    output_file: Optional[str] = None
    entities_detected: Optional[int] = None
    error: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    performance: Optional[PerformanceMetrics] = None


class DetectionResponse(BaseModel):
    """Response model for entity detection endpoints."""
    redaction_mapping: Dict[str, Any]
    performance: Optional[PerformanceMetrics] = None


class RedactionRequest(BaseModel):
    """Request model for redaction endpoint."""
    redaction_mapping: Dict[str, Any]


class ProcessingJobResponse(BaseModel):
    """Response model for async processing job."""
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Response model for job status check."""
    job_id: str
    status: str
    result: Optional[ProcessingResult] = None
    processing_time: Optional[float] = None


class AvailableEnginesResponse(BaseModel):
    """Response model for available engines endpoint."""
    engines: List[str]


class AvailableEntitiesResponse(BaseModel):
    """Response model for available entities endpoint."""
    presidio_entities: List[str]
    gemini_entities: Dict[str, str]
    gliner_entities: Optional[List[str]] = None


class DetectorStatusResponse(BaseModel):
    """Response model for detector status endpoint."""
    initialized: bool
    last_used: Optional[float] = None
    idle_time: Optional[float] = None