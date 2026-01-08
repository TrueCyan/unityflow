"""Tests for LLM-friendly format conversion."""

import json
from pathlib import Path

import pytest

from unityflow.formats import (
    PrefabJSON,
    export_file_to_json,
    export_to_json,
    get_summary,
    import_file_from_json,
    import_from_json,
)
from unityflow.parser import UnityYAMLDocument

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
        assert "metadata" in parsed
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
            "metadata": {"objectCount": 2},
            "gameObjects": {"1": {"name": "Test"}},
            "components": {"2": {"type": "Transform"}},
            "_rawFields": {"1": {"extra": "data"}},
        }

        result = PrefabJSON.from_dict(data)

        assert result.metadata["objectCount"] == 2
        assert result.game_objects["1"]["name"] == "Test"
        assert result.components["2"]["type"] == "Transform"
        assert result.raw_fields["1"]["extra"] == "data"

    def test_from_dict_legacy_key(self):
        """Test creating PrefabJSON from dict with legacy prefabMetadata key."""
        data = {
            "prefabMetadata": {"objectCount": 2},
            "gameObjects": {"1": {"name": "Test"}},
            "components": {"2": {"type": "Transform"}},
        }

        result = PrefabJSON.from_dict(data)

        assert result.metadata["objectCount"] == 2

    def test_from_json(self):
        """Test creating PrefabJSON from JSON string."""
        json_str = '{"metadata": {}, "gameObjects": {"1": {"name": "X"}}, "components": {}}'

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


