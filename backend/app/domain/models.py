"""
Models for Batch Detection and Redaction Responses

This module defines Pydantic models to standardize the APIs JSON responses
for batch detection and redaction operations. Each operation returns a summary
of the overall batch (“BatchSummary” / “RedactBatchSummary”), per-file results
(“FileResult” / “RedactFileResult”), and optional debug information. These models
ensure consistency, omit null fields, and support clear, self-documenting schemas
for clients and API documentation.

Classes:
    FileResult: Represents the outcome of processing a single file in detection.
    BatchSummary: Aggregates statistics for an entire detection batch.
    BatchDetectionDebugInfo: Contains memory and operation ID for debugging.
    BatchDetectionResponse: Top-level wrapper for batch detection responses.
    RedactFileResult: Represents the outcome of redacting a single file.
    RedactBatchSummary: Aggregates statistics for an entire redaction batch.
    BatchRedactResponse: Top-level wrapper for batch redaction error responses.
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class FileResult(BaseModel):
    """
    Represents the result for a single file in a detection batch.

    Attributes:
        file (str): The original filename.
        status (str): "success" or "error".
        results (Optional[Dict[str, Any]]): The detection payload when status == "success".
        error (Optional[str]): Error message when status == "error".
    """
    file: str
    status: str
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    class Config:
        # Omit any fields whose value is None
        exclude_none = True


class BatchSummary(BaseModel):
    """
    Summary of an entire detection batch operation.

    Attributes:
        batch_id (str): Unique identifier for this batch.
        total_files (int): Number of files submitted.
        successful (int): Count of files processed successfully.
        failed (int): Count of files that failed.
        total_time (float): Total processing time in seconds.
        workers (Optional[int]): Number of parallel workers used (if applicable).
        total_matches (Optional[int]): Total number of matches (search-specific).
        search_term (Optional[str]): Search term used (search-specific).
        target_bbox (Optional[str]): Bounding box target (bbox-specific).
    """
    batch_id: str
    total_files: int
    successful: int
    failed: int
    total_time: float
    workers: Optional[int] = None
    total_matches: Optional[int] = None
    search_term: Optional[str] = None
    target_bbox: Optional[str] = None

    class Config:
        exclude_none = True


class BatchDetectionDebugInfo(BaseModel):
    """
    Debug information for a detection batch.

    Attributes:
        memory_usage (Optional[float]): Current memory usage (MB or %).
        peak_memory (Optional[float]): Peak memory usage recorded.
        operation_id (str): Identifier for this specific operation run.
    """
    memory_usage: Optional[float]
    peak_memory: Optional[float]
    operation_id: str

    class Config:
        exclude_none = True


class BatchDetectionResponse(BaseModel):
    """
    Top-level response model for batch detection endpoints.

    Attributes:
        batch_summary (BatchSummary): Aggregated batch statistics.
        file_results (List[FileResult]): Individual file results.
        debug (Optional[BatchDetectionDebugInfo]): Optional debug and memory info.
    """
    batch_summary: BatchSummary
    file_results: List[FileResult]
    debug: Optional[BatchDetectionDebugInfo] = None

    class Config:
        exclude_none = True


class RedactFileResult(BaseModel):
    """
    Represents the result for a single file in a redaction batch.

    Attributes:
        file (str): The original filename.
        status (str): "success" or "error".
        redactions_applied (Optional[int]): Number of redactions applied.
        arcname (Optional[str]): Filename under which the redacted file is archived (ZIP only).
        error (Optional[str]): Error message when status == "error".
    """
    file: str
    status: str
    redactions_applied: Optional[int] = None
    arcname: Optional[str] = None
    error: Optional[str] = None

    class Config:
        exclude_none = True


class RedactBatchSummary(BaseModel):
    """
    Summary of an entire redaction batch operation.

    Attributes:
        batch_id (str): Unique identifier for this redaction run.
        total_files (int): Number of files submitted.
        successful (int): Count of files redacted successfully.
        failed (int): Count of files that failed redaction.
        total_redactions (int): Total redactions applied across all files.
        total_time (float): Total processing time in seconds.
    """
    batch_id: str
    total_files: int
    successful: int
    failed: int
    total_redactions: int
    total_time: float

    class Config:
        exclude_none = True


class BatchRedactResponse(BaseModel):
    """
    Top-level response model for batch redaction endpoints (error paths).

    Attributes:
        batch_summary (RedactBatchSummary): Aggregated batch redaction statistics.
        file_results (List[RedactFileResult]): Individual file redaction results.
    """
    batch_summary: RedactBatchSummary
    file_results: List[RedactFileResult]

    class Config:
        exclude_none = True
