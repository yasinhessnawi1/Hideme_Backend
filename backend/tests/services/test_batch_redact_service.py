import json

import os

import tempfile

import unittest

from unittest.mock import patch, mock_open, AsyncMock

from starlette.responses import StreamingResponse

from backend.app.services.batch_redact_service import BatchRedactService


# Dummy upload file object for filename and MIME type tests
class DummyUploadFile:

    def __init__(self, filename="test.pdf", content_type="application/pdf"):
        self.filename = filename

        self.content_type = content_type


# Dummy PDF redaction service for testing apply_redactions
class DummyPDFRedactionService:

    def __init__(self, content):
        self.content = content

    def apply_redactions(self, mapping, output_path, remove_images):
        return f"{output_path}/redacted.pdf"

    def close(self):
        pass


# Test suite for BatchRedactService functionality
class TestBatchRedactService(unittest.IsolatedAsyncioTestCase):

    # Test parsing single-file redaction mappings
    def test_parse_redaction_mappings_single_file(self):

        json_str = json.dumps({

            "redaction_mapping": {"pages": []},

            "file_info": {"filename": "test.pdf"}

        })

        result = BatchRedactService._parse_redaction_mappings(json_str)

        self.assertIn("test.pdf", result)

    # Test parsing multiple-file redaction mappings
    def test_parse_redaction_mappings_multiple(self):

        json_str = json.dumps({

            "file_results": [

                {

                    "file": "file1.pdf",

                    "status": "success",

                    "results": {"redaction_mapping": {"pages": []}}

                }

            ]

        })

        result = BatchRedactService._parse_redaction_mappings(json_str)

        self.assertIn("file1.pdf", result)

    # Test handling of invalid JSON in parsing mappings
    def test_parse_redaction_mappings_invalid_json(self):

        result = BatchRedactService._parse_redaction_mappings("invalid")

        self.assertEqual(result, {})

    # Test computation of redaction summary values
    def test_compute_redaction_summary_values(self):

        metadata = [{"original_name": "file1.pdf"}]

        mapping = {0: {"status": "success", "redactions_applied": 3}}

        success, fail, total, time, summary = BatchRedactService._compute_redaction_summary(

            metadata, mapping, 0.0, "id"

        )

        self.assertEqual(success, 1)

        self.assertEqual(total, 3)

        self.assertEqual(summary["batch_id"], "id")

    # Test building file results list from metadata and mapping
    def test_build_file_results(self):

        metadata = [{"original_name": "file1.pdf"}, {"original_name": "file2.pdf"}]

        mapping = {

            0: {"status": "success", "output_path": __file__, "redactions_applied": 2},

            1: {"status": "error", "error": "fail"}

        }

        results = BatchRedactService._build_file_results(metadata, mapping)

        self.assertEqual(results[0]["status"], "success")

        self.assertEqual(results[1]["status"], "error")

    # Test streaming ZIP success for existing file
    @patch("builtins.open", new_callable=mock_open, read_data=b"abc")
    @patch("os.path.exists", return_value=True)
    async def test_stream_zip_success(self, mock_exists, mock_file):

        chunks = []

        async for chunk in BatchRedactService._stream_zip("fake.zip"):
            chunks.append(chunk)

        self.assertEqual(chunks[0], b"abc")

    # Test streaming ZIP handles read errors gracefully
    @patch("builtins.open", side_effect=Exception("fail"))
    async def test_stream_zip_error_handling(self, mock_open):

        chunks = []

        async for chunk in BatchRedactService._stream_zip("file.zip"):
            chunks.append(chunk)

        self.assertEqual(chunks[0], b"")

    # Test building streaming response headers include redaction counts
    def test_build_streaming_response_headers(self):

        summary = {

            "total_time": 1.23,

            "successful": 2,

            "failed": 1,

            "total_redactions": 4

        }

        resp = BatchRedactService.build_streaming_response("some.zip", summary, "batch001")

        self.assertIsInstance(resp, StreamingResponse)

        self.assertIn("X-Total-Redactions", resp.headers)

    # Test preparing redaction items with basic inputs
    def test_prepare_redaction_items_basic(self):

        files = [(0, b"abc")]

        meta = [{

            "mapping": {"pages": []},

            "safe_name": "safe.pdf"

        }]

        result = BatchRedactService._prepare_redaction_items(files, meta, "/tmp")

        self.assertEqual(len(result), 1)

        self.assertIn("/tmp", result[0][3])

    # Test preparing files for redaction with valid PDF
    @patch("backend.app.services.batch_redact_service.read_and_validate_file",

           return_value=(b"%PDF", None, 0.1))
    @patch("backend.app.services.batch_redact_service.sanitize_filename", return_value="safe_test.pdf")
    async def test_prepare_files_for_redaction_valid(self, mock_sanitize, mock_read):

        file = DummyUploadFile()

        result_meta, valid_files = await BatchRedactService._prepare_files_for_redaction(

            [file], {"test.pdf": {"pages": []}}, "op123"

        )

        self.assertEqual(len(valid_files), 1)

        self.assertEqual(result_meta[0]["status"], "success")

    # Test preparing files for redaction when read fails
    @patch("backend.app.services.batch_redact_service.read_and_validate_file",

           return_value=(None, "Some error", 0))
    async def test_prepare_files_for_redaction_invalid_file(self, mock_read):

        file = DummyUploadFile()

        result_meta, valid_files = await BatchRedactService._prepare_files_for_redaction(

            [file], {"test.pdf": {"pages": []}}, "op456"

        )

        self.assertEqual(result_meta[0]["status"], "error")

        self.assertEqual(valid_files, [])

    # Test preparing files for redaction with missing mapping entry
    async def test_prepare_files_for_redaction_missing_mapping(self):

        file = DummyUploadFile("not_in_mapping.pdf")

        result_meta, valid_files = await BatchRedactService._prepare_files_for_redaction(

            [file], {}, "op789"

        )

        self.assertEqual(result_meta[0]["status"], "error")

        self.assertEqual(valid_files, [])

    # Test creating zip archive with a single redacted PDF
    def test_create_zip_archive_basic(self):

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "output.zip")

            file_path = os.path.join(tmp, "redacted_sample.pdf")

            with open(file_path, "wb") as f:
                f.write(b"pdfcontent")

            summary = {

                "file_results": [{

                    "file": "test.pdf",

                    "status": "success",

                    "arcname": "test.pdf"

                }]

            }

            metadata = [{"original_name": "test.pdf"}]

            mapping = {0: {"output_path": file_path}}

            BatchRedactService._create_zip_archive(summary, metadata, mapping, zip_path)

            self.assertTrue(os.path.exists(zip_path))

    # Test processing redaction items successfully in parallel
    @patch("backend.app.services.batch_redact_service.PDFRedactionService.apply_redactions",

           return_value="/tmp/redacted.pdf")
    @patch("backend.app.services.batch_redact_service.PDFRedactionService.close")
    @patch("backend.app.services.batch_redact_service.ParallelProcessingCore.process_in_parallel")
    async def test_process_redaction_items_success(self, mock_parallel, mock_close, mock_apply):

        mock_parallel.return_value = [(0, {"status": "success", "output_path": "/tmp/x.pdf", "redactions_applied": 5})]

        items = [(0, b"abc", {"pages": []}, "/tmp/x.pdf")]

        results = await BatchRedactService._process_redaction_items(items, 2, False)

        self.assertIn(0, results)

        self.assertEqual(results[0]["status"], "success")

    # Test processing redaction items logs warning on invalid format
    @patch("backend.app.services.batch_redact_service.ParallelProcessingCore.process_in_parallel")
    async def test_process_redaction_items_error_format(self, mock_parallel):

        mock_parallel.return_value = ["invalid_format"]

        items = [(0, b"abc", {"pages": []}, "/tmp/out.pdf")]

        result = await BatchRedactService._process_redaction_items(items, 2, False)

        self.assertEqual(result, {})  # warning logged, nothing returned

    # Test batch_redact_documents errors on too many files
    @patch("backend.app.services.batch_redact_service.MAX_FILES_COUNT", 1)
    async def test_too_many_files(self):

        result = await BatchRedactService.batch_redact_documents(

            files=[DummyUploadFile(), DummyUploadFile()],

            redaction_mappings="{}"

        )

        self.assertEqual(result.status_code, 400)

        self.assertIn("Too many files", result.body.decode())

    # Test batch_redact_documents errors on invalid mappings JSON
    async def test_invalid_redaction_mappings(self):

        result = await BatchRedactService.batch_redact_documents(

            files=[DummyUploadFile()],

            redaction_mappings="invalid"

        )

        self.assertEqual(result.status_code, 400)

        self.assertIn("No valid redaction mappings", result.body.decode())

    # Test batch_redact_documents handles no valid files case
    @patch("backend.app.services.batch_redact_service.SecureTempFileManager.create_secure_temp_dir_async",

           new_callable=AsyncMock)
    @patch("backend.app.services.batch_redact_service.SecureTempFileManager.secure_delete_directory")
    @patch("backend.app.services.batch_redact_service.BatchRedactService._prepare_files_for_redaction",

           return_value=([], []))
    async def test_no_valid_files(self, mock_prepare, mock_delete, mock_tempdir):

        mock_tempdir.return_value = "/tmp/dir"

        files = [DummyUploadFile()]

        mappings = json.dumps({

            "redaction_mapping": {"pages": []},

            "file_info": {"filename": "test.pdf"}

        })

        result = await BatchRedactService.batch_redact_documents(files, mappings)

        self.assertEqual(result.status_code, 400)

        self.assertIn("No valid files", result.body.decode())

    # Test successful batch redaction end-to-end
    @patch("backend.app.services.batch_redact_service.SecureTempFileManager.create_secure_temp_file_async",

           new_callable=AsyncMock)
    @patch("backend.app.services.batch_redact_service.SecureTempFileManager.create_secure_temp_dir_async",

           new_callable=AsyncMock)
    @patch("backend.app.services.batch_redact_service.BatchRedactService._prepare_files_for_redaction")
    @patch("backend.app.services.batch_redact_service.BatchRedactService._process_redaction_items",

           new_callable=AsyncMock)
    @patch("backend.app.services.batch_redact_service.BatchRedactService._create_zip_archive")
    @patch("backend.app.services.batch_redact_service.record_keeper.record_processing")
    @patch("backend.app.services.batch_redact_service.log_batch_operation")
    @patch("os.path.exists", return_value=True)
    async def test_successful_batch_redact_documents(

            self, mock_exists, mock_log, mock_record, mock_zip, mock_process, mock_prepare, mock_tempdir, mock_tempfile

    ):

        mock_tempdir.return_value = "/tmp/batch"

        mock_tempfile.return_value = "/tmp/batch/file.zip"

        mock_prepare.return_value = (

            [{

                "original_name": "test.pdf",

                "safe_name": "safe_test.pdf",

                "mapping": {"pages": []},

                "content_type": "application/pdf",

                "size": 100,

                "status": "success",

                "read_time": 0.1

            }],

            [(0, b"%PDF")]

        )

        mock_process.return_value = {

            0: {

                "status": "success",

                "output_path": "/tmp/batch/redacted_safe_test.pdf",

                "redactions_applied": 2

            }

        }

        mappings = json.dumps({

            "redaction_mapping": {"pages": [{"sensitive": ["abc"]}]},

            "file_info": {"filename": "test.pdf"}

        })

        response = await BatchRedactService.batch_redact_documents(

            files=[DummyUploadFile()],

            redaction_mappings=mappings

        )

        self.assertIsInstance(response, StreamingResponse)

        self.assertEqual(response.headers["X-Total-Redactions"], "2")

    # Test processing a single redaction item successfully
    @patch("backend.app.services.batch_redact_service.PDFRedactionService", new=DummyPDFRedactionService)
    async def test_process_redaction_item_success(self):

        item = (0, b"pdf", {"pages": [{"sensitive": ["test"]}]}, "/tmp")

        result = await BatchRedactService._process_redaction_items([item], max_workers=1, remove_images=False)

        self.assertIn("status", result[0])

        self.assertEqual(result[0]["status"], "success")

    # Test processing a single redaction item failure case
    @patch("backend.app.services.batch_redact_service.PDFRedactionService")
    async def test_process_redaction_item_failure(self, mock_pdf):

        mock_pdf.side_effect = Exception("redaction failed")

        item = (0, b"pdf", {"pages": [{"sensitive": ["test"]}]}, "/tmp")

        result = await BatchRedactService._process_redaction_items([item], max_workers=1, remove_images=False)

        self.assertEqual(result[0]["status"], "error")