class TestImportFromJSON:
    """Tests for JSON import functionality."""

    def test_import_basic_prefab(self):
        """Test importing a basic prefab from JSON."""
        # First export, then import
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        prefab_json = export_to_json(doc, include_raw=True)

        # Import back
        imported_doc = import_from_json(prefab_json)

        # Verify structure
        assert len(imported_doc.objects) == len(doc.objects)

        # Verify GameObject
        go = imported_doc.get_by_file_id(100000)
        assert go is not None
        assert go.class_id == 1
        content = go.get_content()
        assert content["m_Name"] == "BasicPrefab"
        assert content["m_Layer"] == 0
        assert content["m_IsActive"] == 1

        # Verify Transform
        transform = imported_doc.get_by_file_id(400000)
        assert transform is not None
        assert transform.class_id == 4
        t_content = transform.get_content()
        assert "m_LocalPosition" in t_content
        assert "m_LocalRotation" in t_content
        assert "m_LocalScale" in t_content

    def test_import_preserves_raw_fields(self):
        """Test that raw fields are preserved during import."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        prefab_json = export_to_json(doc, include_raw=True)

        imported_doc = import_from_json(prefab_json)

        # Check raw fields like m_ObjectHideFlags are preserved
        go = imported_doc.get_by_file_id(100000)
        content = go.get_content()
        assert "m_ObjectHideFlags" in content
        assert content["m_ObjectHideFlags"] == 0

    def test_import_hierarchy(self):
        """Test importing a prefab with parent-child hierarchy."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")
        prefab_json = export_to_json(doc, include_raw=True)

        imported_doc = import_from_json(prefab_json)

        # Verify parent transform has children
        parent_transform = imported_doc.get_by_file_id(400000)
        assert parent_transform is not None
        p_content = parent_transform.get_content()
        assert len(p_content["m_Children"]) > 0

        # Verify child transform has parent
        child_transform = imported_doc.get_by_file_id(400002)
        assert child_transform is not None
        c_content = child_transform.get_content()
        assert c_content["m_Father"]["fileID"] == 400000

    def test_roundtrip_yaml_json_yaml(self):
        """Test round-trip conversion: YAML -> JSON -> YAML."""
        original_doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        # Export to JSON
        prefab_json = export_to_json(original_doc, include_raw=True)

        # Import back
        imported_doc = import_from_json(prefab_json)

        # Dump both to YAML and compare structure
        # Note: We compare semantically, not byte-for-byte
        assert len(imported_doc.objects) == len(original_doc.objects)

        for orig_obj in original_doc.objects:
            imported_obj = imported_doc.get_by_file_id(orig_obj.file_id)
            assert imported_obj is not None
            assert imported_obj.class_id == orig_obj.class_id

            orig_content = orig_obj.get_content()
            imp_content = imported_obj.get_content()

            # Compare key fields
            if orig_obj.class_id == 1:  # GameObject
                assert imp_content["m_Name"] == orig_content["m_Name"]
                assert imp_content["m_Layer"] == orig_content["m_Layer"]
                assert imp_content["m_IsActive"] == orig_content["m_IsActive"]
            elif orig_obj.class_id == 4:  # Transform
                assert imp_content["m_LocalPosition"] == orig_content["m_LocalPosition"]
                assert imp_content["m_LocalRotation"] == orig_content["m_LocalRotation"]
                assert imp_content["m_LocalScale"] == orig_content["m_LocalScale"]

    def test_import_modified_json(self):
        """Test importing JSON that was modified."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        prefab_json = export_to_json(doc, include_raw=True)

        # Modify the JSON
        prefab_json.game_objects["100000"]["name"] = "ModifiedName"
        prefab_json.components["400000"]["localPosition"]["y"] = 5.0

        # Import back
        imported_doc = import_from_json(prefab_json)

        # Verify modifications
        go = imported_doc.get_by_file_id(100000)
        content = go.get_content()
        assert content["m_Name"] == "ModifiedName"

        transform = imported_doc.get_by_file_id(400000)
        t_content = transform.get_content()
        assert t_content["m_LocalPosition"]["y"] == 5.0


class TestImportFileFromJSON:
    """Tests for file-based JSON import."""

    def test_import_from_file(self, tmp_path):
        """Test importing from a JSON file."""
        # First export to JSON file
        json_path = tmp_path / "test.json"
        output_path = tmp_path / "output.prefab"

        export_file_to_json(
            FIXTURES_DIR / "basic_prefab.prefab",
            output_path=json_path,
        )

        # Import back
        doc = import_file_from_json(json_path, output_path=output_path)

        assert output_path.exists()
        assert len(doc.objects) == 2  # 1 GameObject + 1 Transform

        # Verify the output file is valid YAML
        reloaded = UnityYAMLDocument.load(output_path)
        assert len(reloaded.objects) == 2

    def test_import_returns_document(self, tmp_path):
        """Test that import returns a valid document without saving."""
        json_path = tmp_path / "test.json"

        export_file_to_json(
            FIXTURES_DIR / "basic_prefab.prefab",
            output_path=json_path,
        )

        # Import without output path
        doc = import_file_from_json(json_path)

        assert doc is not None
        assert len(doc.objects) == 2


class TestRoundTripIntegrity:
    """Tests for round-trip conversion integrity."""

    def test_roundtrip_unsorted_prefab(self):
        """Test round-trip with unsorted prefab (hierarchy test)."""
        original = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")

        # Round-trip
        json_data = export_to_json(original, include_raw=True)
        imported = import_from_json(json_data)

        # Same number of objects
        assert len(imported.objects) == len(original.objects)

        # All file IDs present
        original_ids = {obj.file_id for obj in original.objects}
        imported_ids = {obj.file_id for obj in imported.objects}
        assert original_ids == imported_ids

    def test_roundtrip_preserves_component_order(self):
        """Test that component references are preserved."""
        original = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        json_data = export_to_json(original, include_raw=True)
        imported = import_from_json(json_data)

        orig_go = original.get_by_file_id(100000)
        imp_go = imported.get_by_file_id(100000)

        orig_components = orig_go.get_content()["m_Component"]
        imp_components = imp_go.get_content()["m_Component"]

        assert len(orig_components) == len(imp_components)
        for i, orig_comp in enumerate(orig_components):
            assert orig_comp["component"]["fileID"] == imp_components[i]["component"]["fileID"]

    def test_multiple_roundtrips(self):
        """Test that multiple round-trips produce consistent results."""
        original = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        # First round-trip
        json1 = export_to_json(original, include_raw=True)
        imported1 = import_from_json(json1)

        # Second round-trip
        json2 = export_to_json(imported1, include_raw=True)
        imported2 = import_from_json(json2)

        # Third round-trip
        json3 = export_to_json(imported2, include_raw=True)

        # JSON should be stable after first round-trip
        assert json2.to_json() == json3.to_json()

    def test_roundtrip_preserves_builtin_guids(self, tmp_path):
        """Test that Unity built-in resource GUIDs are preserved during round-trip.

        Unity uses special GUIDs for built-in resources:
        - 0000000000000000e000000000000000: Built-in Extra Resources
        - 0000000000000000f000000000000000: Built-in Default Resources

        These GUIDs look like scientific notation (e.g., 0e000... = 0.0) and
        must not be parsed as floats.
        """
        # Create a scene file with built-in resource references
        scene_yaml = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!104 &2
RenderSettings:
  m_ObjectHideFlags: 0
  m_SpotCookie: {fileID: 10001, guid: 0000000000000000e000000000000000, type: 0}
  m_HaloTexture: {fileID: 10010, guid: 0000000000000000e000000000000000, type: 0}
  m_LightingDataAsset: {fileID: 20201, guid: 0000000000000000f000000000000000, type: 0}
"""
        scene_path = tmp_path / "test.unity"
        scene_path.write_text(scene_yaml)

        # Load and export to JSON
        doc = UnityYAMLDocument.load(scene_path)
        json_data = export_to_json(doc, include_raw=True)

        # Import back from JSON
        imported = import_from_json(json_data)

        # Get the RenderSettings object
        render_settings = imported.get_by_file_id(2)
        assert render_settings is not None

        content = render_settings.get_content()

        # Verify built-in GUIDs are preserved
        assert content["m_SpotCookie"]["guid"] == "0000000000000000e000000000000000"
        assert content["m_SpotCookie"]["fileID"] == 10001
        assert content["m_SpotCookie"]["type"] == 0

        assert content["m_HaloTexture"]["guid"] == "0000000000000000e000000000000000"
        assert content["m_HaloTexture"]["fileID"] == 10010

        assert content["m_LightingDataAsset"]["guid"] == "0000000000000000f000000000000000"
        assert content["m_LightingDataAsset"]["fileID"] == 20201
