"""Tests for path-based query and surgical editing."""

from pathlib import Path

import pytest

from prefab_tool.query import query_path, set_value, get_value
from prefab_tool.parser import UnityYAMLDocument

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

        # Get original value
        go = doc.get_by_file_id(100000)
        original_name = go.get_content()["m_Name"]

        # Set new value
        result = set_value(doc, "gameObjects/100000/m_Name", "NewName")

        assert result is True
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
