import unittest

from backend.app.entity_detection.engines import EntityDetectionEngine


class TestEntityDetectionEngine(unittest.TestCase):

    # Ensure all expected members exist and values are unique
    def test_enum_members_existence_and_uniqueness(self):
        self.assertIn(EntityDetectionEngine.PRESIDIO, EntityDetectionEngine)

        self.assertIn(EntityDetectionEngine.GEMINI, EntityDetectionEngine)

        self.assertIn(EntityDetectionEngine.GLINER, EntityDetectionEngine)

        self.assertIn(EntityDetectionEngine.HIDEME, EntityDetectionEngine)

        self.assertIn(EntityDetectionEngine.HYBRID, EntityDetectionEngine)

        values = [member.value for member in EntityDetectionEngine]

        self.assertEqual(len(values), len(set(values)), "Enum values are not unique")

    # Verify each member is instance of the enum
    def test_enum_member_types(self):
        for member in EntityDetectionEngine:
            self.assertIsInstance(member, EntityDetectionEngine)

    # Access members by name correctly
    def test_enum_name_access(self):
        self.assertEqual(
            EntityDetectionEngine["PRESIDIO"], EntityDetectionEngine.PRESIDIO
        )

        self.assertEqual(EntityDetectionEngine["GEMINI"], EntityDetectionEngine.GEMINI)

    # Invalid name access raises KeyError
    def test_enum_invalid_name_access_raises(self):
        with self.assertRaises(KeyError):
            _ = EntityDetectionEngine["INVALID_ENGINE"]

    # Iterating over enum yields all members
    def test_enum_iteration(self):
        members = list(EntityDetectionEngine)

        self.assertEqual(len(members), 5)

        self.assertIn(EntityDetectionEngine.HYBRID, members)

    # Auto-assigned values are sequential integers
    def test_enum_auto_assignment(self):
        expected_values = list(range(1, 6))

        actual_values = [engine.value for engine in EntityDetectionEngine]

        self.assertEqual(actual_values, expected_values)
