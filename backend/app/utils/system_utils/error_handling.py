"""
Enhanced error handling utilities with security, privacy, and distributed tracing.
This module provides centralized error handling functionality that ensures security
and privacy when handling exceptions, preventing leakage of sensitive information in
error messages while maintaining helpful diagnostics for developers and users.
It includes distributed tracing support and comprehensive logging for security audits.
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

from backend.app.utils.constant.constant import ERROR_TYPE_MESSAGES, SAFE_MESSAGE, ERROR_LOG_PATH, SERVICE_NAME, \
    USE_JSON_LOGGING, ENABLE_DISTRIBUTED_TRACING, SENSITIVE_KEYWORDS, URL_PATTERNS, EMAIL_PATTERN
from backend.app.utils.logging.logger import log_warning, log_error

# Generic type variable for functions.
T = TypeVar('T')

# Configure module logger.
_logger = logging.getLogger("error_handling")


class SecurityAwareErrorHandler:
    """
    Enhanced error handler that ensures security and privacy when handling exceptions.

    This class prevents leaking sensitive information in error messages while maintaining
    helpful diagnostics for developers and maintainers. It complies with GDPR Article 5(1)(f)
    by applying appropriate security measures to error handling and provides distributed tracing
    capabilities for complex, distributed systems.
    """

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
            e (Exception): The exception to handle.
            operation_type (str): The type of operation that encountered the error.
            additional_info (Optional[Dict[str, Any]]): Extra contextual data.
            trace_id (Optional[str]): An optional trace identifier.

        Returns:
            Dict[str, Any]: A sanitized error response dictionary.
        """
        # Generate a unique error identifier.
        error_id = str(uuid.uuid4())
        # If no trace_id is provided, generate one using current time and a short uuid.
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        # Create an info dictionary with the trace identifier.
        info = {"trace_id": trace_id}
        # Merge any additional provided info into the info dictionary.
        if additional_info:
            info.update(additional_info)
        # Sanitize the error message to remove sensitive information.
        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        # Log a general error message with operation details.
        log_error(f"[ERROR] {operation_type} error (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        # Log detailed error information to a file.
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )
        # Fetch a safe error message based on error type from the configuration.
        safe_message = ERROR_TYPE_MESSAGES.get(type(e).__name__, ERROR_TYPE_MESSAGES['Exception'])
        # Override safe_message if the error is deemed sensitive.
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SAFE_MESSAGE
        # Build the response dictionary with redaction, diagnostics, and timestamp.
        response = {
            "redaction_mapping": {"pages": []},
            "entities_detected": {"total": 0, "by_type": {}, "by_page": {}},
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": type(e).__name__,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        # Update the response with any additional context if provided.
        if additional_info:
            response.update(additional_info)
        # Return the sanitized response.
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

        Args:
            e (Exception): The exception that occurred.
            operation_type (str): The type of file processing operation.
            filename (Optional[str]): Name of the file involved in the operation.
            additional_info (Optional[Dict[str, Any]]): Extra context information.
            trace_id (Optional[str]): Optional trace identifier.

        Returns:
            Dict[str, Any]: A sanitized error response dictionary specific to file processing.
        """
        # Generate a unique error identifier.
        error_id = str(uuid.uuid4())
        # Generate a trace identifier if not provided.
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        # Sanitize the error message.
        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        # Sanitize the filename for safety; default to "unknown" if not provided.
        safe_filename = "unknown" if not filename else SecurityAwareErrorHandler._sanitize_filename(filename)
        # Build info dictionary with filename and trace identifier.
        info = {"filename": filename, "trace_id": trace_id}
        # Merge additional info if provided.
        if additional_info:
            info.update(additional_info)
        # Log an error message with file-specific details.
        log_error(
            f"[ERROR] {operation_type} error on {filename or 'unknown file'} (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        # Log detailed error information to file.
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )
        # Get a safe error message using the error type.
        safe_message = ERROR_TYPE_MESSAGES.get(type(e).__name__, ERROR_TYPE_MESSAGES['Exception'])
        # If the error contains sensitive details, override the safe message.
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SAFE_MESSAGE
        # Build a response dictionary with file-specific error details.
        response = {
            "file": safe_filename,
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": type(e).__name__,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        # Update the response with additional information if provided.
        if additional_info:
            response.update(additional_info)
        # Return the final response.
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

        Args:
            e (Exception): The exception encountered.
            operation_type (str): The type of batch operation.
            files_count (int): The number of files involved in the batch.
            additional_info (Optional[Dict[str, Any]]): Extra context data.
            trace_id (Optional[str]): Optional trace identifier.

        Returns:
            Dict[str, Any]: A sanitized error response dictionary for batch processing.
        """
        # Generate a unique error identifier.
        error_id = str(uuid.uuid4())
        # Create a trace identifier if not provided.
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        # Sanitize the error message.
        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        # Build an info dictionary with the files count and trace identifier.
        info = {"files_count": files_count, "trace_id": trace_id}
        # Merge additional information if present.
        if additional_info:
            info.update(additional_info)
        # Log the batch error with the number of files processed.
        log_error(
            f"[ERROR] {operation_type} batch error on {files_count} files (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        # Log the detailed error information.
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )
        # Retrieve a safe error message based on the error type.
        safe_message = ERROR_TYPE_MESSAGES.get(type(e).__name__, ERROR_TYPE_MESSAGES['Exception'])
        # If the error is sensitive, override with a generic safe message.
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SAFE_MESSAGE
        # Build the response containing batch summary details.
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
        # Update the batch summary with any additional information provided.
        if additional_info:
            response["batch_summary"].update(additional_info)
        # Return the final batch error response.
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

        Args:
            e (Exception): The exception that occurred.
            operation_type (str): The type of API gateway operation.
            endpoint (str): The API endpoint involved.
            additional_info (Optional[Dict[str, Any]]): Additional context.
            trace_id (Optional[str]): Optional trace identifier.

        Returns:
            Dict[str, Any]: A sanitized error response dictionary for API gateway issues.
        """
        # Generate a unique error identifier.
        error_id = str(uuid.uuid4())
        # Generate a trace identifier if one is not provided.
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        # Sanitize the error message.
        SecurityAwareErrorHandler._sanitize_error_message(str(e))
        # Sanitize the endpoint URL to remove sensitive parts.
        safe_endpoint = SecurityAwareErrorHandler._sanitize_url(endpoint)
        # Build an info dictionary with endpoint and trace details.
        info = {"endpoint": endpoint, "trace_id": trace_id}
        # Merge additional info if provided.
        if additional_info:
            info.update(additional_info)
        # Log the API gateway error with sanitized endpoint.
        log_error(
            f"[ERROR] {operation_type} error on endpoint {safe_endpoint} (ID: {error_id}, Trace: {trace_id}): {str(e)}")
        # Log detailed error information for debugging.
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(), info
        )
        # Determine the status code based on exception type.
        status_code = 500
        # Set status code to 504 for timeout errors.
        if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
            status_code = 504
        # Use the status code from HTTPException if applicable.
        elif isinstance(e, HTTPException):
            status_code = e.status_code
        # Set code to 502 for connection errors.
        elif isinstance(e, ConnectionError):
            status_code = 502
        # Set code to 400 for value or type errors.
        elif isinstance(e, (ValueError, TypeError)):
            status_code = 400
        # Set code to 403 for permission issues.
        elif isinstance(e, PermissionError):
            status_code = 403
        # Set code to 404 for file not found errors.
        elif isinstance(e, FileNotFoundError) or "404" in str(e):
            status_code = 404
        # Use the detail from HTTPException if available.
        if isinstance(e, HTTPException) and hasattr(e, "detail") and e.detail:
            safe_message = str(e.detail)
        else:
            # Retrieve a safe error message based on error type.
            safe_message = ERROR_TYPE_MESSAGES.get(type(e).__name__, ERROR_TYPE_MESSAGES['Exception'])
        # Override safe_message if the error contains sensitive details.
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SAFE_MESSAGE
        # Build the API gateway error response dictionary.
        response = {
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": type(e).__name__,
            "status_code": status_code,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        # Update response with additional information if provided.
        if additional_info:
            response.update(additional_info)
        # Return the error response.
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

        Args:
            e (Exception): The exception to handle.
            operation_type (str): Type of operation.
            endpoint (Optional[str]): Relevant API endpoint if applicable.
            filename (Optional[str]): Filename if applicable.
            resource_id (str): Identifier for the resource involved.
            default_return (Optional[T]): Default return value if no handler is selected.
            additional_info (Optional[Dict[str, Any]]): Additional context for error handling.
            trace_id (Optional[str]): Optional trace identifier.

        Returns:
            Union[Dict[str, Any], T]: The result from the appropriate handler or default return value.
        """
        # Generate trace_id if it is not provided.
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        # Log the error processing start with the resource identifier and trace information.
        log_error(f"[ERROR] {operation_type} error on {resource_id} (Trace: {trace_id}): {str(e)}")
        # Log the full traceback for debugging purposes.
        log_error(f"[TRACE] {traceback.format_exc()}")
        # Define a mapping of operation types to the specific handler functions.
        handlers = {
            "detection": SecurityAwareErrorHandler.handle_detection_error,
            "file": SecurityAwareErrorHandler.handle_file_processing_error,
            "batch": SecurityAwareErrorHandler.handle_batch_processing_error,
            "api": SecurityAwareErrorHandler.handle_api_gateway_error,
        }
        # Select the appropriate handler based on the operation type.
        handler = next((h for k, h in handlers.items() if k in operation_type), None)
        # If a matching handler is found, use it for processing.
        if handler:
            if "api" in operation_type:
                # For API operations, pass endpoint and additional_info.
                return handler(e, operation_type, endpoint, additional_info, trace_id)
            elif "batch" in operation_type:
                # For batch operations, get file count from additional_info.
                files_count = additional_info.get("files_count", 0) if additional_info else 0
                return handler(e, operation_type, files_count, additional_info, trace_id)
            elif "file" in operation_type:
                # For file operations, pass the filename.
                return handler(e, operation_type, filename, additional_info, trace_id)
            else:
                # For detection or other types, pass additional_info.
                return handler(e, operation_type, additional_info, trace_id)
        # If no handler is found and a default is provided, return the default.
        if default_return is not None:
            return default_return
        # Otherwise, build a generic error response.
        error_id = str(uuid.uuid4())
        error_type = type(e).__name__
        safe_message = ERROR_TYPE_MESSAGES.get(error_type, ERROR_TYPE_MESSAGES['Exception'])
        if SecurityAwareErrorHandler.is_error_sensitive(e):
            safe_message = SAFE_MESSAGE
        response = {
            "status": "error",
            "error": f"{safe_message}. Reference ID: {error_id}",
            "error_type": error_type,
            "error_id": error_id,
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        # Merge additional information into the response if provided.
        if additional_info:
            response.update({k: v for k, v in additional_info.items() if k not in response})
        # Return the generic error response.
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

        Args:
            e (Exception): The exception to log.
            operation_type (str): The type of operation during which the error occurred.
            resource_id (str): Identifier of the affected resource.
            trace_id (Optional[str]): Optional trace identifier.

        Returns:
            str: The trace identifier associated with the logged error.
        """
        # Generate a unique error identifier.
        error_id = str(uuid.uuid4())
        # Generate a trace identifier if not provided.
        if not trace_id:
            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        # Sanitize the error message for logging.
        sanitized_message = SecurityAwareErrorHandler._sanitize_error_message(str(e))
        # Log a concise error message with resource details.
        log_error(f"[ERROR] {operation_type} error (ID: {error_id}, Trace: {trace_id}): {sanitized_message}")
        # Log detailed error information including stack trace and resource identifier.
        SecurityAwareErrorHandler._log_detailed_error(
            error_id, type(e).__name__, str(e), operation_type, traceback.format_exc(),
            {"resource_id": resource_id, "trace_id": trace_id}
        )
        # Return the trace identifier.
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

        Args:
            error_id (str): Unique error identifier.
            error_type (str): Type of error.
            error_message (str): The raw error message.
            operation_type (str): The operation type during which the error occurred.
            stack_trace (str): The complete stack trace.
            additional_info (Optional[Dict[str, Any]]): Extra contextual information.
        """
        try:
            # Determine the log directory from the error log path.
            log_dir = os.path.dirname(ERROR_LOG_PATH)
            # Ensure the log directory exists.
            os.makedirs(log_dir, exist_ok=True)
            # Build an error record dictionary with all relevant details.
            error_record = {
                "error_id": error_id,
                "timestamp": time.time(),
                "error_type": error_type,
                "operation_type": operation_type,
                "error_message": error_message,
                "sanitized_message": SecurityAwareErrorHandler._sanitize_error_message(error_message),
                "stack_trace": stack_trace,
                "environment": os.environ.get("ENVIRONMENT", "development"),
                "service": SERVICE_NAME,
                "additional_info": SecurityAwareErrorHandler._sanitize_additional_info(additional_info),
                "environment_info": SecurityAwareErrorHandler._capture_env_info()
            }
            # If JSON logging is enabled, write the error record as JSON.
            if USE_JSON_LOGGING:
                with open(ERROR_LOG_PATH, "a") as f:
                    f.write(json.dumps(error_record) + "\n")
            else:
                # Otherwise, write a formatted error record.
                with open(ERROR_LOG_PATH, "a") as f:
                    f.write(f"\n--- ERROR: {error_id} at {time.ctime(error_record['timestamp'])} ---\n")
                    f.write(f"Type: {error_type}\n")
                    f.write(f"Operation: {operation_type}\n")
                    f.write(f"Message: {error_message}\n")
                    f.write(f"Sanitized: {error_record['sanitized_message']}\n")
                    f.write("Stack Trace:\n")
                    f.write(stack_trace)
                    # If there is additional info, add it to the log.
                    if error_record.get("additional_info"):
                        f.write("\nAdditional Info:\n")
                        for k, v in error_record["additional_info"].items():
                            f.write(f"  {k}: {v}\n")
                    f.write("\n----------------------------------------\n")
            # If distributed tracing is enabled, send the error record.
            if ENABLE_DISTRIBUTED_TRACING:
                SecurityAwareErrorHandler._send_to_distributed_tracing(error_record)
        except (OSError, IOError) as log_error_ex:
            # Log a warning if writing the detailed error record fails.
            log_warning(f"Failed to log detailed error information: {str(log_error_ex)}")

    @staticmethod
    def _sanitize_additional_info(additional_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Sanitize an additional info dictionary to remove sensitive data.

        Args:
            additional_info (Optional[Dict[str, Any]]): The additional info to sanitize.

        Returns:
            Dict[str, Any]: A sanitized version of the additional info.
        """
        # Initialize an empty dictionary for sanitized info.
        sanitized = {}
        # If additional_info is provided, iterate through its items.
        if additional_info:
            for key, value in additional_info.items():
                # If the value is a string, sanitize it.
                if isinstance(value, str):
                    sanitized[key] = SecurityAwareErrorHandler._sanitize_error_message(value)
                else:
                    # Otherwise, keep the value as is.
                    sanitized[key] = value
        # Return the sanitized dictionary.
        return sanitized

    @staticmethod
    def _capture_env_info() -> Dict[str, Any]:
        """
        Capture relevant environment information for error logging.

        Returns:
            Dict[str, Any]: A dictionary of selected environment variables.
        """
        # Define a list of environment variables to capture.
        env_vars = ["ENVIRONMENT", "SERVICE_NAME", "SERVICE_VERSION", "HOSTNAME", "DEPLOYMENT_ID", "REGION", "ZONE"]
        # Initialize an empty dictionary to store environment information.
        info = {}
        # Iterate over the desired environment variables.
        for var in env_vars:
            # If the variable exists in the environment, add it to the info dictionary.
            if var in os.environ:
                info[var] = os.environ[var]
        # Return the captured environment info.
        return info

    @staticmethod
    def _send_to_distributed_tracing(error_record: Dict[str, Any]) -> None:
        """
        Send error information to a distributed tracing system.

        Args:
            error_record (Dict[str, Any]): The error record to send.

        This is a placeholder for integration with actual distributed tracing systems.
        """
        # Integration with distributed tracing systems would be implemented here.
        pass

    @staticmethod
    def _sanitize_error_message(message: str) -> str:
        """
        Sanitize an error message to remove sensitive information.

        Args:
            message (str): The error message to sanitize.

        Returns:
            str: The sanitized error message.
        """
        # If the message is empty or None, return a default notice.
        if not message:
            return "Error details not available"
        # Convert message to lower case for uniform comparison.
        message_lower = message.lower()
        # Check each sensitive keyword in the message.
        for keyword in SENSITIVE_KEYWORDS:
            if keyword in message_lower:
                # If a sensitive keyword is found, return a redacted message.
                return "Error details redacted for security"

        # Define a helper function to replace file paths with a sanitized version.
        def path_replacer(match):
            path = match.group(0)
            return f"[PATH]/{os.path.basename(path)}"

        # Regex pattern for file paths.
        path_pattern = r'(?:\/[\w\-. ]+)+\/[\w\-. ]+'
        # Replace file paths in the message.
        message = re.sub(path_pattern, path_replacer, message)

        # Define a helper to sanitize JSON content in messages.
        def json_replacer(match):
            json_str = match.group(0)
            key_count = json_str.count(':')
            return f"[JSON_CONTENT:{key_count}_fields]"

        # Regex pattern to detect JSON objects.
        json_pattern = r'\{.*\}'
        # Replace JSON content in the message.
        message = re.sub(json_pattern, json_replacer, message, flags=re.DOTALL)
        # For each URL pattern, replace URLs with a redacted placeholder.
        for pattern in URL_PATTERNS:
            message = re.sub(pattern, '[URL_REDACTED]', message)
        # Replace tokens in the message using a regex.
        token_pattern = r'(auth|token|bearer|jwt|api[-_]?key)[^\s]*'
        message = re.sub(token_pattern, '[AUTH_TOKEN]', message, flags=re.IGNORECASE)
        # Replace email patterns with a placeholder.
        message = re.sub(EMAIL_PATTERN, '[EMAIL]', message)
        # Replace national ID patterns with a placeholder.
        no_id_pattern = r'\b\d{6}\s?\d{5}\b'
        message = re.sub(no_id_pattern, '[NATIONAL_ID]', message)
        # Replace credit card number patterns with a placeholder.
        cc_pattern = r'\b(?:\d{4}[ -]?){3}\d{4}\b'
        message = re.sub(cc_pattern, '[CREDIT_CARD]', message)
        # Replace generic IDs with a placeholder.
        id_pattern = r'\b(?:id|user|account)[\s:=_-]+(\d{4,})\b'
        message = re.sub(id_pattern, lambda m: f"{m.group(1).split(':')[0]}:[ID_NUMBER]", message, flags=re.IGNORECASE)
        # Replace long number sequences with a placeholder.
        number_sequence = r'\b\d{8,16}\b'
        message = re.sub(number_sequence, '[NUMBER_SEQUENCE]', message)
        # Replace IP addresses with a placeholder.
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        message = re.sub(ip_pattern, '[IP_ADDRESS]', message)
        # Return the fully sanitized error message.
        return message

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename to remove potentially sensitive information.

        Args:
            filename (str): The filename to sanitize.

        Returns:
            str: The sanitized filename.
        """
        # If filename is empty, return a default name.
        if not filename:
            return "unnamed_file"
        # Split the filename into base and extension.
        base, ext = os.path.splitext(filename)
        # Define patterns that might indicate sensitive information.
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
        # Check if any sensitive pattern is found in the base name.
        if any(re.search(pattern, base, re.IGNORECASE) for pattern in pii_patterns):
            # Create a sanitized hash of the base name.
            sanitized_base = hashlib.md5(base.encode()).hexdigest()[:8]
            return f"redacted_{sanitized_base}{ext}"
        # If base name is too long, shorten it.
        elif len(base) > 20:
            sanitized_base = base[:6] + '...' + base[-6:]
            return sanitized_base + ext
        # Otherwise, return the filename as is.
        elif len(base) > 6:
            return base + ext
        return filename

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """
        Sanitize a URL to remove sensitive parts while preserving its structure.

        Args:
            url (str): The URL to sanitize.

        Returns:
            str: The sanitized URL.
        """
        # Check if the url is valid.
        if not url or not isinstance(url, str):
            return "unknown_url"
        # Import url parsing utilities.
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        try:
            # Parse the URL into components.
            parsed = urlparse(url)
            # Remove user credentials from netloc if present.
            netloc = parsed.netloc.split("@")[-1] if "@" in parsed.netloc else parsed.netloc
            # Parse the query parameters.
            query_params = parse_qs(parsed.query)
            # Define a list of sensitive query parameter names.
            sensitive_param_names = [
                'key', 'api_key', 'apikey', 'password', 'secret', 'token',
                'auth', 'access_token', 'refresh_token', 'code', 'id_token',
                'user', 'username', 'email', 'session', 'account', 'jwt',
                'credentials', 'client_secret', 'private'
            ]
            # Build a safe set of query parameters.
            safe_params = {
                param: (['[REDACTED]'] if any(sens in param.lower() for sens in sensitive_param_names) else values)
                for param, values in query_params.items()
            }
            # Reconstruct the query string safely.
            safe_query = urlencode(safe_params, doseq=True)
            # Reconstruct and return the sanitized URL.
            return urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                safe_query,
                parsed.fragment
            ))
        except (ValueError, AttributeError) as ex:
            # Log a warning if URL sanitization fails and fallback to regex.
            log_warning(f"URL sanitization failed: {str(ex)}. Falling back to regex.")
            for pattern in URL_PATTERNS:
                url = re.sub(pattern, '[URL_REDACTED]', url)
            # Return the sanitized URL.
            return url

    @staticmethod
    def is_error_sensitive(e: Exception) -> bool:
        """
        Determine if an error might contain sensitive information.

        Args:
            e (Exception): The exception to check.

        Returns:
            bool: True if the error message likely contains sensitive data, otherwise False.
        """
        # Convert the exception message to lower case for analysis.
        message_lower = str(e).lower()
        # Check if any sensitive keyword appears in the message.
        if any(keyword in message_lower for keyword in SENSITIVE_KEYWORDS):
            return True
        # Define additional patterns that indicate sensitive content.
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
        # Check the error message against each sensitive pattern.
        for pattern in sensitive_patterns:
            if re.search(pattern, str(e), re.IGNORECASE):
                return True
        # Return False if no sensitive content is detected.
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
            func (Callable[..., T]): Function to execute.
            error_type (str): Type of operation for error reporting.
            default (Optional[T]): Default return value in case of error.
            log_errors (bool): Flag indicating if errors should be logged.
            trace_id (Optional[str]): Optional trace identifier.
            **kwargs: Arbitrary keyword arguments for the function.

        Returns:
            Tuple[bool, Optional[T], Optional[str]]: A tuple with success status, result (or default), and error message.
        """
        # Attempt to execute the provided function with given arguments.
        try:
            result = func(**kwargs)
            # Return success status with result when no exception occurs.
            return True, result, None
        except Exception as e:
            # If logging is enabled, log the processing error.
            if log_errors:
                trace_id = SecurityAwareErrorHandler.log_processing_error(e, error_type, trace_id=trace_id)
            # Generate a new error identifier.
            error_id = str(uuid.uuid4())
            # Retrieve the error type name.
            error_type_name = type(e).__name__
            # Fetch a safe error message based on error type.
            safe_message = ERROR_TYPE_MESSAGES.get(error_type_name, ERROR_TYPE_MESSAGES['Exception'])
            # If error is sensitive, override with the generic safe message.
            if SecurityAwareErrorHandler.is_error_sensitive(e):
                safe_message = SAFE_MESSAGE
            # Construct the error message including reference IDs.
            error_message = f"{safe_message}. Reference ID: {error_id}, Trace ID: {trace_id}"
            # Return failure status with default value and the error message.
            return False, default, error_message
