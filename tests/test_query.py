"""Tests for path-based query and surgical editing."""

from pathlib import Path

import pytest

from unityflow.parser import UnityYAMLDocument
from unityflow.query import get_value, merge_values, query_path, set_value

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestQueryPath:
    """Tests for path-based querying."""

    def test_query_gameobject_names(self):
        """Test querying all GameObject names."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        results = query_path(doc, "gameObjects/*/name")

        assert len(results) == 1
        assert results[0].value == "BasicPrefab"

    def test_query_component_types(self):
        """Test querying all component types."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        results = query_path(doc, "components/*/type")

        assert len(results) == 1
        assert results[0].value == "Transform"

    def test_query_specific_object(self):
        """Test querying a specific object by ID."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        results = query_path(doc, "gameObjects/100000/name")

        assert len(results) == 1
        assert results[0].value == "BasicPrefab"

    def test_query_nested_property(self):
        """Test querying a nested property."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        results = query_path(doc, "components/400000/localPosition")

        assert len(results) == 1
        pos = results[0].value
        assert "x" in pos
        assert "y" in pos
        assert "z" in pos

    def test_query_nonexistent_path(self):
        """Test querying a path that doesn't exist."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        results = query_path(doc, "gameObjects/999999/name")

        assert len(results) == 0

    def test_query_all_positions(self):
        """Test querying all positions."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")
        results = query_path(doc, "components/*/localPosition")

        # Should have 2 transforms with positions
        assert len(results) == 2


class TestSetValue:
    """Tests for surgical editing."""

    def test_set_simple_value(self):
        """Test setting a simple value."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        # Set new value
        result = set_value(doc, "gameObjects/100000/m_Name", "NewName")

        assert result is True
        go = doc.get_by_file_id(100000)
        assert go.get_content()["m_Name"] == "NewName"

    def test_set_vector_value(self):
        """Test setting a vector value."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        new_pos = {"x": 10.0, "y": 20.0, "z": 30.0}
        result = set_value(doc, "components/400000/m_LocalPosition", new_pos)

        assert result is True

        transform = doc.get_by_file_id(400000)
        pos = transform.get_content()["m_LocalPosition"]
        assert pos["x"] == 10.0
        assert pos["y"] == 20.0
        assert pos["z"] == 30.0

    def test_set_nonexistent_path(self):
        """Test setting a value at nonexistent path."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        result = set_value(doc, "components/999999/localPosition", {"x": 0, "y": 0, "z": 0})

        assert result is False

    def test_set_invalid_path(self):
        """Test setting with invalid path format."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        result = set_value(doc, "invalid", "value")

        assert result is False


class TestGetValue:
    """Tests for get_value convenience function."""

    def test_get_existing_value(self):
        """Test getting an existing value."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        value = get_value(doc, "gameObjects/100000/name")

        assert value == "BasicPrefab"

    def test_get_nonexistent_value(self):
        """Test getting a nonexistent value."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        value = get_value(doc, "gameObjects/999999/name")

        assert value is None


class TestQueryPlayerPrefab:
    """Tests using the Player prefab if available."""

    @pytest.fixture
    def player_doc(self):
        """Load Player prefab if available."""
        player_path = FIXTURES_DIR / "Player_original.prefab"
        if not player_path.exists():
            pytest.skip("Player prefab not available")
        return UnityYAMLDocument.load(player_path)

    def test_query_all_names(self, player_doc):
        """Test querying all GameObject names."""
        results = query_path(player_doc, "gameObjects/*/name")

        assert len(results) > 10  # Player has many objects
        names = [r.value for r in results]
        assert "Player" in names

    def test_query_component_count(self, player_doc):
        """Test counting components by type."""
        results = query_path(player_doc, "components/*/type")

        types = [r.value for r in results]
        assert "Transform" in types
        assert "SpriteRenderer" in types


class TestSetValueCreate:
    """Tests for set_value with create=True option."""

    def test_create_new_field(self):
        """Test creating a new field that doesn't exist."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        # Create a new field
        result = set_value(
            doc,
            "components/400000/newField",
            {"fileID": 123, "guid": "abc", "type": 3},
            create=True,
        )

        assert result is True

        transform = doc.get_by_file_id(400000)
        assert "newField" in transform.get_content()
        assert transform.get_content()["newField"]["fileID"] == 123

    def test_create_fails_without_flag(self):
        """Test that creating a new field fails without create=True."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        result = set_value(
            doc,
            "components/400000/nonExistentField",
            {"value": 123},
            create=False,
        )

        assert result is False

    def test_update_existing_with_create(self):
        """Test that create=True still updates existing fields."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        new_pos = {"x": 99.0, "y": 88.0, "z": 77.0}
        result = set_value(
            doc,
            "components/400000/m_LocalPosition",
            new_pos,
            create=True,
        )

        assert result is True

        transform = doc.get_by_file_id(400000)
        pos = transform.get_content()["m_LocalPosition"]
        assert pos["x"] == 99.0
        assert pos["y"] == 88.0
        assert pos["z"] == 77.0

    def test_create_intermediate_path(self):
        """Test creating intermediate dicts in the path."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        result = set_value(
            doc,
            "components/400000/nested/deep/value",
            123,
            create=True,
        )

        assert result is True

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        assert "nested" in content
        assert "deep" in content["nested"]
        assert content["nested"]["deep"]["value"] == 123


class TestMergeValues:
    """Tests for merge_values function."""

    def test_merge_multiple_fields(self):
        """Test merging multiple new fields."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        updated, created = merge_values(
            doc,
            "components/400000",
            {
                "portalAPrefab": {"fileID": 123, "guid": "abc", "type": 3},
                "portalBPrefab": {"fileID": 456, "guid": "def", "type": 3},
                "rotationStep": 15,
            },
        )

        assert created == 3
        assert updated == 0

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        assert content["portalAPrefab"]["fileID"] == 123
        assert content["portalBPrefab"]["guid"] == "def"
        assert content["rotationStep"] == 15

    def test_merge_update_existing(self):
        """Test merging with existing fields."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        updated, created = merge_values(
            doc,
            "components/400000",
            {
                "m_LocalPosition": {"x": 10.0, "y": 20.0, "z": 30.0},
                "newField": "new_value",
            },
        )

        assert updated == 1  # m_LocalPosition updated
        assert created == 1  # newField created

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        assert content["m_LocalPosition"]["x"] == 10.0
        assert content["newField"] == "new_value"

    def test_merge_no_create(self):
        """Test merging with create=False only updates existing fields."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        updated, created = merge_values(
            doc,
            "components/400000",
            {
                "m_LocalPosition": {"x": 5.0, "y": 5.0, "z": 5.0},
                "nonExistentField": "should_not_create",
            },
            create=False,
        )

        assert updated == 1
        assert created == 0

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        assert content["m_LocalPosition"]["x"] == 5.0
        assert "nonExistentField" not in content

    def test_merge_invalid_path(self):
        """Test merging to invalid path returns zeros."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        updated, created = merge_values(
            doc,
            "components/999999",
            {"field": "value"},
        )

        assert updated == 0
        assert created == 0

    def test_merge_creates_intermediate_path(self):
        """Test that merge creates intermediate paths when needed."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        updated, created = merge_values(
            doc,
            "components/400000/customData",
            {
                "key1": "value1",
                "key2": 42,
            },
            create=True,
        )

        assert created == 2

        transform = doc.get_by_file_id(400000)
        content = transform.get_content()
        assert "customData" in content
        assert content["customData"]["key1"] == "value1"
        assert content["customData"]["key2"] == 42
