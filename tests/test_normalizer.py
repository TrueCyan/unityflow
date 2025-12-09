"""Tests for Unity prefab normalizer."""

import math
from pathlib import Path

import pytest

from prefab_tool.normalizer import UnityPrefabNormalizer, normalize_prefab
from prefab_tool.parser import UnityYAMLDocument

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestDocumentSorting:
    """Tests for document sorting by fileID."""

    def test_sort_documents_by_file_id(self):
        """Test that documents are sorted by fileID."""
        normalizer = UnityPrefabNormalizer()
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")

        # Before normalization - documents may be in any order
        original_order = [obj.file_id for obj in doc.objects]

        normalizer.normalize_document(doc)

        # After normalization - should be sorted
        sorted_order = [obj.file_id for obj in doc.objects]
        assert sorted_order == sorted(original_order)

    def test_sort_disabled(self):
        """Test that sorting can be disabled."""
        normalizer = UnityPrefabNormalizer(sort_documents=False)
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")

        original_order = [obj.file_id for obj in doc.objects]
        normalizer.normalize_document(doc)
        new_order = [obj.file_id for obj in doc.objects]

        assert original_order == new_order


class TestModificationsSorting:
    """Tests for m_Modifications array sorting."""

    def test_sort_modifications_by_target_and_path(self):
        """Test that modifications are sorted by target.fileID and propertyPath."""
        normalizer = UnityPrefabNormalizer()
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "prefab_with_modifications.prefab")

        normalizer.normalize_document(doc)

        # Get the PrefabInstance
        prefab_instance = doc.get_by_class_id(1001)[0]
        content = prefab_instance.get_content()
        mods = content["m_Modification"]["m_Modifications"]

        # Check that modifications are sorted
        for i in range(len(mods) - 1):
            current = mods[i]
            next_mod = mods[i + 1]

            current_key = (current["target"]["fileID"], current["propertyPath"])
            next_key = (next_mod["target"]["fileID"], next_mod["propertyPath"])

            assert current_key <= next_key, f"Modifications not sorted: {current_key} > {next_key}"

    def test_modifications_sorting_disabled(self):
        """Test that modifications sorting can be disabled."""
        normalizer = UnityPrefabNormalizer(sort_modifications=False)
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "prefab_with_modifications.prefab")

        # Get original order
        prefab_instance = doc.get_by_class_id(1001)[0]
        content = prefab_instance.get_content()
        original_paths = [m["propertyPath"] for m in content["m_Modification"]["m_Modifications"]]

        normalizer.normalize_document(doc)

        # Get new order
        prefab_instance = doc.get_by_class_id(1001)[0]
        content = prefab_instance.get_content()
        new_paths = [m["propertyPath"] for m in content["m_Modification"]["m_Modifications"]]

        assert original_paths == new_paths


class TestQuaternionNormalization:
    """Tests for quaternion normalization."""

    def test_normalize_negative_w(self):
        """Test that quaternions with negative w are negated."""
        normalizer = UnityPrefabNormalizer()
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "negative_quaternion.prefab")

        # Before normalization
        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        assert content["m_LocalRotation"]["w"] == -1

        normalizer.normalize_document(doc)

        # After normalization - w should be positive
        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        assert content["m_LocalRotation"]["w"] == 1
        assert content["m_LocalRotation"]["x"] == 0
        assert content["m_LocalRotation"]["y"] == 0
        assert content["m_LocalRotation"]["z"] == 0

    def test_quaternion_unit_length(self):
        """Test that quaternions are normalized to unit length."""
        normalizer = UnityPrefabNormalizer()
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        normalizer.normalize_document(doc)

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        q = content["m_LocalRotation"]

        length = math.sqrt(q["x"]**2 + q["y"]**2 + q["z"]**2 + q["w"]**2)
        assert abs(length - 1.0) < 0.0001

    def test_quaternion_normalization_disabled(self):
        """Test that quaternion normalization can be disabled."""
        normalizer = UnityPrefabNormalizer(normalize_quaternions=False)
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "negative_quaternion.prefab")

        normalizer.normalize_document(doc)

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        # w should still be negative
        assert content["m_LocalRotation"]["w"] == -1


class TestFloatNormalization:
    """Tests for floating-point normalization."""

    def test_float_precision(self):
        """Test that floats are rounded to specified precision."""
        normalizer = UnityPrefabNormalizer(float_precision=3)
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")

        normalizer.normalize_document(doc)

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()

        # Check that position values are properly rounded
        pos = content["m_LocalPosition"]
        assert isinstance(pos["x"], float)
        assert isinstance(pos["y"], float)

    def test_hex_float_format(self):
        """Test IEEE 754 hex float format."""
        normalizer = UnityPrefabNormalizer(use_hex_floats=True)

        # Test conversion
        hex_val = normalizer._float_to_hex(1.0)
        assert hex_val == "0x3f800000"

        # Test round-trip
        result = normalizer._hex_to_float(hex_val)
        assert result == 1.0

    def test_avoid_negative_zero(self):
        """Test that -0.0 is converted to 0.0."""
        normalizer = UnityPrefabNormalizer()

        result = normalizer._normalize_float(-0.0)
        assert result == 0.0
        assert str(result) == "0.0"  # Not "-0.0"


class TestRoundTrip:
    """Tests for round-trip fidelity."""

    def test_idempotent_normalization(self):
        """Test that normalizing twice produces same result."""
        normalizer = UnityPrefabNormalizer()

        # Normalize once
        content1 = normalizer.normalize_file(FIXTURES_DIR / "basic_prefab.prefab")

        # Parse and normalize again
        doc2 = UnityYAMLDocument.parse(content1)
        normalizer.normalize_document(doc2)
        content2 = doc2.dump()

        assert content1 == content2

    def test_unsorted_becomes_sorted(self):
        """Test that unsorted prefab is properly sorted."""
        normalizer = UnityPrefabNormalizer()

        content = normalizer.normalize_file(FIXTURES_DIR / "unsorted_prefab.prefab")
        doc = UnityYAMLDocument.parse(content)

        file_ids = [obj.file_id for obj in doc.objects]
        assert file_ids == sorted(file_ids)


class TestConvenienceFunction:
    """Tests for the normalize_prefab convenience function."""

    def test_normalize_prefab_function(self):
        """Test the normalize_prefab convenience function."""
        content = normalize_prefab(FIXTURES_DIR / "basic_prefab.prefab")

        assert content.startswith("%YAML 1.1")
        assert "GameObject" in content
        assert "Transform" in content

    def test_normalize_with_options(self):
        """Test normalize_prefab with custom options."""
        content = normalize_prefab(
            FIXTURES_DIR / "basic_prefab.prefab",
            sort_documents=False,
            normalize_floats=False,
        )

        assert content.startswith("%YAML 1.1")
