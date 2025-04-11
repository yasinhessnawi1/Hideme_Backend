"""
Enhanced error handling utilities with security, privacy, and distributed tracing.

This module provides centralized error handling functionality that ensures
security and privacy when handling exceptions, preventing leakage of
sensitive information in error messages while maintaining helpful
diagnostics for developers and users. It includes distributed tracing
support and comprehensive logging for security audits.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import traceback
import uuid
from fastapi import HTTPException
from typing import Dict, Any, Optional, TypeVar, Union, Tuple, Callable

from backend.app.utils.logging.logger import log_warning, log_error

# Generic type variable for functions
T = TypeVar('T')

# Configure module logger
_logger = logging.getLogger("error_handling")

# Constant for email pattern (avoids duplicating the literal multiple times)
EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'


class SecurityAwareErrorHandler:
    """
    Enhanced error handler that ensures security and privacy when handling exceptions.

    Prevents leaking sensitive information in error messages while maintaining
    helpful diagnostics for developers and maintainers. Complies with GDPR
    Article 5(1)(f) requiring appropriate security measures and provides
    distributed tracing capabilities for complex systems.
    """

    _SENSITIVE_KEYWORDS = [
        'password', 'secret', 'key', 'token', 'credential', 'auth',
        'ssn', 'social', 'credit', 'card', 'cvv', 'secure', 'private',
        'passport', 'license', 'national', 'health', 'insurance', 'bank',
        'fodselsnummer', 'personnummer', 'address', 'phone', 'email',
        'api', 'access_token', 'refresh_token', 'bearer', 'authorization',
        'admin', 'username', 'login', 'signin', 'certificate', 'privkey'
    ]

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

    _ERROR_LOG_PATH = os.environ.get("ERROR_LOG_PATH", "app/logs/error_logs/detailed_errors.log")
    _USE_JSON_LOGGING = os.environ.get("ERROR_JSON_LOGGING", "true").lower() == "true"
    SAFE_MESSAGE = "Error details have been redacted for security."

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

    _ENABLE_DISTRIBUTED_TRACING = os.environ.get("ENABLE_DISTRIBUTED_TRACING", "false").lower() == "true"
    _SERVICE_NAME = os.environ.get("SERVICE_NAME", "document_processing")

    # Note: Synchronization primitives (e.g., locks) are deferred and not initialized in __init__.

    @staticmethod
    def handle_detection_error(
            e: Exception,
            operation_type: str,
            additional_info: Optional[Dict[str, Any]] = None,
            trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle errors from detection operations without leaking sensitive information.
        """
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        info = {"trace_id": trace_id}
        if additional_info:
            info.update(additional_info)

        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        log_error(f"[ERROR] {operation_type} error (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            type(e).__name__,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )
        # Override safe_message if the error is sensitive.
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SecurityAwareErrorHandler.SAFE_MESSAGE
        response = {
            "redaction_mapping": {"pages": []},
            "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": type(e).__name__,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        if additional_info:
            response.update(additional_info)
        return response

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
        """
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        safe_filename = "unknown" if not filename else SecurityAwareErrorHandler._sanitize_filename(filename)

        info = {"filename": filename, "trace_id": trace_id}
        if additional_info:
            info.update(additional_info)

        log_error(
            f"[ERROR] {operation_type} error on {filename or 'unknown file'} (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            type(e).__name__,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SecurityAwareErrorHandler.SAFE_MESSAGE
        response = {
            "file": safe_filename,
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": type(e).__name__,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        if additional_info:
            response.update(additional_info)
        return response

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
        """
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        info = {"files_count": files_count, "trace_id": trace_id}
        if additional_info:
            info.update(additional_info)

        log_error(
            f"[ERROR] {operation_type} batch error on {files_count} files (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            type(e).__name__,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SecurityAwareErrorHandler.SAFE_MESSAGE
        response = {
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
        if additional_info:
            response["batch_summary"].update(additional_info)
        return response

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
        """
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        safe_endpoint = SecurityAwareErrorHandler._sanitize_url(endpoint)
        info = {"endpoint": endpoint, "trace_id": trace_id}
        if additional_info:
            info.update(additional_info)

        log_error(
            f"[ERROR] {operation_type} error on endpoint {safe_endpoint} (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )

        status_code = 500
        if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
            status_code = 504
        elif isinstance(e, HTTPException):
            status_code = e.status_code
        elif isinstance(e, ConnectionError):
            status_code = 502
        elif isinstance(e, (ValueError, TypeError)):
            status_code = 400
        elif isinstance(e, PermissionError):
            status_code = 403
        elif isinstance(e, FileNotFoundError) or "404" in str(e):
            status_code = 404

        if isinstance(e, HTTPException) and hasattr(e, "detail") and e.detail:
            safe_message = str(e.detail)
        else:
            safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
                type(e).__name__,
                SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
            )
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SecurityAwareErrorHandler.SAFE_MESSAGE
        response = {
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": type(e).__name__,
            "status_code": status_code,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        if additional_info:
            response.update(additional_info)
        return response

    @staticmethod
    def handle_safe_error(
            e: Exception,
            operation_type: str,
            endpoint: Optional[str] = None,
            filename: Optional[str] = None,
            resource_id: str = "",
            default_return: Optional[T] = None,
            additional_info: Optional[Dict[str, Any]] = None,
            trace_id: Optional[str] = None
    ) -> Union[Dict[str, Any], T]:
        """
        Generic error handler that selects the appropriate specialized handler
        based on the operation type and context. Refactored to reduce cognitive complexity.
        """
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        log_error(f"[ERROR] {operation_type} error on {resource_id} (Trace: {trace_id}): {str(e)}")
        log_error(f"[TRACE] {traceback.format_exc()}")

        handlers = {
            "detection": SecurityAwareErrorHandler.handle_detection_error,
            "file": SecurityAwareErrorHandler.handle_file_processing_error,
            "batch": SecurityAwareErrorHandler.handle_batch_processing_error,
            "api": SecurityAwareErrorHandler.handle_api_gateway_error,
        }
        handler = next((h for k, h in handlers.items() if k in operation_type), None)
        if handler:
            if "api" in operation_type:
                return handler(e, operation_type, endpoint, additional_info, trace_id)
            elif "batch" in operation_type:
                files_count = additional_info.get("files_count", 0) if additional_info else 0
                return handler(e, operation_type, files_count, additional_info, trace_id)
            elif "file" in operation_type:
                return handler(e, operation_type, filename, additional_info, trace_id)
            else:
                return handler(e, operation_type, additional_info, trace_id)

        if default_return is not None:
            return default_return

        error_id = str(uuid.uuid4())
        error_type = type(e).__name__
        safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
            error_type,
            SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
        )
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SecurityAwareErrorHandler.SAFE_MESSAGE
        response = {
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": error_type,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        if additional_info:
            response.update({k: v for k, v in additional_info.items() if k not in response})
        return response

    @staticmethod
    def log_processing_error(
            e: Exception,
            operation_type: str,
            resource_id: str = "",
            trace_id: Optional[str] = None
    ) -> str:
        """
        Log an error safely without leaking sensitive information and return a trace ID.
        """
        error_id = str(uuid.uuid4())
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        sanitized_message = SecurityAwareErrorHandler._sanitize_error_message(str(e))
        log_error(f"[ERROR] {operation_type} error (ID: {error_id}, Trace: {trace_id}): {sanitized_message}")
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(),
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
        Refactored to reduce cognitive complexity.
        """
        try:
            log_dir = os.path.dirname(SecurityAwareErrorHandler._ERROR_LOG_PATH)
            os.makedirs(log_dir, exist_ok=True)
            error_record = {
                "error_id": error_id,
                "timestamp": time.time(),
                "error_type": error_type,
                "operation_type": operation_type,
                "error_message": error_message,
                "sanitized_message": SecurityAwareErrorHandler._sanitize_error_message(error_message),
                "stack_trace": stack_trace,
                "environment": os.environ.get("ENVIRONMENT", "development"),
                "service": SecurityAwareErrorHandler._SERVICE_NAME,
                "additional_info": SecurityAwareErrorHandler._sanitize_additional_info(additional_info),
                "environment_info": SecurityAwareErrorHandler._capture_env_info()
            }
            if SecurityAwareErrorHandler._USE_JSON_LOGGING:
                with open(SecurityAwareErrorHandler._ERROR_LOG_PATH, "a") as f:
                    f.write(json.dumps(error_record) + "\n")
            else:
                with open(SecurityAwareErrorHandler._ERROR_LOG_PATH, "a") as f:
                    f.write(f"\n--- ERROR: {error_id} at {time.ctime(error_record['timestamp'])} ---\n")
                    f.write(f"Type: {error_type}\n")
                    f.write(f"Operation: {operation_type}\n")
                    f.write(f"Message: {error_message}\n")
                    f.write(f"Sanitized: {error_record['sanitized_message']}\n")
                    f.write("Stack Trace:\n")
                    f.write(stack_trace)
                    if error_record.get("additional_info"):
                        f.write("\nAdditional Info:\n")
                        for k, v in error_record["additional_info"].items():
                            f.write(f"  {k}: {v}\n")
                    f.write("\n----------------------------------------\n")
            if SecurityAwareErrorHandler._ENABLE_DISTRIBUTED_TRACING:
                SecurityAwareErrorHandler._send_to_distributed_tracing(error_record)
        except (OSError, IOError) as log_error_ex:
            log_warning(f"Failed to log detailed error information: {str(log_error_ex)}")

    @staticmethod
    def _sanitize_additional_info(additional_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Sanitize an additional info dictionary to remove sensitive data.
        """
        sanitized = {}
        if additional_info:
            for key, value in additional_info.items():
                if isinstance(value, str):
                    sanitized[key] = SecurityAwareErrorHandler._sanitize_error_message(value)
                else:
                    sanitized[key] = value
        return sanitized

    @staticmethod
    def _capture_env_info() -> Dict[str, Any]:
        """
        Capture relevant environment information for error logging.
        """
        env_vars = ["ENVIRONMENT", "SERVICE_NAME", "SERVICE_VERSION",
                    "HOSTNAME", "DEPLOYMENT_ID", "REGION", "ZONE"]
        info = {}
        for var in env_vars:
            if var in os.environ:
                info[var] = os.environ[var]
        return info

    @staticmethod
    def _send_to_distributed_tracing(error_record: Dict[str, Any]) -> None:
        """
        Send error information to a distributed tracing system.
        """
        # Integration with distributed tracing systems goes here.
        pass

    @staticmethod
    def _sanitize_error_message(message: str) -> str:
        """
        Sanitize an error message to remove sensitive information.
        """
        if not message:
            return "Error details not available"
        message_lower = message.lower()
        for keyword in SecurityAwareErrorHandler._SENSITIVE_KEYWORDS:
            if keyword in message_lower:
                return "Error details redacted for security"

        def path_replacer(match):
            path = match.group(0)
            return f"[PATH]/{os.path.basename(path)}"

        path_pattern = r'(?:\/[\w\-. ]+)+\/[\w\-. ]+'
        message = re.sub(path_pattern, path_replacer, message)

        def json_replacer(match):
            json_str = match.group(0)
            key_count = json_str.count(':')
            return f"[JSON_CONTENT:{key_count}_fields]"

        json_pattern = r'\{.*\}'
        message = re.sub(json_pattern, json_replacer, message, flags=re.DOTALL)

        for pattern in SecurityAwareErrorHandler._URL_PATTERNS:
            message = re.sub(pattern, '[URL_REDACTED]', message)

        token_pattern = r'(auth|token|bearer|jwt|api[-_]?key)[^\s]*'
        message = re.sub(token_pattern, '[AUTH_TOKEN]', message, flags=re.IGNORECASE)

        message = re.sub(EMAIL_PATTERN, '[EMAIL]', message)
        no_id_pattern = r'\b\d{6}\s?\d{5}\b'
        message = re.sub(no_id_pattern, '[NATIONAL_ID]', message)
        cc_pattern = r'\b(?:\d{4}[ -]?){3}\d{4}\b'
        message = re.sub(cc_pattern, '[CREDIT_CARD]', message)
        id_pattern = r'\b(?:id|user|account)[\s:=_-]+(\d{4,})\b'
        message = re.sub(id_pattern, lambda m: f"{m.group(1).split(':')[0]}:[ID_NUMBER]", message, flags=re.IGNORECASE)
        number_sequence = r'\b\d{8,16}\b'
        message = re.sub(number_sequence, '[NUMBER_SEQUENCE]', message)
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        message = re.sub(ip_pattern, '[IP_ADDRESS]', message)

        return message

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename to remove potentially sensitive information.
        """
        if not filename:
            return "unnamed_file"
        base, ext = os.path.splitext(filename)
        pii_patterns = [
            EMAIL_PATTERN,
            r'\b\d{6}\s?\d{5}\b',
            r'\b\d{3}[-\.\s]?\d{2}[-\.\s]?\d{4}\b',
            r'\b(?:\+\d{1,3}[-\.\s]?)?(?:\d{1,4}[-\.\s]?){2,5}\d{1,4}\b',
            r'password',
            r'secure',
            r'confidential',
            r'private',
            r'secret'
        ]
        if any(re.search(pattern, base, re.IGNORECASE) for pattern in pii_patterns):
            sanitized_base = hashlib.md5(base.encode()).hexdigest()[:8]
            return f"redacted_{sanitized_base}{ext}"
        elif len(base) > 20:
            sanitized_base = base[:6] + '...' + base[-6:]
            return sanitized_base + ext
        elif len(base) > 6:
            return base + ext
        return filename

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """
        Sanitize a URL to remove sensitive parts while preserving its structure.
        """
        if not url or not isinstance(url, str):
            return "unknown_url"
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc.split("@")[-1] if "@" in parsed.netloc else parsed.netloc
            query_params = parse_qs(parsed.query)
            sensitive_param_names = [
                'key', 'api_key', 'apikey', 'password', 'secret', 'token',
                'auth', 'access_token', 'refresh_token', 'code', 'id_token',
                'user', 'username', 'email', 'session', 'account', 'jwt',
                'credentials', 'client_secret', 'private'
            ]
            safe_params = {
                param: (['[REDACTED]'] if any(sens in param.lower() for sens in sensitive_param_names) else values)
                for param, values in query_params.items()
            }
            safe_query = urlencode(safe_params, doseq=True)
            return urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                safe_query,
                parsed.fragment
            ))
        except (ValueError, AttributeError) as ex:
            log_warning(f"URL sanitization failed: {str(ex)}. Falling back to regex.")
            for pattern in SecurityAwareErrorHandler._URL_PATTERNS:
                url = re.sub(pattern, '[URL_REDACTED]', url)
            return url

    @staticmethod
    def is_error_sensitive(e: Exception) -> bool:
        """
        Determine if an error might contain sensitive information.
        """
        message_lower = str(e).lower()
        if any(keyword in message_lower for keyword in SecurityAwareErrorHandler._SENSITIVE_KEYWORDS):
            return True
        sensitive_patterns = [
            EMAIL_PATTERN,
            r'password[=:]\S+',
            r'key[=:]\S+',
            r'token[=:]\S+',
            r'secret[=:]\S+',
            r'auth[=:]\S+',
            r'Basic\s+[A-Za-z0-9+/=]+',
            r'Bearer\s+[A-Za-z0-9._-]+',
            r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            r'filename.*\.(pdf|docx|txt)',
            r'traceback',
            r'user[=:]\S+',
            r'pass[=:]\S+',
            r'SELECT\s+.*\s+FROM',
        ]
        for pattern in sensitive_patterns:
            if re.search(pattern, str(e), re.IGNORECASE):
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

        This method executes the provided callable with the given keyword arguments.
        In the event of an exception, it logs the error details, checks if the error
        might contain sensitive information using is_error_sensitive, and returns a
        tuple indicating whether the execution succeeded, the result (or a default),
        and a safe error message.

        Args:
            func: Function to execute.
            error_type: Type of operation for error reporting.
            default: Default return value in case of error.
            log_errors: Whether to log errors.
            trace_id: Optional trace ID for distributed tracing.
            **kwargs: Arguments to pass to the function.

        Returns:
            Tuple of (success, result, error_message).
        """
        try:
            result = func(**kwargs)
            return True, result, None
        except Exception as e:
            if log_errors:
                trace_id = SecurityAwareErrorHandler.log_processing_error(e, error_type, trace_id=trace_id)
            error_id = str(uuid.uuid4())
            error_type_name = type(e).__name__
            safe_message = SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES.get(
                error_type_name,
                SecurityAwareErrorHandler._ERROR_TYPE_MESSAGES['Exception']
            )
            if SecurityAwareErrorHandler.is_error_sensitive(e):
                safe_message = SecurityAwareErrorHandler.SAFE_MESSAGE
            error_message = f"{safe_message}. Reference ID: {error_id}, Trace ID: {trace_id}"
            return False, default, error_message
