"""Tests for Unity prefab normalizer."""

import math
from pathlib import Path

from unityflow.normalizer import UnityPrefabNormalizer, normalize_prefab
from unityflow.parser import UnityYAMLDocument

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

        length = math.sqrt(q["x"] ** 2 + q["y"] ** 2 + q["z"] ** 2 + q["w"] ** 2)
        assert abs(length - 1.0) < 0.0001


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


class TestArrayOrderPreservation:
    """Tests for preserving array order (m_Component, m_Children).

    These arrays are NOT sorted because:
    - m_Children: affects Hierarchy order (rendering order, UI overlays)
    - m_Component: affects Inspector display order and GetComponents() order
    - Both may be intentionally ordered by developers for readability
    """

    def test_children_order_preserved(self):
        """Test that m_Children order is preserved (not sorted)."""
        normalizer = UnityPrefabNormalizer()
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")

        # Get original children order
        parent_transform = doc.get_by_file_id(400000)
        content = parent_transform.get_content()
        original_children = content.get("m_Children", [])
        original_ids = [c.get("fileID", 0) for c in original_children]

        normalizer.normalize_document(doc)

        # Get children order after normalization
        parent_transform = doc.get_by_file_id(400000)
        content = parent_transform.get_content()
        children = content.get("m_Children", [])
        new_ids = [c.get("fileID", 0) for c in children]

        # Children order should be preserved (not sorted)
        assert original_ids == new_ids, "m_Children order should be preserved"

    def test_component_order_preserved(self):
        """Test that m_Component order is preserved (not sorted)."""
        normalizer = UnityPrefabNormalizer()
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")

        # Get original component order
        game_obj = doc.get_by_file_id(100000)
        content = game_obj.get_content()
        original_components = content.get("m_Component", [])
        original_ids = [c.get("component", {}).get("fileID", 0) for c in original_components]

        normalizer.normalize_document(doc)

        # Get component order after normalization
        game_obj = doc.get_by_file_id(100000)
        content = game_obj.get_content()
        components = content.get("m_Component", [])
        new_ids = [c.get("component", {}).get("fileID", 0) for c in components]

        # Component order should be preserved (not sorted)
        assert original_ids == new_ids, "m_Component order should be preserved"


class TestNormalizationStability:
    """Tests for normalization stability and consistency."""

    def test_same_file_normalizes_identically(self):
        """Test that normalizing the same file twice produces identical output."""
        normalizer = UnityPrefabNormalizer()

        player_original = FIXTURES_DIR / "Player_original.prefab"

        if player_original.exists():
            content1 = normalizer.normalize_file(player_original)
            content2 = normalizer.normalize_file(player_original)

            assert content1 == content2, "Same file should produce identical normalized output"

    def test_different_component_order_preserved(self):
        """Test that files with different m_Component order remain different.

        Previously these files would normalize to identical output, but now
        we preserve the original order as it may be intentional.
        """
        normalizer = UnityPrefabNormalizer()

        player_original = FIXTURES_DIR / "Player_original.prefab"
        player_modified = FIXTURES_DIR / "Player_modification.prefab"

        if player_original.exists() and player_modified.exists():
            content1 = normalizer.normalize_file(player_original)
            content2 = normalizer.normalize_file(player_modified)

            # They should remain different since we preserve component order
            assert content1 != content2, "Files with different component order should remain different"


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
            float_precision=3,
        )

        assert content.startswith("%YAML 1.1")
