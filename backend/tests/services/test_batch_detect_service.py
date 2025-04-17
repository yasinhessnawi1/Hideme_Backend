import unittest
from unittest.mock import patch, AsyncMock

from backend.app.entity_detection import EntityDetectionEngine
from backend.app.services.batch_detect_service import BatchDetectService


class DummyFile:
    def __init__(self, filename="test.pdf", content_type="application/pdf"):
        self.filename = filename
        self.content_type = content_type


class BrokenDetector:
    def detect_sensitive_data(self, *_): return {"not": "a tuple"}


class DummyDetector:
    def detect_sensitive_data(self, data, entities):
        return ([{"text": "John"}], {"pages": [{"page": 0, "sensitive": ["John"]}]})


class FailingHybrid:
    def __init__(self): self.detectors = [self]

    def detect_sensitive_data(self, *_): raise Exception("fail engine")


class DummyHybridDetector:
    def __init__(self, detectors=None):
        self.detectors = detectors or [self]

    def detect_sensitive_data(self, data, entities):
        return ([{"text": "email", "score": 0.99}], {"pages": [{"page": 0, "sensitive": [{"text": "email"}]}]})


class DummyInit:
    def get_detector(self, engine, config=None):
        return DummyHybridDetector() if engine == EntityDetectionEngine.HYBRID else DummyDetector()


