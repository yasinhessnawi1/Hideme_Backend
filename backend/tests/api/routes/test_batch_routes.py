import os
import io
import json
import base64
import pytest

from fastapi import UploadFile, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from starlette.responses import Response as StarletteResponse, StreamingResponse
from backend.app.api.main import create_app

os.environ["GO_BACKEND_URL"] = "http://dummy"

client = TestClient(create_app())

DUMMY_API_KEY = base64.urlsafe_b64encode(b"\x00" * 32).decode()


def encrypt_data(plaintext: bytes, api_key: str) -> bytes:
    key = base64.urlsafe_b64decode(api_key)

    nonce = os.urandom(12)

    aesgcm = AESGCM(key)

    return nonce + aesgcm.encrypt(nonce, plaintext, None)


def decrypt_data(blob: bytes, api_key: str) -> bytes:
    key = base64.urlsafe_b64decode(api_key)

    nonce, ct = blob[:12], blob[12:]

    return AESGCM(key).decrypt(nonce, ct, None)


@pytest.fixture
def encrypted_file():
    raw = b"PDFDATA"

    return "test.pdf", io.BytesIO(encrypt_data(raw, DUMMY_API_KEY)), "application/pdf"


@pytest.fixture
def enc_req_entities():
    return encrypt_data(b"PERSON,ORG", DUMMY_API_KEY)


@pytest.fixture
def enc_remove_words():
    return encrypt_data(b"secret,confidential", DUMMY_API_KEY)


@pytest.fixture
def enc_search_terms():
    return encrypt_data(b"findme", DUMMY_API_KEY)


@pytest.fixture
def enc_bbox():
    payload = json.dumps({"x0": 0, "y0": 0, "x1": 10, "y1": 10}).encode()

    return encrypt_data(payload, DUMMY_API_KEY)


@pytest.fixture
def enc_redaction_map():
    payload = json.dumps({"foo": "bar"}).encode()

    return encrypt_data(payload, DUMMY_API_KEY)


class DummyZipResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    async def body(self):
        return self._payload


