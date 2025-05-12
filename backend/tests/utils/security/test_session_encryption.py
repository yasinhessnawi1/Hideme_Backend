import os

import aiohttp
import pytest
import base64
import json

import importlib
import backend.app.utils.security.session_encryption as semod

from io import BytesIO
from fastapi import UploadFile, HTTPException
from unittest.mock import AsyncMock, patch

os.environ["GO_BACKEND_URL"] = "http://dummy"


importlib.reload(semod)
SessionEncryptionManager = semod.SessionEncryptionManager


# Dummy aiohttp replacements
class DummyResponse:
    def __init__(self, status=200, json_data=None):
        self.status = status

        self._json = json_data or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # nothing to clean up in this dummy response
        pass

    async def json(self):
        return self._json


class DummySession:
    def __init__(self, *args, **kwargs):
        # no real initialization needed for the dummy
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # no resources to release for the dummy session
        pass

    def get(self, url, headers=None):
        if url.endswith("/api/auth/verify"):

            return DummyResponse(200)

        if url.endswith("/api/auth/verify-key"):

            return DummyResponse(200)

        if "/api/keys/" in url and url.endswith("/decode"):

            return DummyResponse(200, {"data": {"key": "dummy_key"}})

        return DummyResponse(404)

    @staticmethod
    def post():
        return DummyResponse(200)


class ErrorSession:
    def __init__(self, *args, **kwargs):
        # no state; just used to simulate network failures
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        # nothing to clean up after simulating a failure
        pass

    def get(self, *args, **kwargs):
        # always fail to simulate a downstream network error
        raise aiohttp.ClientError("network down")

    def post(self, *args, **kwargs):
        # always fail to simulate a downstream network error
        raise aiohttp.ClientError("network down")


@pytest.fixture(autouse=True)
def reset_env_and_singleton(monkeypatch):
    monkeypatch.delenv("GO_BACKEND_URL", raising=False)

    semod.SessionEncryptionManager._instance = None


@pytest.fixture
def patched_session(monkeypatch):
    monkeypatch.setenv("GO_BACKEND_URL", "http://dummy")

    monkeypatch.setattr(
        "backend.app.utils.security.session_encryption.aiohttp.ClientSession",
        DummySession,
    )


@pytest.fixture(autouse=True)
def patch_error_session(monkeypatch):
    monkeypatch.setenv("GO_BACKEND_URL", "http://dummy")

    monkeypatch.setattr(
        "backend.app.utils.security.session_encryption.aiohttp.ClientSession",
        ErrorSession,
    )

    semod.SessionEncryptionManager._instance = None


@pytest.fixture
def manager(patched_session):
    return SessionEncryptionManager.get_instance()


@pytest.fixture
def dummy_api_key():
    return base64.urlsafe_b64encode(b"\x00" * 32).decode()


@pytest.fixture
def dummy_data():
    return b"Hello, World!"


@pytest.fixture
def plain_upload():
    return UploadFile(filename="plain.txt", file=BytesIO(b"plain"))


@pytest.fixture
def encrypted_upload(manager, dummy_api_key):
    enc = manager.encrypt_bytes(b"secret", dummy_api_key)

    return UploadFile(filename="secret.txt", file=BytesIO(enc))


