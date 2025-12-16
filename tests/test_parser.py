"""Tests for Unity YAML parser."""

from pathlib import Path

import pytest

from unityflow.parser import (
    UnityYAMLDocument,
    UnityYAMLObject,
    CLASS_IDS,
    parse_file_reference,
    create_file_reference,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestUnityYAMLDocument:
    """Tests for UnityYAMLDocument class."""

    def test_load_basic_prefab(self):
        """Test loading a basic prefab file."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        assert len(doc.objects) == 2
        assert doc.source_path == FIXTURES_DIR / "basic_prefab.prefab"

    def test_parse_document_headers(self):
        """Test that document headers are parsed correctly."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        # Check GameObject
        game_obj = doc.get_by_file_id(100000)
        assert game_obj is not None
        assert game_obj.class_id == 1
        assert game_obj.class_name == "GameObject"

        # Check Transform
        transform = doc.get_by_file_id(400000)
        assert transform is not None
        assert transform.class_id == 4
        assert transform.class_name == "Transform"

    def test_get_by_class_id(self):
        """Test filtering objects by class ID."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "unsorted_prefab.prefab")

        game_objects = doc.get_by_class_id(1)
        assert len(game_objects) == 2

        transforms = doc.get_by_class_id(4)
        assert len(transforms) == 2

    def test_get_game_objects(self):
        """Test convenience method for getting GameObjects."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        game_objects = doc.get_game_objects()
        assert len(game_objects) == 1
        assert game_objects[0].class_id == 1

    def test_get_transforms(self):
        """Test convenience method for getting Transforms."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        transforms = doc.get_transforms()
        assert len(transforms) == 1
        assert transforms[0].class_id == 4

    def test_iteration(self):
        """Test iterating over document objects."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        objects = list(doc)
        assert len(objects) == 2
        assert all(isinstance(obj, UnityYAMLObject) for obj in objects)

    def test_parse_content(self):
        """Test parsing YAML content from string."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &12345
GameObject:
  m_Name: TestObject
"""
        doc = UnityYAMLDocument.parse(content)

        assert len(doc.objects) == 1
        assert doc.objects[0].file_id == 12345
        assert doc.objects[0].class_id == 1

    def test_dump_roundtrip(self):
        """Test that dump produces valid output."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        content = doc.dump()

        # Should start with Unity header
        assert content.startswith("%YAML 1.1")
        assert "!u!" in content

        # Should be parseable again
        doc2 = UnityYAMLDocument.parse(content)
        assert len(doc2.objects) == len(doc.objects)


class TestUnityYAMLObject:
    """Tests for UnityYAMLObject class."""

    def test_root_key(self):
        """Test getting the root key of an object."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        game_obj = doc.get_by_file_id(100000)
        assert game_obj.root_key == "GameObject"

        transform = doc.get_by_file_id(400000)
        assert transform.root_key == "Transform"

    def test_get_content(self):
        """Test getting the content under root key."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        game_obj = doc.get_by_file_id(100000)
        content = game_obj.get_content()

        assert content is not None
        assert content["m_Name"] == "BasicPrefab"

    def test_class_name_unknown(self):
        """Test class name for unknown class IDs."""
        obj = UnityYAMLObject(class_id=99999, file_id=1, data={})
        assert "Unknown" in obj.class_name


class TestFileReference:
    """Tests for file reference utilities."""

    def test_parse_internal_reference(self):
        """Test parsing an internal file reference."""
        ref = {"fileID": 12345}
        result = parse_file_reference(ref)

        assert result == (12345, None, None)

    def test_parse_external_reference(self):
        """Test parsing an external file reference with GUID."""
        ref = {"fileID": 11500000, "guid": "abc123", "type": 3}
        result = parse_file_reference(ref)

        assert result == (11500000, "abc123", 3)

    def test_parse_null_reference(self):
        """Test parsing a null reference."""
        result = parse_file_reference(None)
        assert result is None

    def test_create_internal_reference(self):
        """Test creating an internal file reference."""
        ref = create_file_reference(12345)

        assert ref["fileID"] == 12345
        assert "guid" not in ref
        assert "type" not in ref

    def test_create_external_reference(self):
        """Test creating an external file reference."""
        ref = create_file_reference(11500000, guid="abc123", ref_type=3)

        assert ref["fileID"] == 11500000
        assert ref["guid"] == "abc123"
        assert ref["type"] == 3


class TestScalarFormatting:
    """Tests for YAML scalar formatting."""

    def test_standalone_dash_is_quoted(self):
        """Test that standalone '-' is quoted to prevent YAML null interpretation."""
        from prefab_tool.fast_parser import _format_scalar

        result = _format_scalar("-")
        assert result == "'-'", "Standalone '-' must be quoted"

    def test_standalone_tilde_is_quoted(self):
        """Test that standalone '~' is quoted to prevent YAML null interpretation."""
        from prefab_tool.fast_parser import _format_scalar

        result = _format_scalar("~")
        assert result == "'~'", "Standalone '~' must be quoted"

    def test_dash_with_space_is_quoted(self):
        """Test that '- ' prefix is quoted to prevent list item interpretation."""
        from prefab_tool.fast_parser import _format_scalar

        result = _format_scalar("- test")
        assert result.startswith("'"), "'- ' prefixed strings must be quoted"

    def test_normal_strings_not_quoted(self):
        """Test that normal strings are not unnecessarily quoted."""
        from prefab_tool.fast_parser import _format_scalar

        assert _format_scalar("hello") == "hello"
        assert _format_scalar("test_value") == "test_value"

    def test_roundtrip_dash_string(self):
        """Test that '-' string survives a parse-dump roundtrip."""
        content = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &12345
MonoBehaviour:
  m_SomeField: '-'
"""
        doc = UnityYAMLDocument.parse(content)
        obj = doc.get_by_file_id(12345)
        content_data = obj.get_content()

        # The value should be preserved as string "-"
        assert content_data["m_SomeField"] == "-", "'-' value should be preserved as string"

        # Dump and parse again
        dumped = doc.dump()
        doc2 = UnityYAMLDocument.parse(dumped)
        obj2 = doc2.get_by_file_id(12345)
        content_data2 = obj2.get_content()

        assert content_data2["m_SomeField"] == "-", "'-' value should survive roundtrip"