class TestBatchEncryptedRoutes:

    # batch_detect success
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchDetectService.detect_entities_in_files",
        new_callable=AsyncMock,
    )
    def test_batch_detect_success(
        self,
        mock_detect,
        mock_prepare,
        encrypted_file,
        enc_req_entities,
        enc_remove_words,
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"requested_entities": "PERSON,ORG", "remove_words": "secret,confidential"},
            DUMMY_API_KEY,
        )

        mock_result = MagicMock()

        mock_result.model_dump.return_value = {"status": "ok", "count": 2}

        mock_detect.return_value = mock_result

        b64_req = base64.urlsafe_b64encode(enc_req_entities).decode()

        b64_rem = base64.urlsafe_b64encode(enc_remove_words).decode()

        resp = client.post(
            "/batch/detect",
            files=[("files", encrypted_file)],
            data={
                "threshold": "0.5",
                "detection_engine": "presidio",
                "requested_entities": b64_req,
                "remove_words": b64_rem,
            },
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 200

        cipher_b64 = resp.json()["encrypted_data"]

        inner = json.loads(
            decrypt_data(base64.urlsafe_b64decode(cipher_b64), DUMMY_API_KEY)
        )

        assert inner == {"status": "ok", "count": 2}

        mock_detect.assert_awaited_once()

    # batch_detect invalid threshold
    @patch(
        "backend.app.api.routes.batch_routes.validate_threshold_score",
        side_effect=HTTPException(status_code=400, detail="bad threshold"),
    )
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_detect_bad_threshold(
        self,
        mock_prepare,
        mock_validate,
        encrypted_file,
        enc_req_entities,
        enc_remove_words,
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"requested_entities": "X", "remove_words": "Y"},
            DUMMY_API_KEY,
        )

        b64_req = base64.urlsafe_b64encode(enc_req_entities).decode()

        b64_rem = base64.urlsafe_b64encode(enc_remove_words).decode()

        resp = client.post(
            "/batch/detect",
            files=[("files", encrypted_file)],
            data={
                "threshold": "2.0",
                "requested_entities": b64_req,
                "remove_words": b64_rem,
            },
            headers={"session-key": "s", "api-key-id": "id"},
        )

        mock_prepare.assert_awaited_once()

        assert resp.status_code == 400

        assert "bad threshold" in resp.text

    # batch_detect unsupported engine
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_detect_invalid_engine(self, mock_prepare, encrypted_file):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {},
            DUMMY_API_KEY,
        )

        resp = client.post(
            "/batch/detect",
            files=[("files", encrypted_file)],
            data={"threshold": "0.1", "detection_engine": "no_such_engine"},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 400

        assert "Invalid detection engine" in resp.json()["detail"]

    # batch_detect internal error
    @patch(
        "backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error",
        return_value={"detail": "err", "status_code": 500},
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchDetectService.detect_entities_in_files",
        side_effect=Exception("oops"),
    )
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_detect_internal_error(
        self,
        mock_prepare,
        mock_detect,
        mock_handle,
        encrypted_file,
        enc_req_entities,
        enc_remove_words,
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"requested_entities": "X", "remove_words": "Y"},
            None,
        )

        b64_req = base64.urlsafe_b64encode(enc_req_entities).decode()

        b64_rem = base64.urlsafe_b64encode(enc_remove_words).decode()

        resp = client.post(
            "/batch/detect",
            files=[("files", encrypted_file)],
            data={
                "threshold": "0.3",
                "requested_entities": b64_req,
                "remove_words": b64_rem,
            },
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 500

        assert resp.json()["detail"] == "err"

    # batch_hybrid_detect success
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchDetectService.detect_entities_in_files",
        new_callable=AsyncMock,
    )
    def test_batch_hybrid_success(
        self,
        mock_detect,
        mock_prepare,
        encrypted_file,
        enc_req_entities,
        enc_remove_words,
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"requested_entities": "E", "remove_words": "W"},
            DUMMY_API_KEY,
        )

        mock_result = MagicMock()

        mock_result.model_dump.return_value = {"ok": True}

        mock_detect.return_value = mock_result

        b64_req = base64.urlsafe_b64encode(enc_req_entities).decode()

        b64_rem = base64.urlsafe_b64encode(enc_remove_words).decode()

        resp = client.post(
            "/batch/hybrid_detect",
            files=[("files", encrypted_file)],
            data={
                "threshold": "0.5",
                "requested_entities": b64_req,
                "remove_words": b64_rem,
            },
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 200

        inner = json.loads(
            decrypt_data(
                base64.urlsafe_b64decode(resp.json()["encrypted_data"]), DUMMY_API_KEY
            )
        )

        assert inner == {"ok": True}

    # batch_hybrid_detect no engines selected
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_hybrid_no_engine(self, mock_prepare, encrypted_file):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {},
            DUMMY_API_KEY,
        )

        resp = client.post(
            "/batch/hybrid_detect",
            files=[("files", encrypted_file)],
            data={
                "threshold": "0.5",
                "use_presidio": "false",
                "use_gemini": "false",
                "use_gliner": "false",
                "use_hideme": "false",
            },
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 400

        assert "Select at least one detection engine" in resp.json()["detail"]

    # batch_search success
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchSearchService.batch_search_text",
        new_callable=AsyncMock,
    )
    def test_batch_search_success(
        self, mock_search, mock_prepare, encrypted_file, enc_search_terms
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"search_terms": "findme"},
            DUMMY_API_KEY,
        )

        mock_result = MagicMock()

        mock_result.model_dump.return_value = {"found": 3}

        mock_search.return_value = mock_result

        b64_terms = base64.urlsafe_b64encode(enc_search_terms).decode()

        resp = client.post(
            "/batch/search",
            files=[("files", encrypted_file)],
            data={"search_terms": b64_terms},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 200

        inner = json.loads(
            decrypt_data(
                base64.urlsafe_b64decode(resp.json()["encrypted_data"]), DUMMY_API_KEY
            )
        )

        assert inner == {"found": 3}

    # batch_search internal error
    @patch(
        "backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error",
        side_effect=lambda e, *a, **k: {"detail": "oops", "status_code": 500},
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchSearchService.batch_search_text",
        side_effect=Exception("explode"),
    )
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_search_internal_error(
        self, mock_prepare, mock_search, mock_handle, encrypted_file, enc_search_terms
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"search_terms": "findme"},
            None,
        )

        b64_terms = base64.urlsafe_b64encode(enc_search_terms).decode()

        resp = client.post(
            "/batch/search",
            files=[("files", encrypted_file)],
            data={"search_terms": b64_terms},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 500

        assert resp.json()["detail"] == "oops"

    # batch_find_words success
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchSearchService.find_words_by_bbox",
        new_callable=AsyncMock,
    )
    def test_batch_find_words_success(
        self, mock_find, mock_prepare, encrypted_file, enc_bbox
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"bounding_box": json.dumps({"x0": 0, "y0": 0, "x1": 10, "y1": 10})},
            DUMMY_API_KEY,
        )

        mock_result = MagicMock()

        mock_result.model_dump.return_value = {"words": ["a", "b"]}

        mock_find.return_value = mock_result

        b64_bbox = base64.urlsafe_b64encode(enc_bbox).decode()

        resp = client.post(
            "/batch/find_words",
            files=[("files", encrypted_file)],
            data={"bounding_box": b64_bbox},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 200

        inner = json.loads(
            decrypt_data(
                base64.urlsafe_b64decode(resp.json()["encrypted_data"]), DUMMY_API_KEY
            )
        )

        assert inner == {"words": ["a", "b"]}

    # batch_find_words bad bbox JSON
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_find_words_bad_bbox_format(
        self, mock_prepare, encrypted_file, enc_bbox
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"bounding_box": "not json"},
            DUMMY_API_KEY,
        )

        b64_bbox = base64.urlsafe_b64encode(enc_bbox).decode()

        resp = client.post(
            "/batch/find_words",
            files=[("files", encrypted_file)],
            data={"bounding_box": b64_bbox},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 400

        assert resp.json()["detail"] == "Invalid bounding box format."

    # batch_find_words missing keys
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_find_words_missing_keys(
        self, mock_prepare, encrypted_file, enc_bbox
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"bounding_box": json.dumps({"x0": 0, "y0": 0, "x1": 5})},
            DUMMY_API_KEY,
        )

        b64_bbox = base64.urlsafe_b64encode(enc_bbox).decode()

        resp = client.post(
            "/batch/find_words",
            files=[("files", encrypted_file)],
            data={"bounding_box": b64_bbox},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 400

        assert resp.json()["detail"] == "Invalid bounding box keys"

    # batch_redact success (encrypted response)
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchRedactService.batch_redact_documents",
        new_callable=AsyncMock,
    )
    def test_batch_redact_success_encrypted(
        self, mock_redact, mock_prepare, encrypted_file, enc_redaction_map
    ):
        payload = json.dumps({"ok": True}).encode()

        mock_redact.return_value = StarletteResponse(
            payload, media_type="application/octet-stream"
        )

        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"redaction_mappings": json.dumps({"foo": "bar"})},
            DUMMY_API_KEY,
        )

        b64_map = base64.urlsafe_b64encode(enc_redaction_map).decode()

        resp = client.post(
            "/batch/redact",
            files=[("files", encrypted_file)],
            data={"redaction_mappings": b64_map},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 200

        cipher_b64 = resp.json()["encrypted_data"]

        decrypted = decrypt_data(base64.urlsafe_b64decode(cipher_b64), DUMMY_API_KEY)

        assert json.loads(decrypted) == {"ok": True}

        mock_prepare.assert_awaited_once()

        mock_redact.assert_awaited_once()

    # batch_redact public mode (no encryption)
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchRedactService.batch_redact_documents",
        new_callable=AsyncMock,
    )
    def test_batch_redact_success_public(
        self, mock_redact, mock_prepare, encrypted_file, enc_redaction_map
    ):
        raw_zip = b"ZIPCONTENT"

        mock_redact.return_value = StreamingResponse(
            content=[raw_zip], media_type="application/zip"
        )

        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"redaction_mappings": json.dumps({"foo": "bar"})},
            None,
        )

        b64_map = base64.urlsafe_b64encode(enc_redaction_map).decode()

        resp = client.post(
            "/batch/redact",
            files=[("files", encrypted_file)],
            data={"redaction_mappings": b64_map},
        )

        assert resp.status_code == 200

        assert resp.content == raw_zip

    # batch_redact internal error
    @patch(
        "backend.app.api.routes.batch_routes.SecurityAwareErrorHandler.handle_safe_error",
        side_effect=lambda e, *a, **k: {"detail": "err", "status_code": 500},
    )
    @patch(
        "backend.app.api.routes.batch_routes.BatchRedactService.batch_redact_documents",
        side_effect=Exception("fail"),
    )
    @patch(
        "backend.app.api.routes.batch_routes.session_manager.prepare_inputs",
        new_callable=AsyncMock,
    )
    def test_batch_redact_internal_error(
        self, mock_prepare, mock_redact, mock_handle, encrypted_file, enc_redaction_map
    ):
        mock_prepare.return_value = (
            [UploadFile(filename="test.pdf", file=io.BytesIO(b"PDFDATA"))],
            {"redaction_mappings": json.dumps({"foo": "bar"})},
            None,
        )

        b64_map = base64.urlsafe_b64encode(enc_redaction_map).decode()

        resp = client.post(
            "/batch/redact",
            files=[("files", encrypted_file)],
            data={"redaction_mappings": b64_map},
            headers={"session-key": "s", "api-key-id": "id"},
        )

        assert resp.status_code == 500

        assert resp.json()["detail"] == "err"
