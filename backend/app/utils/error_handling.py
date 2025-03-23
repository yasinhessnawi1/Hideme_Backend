"""
Enhanced error handling utilities with security, privacy, and distributed tracing.

This module provides centralized error handling functionality that ensures
security and privacy when handling exceptions, preventing leakage of
sensitive information in error messages while maintaining helpful
diagnostics for developers and users. It includes distributed tracing
support and comprehensive logging for security audits.
"""
import asyncio
import uuid
import json
import traceback
import re
import os
import time
import logging
from typing import Dict, Any, Optional, TypeVar, Callable, Union, Tuple, Awaitable

from backend.app.utils.logger import log_warning, log_error

# Type variable for generic functions
T = TypeVar('T')

# Configure module logger
_logger = logging.getLogger("error_handling")


class SecurityAwareErrorHandler:
    """
    Enhanced error handler that ensures security and privacy when handling exceptions.

    Prevents leaking sensitive information in error messages while maintaining
    helpful diagnostics for developers and maintainers. Complies with GDPR
    Article 5(1)(f) requiring appropriate security measures and provides
    distributed tracing capabilities for complex systems.
    """

    # Sensitive keywords that should not appear in error messages
    _SENSITIVE_KEYWORDS = [
        'password', 'secret', 'key', 'token', 'credential', 'auth',
        'ssn', 'social', 'credit', 'card', 'cvv', 'secure', 'private',
        'passport', 'license', 'national', 'health', 'insurance', 'bank',
        'fodselsnummer', 'personnummer', 'address', 'phone', 'email',
        'api', 'access_token', 'refresh_token', 'bearer', 'authorization',
        'admin', 'username', 'login', 'signin', 'certificate', 'privkey'
    ]

    # Map of error types to safe error messages
    _ERROR_TYPE_MESSAGES = {
        'ValueError': 'Invalid value provided',
        'TypeError': 'Incorrect data type',
        'KeyError': 'Required key not found',
        'IndexError': 'Index out of range',
        'FileNotFoundError': 'Required file not found',
        'PermissionError': 'Permission denied',
        'IOError': 'I/O operation failed',
        'OSError': 'Operating system error',
        'ConnectionError': 'Connection failed',
        'TimeoutError': 'Operation timed out',
        'json.JSONDecodeError': 'Invalid JSON format',
        'ZeroDivisionError': 'Division by zero error',
        'AttributeError': 'Missing required attribute',
        'ImportError': 'Required module not available',
        'ModuleNotFoundError': 'Required module not found',
        'MemoryError': 'Insufficient memory to complete operation',
        'RuntimeError': 'Runtime execution error',
        'asyncio.TimeoutError': 'Asynchronous operation timed out',
        'UnicodeDecodeError': 'Character encoding error',
        'UnicodeEncodeError': 'Character encoding error',
        'NotImplementedError': 'Feature not implemented',
        'Exception': 'An error occurred'
    }

    # Paths to log detailed error information
    _ERROR_LOG_PATH = os.environ.get("ERROR_LOG_PATH", "app/logs/error_logs/detailed_errors.log")

    # JSON logging format for machine readability
    _USE_JSON_LOGGING = os.environ.get("ERROR_JSON_LOGGING", "true").lower() == "true"

    # URL patterns to sanitize (to avoid leaking internal URLs)
    _URL_PATTERNS = [
        r'https?://[^\s/$.?#].[^\s]*',  # Standard URLs
        r'redis://[^\s]*',  # Redis URLs
        r'mongodb://[^\s]*',  # MongoDB URLs
        r'postgresql://[^\s]*',  # PostgreSQL URLs
        r'mysql://[^\s]*',  # MySQL URLs
        r'jdbc:[^\s]*',  # JDBC URLs
        r'file://[^\s]*',  # File URLs
        r'ftp://[^\s]*',  # FTP URLs
        r's3://[^\s]*'  # S3 URLs
    ]

    # Distributed tracing configuration
    _ENABLE_DISTRIBUTED_TRACING = os.environ.get("ENABLE_DISTRIBUTED_TRACING", "false").lower() == "true"
    _SERVICE_NAME = os.environ.get("SERVICE_NAME", "document_processing")

    @staticmethod
    def handle_detection_error(
            e: Exception,
            operation_type: str,
            additional_info: Optional[Dict[str, Any]] = None,
            trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle errors from detection operations without leaking sensitive information.

        Args:
            e: The exception that occurred
            operation_type: Type of operation that failed
            additional_info: Optional additional information to include in response
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Standardized error response that doesn't leak implementation details
        """
        # Generate error ID and trace ID for tracking
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Sanitize the error message
        e = SecurityAwareErrorHandler._sanitize_error_message(str(e))

        # Get error type name
        error_type = type(e).__name__

        # Log the unsanitized error for debugging (internal only)
        log_error(f"[ERROR] {operation_type} error (ID: {error_id}, Trace: {trace_id}): {str(e)}")

        # Log detailed error with stack trace to file for investigation
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, error_type, str(e), operation_type, traceback.format_exc(),
            {"trace_id": trace_id}
        )

        # Use generic error message based on type if available
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            error_type,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )

        # Build standard error response
        error_response = {
            "redaction_mapping": {"pages": []},
            "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": error_type,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }

        # Add additional info if provided
        if additional_info:
            for key, value in additional_info.items():
                if key not in error_response:  # Don't overwrite standard fields
                    error_response[key] = value

        return error_response

    @staticmethod
    def handle_file_processing_error(
            e: Exception,
            operation_type: str,
            filename: Optional[str] = None,
            additional_info: Optional[Dict[str, Any]] = None,
            trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle errors from file processing operations without leaking sensitive information.

        Args:
            e: The exception that occurred
            operation_type: Type of operation that failed
            filename: Optional filename for reference
            additional_info: Optional additional information to include in response
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Standardized error response that doesn't leak implementation details
        """
        # Generate IDs for tracking
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Sanitize the error message and filename
        e = SecurityAwareErrorHandler._sanitize_error_message(str(e))
        safe_filename = "unknown" if not filename else SecurityAwareErrorHandler._sanitize_filename(filename)

        # Get error type name
        error_type = type(e).__name__

        # Log the uninitialized error for debugging (internal only)
        log_error(
            f"[ERROR] {operation_type} error on {filename or 'unknown file'} (ID: {error_id}, Trace: {trace_id}): {str(e)}")

        # Log detailed error with stack trace to file for investigation
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, error_type, str(e), operation_type, traceback.format_exc(),
            {"filename": filename, "trace_id": trace_id}
        )

        # Use generic error message based on type if available
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            error_type,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )

        # Build standard error response
        error_response = {
            "file": safe_filename,
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": error_type,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }

        # Add additional info if provided
        if additional_info:
            for key, value in additional_info.items():
                if key not in error_response:  # Don't overwrite standard fields
                    error_response[key] = value

        return error_response

    @staticmethod
    def handle_batch_processing_error(
            e: Exception,
            operation_type: str,
            files_count: int = 0,
            additional_info: Optional[Dict[str, Any]] = None,
            trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle errors from batch processing operations without leaking sensitive information.

        This method is used when processing multiple files in a batch operation and
        provides specific batch-oriented information in the response.

        Args:
            e: The exception that occurred
            operation_type: Type of operation that failed
            files_count: Number of files being processed
            additional_info: Optional additional information to include in response
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Standardized error response for batch operations
        """
        # Generate IDs for tracking
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Sanitize the error message
        e = SecurityAwareErrorHandler._sanitize_error_message(str(e))

        # Get error type name
        error_type = type(e).__name__

        # Log the uninitialized error for debugging (internal only)
        log_error(
            f"[ERROR] {operation_type} batch error on {files_count} files (ID: {error_id}, Trace: {trace_id}): {str(e)}")

        # Log detailed error with stack trace to file for investigation
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, error_type, str(e), operation_type, traceback.format_exc(),
            {"files_count": files_count, "trace_id": trace_id}
        )

        # Use generic error message based on type if available
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            error_type,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )

        # Build standard error response
        error_response = {
            "batch_summary": {
                "total_files": files_count,
                "successful": 0,
                "failed": files_count,
                "total_entities": 0,
                "total_time": 0,
                "error": f"{safe_message}. Reference ID: {error_id}",
                "error_id": error_id,
                "trace_id": trace_id,
                "timestamp": time.time()
            },
            "file_results": []
        }

        # Add additional info if provided
        if additional_info:
            for key, value in additional_info.items():
                if key not in error_response["batch_summary"]:  # Don't overwrite standard fields
                    error_response["batch_summary"][key] = value

        return error_response

    @staticmethod
    def handle_api_gateway_error(
            e: Exception,
            operation_type: str,
            endpoint: str,
            additional_info: Optional[Dict[str, Any]] = None,
            trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle errors from API gateway operations without leaking sensitive information.

        This is useful for API gateways and proxies that handle multiple backend services.

        Args:
            e: The exception that occurred
            operation_type: Type of operation that failed
            endpoint: API endpoint being accessed
            additional_info: Optional additional information to include in response
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Standardized error response for API gateway errors
        """
        # Generate IDs for tracking
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Sanitize the error message and endpoint
        e = SecurityAwareErrorHandler._sanitize_error_message(str(e))
        safe_endpoint = SecurityAwareErrorHandler._sanitize_url(endpoint)

        # Get error type name
        error_type = type(e).__name__

        # Log the uninitialized error for debugging (internal only)
        log_error(
            f"[ERROR] {operation_type} error on endpoint {safe_endpoint} (ID: {error_id}, Trace: {trace_id}): {str(e)}")

        # Log detailed error with stack trace to file for investigation
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, error_type, str(e), operation_type, traceback.format_exc(),
            {"endpoint": endpoint, "trace_id": trace_id}
        )

        # Determine HTTP status code based on error type
        status_code = 500  # Default to internal server error
        if isinstance(e, TimeoutError) or isinstance(e, asyncio.TimeoutError):
            status_code = 504  # Gateway Timeout
        elif isinstance(e, ConnectionError):
            status_code = 502  # Bad Gateway
        elif isinstance(e, ValueError) or isinstance(e, TypeError):
            status_code = 400  # Bad Request
        elif isinstance(e, PermissionError):
            status_code = 403  # Forbidden
        elif isinstance(e, FileNotFoundError) or "404" in str(e):
            status_code = 404  # Not Found

        # Use generic error message based on type if available
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            error_type,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )

        # Build standard error response
        error_response = {
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": error_type,
            "status_code": status_code,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }

        # Add additional info if provided
        if additional_info:
            for key, value in additional_info.items():
                if key not in error_response:  # Don't overwrite standard fields
                    error_response[key] = value

        return error_response

    @staticmethod
    def handle_safe_error(
            e: Exception,
            operation_type: str,
            resource_id: str = "",
            default_return: Optional[T] = None,
            additional_info: Optional[Dict[str, Any]] = None,
            trace_id: Optional[str] = None
    ) -> Union[Dict[str, Any], T]:
        """
        Generic error handler that selects the appropriate specialized handler
        based on the operation type and context.

        Args:
            e: The exception that occurred
            operation_type: Type of operation that failed
            resource_id: Identifier for the resource being processed
            default_return: Optional default return value if needed
            additional_info: Optional additional information to include in response
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Appropriate error response or default return value
        """
        # Generate trace ID if not provided
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Log stack trace for debugging purposes
        log_error(f"[ERROR] {operation_type} error on {resource_id} (Trace: {trace_id}): {str(e)}")
        log_error(f"[TRACE] {traceback.format_exc()}")

        # Select appropriate handler based on operation type
        if "detection" in operation_type:
            return SecurityAwareErrorHandler.handle_detection_error(
                e, operation_type, additional_info, trace_id)
        elif "file" in operation_type:
            return SecurityAwareErrorHandler.handle_file_processing_error(
                e, operation_type, resource_id, additional_info, trace_id)
        elif "batch" in operation_type:
            files_count = additional_info.get("files_count", 0) if additional_info else 0
            return SecurityAwareErrorHandler.handle_batch_processing_error(
                e, operation_type, files_count, additional_info, trace_id)
        elif "api" in operation_type:
            return SecurityAwareErrorHandler.handle_api_gateway_error(
                e, operation_type, resource_id, additional_info, trace_id)
        elif default_return is not None:
            # Use the provided default return value
            return default_return
        else:
            # Generic error response
            error_id = str(uuid.uuid4())
            error_type = type(e).__name__
            safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
                error_type,
                SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
            )

            # Build response
            error_response = {
                "status": "error",
                "error": f"{safe_message}. Reference ID: {error_id}",
                "error_type": error_type,
                "error_id": error_id,
                "trace_id": trace_id,
                "timestamp": time.time()
            }

            # Add additional info if provided
            if additional_info:
                for key, value in additional_info.items():
                    if key not in error_response:  # Don't overwrite standard fields
                        error_response[key] = value

            return error_response

    @staticmethod
    def log_processing_error(
            e: Exception,
            operation_type: str,
            resource_id: str = "",
            trace_id: Optional[str] = None
    ) -> str:
        """
        Log an error safely without leaking sensitive information and return a trace ID.

        Args:
            e: The exception that occurred
            operation_type: Type of operation that failed
            resource_id: Identifier for the resource being processed
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Trace ID for tracking the error
        """
        # Generate IDs for tracking
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        error_type = type(e).__name__
        sanitized_message = SecurityAwareErrorHandler._sanitize_error_message(str(e))

        log_error(f"[ERROR] {operation_type} error (ID: {error_id}, Trace: {trace_id}): {sanitized_message}")

        # Log detailed error with stack trace to file for investigation
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, error_type, str(e), operation_type, traceback.format_exc(),
            {"resource_id": resource_id, "trace_id": trace_id}
        )

        return trace_id

    @staticmethod
    def _log_detailed_error(
            error_id: str,
            error_type: str,
            error_message: str,
            operation_type: str,
            stack_trace: str,
            additional_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log detailed error information to a file for debugging purposes.

        This method keeps detailed error information for investigation
        without exposing it in API responses, with enhanced security
        and privacy protection.

        Args:
            error_id: Unique identifier for the error
            error_type: Type of the exception
            error_message: Raw error message
            operation_type: Type of operation that failed
            stack_trace: Full stack trace
            additional_info: Any additional context information
        """
        try:
            # Ensure log directory exists
            os.makedirs(os.path.dirname(SecurityAwareErrorHandler._ERROR_LOG_PATH), exist_ok=True)

            # Create a detailed error record
            error_record = {
                "error_id": error_id,
                "timestamp": time.time(),
                "error_type": error_type,
                "operation_type": operation_type,
                "error_message": error_message,
                "sanitized_message": SecurityAwareErrorHandler._sanitize_error_message(error_message),
                "stack_trace": stack_trace,
                "environment": os.environ.get("ENVIRONMENT", "development"),
                "service": SecurityAwareErrorHandler._SERVICE_NAME
            }

            # Add additional info if provided
            if additional_info:
                # Sanitize additional info to remove sensitive data
                sanitized_info = {}
                for key, value in additional_info.items():
                    if isinstance(value, str):
                        sanitized_info[key] = SecurityAwareErrorHandler._sanitize_error_message(value)
                    else:
                        sanitized_info[key] = value
                error_record["additional_info"] = sanitized_info

            # Add environment-specific information
            env_vars_to_capture = [
                "ENVIRONMENT", "SERVICE_NAME", "SERVICE_VERSION",
                "HOSTNAME", "DEPLOYMENT_ID", "REGION", "ZONE"
            ]
            env_info = {}
            for env_var in env_vars_to_capture:
                if env_var in os.environ:
                    env_info[env_var] = os.environ[env_var]

            if env_info:
                error_record["environment_info"] = env_info

            # Write to log file using the preferred format
            if SecurityAwareErrorHandler._USE_JSON_LOGGING:
                with open(SecurityAwareErrorHandler._ERROR_LOG_PATH, "a") as f:
                    f.write(json.dumps(error_record) + "\n")
            else:
                # Format for human readability
                with open(SecurityAwareErrorHandler._ERROR_LOG_PATH, "a") as f:
                    f.write(f"\n--- ERROR: {error_id} at {time.ctime(error_record['timestamp'])} ---\n")
                    f.write(f"Type: {error_type}\n")
                    f.write(f"Operation: {operation_type}\n")
                    f.write(f"Message: {error_message}\n")
                    f.write(f"Sanitized: {error_record['sanitized_message']}\n")
                    f.write("Stack Trace:\n")
                    f.write(stack_trace)
                    f.write("\n")
                    if 'additional_info' in error_record:
                        f.write("Additional Info:\n")
                        for k, v in error_record['additional_info'].items():
                            f.write(f"  {k}: {v}\n")
                    f.write("----------------------------------------\n")

            # Send to distributed tracing system if enabled
            if SecurityAwareErrorHandler._ENABLE_DISTRIBUTED_TRACING:
                SecurityAwareErrorHandler._send_to_distributed_tracing(error_record)

        except Exception as e:
            # If error logging fails, just log a warning - don't break the app
            log_warning(f"Failed to log detailed error information: {str(e)}")

    @staticmethod
    def _send_to_distributed_tracing(error_record: Dict[str, Any]) -> None:
        """
        Send error information to a distributed tracing system.

        This is a placeholder for integration with systems like Jaeger, Zipkin, etc.

        Args:
            error_record: Error record to send
        """
        # This would be implemented based on the specific distributed tracing system
        # For example, OpenTelemetry, Jaeger, Zipkin, or cloud-specific solutions
        pass

    def create_api_error_response(
            e: Exception,
            operation_type: str,
            status_code: int = 500,
            resource_id: str = ""
    ) -> Tuple[Dict[str, Any], int]:
        """
        Create a standardized API error response with safe error messages.

        This ensures consistent error handling across all API endpoints.

        Args:
            e: The exception that occurred
            operation_type: Type of operation that failed
            status_code: HTTP status code to return
            resource_id: Identifier for the resource being processed

        Returns:
            Tuple of (error_response_dict, status_code)
        """
        # Generate error ID for tracking
        error_id = str(uuid.uuid4())
        trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Get error type
        error_type = type(e).__name__

        # Log the error with full details for internal tracking
        log_error(f"[ERROR] {operation_type} error (ID: {error_id}, Trace: {trace_id}): {str(e)}")

        # Log detailed error with stack trace to file for investigation
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, error_type, str(e), operation_type, traceback.format_exc(),
            {"resource_id": resource_id, "trace_id": trace_id}
        )

        # Use generic error message based on type if available
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            error_type,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )

        # Return sanitized error response
        return {
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": error_type,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }, status_code
    @staticmethod
    def _sanitize_error_message(message: str) -> str:
        """
        Sanitize an error message to remove sensitive information.

        This enhanced version uses more sophisticated patterns to detect and
        redact potentially sensitive information while preserving useful
        error context.

        Args:
            message: Original error message

        Returns:
            Sanitized error message
        """
        if not message:
            return "Error details not available"

        # Make lowercase for comparison
        message_lower = message.lower()

        # Check for sensitive keywords
        for keyword in SecurityAwareErrorHandler._SENSITIVE_KEYWORDS:
            if keyword in message_lower:
                return "Error details redacted for security"

        # Remove file paths (preserve filename for context)
        # Pattern for common file paths
        def path_replacer(match):
            path = match.group(0)
            filename = os.path.basename(path)
            return f"[PATH]/{filename}"

        path_pattern = r'(?:\/[\w\-. ]+)+\/[\w\-. ]+'
        message = re.sub(path_pattern, path_replacer, message)

        # Remove potential JSON content while preserving structure type
        def json_replacer(match):
            json_str = match.group(0)
            # Count keys to give some context about the structure
            key_count = json_str.count(':')
            return f"[JSON_CONTENT:{key_count}_fields]"

        json_pattern = r'\{.*\}'
        message = re.sub(json_pattern, json_replacer, message, flags=re.DOTALL)

        # Remove URLs and connection strings
        for pattern in SecurityAwareErrorHandler._URL_PATTERNS:
            message = re.sub(pattern, '[URL_REDACTED]', message)

        # Remove potential authentication tokens
        token_pattern = r'(auth|token|bearer|jwt|api[-_]?key)[^\s]*'
        message = re.sub(token_pattern, '[AUTH_TOKEN]', message, flags=re.IGNORECASE)

        # Remove potential PII like emails, numbers, etc.
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        message = re.sub(email_pattern, '[EMAIL]', message)

        # Norwegian national ID
        no_id_pattern = r'\b\d{6}\s?\d{5}\b'
        message = re.sub(no_id_pattern, '[NATIONAL_ID]', message)

        # Credit card numbers
        cc_pattern = r'\b(?:\d{4}[ -]?){3}\d{4}\b'
        message = re.sub(cc_pattern, '[CREDIT_CARD]', message)

        # General ID numbers
        id_pattern = r'\b(?:id|user|account)[\s:=_-]+(\d{4,})\b'
        message = re.sub(id_pattern, lambda m: f"{m.group(1).split(':')[0]}:[ID_NUMBER]", message, flags=re.IGNORECASE)

        # Other number sequences that could be sensitive
        number_sequence = r'\b\d{8,16}\b'
        message = re.sub(number_sequence, '[NUMBER_SEQUENCE]', message)

        # IP addresses
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        message = re.sub(ip_pattern, '[IP_ADDRESS]', message)

        return message

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename to remove potentially sensitive information.

        This enhanced version uses more sophisticated detection to identify
        and redact sensitive information in filenames while preserving
        file extensions and enough information for debugging.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed_file"

        # Extract extension
        base, ext = os.path.splitext(filename)

        # Check for PII patterns in filename
        pii_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b\d{6}\s?\d{5}\b',  # Norwegian national ID
            r'\b\d{3}[-\.\s]?\d{2}[-\.\s]?\d{4}\b',  # SSN-like pattern
            r'\b(?:\+\d{1,3}[-\.\s]?)?(?:\d{1,4}[-\.\s]?){2,5}\d{1,4}\b',  # Phone number
            r'password',
            r'secure',
            r'confidential',
            r'private',
            r'secret'
        ]

        has_pii = False
        for pattern in pii_patterns:
            if re.search(pattern, base, re.IGNORECASE):
                has_pii = True
                break

        # If PII found, sanitize more aggressively
        if has_pii:
            # Hash the basename but keep extension
            import hashlib
            sanitized_base = hashlib.md5(base.encode()).hexdigest()[:8]
            return f"redacted_{sanitized_base}{ext}"
        # For long filenames, truncate to avoid information leakage
        elif len(base) > 20:
            sanitized_base = base[:6] + '...' + base[-6:]
            return sanitized_base + ext
        # For shorter filenames with no obvious PII, use a lighter approach
        elif len(base) > 6:
            return base + ext

        # For very short filenames, just return as is
        return filename

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """
        Sanitize a URL to remove sensitive parts while preserving structure.

        Args:
            url: URL to sanitize

        Returns:
            Sanitized URL with sensitive parts removed
        """
        if not url:
            return "unknown_url"

        try:
            # Import here to avoid dependency issues
            from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

            # Parse the URL
            parsed = urlparse(url)

            # Remove username/password if present
            netloc = parsed.netloc
            if "@" in netloc:
                netloc = netloc.split("@")[1]

            # Remove query parameters that might contain sensitive info
            query_params = parse_qs(parsed.query)
            safe_params = {}
            sensitive_param_names = [
                'key', 'api_key', 'apikey', 'password', 'secret', 'token',
                'auth', 'access_token', 'refresh_token', 'code', 'id_token',
                'user', 'username', 'email', 'session', 'account', 'jwt',
                'credentials', 'client_secret', 'private'
            ]

            # Keep only safe query parameters
            for param, values in query_params.items():
                if any(sensitive in param.lower() for sensitive in sensitive_param_names):
                    safe_params[param] = ['[REDACTED]']
                else:
                    safe_params[param] = values

            # Rebuild the URL with sanitized components
            safe_query = urlencode(safe_params, doseq=True)
            safe_url = urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                safe_query,
                parsed.fragment
            ))

            return safe_url

        except Exception:
            # If URL parsing fails, use regex as fallback
            for pattern in SecurityAwareErrorHandler._URL_PATTERNS:
                url = re.sub(pattern, '[URL_REDACTED]', url)
            return url

    @staticmethod
    def is_error_sensitive(e: Exception) -> bool:
        """
        Determine if an error might contain sensitive information.

        Args:
            e: The exception to check

        Returns:
            True if the error might contain sensitive information, False otherwise
        """
        # Check error message for sensitive keywords
        message_lower = str(e).lower()

        for keyword in SecurityAwareErrorHandler._SENSITIVE_KEYWORDS:
            if keyword in message_lower:
                return True

        # Check for common sensitive patterns
        sensitive_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'password[=:]\S+',  # Password assignments
            r'key[=:]\S+',  # API keys
            r'token[=:]\S+',  # Tokens
            r'secret[=:]\S+',  # Secrets
            r'auth[=:]\S+',  # Auth strings
            r'Basic\s+[A-Za-z0-9+/=]+',  # Basic auth
            r'Bearer\s+[A-Za-z0-9._-]+',  # Bearer tokens
            r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',  # JWT format
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',  # IP addresses
            r'filename.*\.(pdf|docx|txt)',  # Filenames
            r'traceback',  # Stack traces
            r'user[=:]\S+',  # Usernames
            r'pass[=:]\S+',  # Passwords again
            r'SELECT\s+.*\s+FROM',  # SQL snippets
        ]

        message = str(e)
        for pattern in sensitive_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    @staticmethod
    def safe_execution(
            func: Callable[..., T],
            error_type: str,
            default: Optional[T] = None,
            log_errors: bool = True,
            trace_id: Optional[str] = None,
            **kwargs
    ) -> Tuple[bool, Optional[T], Optional[str]]:
        """
        Execute a function with safe error handling and tracing support.

        Args:
            func: Function to execute
            error_type: Type of operation for error reporting
            default: Default return value in case of error
            log_errors: Whether to log errors
            trace_id: Optional trace ID for distributed tracing
            **kwargs: Arguments to pass to the function

        Returns:
            Tuple of (success, result, error_message)
        """
        try:
            result = func(**kwargs)
            return True, result, None
        except Exception as e:
            if log_errors:
                trace_id = SecurityAwareErrorHandler.log_processing_error(
                    e, error_type, trace_id=trace_id
                )

            # Generate a safe error message
            error_id = str(uuid.uuid4())
            error_type_name = type(e).__name__
            safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
                error_type_name,
                SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
            )
            error_message = f"{safe_message}. Reference ID: {error_id}, Trace ID: {trace_id}"

            return False, default, error_message

    @staticmethod
    async def safe_async_execution(
            func: Callable[..., Awaitable[T]],
            error_type: str,
            default: Optional[T] = None,
            log_errors: bool = True,
            trace_id: Optional[str] = None,
            **kwargs
    ) -> Tuple[bool, Optional[T], Optional[str]]:
        """
        Execute an async function with safe error handling and tracing support.

        Args:
            func: Async function to execute
            error_type: Type of operation for error reporting
            default: Default return value in case of error
            log_errors: Whether to log errors
            trace_id: Optional trace ID for distributed tracing
            **kwargs: Arguments to pass to the function

        Returns:
            Tuple of (success, result, error_message)
        """
        try:
            result = await func(**kwargs)
            return True, result, None
        except Exception as e:
            if log_errors:
                trace_id = SecurityAwareErrorHandler.log_processing_error(
                    e, error_type, trace_id=trace_id
                )

            # Generate a safe error message
            error_id = str(uuid.uuid4())
            error_type_name = type(e).__name__
            safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
                error_type_name,
                SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
            )
            error_message = f"{safe_message}. Reference ID: {error_id}, Trace ID: {trace_id}"

            return False, default, error_message

    @staticmethod
    def wrap_async_execution(
            func: Callable[..., Any],
            error_type: str,
            resource_id: str = "",
            timeout: Optional[float] = None
    ):
        """
        Decorator to wrap async function execution with standardized error handling.

        This method wraps asynchronous API endpoint handlers to provide
        consistent error handling across all endpoints, with enhanced
        timeout handling and distributed tracing.

        Args:
            func: Async function to wrap
            error_type: Type of operation for error reporting
            resource_id: Identifier for the resource being processed
            timeout: Optional timeout in seconds

        Returns:
            Wrapped async function with error handling
        """
        from functools import wraps

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate trace ID for distributed tracing
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

            try:
                # Apply timeout if specified
                if timeout is not None:
                    try:
                        result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                    except asyncio.TimeoutError:
                        # Handle timeouts specifically
                        raise TimeoutError(f"Operation timed out after {timeout} seconds")
                else:
                    result = await func(*args, **kwargs)

                return result
            except Exception as e:
                # Use the appropriate error handler
                return SecurityAwareErrorHandler.handle_safe_error(
                    e, error_type, resource_id, trace_id=trace_id
                )

        return wrapper