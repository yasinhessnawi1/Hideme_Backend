"""
SessionEncryptionManager: Secure Session & API Key Validation, and AES‐GCM Data Encryption/Decryption Utilities.

This module provides functionality to:
- Validate session tokens against a Go backend
- Validate standalone API keys via a Go backend “verify-key” endpoint
- Fetch per-tenant API encryption keys securely
- Encrypt and decrypt arbitrary byte payloads using AES-GCM
- Conditionally decrypt incoming FastAPI uploads and form fields based on header mode:
    • Session mode (session_key + api_key_id)
    • Raw-API-key mode (X-API-Key only)
    • Public mode (no decryption)
- Conditionally encrypt outgoing JSON responses when an AES key was used for input decryption

"""

import asyncio
import base64
import json
import os
import aiohttp

from io import BytesIO
from typing import List, Optional, Tuple, Dict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, UploadFile
from starlette.responses import JSONResponse

from backend.app.utils.logging.logger import log_error
from backend.app.utils.system_utils.error_handling import SecurityAwareErrorHandler


class SessionEncryptionManager:
    """
    Manages secure session validation, API key fetching, encryption, and decryption.
    Enforces singleton usage to maintain a single configuration instance at runtime.
    """
    # Holds the singleton instance once initialized
    _instance: Optional["SessionEncryptionManager"] = None

    def __init__(self, go_backend_url: Optional[str] = None):
        """
        Initialize the SessionEncryptionManager.

        Args:
            go_backend_url (Optional[str]): URL of the Go backend for session validation and key retrieval.
        """
        # Prevent multiple instantiations of the singleton
        if SessionEncryptionManager._instance is not None:
            raise RuntimeError("SessionEncryptionManager is a singleton! Use get_instance().")

        # Determine backend URL from constructor or environment
        url = go_backend_url or os.getenv("GO_BACKEND_URL")
        # Fail fast if no URL is provided
        if not url:
            raise RuntimeError(
                "GO_BACKEND_URL must be set in the environment before initializing SessionEncryptionManager"
            )
        # Store the backend URL for later API calls
        self.go_backend_url = url
        # Mark this instance as the singleton
        SessionEncryptionManager._instance = self

    @classmethod
    def get_instance(cls) -> "SessionEncryptionManager":
        """
        Retrieve the singleton instance, creating it if necessary.
        """
        # Instantiate if not already done
        if cls._instance is None:
            cls()
        # Return the existing instance
        return cls._instance

    async def validate_session_key(self, session_key: str) -> bool:
        """
        Validate a session key against the Go backend.

        Args:
            session_key (str): Bearer token to validate.

        Returns:
            bool: True if the session is valid (HTTP 200), False otherwise.
        """
        # Compose verification endpoint URL
        url = f"{self.go_backend_url}/api/auth/verify"
        # Prepare auth header
        headers = {"Authorization": f"Bearer {session_key}"}
        try:
            # Open an asynchronous HTTP session
            async with aiohttp.ClientSession() as session:
                # Send GET request for validation
                async with session.get(url, headers=headers) as resp:
                    # Return True only on HTTP 200
                    return resp.status == 200
        except aiohttp.ClientError as e:
            # Handle network-related errors securely
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_validate_session", endpoint=url
            )
            raise HTTPException(status_code=502, detail=error_info)
        except Exception as e:
            # Handle unexpected errors securely
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_validate_session", endpoint=url
            )
            raise HTTPException(status_code=400, detail=error_info)

    async def fetch_api_key(self, session_key: str, api_key_id: str) -> str:
        """
        Fetch the full API encryption key from the Go backend.

        Args:
            session_key (str): Validated bearer token.
            api_key_id (str): Identifier of the API key to decode.

        Returns:
            str: The raw API key string.
        """
        # Compose key-fetch endpoint URL
        url = f"{self.go_backend_url}/api/keys/{api_key_id}/decode"
        # Prepare auth header
        headers = {"Authorization": f"Bearer {session_key}"}
        try:
            # Open an asynchronous HTTP session
            async with aiohttp.ClientSession() as session:
                # Send GET request to retrieve the key
                async with session.get(url, headers=headers) as resp:
                    # On success, parse JSON and return the key
                    if resp.status == 200:
                        body = await resp.json()
                        return body["data"]["key"]
                    # Raise if any non-200 status code
                    else:
                        raise ValueError(f"Failed to retrieve API key, status code: {resp.status}")
        except aiohttp.ClientError as e:
            # Handle network issues securely
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_fetch_api_key", endpoint=url
            )
            raise HTTPException(status_code=502, detail=error_info)
        except Exception as e:
            # Handle other unexpected errors
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_fetch_api_key", endpoint=url
            )
            raise HTTPException(status_code=400, detail=error_info)

    async def validate_raw_api_key(self, raw_key: str) -> str:
        """
        Validate a standalone API key by calling the Go backend’s /api/auth/verify-key endpoint.
        On success, returns the provided key as the AES key for encryption/decryption.

        Args:
            raw_key (str): The X-API-Key header value provided by the client.

        Returns:
            str: The same raw_key, to be used as the AES key when valid.
        """
        # Build the full URL for key verification
        url = f"{self.go_backend_url}/api/auth/verify-key"
        try:
            # Open an aiohttp session for the HTTP request
            async with aiohttp.ClientSession() as session:
                # Issue GET with the X-API-Key header
                async with session.get(url, headers={"X-API-Key": raw_key}) as resp:
                    # If the backend returns 200 OK, key is valid
                    if resp.status == 200:
                        # Return the raw_key itself to be used as AES key
                        return raw_key
                    # Any other status, API key invalid
                    raise HTTPException(status_code=401, detail="Invalid API key")
        except aiohttp.ClientError as e:
            # Handle network errors securely, without leaking details
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "api_validate_raw_key", endpoint=url
            )
            # Map to 502 Bad Gateway for upstream failures
            raise HTTPException(status_code=502, detail=error_info)

    @staticmethod
    def decrypt_bytes(encrypted_data: bytes, api_key: str) -> bytes:
        """
        Decrypt byte data using AES-GCM with the provided API key.

        Args:
            encrypted_data (bytes): Nonce concatenated with ciphertext.
            api_key (str): Base64 URL-safe encoded AES key.

        Returns:
            bytes: Decrypted plaintext bytes.
        """
        try:
            # Decode the AES key from URL-safe base64
            key_bytes = base64.urlsafe_b64decode(api_key.encode())
            # Extract the first 12 bytes as the nonce
            nonce = encrypted_data[:12]
            # The rest is the ciphertext and tag
            ciphertext = encrypted_data[12:]
            # Initialize the AESGCM cipher object
            aesgcm = AESGCM(key_bytes)
            # Decrypt and return plaintext
            return aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            # Secure error handling without leaking secrets
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_decryption", resource_id="decrypt_bytes"
            )
            raise HTTPException(status_code=400, detail=error_info)

    @staticmethod
    def encrypt_bytes(data: bytes, api_key: str) -> bytes:
        """
        Encrypt byte data using AES-GCM with the provided API key.

        Args:
            data (bytes): Plaintext bytes to encrypt.
            api_key (str): Base64 URL-safe encoded AES key.

        Returns:
            bytes: Nonce concatenated with ciphertext and tag.
        """
        try:
            # Decode AES key from URL-safe base64
            key_bytes = base64.urlsafe_b64decode(api_key.encode())
            # Generate a secure random 12-byte nonce
            nonce = os.urandom(12)
            # Initialize AESGCM cipher object
            aesgcm = AESGCM(key_bytes)
            # Encrypt and prepend the nonce
            return nonce + aesgcm.encrypt(nonce, data, None)
        except Exception as e:
            # Securely handle encryption errors
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_encryption", resource_id="encrypt_bytes"
            )
            raise HTTPException(status_code=400, detail=error_info)

    @staticmethod
    def decrypt_files(files: List[bytes], api_key: str) -> List[bytes]:
        """
        Decrypt multiple encrypted file contents in batch.

        Args:
            files (List[bytes]): List of encrypted file byte arrays.
            api_key (str): API key for decryption.

        Returns:
            List[bytes]: List of decrypted file contents.
        """
        try:
            # Apply decrypt_bytes to each file
            return [SessionEncryptionManager.decrypt_bytes(content, api_key) for content in files]
        except Exception as e:
            # Handle batch decryption errors securely
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_batch_decryption", resource_id="decrypt_files"
            )
            raise HTTPException(status_code=400, detail=error_info)

    @staticmethod
    async def decrypt_text(encrypted_text: bytes, api_key: str) -> str:
        """
        Decrypt a single encrypted text field to UTF-8 string.

        Args:
            encrypted_text (bytes): Encrypted bytes containing nonce + ciphertext.
            api_key (str): API key for decryption.

        Returns:
            str: Decrypted plaintext string.
        """
        try:
            # Decrypt to bytes first
            decrypted_bytes = SessionEncryptionManager.decrypt_bytes(encrypted_text, api_key)
            # Decode bytes to string
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            # Secure text decryption error handling
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "text_decryption", resource_id="decrypt_text"
            )
            raise HTTPException(status_code=400, detail=error_info)

    @staticmethod
    def encrypt_response(response_data: bytes, api_key: str) -> bytes:
        """
        Encrypt outgoing server response bytes with AES-GCM.

        Args:
            response_data (bytes): Plaintext response bytes.
            api_key (str): API key for encryption.

        Returns:
            bytes: Encrypted response bytes (nonce + ciphertext).
        """
        try:
            # Reuse encrypt_bytes logic
            return SessionEncryptionManager.encrypt_bytes(response_data, api_key)
        except Exception as e:
            # Secure batch encryption error handling
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "file_batch_encryption", resource_id="encrypt_response"
            )
            raise HTTPException(status_code=400, detail=error_info)

    async def validate_and_fetch_api_key(self, session_key: str, api_key_id: str) -> str:
        """
        Combined workflow to validate session and fetch API key.

        Args:
            session_key (str): Bearer token from client.
            api_key_id (str): Desired API key identifier.

        Returns:
            str: Decrypted API key string.
        """
        # Ensure both headers are provided
        if not session_key or not api_key_id:
            raise HTTPException(status_code=400, detail="Missing session_key or api_key_id in headers")
        # Validate the session token
        valid = await self.validate_session_key(session_key)
        # Reject if token is invalid
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid session key")
        # Fetch and return the API key
        return await self.fetch_api_key(session_key, api_key_id)

    async def prepare_inputs(
            self,
            files: List[UploadFile],
            form_fields: Dict[str, Optional[str]],
            session_key: Optional[str],
            api_key_id: Optional[str],
            raw_api_key: Optional[str]
    ) -> Tuple[List[UploadFile], Dict[str, Optional[str]], Optional[str]]:
        """
        Dispatch to the correct input-preparation mode and handle errors securely.

        Modes:
          1. session-authenticated: session_key + api_key_id
          2. raw-API-key:           raw_api_key only
          3. public:                no keys provided → passthrough

        Args:
            files:       List[UploadFile], possibly encrypted.
            form_fields: Dict[field_name, encrypted Base64 or plaintext].
            session_key: Optional Bearer token header.
            api_key_id:  Optional API key ID header.
            raw_api_key: Optional standalone X-API-Key header.

        Returns:
          - decrypted (or original) files
          - decrypted (or original) form field values
          - AES key used for decryption (None in public mode)
        """
        try:
            # Session mode if both headers present
            if session_key and api_key_id:
                return await self._prepare_session_inputs(
                    files, form_fields, session_key, api_key_id
                )

            # Raw-API-key mode if provided
            if raw_api_key:
                return await self._prepare_raw_inputs(
                    files, form_fields, raw_api_key
                )

            # Public mode: no decryption or encryption
            return files, form_fields, None

        except HTTPException:
            # Re-raise HTTPExceptions
            raise
        except Exception as e:
            # Securely handle unexpected errors
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "prepare_inputs", resource_id="prepare_inputs"
            )
            raise HTTPException(status_code=400, detail=error_info)

    async def _prepare_session_inputs(
            self,
            files: List[UploadFile],
            form_fields: Dict[str, Optional[str]],
            session_key: str,
            api_key_id: str
    ) -> Tuple[List[UploadFile], Dict[str, Optional[str]], str]:
        """
        Perform strict decryption of all inputs using a session-validated key.

        Steps:
          1. Validate the session token and retrieve the per-tenant AES key.
          2. Base64-decode every non-null form field into raw ciphertext bytes.
          3. Decrypt the uploaded files and form fields via AES-GCM.

        Args:
            files: List of potentially encrypted UploadFile objects.
            form_fields: Mapping of field names to Base64-URL-encoded ciphertext strings or None.
            session_key: Bearer token for session authentication.
            api_key_id: Identifier of the API key to fetch for decryption.

        Returns:
            A tuple of:
              - Decrypted UploadFile list.
              - Dict mapping field names to plaintext strings.
              - The Base64-URL-encoded AES key used for decryption.
        """
        try:
            # Validate session and retrieve AES key from backend
            api_key = await self.validate_and_fetch_api_key(session_key, api_key_id)

            # Prepare container for decoded form field bytes
            decoded: Dict[str, Optional[bytes]] = {}
            for name, val in form_fields.items():
                if val is None:
                    # Preserve None for missing fields
                    decoded[name] = None
                else:
                    # Attempt Base64-URL-safe decode of ciphertext
                    try:
                        decoded[name] = base64.urlsafe_b64decode(val.encode())
                    except Exception:
                        # Client provided invalid Base64 string
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid Base64 for field '{name}'"
                        )

            # Decrypt files and form fields using the AES key
            files_out, fields_out = await self._decrypt_with_key(
                files=files,
                encrypted_fields=decoded,
                api_key=api_key
            )

            # Return decrypted data and the AES key
            return files_out, fields_out, api_key

        except HTTPException:
            # Re-raise known HTTP errors unchanged
            raise
        except Exception as e:
            # Securely handle unexpected errors without leaking details
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "prepare_session_inputs", resource_id="prepare_inputs"
            )
            raise HTTPException(status_code=400, detail=error_info)

    async def _prepare_raw_inputs(
            self,
            files: List[UploadFile],
            form_fields: Dict[str, Optional[str]],
            raw_api_key: str
    ) -> Tuple[List[UploadFile], Dict[str, Optional[str]], Optional[str]]:
        """
        Handle raw-API-key mode: validate the key, attempt to decrypt each field and file,
        fall back to plaintext/raw on failure, and only return the AES key if at least
        one decryption succeeded.

        Args:
            files: Uploaded files (some may be encrypted).
            form_fields: Dict mapping field names to either Base64-URL ciphertext or plaintext.
            raw_api_key: Standalone API key header value.

        Returns:
            Tuple of:
              - List of UploadFile objects (decrypted or original).
              - Dict of field names to plaintext strings.
              - The AES key if any decryption occurred, otherwise None.
        """
        try:
            # Validate the standalone API key and fetch the AES key
            api_key = await self.validate_raw_api_key(raw_api_key)
            # Initialize flag to track if any decryption succeeds
            decrypted_any = False

            # Prepare output dictionary for decrypted or fallback field values
            fields_out: Dict[str, Optional[str]] = {}
            # Iterate over each form field
            for name, val in form_fields.items():
                # If the field value is None, preserve it as None
                if val is None:
                    fields_out[name] = None
                else:
                    # Process this field and capture whether decryption occurred
                    plaintext, did_decrypt = await self._process_raw_field(val, api_key)
                    # Store the resulting plaintext or fallback text
                    fields_out[name] = plaintext
                    # Update the decryption flag if this field was decrypted
                    decrypted_any |= did_decrypt

            # Process uploaded files with best-effort decryption
            files_out, files_decrypted = await self._process_raw_files(files, api_key)
            # Update the decryption flag if any file was decrypted
            decrypted_any |= files_decrypted

            # Return the AES key only if we decrypted at least one item
            return files_out, fields_out, (api_key if decrypted_any else None)

        except HTTPException:
            # Propagate known HTTPExceptions (e.g., invalid key) unchanged
            raise
        except Exception as e:
            # Handle unexpected errors through the secure error handler
            info = SecurityAwareErrorHandler.handle_safe_error(
                e, "prepare_raw_inputs", resource_id="prepare_inputs"
            )
            # Raise a generic HTTPException with sanitized info
            raise HTTPException(status_code=400, detail=info)

    async def _process_raw_field(
            self,
            val: str,
            api_key: str
    ) -> Tuple[str, bool]:
        """
        Try to Base64-decode and AES-GCM decrypt a single form field value.
        Fallback to plaintext on any failure.

        Args:
            val: The original field string (Base64-URL or plaintext).
            api_key: AES key for decryption.

        Returns:
            A tuple of (plaintext_value, did_decrypt_flag).
        """
        # Attempt Base64-URL-safe decoding of the field value
        try:
            blob = base64.urlsafe_b64decode(val.encode())
        except Exception as e:
            # Log decode failure and return the original plaintext
            log_error(f"[RAW] Base64 decode failed for field '{val}': {e}")
            return val, False

        # Attempt AES-GCM decryption on the decoded bytes
        try:
            plaintext = await self.decrypt_text(blob, api_key)
            # Return decrypted plaintext and mark as decrypted
            return plaintext, True
        except HTTPException:
            # Client-facing decryption error → treat decoded bytes as text
            return blob.decode(errors="ignore"), False
        except Exception as e:
            # Log unexpected decryption failure and return decoded text
            log_error(f"[RAW] Decryption error for field '{val}': {e}")
            return blob.decode(errors="ignore"), False

    async def _process_raw_files(
            self,
            files: List[UploadFile],
            api_key: str
    ) -> Tuple[List[UploadFile], bool]:
        """
        Attempt AES-GCM decryption on each uploaded file.
        Fallback to raw bytes if decryption fails.

        Args:
            files: List of potentially encrypted UploadFile objects.
            api_key: AES key for decryption.

        Returns:
            A tuple of (processed_files, did_decrypt_any_flag).
        """
        # Read the raw bytes of all files concurrently
        try:
            blobs = await asyncio.gather(*(f.read() for f in files))
        except Exception as e:
            # Handle file-read errors securely
            info = SecurityAwareErrorHandler.handle_safe_error(
                e, "process_raw_files", resource_id="read_files"
            )
            raise HTTPException(status_code=400, detail=info)

        # Prepare list for processed UploadFile objects
        processed: List[UploadFile] = []
        # Flag to track if any file was decrypted
        decrypted_any = False

        # Iterate through original files and their raw byte blobs
        for orig, blob in zip(files, blobs):
            # Attempt AES-GCM decryption for this blob
            try:
                decrypted = self.decrypt_bytes(blob, api_key)
                # Wrap decrypted bytes in a new UploadFile
                new_upload = UploadFile(
                    filename=orig.filename,
                    file=BytesIO(decrypted),
                    headers=orig.headers
                )
                processed.append(new_upload)
                decrypted_any = True
            except Exception as e:
                # Log decryption failure and fallback to raw bytes
                log_error(f"[RAW] File decryption failed for '{orig.filename}': {e}")
                processed.append(UploadFile(filename=orig.filename, file=BytesIO(blob)))

        # Return the list of processed files and whether any decryption succeeded
        return processed, decrypted_any

    async def _decrypt_with_key(
            self,
            files: List[UploadFile],
            encrypted_fields: Dict[str, Optional[bytes]],
            api_key: str
    ) -> Tuple[List[UploadFile], Dict[str, Optional[str]]]:
        """
        Decrypt-only helper: assumes the AES key is already validated and provided.

        Args:
            files: List of UploadFile objects whose contents are encrypted.
            encrypted_fields: Mapping of field names to encrypted raw bytes (or None).
            api_key: Base64-URL-encoded AES key used to perform decryption.

        Returns:
            Tuple containing:
              - A list of UploadFile objects with decrypted content streams.
              - A dict mapping field names to their decrypted plaintext strings.

        Raises:
            HTTPException: If any decryption step fails.
        """
        try:
            # Read the encrypted bytes from all UploadFile streams concurrently
            contents = await asyncio.gather(*(file.read() for file in files))

            # Decrypt each file’s byte content using AES-GCM
            decrypted_bytes_list = self.decrypt_files(contents, api_key)

            # Wrap the decrypted bytes back into new UploadFile objects
            files_out = []
            for f, decrypted_bytes in zip(files, decrypted_bytes_list):
                new_upload = UploadFile(
                    filename=f.filename,
                    file=BytesIO(decrypted_bytes),
                    headers=f.headers
                )
                files_out.append(new_upload)

            # Prepare a container for decrypted form field values
            fields_out: Dict[str, Optional[str]] = {}

            # Decrypt each field’s raw bytes into a UTF-8 string
            for name, raw_bytes in encrypted_fields.items():
                if raw_bytes is not None:
                    fields_out[name] = await self.decrypt_text(raw_bytes, api_key)
                else:
                    fields_out[name] = None

            # Return the list of decrypted files and the decrypted field mapping
            return files_out, fields_out

        except HTTPException:
            # Propagate HTTPExceptions unchanged
            raise
        except Exception as e:
            # Securely handle decryption errors without leaking sensitive information
            error_info = SecurityAwareErrorHandler.handle_safe_error(
                e, "decrypt_with_key", resource_id="_decrypt_with_key"
            )
            raise HTTPException(status_code=400, detail=error_info)

    def wrap_response(
            self,
            result: Dict,
            api_key: Optional[str]
    ) -> JSONResponse:
        """
        Conditionally encrypt outgoing JSON payload if an API key is provided.

        Args:
            result: The plain Python dict that should be JSON‐serialized.
            api_key: The AES key for encrypting the payload (None for no encryption).

        Returns:
            JSONResponse containing either:
              - {"encrypted_data": "<Base64-URL-encoded ciphertext>"} when api_key is provided, or
              - The original result dict when api_key is None.

        Raises:
            HTTPException: If encryption fails.
        """
        # If an AES key is available, encrypt the serialized JSON
        if api_key:
            try:
                # Serialize the result dict to bytes
                raw = json.dumps(result).encode("utf-8")
                # Encrypt the raw bytes using AES-GCM
                cipher = self.encrypt_response(raw, api_key)
                # Encode the ciphertext as Base64-URL for safe transport in JSON
                b64 = base64.urlsafe_b64encode(cipher).decode()
                # Return only the encrypted blob under a single key
                return JSONResponse({"encrypted_data": b64})
            except HTTPException:
                # Propagate HTTPExceptions unchanged
                raise
            except Exception as e:
                # Securely handle encryption errors
                error_info = SecurityAwareErrorHandler.handle_safe_error(
                    e, "wrap_response", resource_id="wrap_response"
                )
                raise HTTPException(status_code=500, detail=error_info)

        # No encryption requested: return standard JSONResponse directly
        return JSONResponse(result)


# Instantiate or retrieve the singleton for application-wide use
session_manager = SessionEncryptionManager.get_instance()