class TestBatchDetectService(unittest.IsolatedAsyncioTestCase):

    @patch("backend.app.services.batch_detect_service.MAX_FILES_COUNT", 3)
    async def test_exceeds_max_files(self):
        files = [DummyFile() for _ in range(4)]
        result = await BatchDetectService.detect_entities_in_files(files)
        self.assertIn("detail", result)
        self.assertIn("operation_id", result)

    @patch("backend.app.services.batch_detect_service.validate_all_engines_requested_entities",
           side_effect=Exception("Invalid"))
    async def test_invalid_requested_entities(self, mock_validate):
        result = await BatchDetectService.detect_entities_in_files([DummyFile()])

        self.assertIn("batch_summary", result)
        self.assertIn("error", result["batch_summary"])
        self.assertIn("Reference ID", result["batch_summary"]["error"])
        self.assertEqual(result["batch_summary"]["successful"], 0)
        self.assertEqual(result["batch_summary"]["failed"], 0)
        self.assertEqual(result["file_results"], [])

    @patch("backend.app.services.batch_detect_service.validate_all_engines_requested_entities", return_value=["EMAIL"])
    @patch("backend.app.services.batch_detect_service.BatchDetectService._get_initialized_detector",
           side_effect=Exception("init failed"))
    async def test_initialization_failure(self, mock_init, mock_val):
        result = await BatchDetectService.detect_entities_in_files([DummyFile()])

        self.assertIn("batch_summary", result)
        self.assertIn("error", result["batch_summary"])
        self.assertIn("Reference ID", result["batch_summary"]["error"])
        self.assertEqual(result["batch_summary"]["successful"], 0)
        self.assertEqual(result["batch_summary"]["failed"], 0)

    @patch("backend.app.services.batch_detect_service.validate_all_engines_requested_entities", return_value=["EMAIL"])
    @patch("backend.app.services.batch_detect_service.BatchDetectService._get_initialized_detector",
           return_value=DummyHybridDetector())
    @patch("backend.app.services.batch_detect_service.BatchDetectService._read_pdf_files",
           return_value=([None], ["file.pdf"], [{}]))
    async def test_invalid_file_skips_detection(self, mock_read, mock_init, mock_val):
        result = await BatchDetectService.detect_entities_in_files([DummyFile()])
        self.assertEqual(result["file_results"][0]["status"], "error")

    @patch("backend.app.services.batch_detect_service.validate_all_engines_requested_entities", return_value=["EMAIL"])
    @patch("backend.app.services.batch_detect_service.BatchDetectService._get_initialized_detector",
           return_value=DummyHybridDetector())
    @patch("backend.app.services.batch_detect_service.BatchDetectService._read_pdf_files", return_value=(
            [b"%PDF"], ["file.pdf"],
            [{"filename": "file.pdf", "content_type": "application/pdf", "size": 123, "read_time": 0.1}]))
    @patch("backend.app.services.batch_detect_service.PDFTextExtractor.extract_batch_text",
           return_value=[(0, {"pages": [{"words": ["hello"]}]})])
    async def test_successful_batch_detection(self, mock_extract, mock_read, mock_init, mock_val):
        result = await BatchDetectService.detect_entities_in_files([DummyFile()])
        self.assertEqual(result["file_results"][0]["status"], "success")
        self.assertIn("batch_summary", result)
        self.assertIn("file_info", result["file_results"][0]["results"])

    @patch("backend.app.services.batch_detect_service.minimize_extracted_data",
           return_value={"pages": [{"words": ["test"]}]})
    @patch("backend.app.services.batch_detect_service.replace_original_text_in_redaction",
           return_value={"pages": [{"page": 0, "sensitive": [{"text": "John"}]}]})
    async def test_process_detection_for_file_single(self, mock_replace, mock_min):
        result = await BatchDetectService._process_detection_for_file(
            extracted={"pages": [{"words": ["test"]}]},
            filename="sample.pdf",
            file_meta={"filename": "sample.pdf", "content_type": "application/pdf", "size": 100},
            entity_list=["EMAIL"],
            detector=DummyDetector(),
            detection_engine=EntityDetectionEngine.PRESIDIO,
            use_presidio=True,
            use_gemini=False,
            use_gliner=False,
            use_hideme=False,
            remove_words=None,
            threshold=0.5
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("model_info", result["results"])

    @patch("backend.app.services.batch_detect_service.minimize_extracted_data",
           return_value={"pages": [{"words": ["fail"]}]})
    @patch("backend.app.services.batch_detect_service.replace_original_text_in_redaction", return_value={"pages": []})
    async def test_process_single_detection_invalid_result(self, mock_replace, mock_min):
        with self.assertRaises(ValueError):
            await BatchDetectService._process_single_detection(
                {"pages": [{"words": ["fail"]}]},
                ["EMAIL"],
                BrokenDetector()
            )

    def test_merge_pages_logic(self):
        combined = {"pages": [{"page": 0, "sensitive": ["a"]}]}
        new_mapping = {"pages": [{"page": 0, "sensitive": ["b"]}, {"page": 1, "sensitive": ["c"]}]}
        BatchDetectService._merge_pages(combined, new_mapping)
        self.assertEqual(len(combined["pages"]), 2)
        self.assertIn("b", combined["pages"][0]["sensitive"])

    @patch("backend.app.services.batch_detect_service.initialization_service", new_callable=lambda: DummyInit())
    async def test_get_initialized_detector_hybrid(self, mock_init):
        detector = await BatchDetectService._get_initialized_detector(
            EntityDetectionEngine.HYBRID, use_presidio=True, use_gemini=False, use_gliner=False, use_hideme=False
        )
        self.assertIsInstance(detector, DummyHybridDetector)

    @patch("backend.app.services.batch_detect_service.initialization_service", new_callable=lambda: DummyInit())
    async def test_get_initialized_detector_single(self, mock_init):
        detector = await BatchDetectService._get_initialized_detector(EntityDetectionEngine.PRESIDIO)
        self.assertIsInstance(detector, DummyDetector)

    @patch("backend.app.services.batch_detect_service.PDFTextExtractor.extract_batch_text",
           side_effect=Exception("boom"))
    async def test_batch_extract_text_exception(self, mock_extract):
        with self.assertRaises(Exception) as ctx:
            await BatchDetectService._batch_extract_text([b"PDF"], 2)
        self.assertIn("boom", str(ctx.exception))

    @patch("backend.app.services.batch_detect_service.replace_original_text_in_redaction", return_value={"pages": []})
    async def test_process_hybrid_detection_fails_gracefully(self, mock_replace):
        result = await BatchDetectService._process_hybrid_detection(
            minimized_extracted={"pages": [{"words": ["x"]}]},
            entity_list=["EMAIL"],
            detector=FailingHybrid()
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(result[0], [])  # empty entities

    @patch("backend.app.services.batch_detect_service.read_and_validate_file", new_callable=AsyncMock)
    async def test_read_pdf_files_valid_and_invalid(self, mock_read):
        mock_read.side_effect = [
            (b"valid-content", None, 0.5),
            (None, {"error": "Validation error"}, 0.2),
            Exception("read failed")
        ]
        files = [
            DummyFile("good.pdf"),
            DummyFile("bad.pdf"),
            DummyFile("fail.pdf")
        ]
        pdfs, names, meta = await BatchDetectService._read_pdf_files(files, "batch_op")

        self.assertEqual(pdfs, [b"valid-content", None, None])
        self.assertEqual(names, ["good.pdf", "bad.pdf", "fail.pdf"])
        self.assertEqual(meta[0]["size"], len(b"valid-content"))
        self.assertEqual(meta[2]["content_type"], "unknown")

    @patch("backend.app.services.batch_detect_service.replace_original_text_in_redaction", return_value={"pages": []})
    async def test_process_hybrid_detection_all_cases(self, mock_replace):
        class Detector1:  # Raises exception
            def detect_sensitive_data(self, *_): raise Exception("Boom")

        class Detector2:  # Returns wrong format
            def detect_sensitive_data(self, *_): return {"invalid": "format"}

        class Detector3:  # Valid
            def detect_sensitive_data(self, *_): return ([{"text": "john"}], {"pages": [{"page": 0, "sensitive": []}]})

        hybrid_detector = DummyHybridDetector([Detector1(), Detector2(), Detector3()])

        result_entities, result_mapping = await BatchDetectService._process_hybrid_detection(
            {"pages": [{"words": ["hello"]}]},
            ["EMAIL"],
            hybrid_detector
        )
        self.assertEqual(len(result_entities), 1)
        self.assertIn("pages", result_mapping)

    @patch("backend.app.services.batch_detect_service.initialization_service")
    async def test_get_initialized_detector_variants(self, mock_service):
        mock_service.get_detector.side_effect = [
            DummyDetector(), DummyDetector(), DummyDetector(), None
        ]

        d1 = await BatchDetectService._get_initialized_detector(EntityDetectionEngine.GLINER, entity_list=["EMAIL"])
        self.assertIsInstance(d1, DummyDetector)

        d2 = await BatchDetectService._get_initialized_detector(EntityDetectionEngine.PRESIDIO)
        self.assertIsInstance(d2, DummyDetector)

        d3 = await BatchDetectService._get_initialized_detector(EntityDetectionEngine.HYBRID, use_gliner=True)
        self.assertIsInstance(d3, DummyDetector)

        with self.assertRaises(ValueError):
            await BatchDetectService._get_initialized_detector(EntityDetectionEngine.PRESIDIO)
