"""Tests for LLM-friendly format conversion."""

import json
from pathlib import Path

import pytest

from prefab_tool.formats import (
    export_to_json,
    export_file_to_json,
    get_summary,
    PrefabJSON,
)
from prefab_tool.parser import UnityYAMLDocument

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestExportToJSON:
    """Tests for JSON export functionality."""

    def test_export_basic_prefab(self):
        """Test exporting a basic prefab to JSON."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        result = export_to_json(doc)

        assert "100000" in result.game_objects
        assert "400000" in result.components

        # Check GameObject structure
        go = result.game_objects["100000"]
        assert go["name"] == "BasicPrefab"
        assert go["layer"] == 0
        assert "components" in go

        # Check Transform structure
        transform = result.components["400000"]
        assert transform["type"] == "Transform"
        assert "localPosition" in transform
        assert "localRotation" in transform
        assert "localScale" in transform

    def test_export_with_raw_fields(self):
        """Test that raw fields are preserved."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        result = export_to_json(doc, include_raw=True)

        assert result.raw_fields  # Should have some raw fields

    def test_export_without_raw_fields(self):
        """Test export without raw fields."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        result = export_to_json(doc, include_raw=False)

        assert not result.raw_fields

    def test_to_json_string(self):
        """Test converting to JSON string."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        result = export_to_json(doc)

        json_str = result.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "prefabMetadata" in parsed
        assert "gameObjects" in parsed
        assert "components" in parsed


class TestExportFileToJSON:
    """Tests for file-based JSON export."""

    def test_export_to_file(self, tmp_path):
        """Test exporting to a file."""
        output_path = tmp_path / "output.json"

        export_file_to_json(
            FIXTURES_DIR / "basic_prefab.prefab",
            output_path=output_path,
        )

        assert output_path.exists()

        # Verify content
        content = json.loads(output_path.read_text())
        assert "gameObjects" in content


class TestPrefabJSON:
    """Tests for PrefabJSON dataclass."""

    def test_from_dict(self):
        """Test creating PrefabJSON from dict."""
        data = {
            "prefabMetadata": {"objectCount": 2},
            "gameObjects": {"1": {"name": "Test"}},
            "components": {"2": {"type": "Transform"}},
            "_rawFields": {"1": {"extra": "data"}},
        }

        result = PrefabJSON.from_dict(data)

        assert result.metadata["objectCount"] == 2
        assert result.game_objects["1"]["name"] == "Test"
        assert result.components["2"]["type"] == "Transform"
        assert result.raw_fields["1"]["extra"] == "data"

    def test_from_json(self):
        """Test creating PrefabJSON from JSON string."""
        json_str = '{"prefabMetadata": {}, "gameObjects": {"1": {"name": "X"}}, "components": {}}'

        result = PrefabJSON.from_json(json_str)

        assert result.game_objects["1"]["name"] == "X"


class TestGetSummary:
    """Tests for document summary generation."""

    def test_summary_basic(self):
        """Test summary of basic prefab."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        summary = get_summary(doc)

        s = summary["summary"]
        assert s["totalGameObjects"] == 1
        assert s["totalComponents"] == 1
        assert "Transform" in s["typeCounts"]

    def test_summary_hierarchy(self):
        """Test hierarchy in summary."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")
        summary = get_summary(doc)

        s = summary["summary"]
        assert len(s["hierarchy"]) > 0

    def test_summary_player_prefab(self):
        """Test summary of complex prefab."""
        player_path = FIXTURES_DIR / "Player_original.prefab"
        if not player_path.exists():
            pytest.skip("Player prefab not available")

        doc = UnityYAMLDocument.load(player_path)
        summary = get_summary(doc)

        s = summary["summary"]
        assert s["totalGameObjects"] > 0
        assert s["totalComponents"] > 0
