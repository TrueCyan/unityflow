import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from unityflow.fbx_loader import (
    _parse_file_id_to_recycle_name,
    _parse_internal_id_to_name_table,
    _resolve_file_id,
    is_model_file,
    load_fbx_as_document,
)


class TestIsModelFile:
    def test_fbx(self):
        assert is_model_file(Path("model.fbx")) is True
        assert is_model_file(Path("model.FBX")) is True

    def test_other_model_formats(self):
        assert is_model_file(Path("model.obj")) is True
        assert is_model_file(Path("model.dae")) is True
        assert is_model_file(Path("model.gltf")) is True
        assert is_model_file(Path("model.glb")) is True

    def test_non_model(self):
        assert is_model_file(Path("file.prefab")) is False
        assert is_model_file(Path("file.unity")) is False
        assert is_model_file(Path("file.cs")) is False


class TestParseFileIDToRecycleName:
    def test_basic_mapping(self):
        content = """\
fileFormatVersion: 2
guid: abc123
ModelImporter:
  fileIDToRecycleName:
    100000: //RootNode
    100002: Armature
    400000: //RootNode
    400002: Armature
  externalObjects: {}
"""
        result = _parse_file_id_to_recycle_name(content)
        assert result[(1, "//RootNode")] == 100000
        assert result[(1, "Armature")] == 100002
        assert result[(4, "//RootNode")] == 400000
        assert result[(4, "Armature")] == 400002

    def test_empty_section(self):
        content = """\
ModelImporter:
  fileIDToRecycleName: {}
  externalObjects: {}
"""
        result = _parse_file_id_to_recycle_name(content)
        assert result == {}

    def test_no_section(self):
        content = """\
ModelImporter:
  externalObjects: {}
"""
        result = _parse_file_id_to_recycle_name(content)
        assert result == {}


class TestParseInternalIDToNameTable:
    def test_basic_mapping(self):
        content = """\
ModelImporter:
  internalIDToNameTable:
  - first:
      1: 100000
    second: Root
  - first:
      4: 400000
    second: Root
  - first:
      1: 100002
    second: Hips
"""
        result = _parse_internal_id_to_name_table(content)
        assert result[(1, "Root")] == 100000
        assert result[(4, "Root")] == 400000
        assert result[(1, "Hips")] == 100002

    def test_empty_table(self):
        content = """\
ModelImporter:
  internalIDToNameTable: []
"""
        result = _parse_internal_id_to_name_table(content)
        assert result == {}


class TestResolveFileID:
    def test_from_meta_mapping(self):
        mapping = {(1, "Root"): 100000, (4, "Root"): 400000}
        counters: dict[int, int] = {}
        assert _resolve_file_id(mapping, 1, "Root", counters) == 100000

    def test_fallback_to_formula(self):
        counters: dict[int, int] = {}
        assert _resolve_file_id({}, 1, "Root", counters) == 100000
        assert _resolve_file_id({}, 1, "Child1", counters) == 100002
        assert _resolve_file_id({}, 4, "Root", counters) == 400000
        assert _resolve_file_id({}, 4, "Child1", counters) == 400002

    def test_counters_independent_per_class(self):
        counters: dict[int, int] = {}
        _resolve_file_id({}, 1, "A", counters)
        _resolve_file_id({}, 4, "A", counters)
        assert _resolve_file_id({}, 1, "B", counters) == 100002
        assert _resolve_file_id({}, 4, "B", counters) == 400002


