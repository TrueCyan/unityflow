"""Tests for LLM helper functions - fileID generation, object creation, RectTransform utilities."""

from pathlib import Path

import pytest

from unityflow.formats import (
    RectTransformEditorValues,
    create_rect_transform_file_values,
    editor_to_file_values,
    export_to_json,
    file_to_editor_values,
    import_from_json,
)
from unityflow.parser import (
    UnityYAMLDocument,
    create_game_object,
    create_mono_behaviour,
    create_rect_transform,
    create_transform,
    generate_file_id,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestFileIDGeneration:
    """Tests for fileID generation."""

    def test_generate_file_id_unique(self):
        """Test that generated fileIDs are unique."""
        ids = set()
        for _ in range(100):
            new_id = generate_file_id()
            assert new_id not in ids
            ids.add(new_id)

    def test_generate_file_id_avoids_existing(self):
        """Test that generated fileID avoids existing IDs."""
        existing = {100000, 200000, 300000}
        for _ in range(10):
            new_id = generate_file_id(existing)
            assert new_id not in existing

    def test_generate_file_id_large_number(self):
        """Test that generated fileID is a large number (Unity convention)."""
        file_id = generate_file_id()
        assert file_id > 1000000  # Unity uses large numbers

    def test_document_generate_unique_file_id(self):
        """Test document's generate_unique_file_id method."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")
        existing_ids = doc.get_all_file_ids()

        new_id = doc.generate_unique_file_id()
        assert new_id not in existing_ids


class TestCreateGameObject:
    """Tests for create_game_object helper."""

    def test_create_basic_game_object(self):
        """Test creating a basic GameObject."""
        go = create_game_object("TestObject")

        assert go.class_id == 1
        assert go.class_name == "GameObject"

        content = go.get_content()
        assert content["m_Name"] == "TestObject"
        assert content["m_Layer"] == 0
        assert content["m_TagString"] == "Untagged"
        assert content["m_IsActive"] == 1

    def test_create_game_object_with_options(self):
        """Test creating a GameObject with custom options."""
        go = create_game_object(
            name="Player",
            file_id=12345,
            layer=5,
            tag="Player",
            is_active=False,
            components=[100, 200, 300],
        )

        assert go.file_id == 12345

        content = go.get_content()
        assert content["m_Name"] == "Player"
        assert content["m_Layer"] == 5
        assert content["m_TagString"] == "Player"
        assert content["m_IsActive"] == 0
        assert len(content["m_Component"]) == 3
        assert content["m_Component"][0]["component"]["fileID"] == 100


class TestCreateTransform:
    """Tests for create_transform helper."""

    def test_create_basic_transform(self):
        """Test creating a basic Transform."""
        transform = create_transform(game_object_id=100000)

        assert transform.class_id == 4
        assert transform.class_name == "Transform"

        content = transform.get_content()
        assert content["m_GameObject"]["fileID"] == 100000
        assert content["m_LocalPosition"] == {"x": 0, "y": 0, "z": 0}
        assert content["m_LocalRotation"] == {"x": 0, "y": 0, "z": 0, "w": 1}
        assert content["m_LocalScale"] == {"x": 1, "y": 1, "z": 1}
        assert content["m_Father"]["fileID"] == 0

    def test_create_transform_with_position(self):
        """Test creating a Transform with custom position."""
        transform = create_transform(
            game_object_id=100000,
            position={"x": 10, "y": 20, "z": 30},
            parent_id=500000,
        )

        content = transform.get_content()
        assert content["m_LocalPosition"] == {"x": 10, "y": 20, "z": 30}
        assert content["m_Father"]["fileID"] == 500000


class TestCreateRectTransform:
    """Tests for create_rect_transform helper."""

    def test_create_basic_rect_transform(self):
        """Test creating a basic RectTransform."""
        rt = create_rect_transform(game_object_id=100000)

        assert rt.class_id == 224
        assert rt.class_name == "RectTransform"

        content = rt.get_content()
        assert content["m_GameObject"]["fileID"] == 100000
        assert content["m_AnchorMin"] == {"x": 0.5, "y": 0.5}
        assert content["m_AnchorMax"] == {"x": 0.5, "y": 0.5}
        assert content["m_Pivot"] == {"x": 0.5, "y": 0.5}

    def test_create_rect_transform_stretch(self):
        """Test creating a RectTransform with stretch anchors."""
        rt = create_rect_transform(
            game_object_id=100000,
            anchor_min={"x": 0, "y": 0},
            anchor_max={"x": 1, "y": 1},
            anchored_position={"x": 0, "y": 0},
            size_delta={"x": 0, "y": 0},
        )

        content = rt.get_content()
        assert content["m_AnchorMin"] == {"x": 0, "y": 0}
        assert content["m_AnchorMax"] == {"x": 1, "y": 1}
        assert content["m_SizeDelta"] == {"x": 0, "y": 0}


class TestCreateMonoBehaviour:
    """Tests for create_mono_behaviour helper."""

    def test_create_basic_mono_behaviour(self):
        """Test creating a basic MonoBehaviour."""
        mb = create_mono_behaviour(
            game_object_id=100000,
            script_guid="abcd1234efgh5678",
        )

        assert mb.class_id == 114
        assert mb.class_name == "MonoBehaviour"

        content = mb.get_content()
        assert content["m_GameObject"]["fileID"] == 100000
        assert content["m_Script"]["guid"] == "abcd1234efgh5678"
        assert content["m_Script"]["type"] == 3
        assert content["m_Enabled"] == 1

    def test_create_mono_behaviour_with_properties(self):
        """Test creating a MonoBehaviour with custom properties."""
        mb = create_mono_behaviour(
            game_object_id=100000,
            script_guid="abcd1234efgh5678",
            properties={
                "speed": 10.5,
                "targetRef": {"fileID": 200000},
                "itemList": [1, 2, 3],
            },
        )

        content = mb.get_content()
        assert content["speed"] == 10.5
        assert content["targetRef"]["fileID"] == 200000
        assert content["itemList"] == [1, 2, 3]


class TestRectTransformEditorFileConversion:
    """Tests for RectTransform editor <-> file format conversion."""

    def test_anchored_mode_conversion(self):
        """Test conversion in anchored mode (fixed position and size)."""
        # Editor values: center anchor, pos (100, 50), size 200x100
        editor = RectTransformEditorValues(
            anchor_min_x=0.5,
            anchor_min_y=0.5,
            anchor_max_x=0.5,
            anchor_max_y=0.5,
            pivot_x=0.5,
            pivot_y=0.5,
            pos_x=100,
            pos_y=50,
            width=200,
            height=100,
        )

        # Convert to file values
        file_vals = editor_to_file_values(editor)

        assert file_vals.anchor_min == {"x": 0.5, "y": 0.5}
        assert file_vals.anchor_max == {"x": 0.5, "y": 0.5}
        assert file_vals.anchored_position == {"x": 100, "y": 50}
        assert file_vals.size_delta == {"x": 200, "y": 100}

        # Convert back to editor values
        editor_back = file_to_editor_values(file_vals)

        assert editor_back.pos_x == 100
        assert editor_back.pos_y == 50
        assert editor_back.width == 200
        assert editor_back.height == 100

    def test_stretch_mode_conversion(self):
        """Test conversion in full stretch mode."""
        # Editor values: full stretch, all offsets 0
        editor = RectTransformEditorValues(
            anchor_min_x=0,
            anchor_min_y=0,
            anchor_max_x=1,
            anchor_max_y=1,
            pivot_x=0.5,
            pivot_y=0.5,
            left=0,
            right=0,
            top=0,
            bottom=0,
        )

        # Convert to file values
        file_vals = editor_to_file_values(editor)

        assert file_vals.anchor_min == {"x": 0, "y": 0}
        assert file_vals.anchor_max == {"x": 1, "y": 1}
        assert file_vals.anchored_position == {"x": 0, "y": 0}
        assert file_vals.size_delta == {"x": 0, "y": 0}

        # Convert back to editor values
        editor_back = file_to_editor_values(file_vals)

        assert editor_back.left == 0
        assert editor_back.right == 0
        assert editor_back.top == 0
        assert editor_back.bottom == 0

    def test_stretch_with_offsets(self):
        """Test stretch mode with non-zero offsets."""
        # Editor values: stretch with 10px margins
        editor = RectTransformEditorValues(
            anchor_min_x=0,
            anchor_min_y=0,
            anchor_max_x=1,
            anchor_max_y=1,
            pivot_x=0.5,
            pivot_y=0.5,
            left=10,
            right=10,
            top=10,
            bottom=10,
        )

        file_vals = editor_to_file_values(editor)

        # With 10px margins on all sides:
        # offsetMin = (10, 10), offsetMax = (-10, -10)
        # anchoredPosition = (10 + (-10)) / 2 = 0, (10 + (-10)) / 2 = 0
        # sizeDelta = (-10 - 10) = -20, (-10 - 10) = -20
        assert file_vals.anchored_position == {"x": 0, "y": 0}
        assert file_vals.size_delta == {"x": -20, "y": -20}

        # Round-trip
        editor_back = file_to_editor_values(file_vals)
        assert editor_back.left == pytest.approx(10)
        assert editor_back.right == pytest.approx(10)
        assert editor_back.top == pytest.approx(10)
        assert editor_back.bottom == pytest.approx(10)

    def test_horizontal_stretch_vertical_anchored(self):
        """Test mixed mode: horizontal stretch, vertical anchored."""
        editor = RectTransformEditorValues(
            anchor_min_x=0,
            anchor_min_y=0.5,
            anchor_max_x=1,
            anchor_max_y=0.5,
            pivot_x=0.5,
            pivot_y=0.5,
            left=20,
            right=20,
            pos_y=0,
            height=50,
        )

        file_vals = editor_to_file_values(editor)

        # Horizontal: stretch with 20px margins
        # Vertical: anchored at center with height 50
        assert file_vals.anchor_min == {"x": 0, "y": 0.5}
        assert file_vals.anchor_max == {"x": 1, "y": 0.5}
        assert file_vals.size_delta["y"] == 50  # Height

        editor_back = file_to_editor_values(file_vals)
        assert editor_back.left == pytest.approx(20)
        assert editor_back.right == pytest.approx(20)
        assert editor_back.pos_y == pytest.approx(0)
        assert editor_back.height == pytest.approx(50)

    def test_non_center_pivot(self):
        """Test conversion with non-center pivot."""
        # Anchored mode with pivot at bottom-left
        editor = RectTransformEditorValues(
            anchor_min_x=0,
            anchor_min_y=0,
            anchor_max_x=0,
            anchor_max_y=0,
            pivot_x=0,
            pivot_y=0,
            pos_x=100,
            pos_y=100,
            width=200,
            height=150,
        )

        file_vals = editor_to_file_values(editor)
        editor_back = file_to_editor_values(file_vals)

        assert editor_back.pos_x == pytest.approx(100)
        assert editor_back.pos_y == pytest.approx(100)
        assert editor_back.width == pytest.approx(200)
        assert editor_back.height == pytest.approx(150)


class TestCreateRectTransformFileValues:
    """Tests for create_rect_transform_file_values helper."""

    def test_center_preset(self):
        """Test center anchor preset."""
        vals = create_rect_transform_file_values(
            anchor_preset="center",
            pos_x=50,
            pos_y=30,
            width=100,
            height=50,
        )

        assert vals.anchor_min == {"x": 0.5, "y": 0.5}
        assert vals.anchor_max == {"x": 0.5, "y": 0.5}
        assert vals.anchored_position == {"x": 50, "y": 30}
        assert vals.size_delta == {"x": 100, "y": 50}

    def test_stretch_all_preset(self):
        """Test full stretch preset."""
        vals = create_rect_transform_file_values(
            anchor_preset="stretch-all",
            left=10,
            right=10,
            top=10,
            bottom=10,
        )

        assert vals.anchor_min == {"x": 0, "y": 0}
        assert vals.anchor_max == {"x": 1, "y": 1}
        # With 10px margins all around, sizeDelta should be -20, -20
        assert vals.size_delta == {"x": -20, "y": -20}

    def test_top_left_preset(self):
        """Test top-left anchor preset."""
        vals = create_rect_transform_file_values(
            anchor_preset="top-left",
            pos_x=50,
            pos_y=-30,  # Negative because anchor is at top
            width=100,
            height=50,
        )

        assert vals.anchor_min == {"x": 0, "y": 1}
        assert vals.anchor_max == {"x": 0, "y": 1}


class TestRectTransformExportImport:
    """Tests for RectTransform JSON export/import."""

    def test_export_rect_transform_from_file(self):
        """Test exporting RectTransform from a real prefab file."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "BossSceneUI.prefab")
        json_data = export_to_json(doc, include_raw=True)

        # Find a RectTransform component
        rect_transforms = [
            (fid, comp) for fid, comp in json_data.components.items() if comp.get("type") == "RectTransform"
        ]

        assert len(rect_transforms) > 0

        # Check that rectTransform is exported (single field for all values)
        file_id, rt_data = rect_transforms[0]
        assert "rectTransform" in rt_data

        # Check rectTransform structure (Inspector-style values)
        assert "anchorMin" in rt_data["rectTransform"]
        assert "anchorMax" in rt_data["rectTransform"]
        assert "pivot" in rt_data["rectTransform"]
        # Mode-specific: either posX/posY/width/height or left/right/top/bottom

    def test_import_rect_transform(self):
        """Test importing RectTransform using rectTransform field."""
        # Create a document with a RectTransform
        doc = UnityYAMLDocument()
        go = create_game_object("TestUI", file_id=100000, components=[200000])
        rt = create_rect_transform(game_object_id=100000, file_id=200000)
        doc.add_object(go)
        doc.add_object(rt)

        # Export to JSON
        json_data = export_to_json(doc, include_raw=True)

        # Modify using rectTransform (what LLM would do)
        json_data.components["200000"]["rectTransform"] = {
            "anchorMin": {"x": 0, "y": 0},
            "anchorMax": {"x": 1, "y": 1},
            "pivot": {"x": 0.5, "y": 0.5},
            "posZ": 0,
            "left": 20,
            "right": 20,
            "top": 10,
            "bottom": 10,
        }

        # Import back
        imported_doc = import_from_json(json_data)

        # Check the RectTransform
        rt_obj = imported_doc.get_by_file_id(200000)
        content = rt_obj.get_content()

        assert content["m_AnchorMin"] == {"x": 0, "y": 0}
        assert content["m_AnchorMax"] == {"x": 1, "y": 1}
        # With 20/20/10/10 margins:
        # sizeDelta.x = -20 - 20 = -40
        # sizeDelta.y = -10 - 10 = -20
        assert content["m_SizeDelta"]["x"] == pytest.approx(-40)
        assert content["m_SizeDelta"]["y"] == pytest.approx(-20)

    def test_roundtrip_rect_transform(self):
        """Test round-trip conversion preserves RectTransform values."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "BossSceneUI.prefab")

        # Get original RectTransform values
        rt_objs = doc.get_rect_transforms()
        assert len(rt_objs) > 0

        original_rt = rt_objs[0]
        original_content = original_rt.get_content()

        # Export and import
        json_data = export_to_json(doc, include_raw=True)
        imported_doc = import_from_json(json_data)

        # Check that values are preserved
        imported_rt = imported_doc.get_by_file_id(original_rt.file_id)
        imported_content = imported_rt.get_content()

        assert imported_content["m_AnchorMin"] == original_content["m_AnchorMin"]
        assert imported_content["m_AnchorMax"] == original_content["m_AnchorMax"]
        assert imported_content["m_Pivot"] == original_content["m_Pivot"]


class TestDocumentObjectManagement:
    """Tests for UnityYAMLDocument object management."""

    def test_add_object(self):
        """Test adding objects to a document."""
        doc = UnityYAMLDocument()

        go = create_game_object("Test", file_id=100)
        transform = create_transform(100, file_id=200)

        doc.add_object(go)
        doc.add_object(transform)

        assert len(doc.objects) == 2
        assert doc.get_by_file_id(100) is not None
        assert doc.get_by_file_id(200) is not None

    def test_remove_object(self):
        """Test removing objects from a document."""
        doc = UnityYAMLDocument()

        go = create_game_object("Test", file_id=100)
        transform = create_transform(100, file_id=200)

        doc.add_object(go)
        doc.add_object(transform)

        result = doc.remove_object(100)
        assert result is True
        assert len(doc.objects) == 1
        assert doc.get_by_file_id(100) is None

    def test_get_all_file_ids(self):
        """Test getting all fileIDs from a document."""
        doc = UnityYAMLDocument.load(FIXTURES_DIR / "basic_prefab.prefab")

        ids = doc.get_all_file_ids()
        assert 100000 in ids
        assert 400000 in ids

    def test_create_full_prefab_programmatically(self):
        """Test creating a complete prefab from scratch."""
        doc = UnityYAMLDocument()

        # Create GameObject
        go_id = doc.generate_unique_file_id()
        rt_id = doc.generate_unique_file_id()

        go = create_game_object("MyUIElement", file_id=go_id, components=[rt_id])
        rt = create_rect_transform(
            game_object_id=go_id,
            file_id=rt_id,
            anchor_min={"x": 0.5, "y": 0.5},
            anchor_max={"x": 0.5, "y": 0.5},
            anchored_position={"x": 100, "y": 50},
            size_delta={"x": 200, "y": 100},
        )

        doc.add_object(go)
        doc.add_object(rt)

        # Verify
        assert len(doc.objects) == 2
        assert doc.get_game_objects()[0].get_content()["m_Name"] == "MyUIElement"

        # Verify YAML output
        yaml_content = doc.dump()
        assert "MyUIElement" in yaml_content
        assert "RectTransform" in yaml_content


class TestLayoutDrivenProperties:
    """Tests for layout-driven property detection and marking."""

    def test_content_size_fitter_marks_driven_properties(self):
        """Test that ContentSizeFitter marks width/height as driven."""
        doc = UnityYAMLDocument()

        # Create GameObject with RectTransform and ContentSizeFitter
        go_id = doc.generate_unique_file_id()
        rt_id = doc.generate_unique_file_id()
        csf_id = doc.generate_unique_file_id()

        go = create_game_object(
            "TextContainer",
            file_id=go_id,
            components=[rt_id, csf_id],
        )
        rt = create_rect_transform(
            game_object_id=go_id,
            file_id=rt_id,
            size_delta={"x": 100, "y": 50},
        )
        # ContentSizeFitter with both horizontal and vertical fit
        csf = create_mono_behaviour(
            game_object_id=go_id,
            file_id=csf_id,
            script_guid="3245ec927659c4140ac4f8d17403cc18",  # ContentSizeFitter
            properties={
                "m_HorizontalFit": 2,  # PreferredSize
                "m_VerticalFit": 2,  # PreferredSize
            },
        )

        doc.add_object(go)
        doc.add_object(rt)
        doc.add_object(csf)

        # Export to JSON
        json_data = export_to_json(doc)

        # Check RectTransform has _layoutDriven info
        rt_json = json_data.components[str(rt_id)]
        assert "_layoutDriven" in rt_json
        assert rt_json["_layoutDriven"]["drivenBy"] == "ContentSizeFitter"
        assert "width" in rt_json["_layoutDriven"]["drivenProperties"]
        assert "height" in rt_json["_layoutDriven"]["drivenProperties"]
        assert rt_json["_layoutDriven"]["driverComponentId"] == str(csf_id)

        # Driven properties should show "<driven>" placeholder
        assert rt_json["rectTransform"]["width"] == "<driven>"
        assert rt_json["rectTransform"]["height"] == "<driven>"

    def test_content_size_fitter_horizontal_only(self):
        """Test ContentSizeFitter with only horizontal fit."""
        doc = UnityYAMLDocument()

        go_id = doc.generate_unique_file_id()
        rt_id = doc.generate_unique_file_id()
        csf_id = doc.generate_unique_file_id()

        go = create_game_object("HorzFit", file_id=go_id, components=[rt_id, csf_id])
        rt = create_rect_transform(
            game_object_id=go_id,
            file_id=rt_id,
            size_delta={"x": 200, "y": 100},  # Set explicit size
        )
        csf = create_mono_behaviour(
            game_object_id=go_id,
            file_id=csf_id,
            script_guid="3245ec927659c4140ac4f8d17403cc18",
            properties={
                "m_HorizontalFit": 1,  # MinSize
                "m_VerticalFit": 0,  # Unconstrained
            },
        )

        doc.add_object(go)
        doc.add_object(rt)
        doc.add_object(csf)

        json_data = export_to_json(doc)
        rt_json = json_data.components[str(rt_id)]

        assert "_layoutDriven" in rt_json
        assert "width" in rt_json["_layoutDriven"]["drivenProperties"]
        assert "height" not in rt_json["_layoutDriven"]["drivenProperties"]

        # Only width should be driven, height should have actual value
        assert rt_json["rectTransform"]["width"] == "<driven>"
        assert rt_json["rectTransform"]["height"] == 100.0

    def test_layout_group_marks_children_as_driven(self):
        """Test that VerticalLayoutGroup marks children's properties as driven."""
        doc = UnityYAMLDocument()

        # Parent with VerticalLayoutGroup
        parent_go_id = doc.generate_unique_file_id()
        parent_rt_id = doc.generate_unique_file_id()
        vlg_id = doc.generate_unique_file_id()

        # Child
        child_go_id = doc.generate_unique_file_id()
        child_rt_id = doc.generate_unique_file_id()

        parent_go = create_game_object(
            "LayoutParent",
            file_id=parent_go_id,
            components=[parent_rt_id, vlg_id],
        )
        parent_rt = create_rect_transform(
            game_object_id=parent_go_id,
            file_id=parent_rt_id,
            children_ids=[child_rt_id],
        )
        vlg = create_mono_behaviour(
            game_object_id=parent_go_id,
            file_id=vlg_id,
            script_guid="59f8146938fff824cb5fd77236b75775",  # VerticalLayoutGroup
            properties={
                "m_ChildControlWidth": 1,
                "m_ChildControlHeight": 1,
            },
        )

        child_go = create_game_object(
            "LayoutChild",
            file_id=child_go_id,
            components=[child_rt_id],
        )
        child_rt = create_rect_transform(
            game_object_id=child_go_id,
            file_id=child_rt_id,
            parent_id=parent_rt_id,
        )

        doc.add_object(parent_go)
        doc.add_object(parent_rt)
        doc.add_object(vlg)
        doc.add_object(child_go)
        doc.add_object(child_rt)

        json_data = export_to_json(doc)

        # Parent RectTransform should NOT have _layoutDriven
        parent_rt_json = json_data.components[str(parent_rt_id)]
        assert "_layoutDriven" not in parent_rt_json

        # Child RectTransform SHOULD have _layoutDriven
        child_rt_json = json_data.components[str(child_rt_id)]
        assert "_layoutDriven" in child_rt_json
        assert child_rt_json["_layoutDriven"]["drivenBy"] == "VerticalLayoutGroup"
        assert "width" in child_rt_json["_layoutDriven"]["drivenProperties"]
        assert "height" in child_rt_json["_layoutDriven"]["drivenProperties"]
        assert "posX" in child_rt_json["_layoutDriven"]["drivenProperties"]
        assert "posY" in child_rt_json["_layoutDriven"]["drivenProperties"]

    def test_no_layout_component_no_driven_marker(self):
        """Test that RectTransform without layout components has no _layoutDriven."""
        doc = UnityYAMLDocument()

        go_id = doc.generate_unique_file_id()
        rt_id = doc.generate_unique_file_id()

        go = create_game_object("NormalUI", file_id=go_id, components=[rt_id])
        rt = create_rect_transform(game_object_id=go_id, file_id=rt_id)

        doc.add_object(go)
        doc.add_object(rt)

        json_data = export_to_json(doc)
        rt_json = json_data.components[str(rt_id)]

        assert "_layoutDriven" not in rt_json

    def test_import_normalizes_driven_properties(self):
        """Test that import normalizes driven properties to 0."""
        doc = UnityYAMLDocument()

        go_id = doc.generate_unique_file_id()
        rt_id = doc.generate_unique_file_id()
        csf_id = doc.generate_unique_file_id()

        go = create_game_object("Test", file_id=go_id, components=[rt_id, csf_id])
        rt = create_rect_transform(
            game_object_id=go_id,
            file_id=rt_id,
            size_delta={"x": 200, "y": 100},
        )
        csf = create_mono_behaviour(
            game_object_id=go_id,
            file_id=csf_id,
            script_guid="3245ec927659c4140ac4f8d17403cc18",
            properties={"m_HorizontalFit": 2, "m_VerticalFit": 2},
        )

        doc.add_object(go)
        doc.add_object(rt)
        doc.add_object(csf)

        # Export to JSON
        json_data = export_to_json(doc)

        # Even if LLM modifies the driven values, they should be normalized to 0
        rt_json = json_data.components[str(rt_id)]

        # The values are "<driven>" so LLM might try to change them
        # but they should normalize to 0 on import
        rt_json["rectTransform"]["width"] = 300  # Try to change
        rt_json["rectTransform"]["height"] = 150  # Try to change

        # Import back
        doc2 = import_from_json(json_data)

        # Driven properties should be normalized to 0 regardless of what was set
        rt2 = doc2.get_by_file_id(rt_id)
        content = rt2.get_content()
        assert content["m_SizeDelta"]["x"] == 0  # Normalized to 0
        assert content["m_SizeDelta"]["y"] == 0  # Normalized to 0

    def test_import_preserves_non_driven_properties(self):
        """Test that import preserves non-driven properties correctly."""
        doc = UnityYAMLDocument()

        go_id = doc.generate_unique_file_id()
        rt_id = doc.generate_unique_file_id()
        csf_id = doc.generate_unique_file_id()

        go = create_game_object("Test", file_id=go_id, components=[rt_id, csf_id])
        rt = create_rect_transform(
            game_object_id=go_id,
            file_id=rt_id,
            size_delta={"x": 200, "y": 100},
        )
        # Only horizontal fit - height is NOT driven
        csf = create_mono_behaviour(
            game_object_id=go_id,
            file_id=csf_id,
            script_guid="3245ec927659c4140ac4f8d17403cc18",
            properties={"m_HorizontalFit": 2, "m_VerticalFit": 0},
        )

        doc.add_object(go)
        doc.add_object(rt)
        doc.add_object(csf)

        # Export to JSON
        json_data = export_to_json(doc)
        rt_json = json_data.components[str(rt_id)]

        # Modify the non-driven height
        rt_json["rectTransform"]["height"] = 250

        # Import back
        doc2 = import_from_json(json_data)

        rt2 = doc2.get_by_file_id(rt_id)
        content = rt2.get_content()
        assert content["m_SizeDelta"]["x"] == 0  # Width driven -> normalized to 0
        assert content["m_SizeDelta"]["y"] == 250  # Height NOT driven -> preserved