@pytest.mark.asyncio
class TestSessionEncryptionManager:

    # Initialization errors
    def test_missing_env_raises(self):
        with pytest.raises(RuntimeError):
            semod.SessionEncryptionManager._instance = None

            semod.SessionEncryptionManager.get_instance()

    def test_duplicate_init_raises(self, patched_session):
        SessionEncryptionManager.get_instance()

        with pytest.raises(RuntimeError):
            SessionEncryptionManager("http://dummy")

    # Core crypto
    async def test_encrypt_decrypt_bytes(self, manager, dummy_data, dummy_api_key):
        enc = manager.encrypt_bytes(dummy_data, dummy_api_key)

        assert manager.decrypt_bytes(enc, dummy_api_key) == dummy_data

    def test_encrypt_bytes_bad_key(self, manager):
        with pytest.raises(HTTPException):
            manager.encrypt_bytes(b"data", "not_base64")

    def test_decrypt_bytes_bad_blob(self, manager, dummy_api_key):
        with pytest.raises(HTTPException):
            manager.decrypt_bytes(b"bad", dummy_api_key)

    async def test_decrypt_text(self, manager, dummy_data, dummy_api_key):
        enc = manager.encrypt_bytes(dummy_data, dummy_api_key)

        assert await manager.decrypt_text(enc, dummy_api_key) == dummy_data.decode()

    async def test_decrypt_text_invalid(self, manager, dummy_api_key):
        with pytest.raises(HTTPException):
            await manager.decrypt_text(b"oops", dummy_api_key)

    def test_decrypt_files(self, manager, dummy_data, dummy_api_key):
        enc = manager.encrypt_bytes(dummy_data, dummy_api_key)

        assert manager.decrypt_files([enc], dummy_api_key) == [dummy_data]

    async def test_encrypt_response_roundtrip(self, manager, dummy_data, dummy_api_key):
        enc = manager.encrypt_response(dummy_data, dummy_api_key)

        assert manager.decrypt_bytes(enc, dummy_api_key) == dummy_data

    # Key validation
    async def test_validate_session_key(self, manager):
        assert await manager.validate_session_key("any") is True

    async def test_validate_raw_api_key_success(self, manager):
        assert await manager.validate_raw_api_key("raw") == "raw"

    async def test_validate_raw_api_key_failure(self, manager, monkeypatch):
        class Bad(DummySession):

            def get(self, url, headers=None):
                return DummyResponse(401)

        monkeypatch.setattr(
            "backend.app.utils.security.session_encryption.aiohttp.ClientSession", Bad
        )

        with pytest.raises(HTTPException):
            await manager.validate_raw_api_key("raw")

    async def test_fetch_api_key(self, manager):
        assert await manager.fetch_api_key("tok", "id") == "dummy_key"

    async def test_validate_and_fetch_missing(self, manager):
        with pytest.raises(HTTPException):
            await manager.validate_and_fetch_api_key("", "")

    async def test_validate_and_fetch_invalid_session(self, manager):
        manager.validate_session_key = AsyncMock(return_value=False)

        with pytest.raises(HTTPException):
            await manager.validate_and_fetch_api_key("bad", "id")

    async def test_validate_and_fetch_success(self, manager):
        manager.validate_session_key = AsyncMock(return_value=True)

        manager.fetch_api_key = AsyncMock(return_value="got")

        assert await manager.validate_and_fetch_api_key("ok", "id") == "got"

    # wrap_response
    async def test_wrap_response_plain(self, manager):
        resp = manager.wrap_response({"a": 1}, api_key=None)

        assert resp.status_code == 200

        assert resp.body == b'{"a":1}'

    async def test_wrap_response_encrypted(self, manager, dummy_api_key):
        resp = manager.wrap_response({"x": 123}, api_key=dummy_api_key)

        payload = json.loads(resp.body)

        assert "encrypted_data" in payload

        ct = base64.urlsafe_b64decode(payload["encrypted_data"])

        assert json.loads(manager.decrypt_bytes(ct, dummy_api_key)) == {"x": 123}

    # prepare_inputs public/session/raw
    async def test_public_passthrough(self, manager, plain_upload):
        files, fields, api = await manager.prepare_inputs(
            [plain_upload], {"f": "v"}, None, None, None
        )

        assert files == [plain_upload] and fields == {"f": "v"} and api is None

    @patch.object(
        SessionEncryptionManager, "validate_and_fetch_api_key", new_callable=AsyncMock
    )
    async def test_session_prepare(self, mock_vaf, manager, dummy_api_key):
        mock_vaf.return_value = dummy_api_key

        secret, txt = b"file", "hello"

        enc_file = manager.encrypt_bytes(secret, dummy_api_key)

        enc_field = base64.urlsafe_b64encode(
            manager.encrypt_bytes(txt.encode(), dummy_api_key)
        ).decode()

        upload = UploadFile(filename="s.txt", file=BytesIO(enc_file))

        files, fields, api = await manager.prepare_inputs(
            [upload], {"fld": enc_field}, "s", "i", None
        )

        assert await files[0].read() == secret

        assert fields["fld"] == txt

        assert api == dummy_api_key

    async def test_session_prepare_bad_base64(self, manager, dummy_api_key):
        manager.validate_and_fetch_api_key = AsyncMock(return_value=dummy_api_key)

        upload = UploadFile(filename="x", file=BytesIO(b"ok"))

        with pytest.raises(HTTPException):
            await manager.prepare_inputs([upload], {"fld": "!!"}, "s", "i", None)

    async def test_raw_prepare_mixed(self, manager, dummy_api_key):
        manager.validate_raw_api_key = AsyncMock(return_value=dummy_api_key)

        sec, pl = b"s", b"p"

        enc_blob = manager.encrypt_bytes(sec, dummy_api_key)

        up_e = UploadFile(filename="e", file=BytesIO(enc_blob))

        up_p = UploadFile(filename="p", file=BytesIO(pl))

        fld = base64.urlsafe_b64encode(
            manager.encrypt_bytes(sec, dummy_api_key)
        ).decode()

        files, fields, api = await manager.prepare_inputs(
            [up_e, up_p], {"a": fld, "b": "txt"}, None, None, "raw"
        )

        assert fields["a"] == "s" and fields["b"] == "txt"

        assert await files[0].read() == sec and await files[1].read() == pl

        assert api == dummy_api_key

    async def test_raw_prepare_no_decrypt(self, manager, dummy_api_key):
        manager.validate_raw_api_key = AsyncMock(return_value=dummy_api_key)

        files, fields, api = await manager.prepare_inputs(
            [], {"x": "plain"}, None, None, "raw"
        )

        assert api is None and fields == {"x": "plain"} and files == []

    @pytest.mark.asyncio
    async def test_validate_session_key_network_error(self, monkeypatch):
        SessionEncryptionManager._instance = None

        monkeypatch.setenv("GO_BACKEND_URL", "http://dummy")

        monkeypatch.setattr(
            "backend.app.utils.security.session_encryption.aiohttp.ClientSession",
            ErrorSession,
        )

        mgr = SessionEncryptionManager.get_instance()

        with pytest.raises(HTTPException) as exc:
            await mgr.validate_session_key("any-token")

        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_fetch_api_key_network_error(self, monkeypatch):
        SessionEncryptionManager._instance = None

        monkeypatch.setenv("GO_BACKEND_URL", "http://dummy")

        monkeypatch.setattr(
            "backend.app.utils.security.session_encryption.aiohttp.ClientSession",
            ErrorSession,
        )

        mgr = SessionEncryptionManager.get_instance()

        with pytest.raises(HTTPException) as exc:
            await mgr.fetch_api_key("dummy_session_token", "dummy_api_key_id")

        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_validate_raw_api_key_network_error(self, monkeypatch):
        SessionEncryptionManager._instance = None

        monkeypatch.setenv("GO_BACKEND_URL", "http://dummy")

        monkeypatch.setattr(
            "backend.app.utils.security.session_encryption.aiohttp.ClientSession",
            ErrorSession,
        )

        mgr = SessionEncryptionManager.get_instance()

        with pytest.raises(HTTPException) as exc:
            await mgr.validate_raw_api_key("some-raw-key")

        assert exc.value.status_code == 502

    def test_decrypt_bytes_with_bad_key(self, manager):
        with pytest.raises(HTTPException):
            manager.decrypt_bytes(b"\x00" * 20, "not_base64")

    def test_encrypt_bytes_with_bad_key(self, manager):
        with pytest.raises(HTTPException):
            manager.encrypt_bytes(b"foo", "not_base64")

    @pytest.mark.asyncio
    async def test_decrypt_text_bad_blob(self, manager, dummy_api_key):
        with pytest.raises(HTTPException):
            await manager.decrypt_text(b"short", dummy_api_key)

    def test_decrypt_files_propagates(self, manager, dummy_api_key):
        def bad(_: bytes):
            raise HTTPException(status_code=400, detail="oops")

        monkey = patch.object(
            SessionEncryptionManager, "decrypt_bytes", side_effect=bad
        )

        with monkey:
            with pytest.raises(HTTPException):
                manager.decrypt_files([b"any"], dummy_api_key)

    @pytest.mark.asyncio
    async def test_encrypt_response_error(self, manager, dummy_api_key):
        monkey = patch.object(
            SessionEncryptionManager, "encrypt_bytes", side_effect=ValueError("bad")
        )

        with monkey:
            with pytest.raises(HTTPException) as exc:
                manager.wrap_response({"a": 1}, api_key=dummy_api_key)

            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_wrap_response_propagates_http_exception(
        self, manager, dummy_api_key
    ):
        monkey = patch.object(
            SessionEncryptionManager,
            "encrypt_response",
            side_effect=HTTPException(status_code=400, detail="x"),
        )

        with monkey:
            with pytest.raises(HTTPException) as exc:
                manager.wrap_response({"a": 1}, api_key=dummy_api_key)

            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_prepare_inputs_unexpected_error(self, manager):
        manager.validate_raw_api_key = AsyncMock(return_value="k")

        monkey = patch.object(
            manager, "_prepare_raw_inputs", side_effect=RuntimeError("boom")
        )

        with monkey:
            with pytest.raises(HTTPException) as exc:
                await manager.prepare_inputs([], {}, None, None, "raw")

            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test__process_raw_field_base64_decode(self, manager, dummy_api_key):
        val, did = await manager._process_raw_field("not_base64!!!", dummy_api_key)

        assert val == "not_base64!!!" and did is False

    @pytest.mark.asyncio
    async def test__process_raw_field_decrypt_http_exc(self, manager, dummy_api_key):
        blob = base64.urlsafe_b64encode(b"xyz").decode()

        monkey = patch.object(
            manager,
            "decrypt_text",
            side_effect=HTTPException(status_code=400, detail="no"),
        )

        with monkey:
            val, did = await manager._process_raw_field(blob, dummy_api_key)

        assert val == b"xyz".decode(errors="ignore") and did is False

    @pytest.mark.asyncio
    async def test__process_raw_files_read_error(self, manager):
        class BadFile:
            filename = "x"

            headers = {}

            async def read(self):
                raise RuntimeError("read fail")

        manager.validate_raw_api_key = AsyncMock(return_value="k")

        with pytest.raises(HTTPException):
            await manager._process_raw_files([BadFile()], "k")

    @pytest.mark.asyncio
    async def test__process_raw_files_decrypt_failure(self, manager, dummy_api_key):
        blob = b"data"

        up = UploadFile(filename="f", file=BytesIO(blob))

        patcher = patch.object(
            SessionEncryptionManager, "decrypt_bytes", side_effect=Exception("x")
        )

        with patcher:
            files_out, did = await manager._process_raw_files([up], dummy_api_key)

        data = await files_out[0].read()

        assert data == blob and did is False

    @pytest.mark.asyncio
    async def test__decrypt_with_key_read_error(self, manager):
        class BadFile2:
            filename = "x"

            headers = {}

            async def read(self):
                raise RuntimeError

        with pytest.raises(HTTPException):
            await manager._decrypt_with_key([BadFile2()], {}, "k")

    @pytest.mark.asyncio
    async def test__decrypt_with_key_decrypt_error(self, manager, dummy_api_key):
        class GoodFile:
            filename = "x"

            headers = {}

            @staticmethod
            async def read():
                return b"ok"

        monkey = patch.object(
            SessionEncryptionManager, "decrypt_files", side_effect=ValueError("fail")
        )

        with monkey:
            with pytest.raises(HTTPException):
                await manager._decrypt_with_key([GoodFile()], {"f": b""}, dummy_api_key)