class TestLoadFbxAsDocument:
    def _make_mock_node(self, name, children=None, parent=None, is_root=False, has_mesh=False, has_skin=False):
        node = MagicMock()
        node.name = name
        node.children = children or []
        node.parent = parent
        node.is_root = is_root

        if has_mesh:
            node.mesh = MagicMock()
            if has_skin:
                node.mesh.skin_deformers = [MagicMock()]
            else:
                node.mesh.skin_deformers = []
        else:
            node.mesh = None

        transform = MagicMock()
        transform.translation.x = 0.0
        transform.translation.y = 0.0
        transform.translation.z = 0.0
        transform.rotation.x = 0.0
        transform.rotation.y = 0.0
        transform.rotation.z = 0.0
        transform.rotation.w = 1.0
        transform.scale.x = 1.0
        transform.scale.y = 1.0
        transform.scale.z = 1.0
        node.local_transform = transform

        return node

    def _make_mock_scene(self):
        root = self._make_mock_node("RootNode", is_root=True)
        child_a = self._make_mock_node("Armature", parent=root, has_mesh=False)
        child_b = self._make_mock_node("Body", parent=child_a, has_mesh=True, has_skin=True)
        child_c = self._make_mock_node("Head", parent=child_a, has_mesh=True, has_skin=False)
        child_a.children = [child_b, child_c]
        root.children = [child_a]

        scene = MagicMock()
        scene.root_node = root
        return scene

    @patch("unityflow.fbx_loader.ufbx")
    def test_basic_hierarchy(self, mock_ufbx):
        mock_ufbx.load_file.return_value = self._make_mock_scene()

        with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as f:
            fbx_path = Path(f.name)

        doc = load_fbx_as_document(fbx_path)
        assert doc is not None

        go_objects = [o for o in doc.objects if o.class_id == 1]
        transform_objects = [o for o in doc.objects if o.class_id == 4]
        assert len(go_objects) == 3
        assert len(transform_objects) == 3

        names = {o.get_content()["m_Name"] for o in go_objects}
        assert names == {"Armature", "Body", "Head"}

        fbx_path.unlink(missing_ok=True)

    @patch("unityflow.fbx_loader.ufbx")
    def test_mesh_components(self, mock_ufbx):
        mock_ufbx.load_file.return_value = self._make_mock_scene()

        with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as f:
            fbx_path = Path(f.name)

        doc = load_fbx_as_document(fbx_path)

        skinned_renderers = [o for o in doc.objects if o.class_id == 137]
        assert len(skinned_renderers) == 1

        mesh_filters = [o for o in doc.objects if o.class_id == 33]
        mesh_renderers = [o for o in doc.objects if o.class_id == 23]
        assert len(mesh_filters) == 1
        assert len(mesh_renderers) == 1

        fbx_path.unlink(missing_ok=True)

    @patch("unityflow.fbx_loader.ufbx")
    def test_parent_child_links(self, mock_ufbx):
        mock_ufbx.load_file.return_value = self._make_mock_scene()

        with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as f:
            fbx_path = Path(f.name)

        doc = load_fbx_as_document(fbx_path)

        transforms_by_go_name = {}
        go_by_id = {}
        for o in doc.objects:
            if o.class_id == 1:
                go_by_id[o.file_id] = o.get_content()["m_Name"]

        for o in doc.objects:
            if o.class_id == 4:
                content = o.get_content()
                go_name = go_by_id.get(content["m_GameObject"]["fileID"])
                if go_name:
                    transforms_by_go_name[go_name] = content

        armature_t = transforms_by_go_name["Armature"]
        assert armature_t["m_Father"]["fileID"] == 0
        assert len(armature_t["m_Children"]) == 2

        body_t = transforms_by_go_name["Body"]
        armature_transform_id = next(
            o.file_id
            for o in doc.objects
            if o.class_id == 4
            and o.get_content()["m_GameObject"]["fileID"]
            == next(o2.file_id for o2 in doc.objects if o2.class_id == 1 and o2.get_content()["m_Name"] == "Armature")
        )
        assert body_t["m_Father"]["fileID"] == armature_transform_id

        fbx_path.unlink(missing_ok=True)

    @patch("unityflow.fbx_loader.ufbx")
    def test_meta_file_mapping(self, mock_ufbx):
        root = self._make_mock_node("RootNode", is_root=True)
        child = self._make_mock_node("MyNode", parent=root)
        root.children = [child]
        scene = MagicMock()
        scene.root_node = root
        mock_ufbx.load_file.return_value = scene

        with tempfile.TemporaryDirectory() as tmpdir:
            fbx_path = Path(tmpdir) / "model.fbx"
            fbx_path.write_bytes(b"")
            meta_path = Path(tmpdir) / "model.fbx.meta"
            meta_path.write_text(
                """\
fileFormatVersion: 2
guid: abc123
ModelImporter:
  fileIDToRecycleName:
    100000: MyNode
    400000: MyNode
""",
                encoding="utf-8",
            )

            doc = load_fbx_as_document(fbx_path)
            assert doc is not None

            go = next(o for o in doc.objects if o.class_id == 1)
            assert go.file_id == 100000

            transform = next(o for o in doc.objects if o.class_id == 4)
            assert transform.file_id == 400000
