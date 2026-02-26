from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import ufbx

from unityflow.parser import UnityYAMLDocument, UnityYAMLObject

MODEL_EXTENSIONS = frozenset({".fbx", ".obj", ".dae", ".blend", ".3ds", ".max", ".gltf", ".glb"})

_CLASS_ID_GAME_OBJECT = 1
_CLASS_ID_TRANSFORM = 4
_CLASS_ID_MESH_RENDERER = 23
_CLASS_ID_MESH_FILTER = 33
_CLASS_ID_SKINNED_MESH_RENDERER = 137


def is_model_file(path: Path) -> bool:
    return path.suffix.lower() in MODEL_EXTENSIONS


def load_fbx_as_document(fbx_path: Path) -> UnityYAMLDocument | None:
    meta_mapping = _parse_fbx_meta(Path(str(fbx_path) + ".meta"))

    try:
        scene = ufbx.load_file(str(fbx_path))
    except Exception:
        return None

    doc = UnityYAMLDocument()
    doc.source_path = fbx_path

    nodes = _collect_nodes_depth_first(scene.root_node)
    if not nodes:
        return None

    counters: dict[int, int] = {}
    node_file_ids: dict[int, dict[int, int]] = {}

    for node in nodes:
        class_ids = _node_class_ids(node)
        ids: dict[int, int] = {}
        for cid in class_ids:
            fid = _resolve_file_id(meta_mapping, cid, node.name, counters)
            ids[cid] = fid
        node_file_ids[id(node)] = ids

    for node in nodes:
        ids = node_file_ids[id(node)]
        go_id = ids[_CLASS_ID_GAME_OBJECT]
        transform_id = ids[_CLASS_ID_TRANSFORM]

        child_transform_ids = []
        for child in node.children:
            child_ids = node_file_ids.get(id(child))
            if child_ids:
                child_transform_ids.append({"fileID": child_ids[_CLASS_ID_TRANSFORM]})

        parent_transform_id = 0
        if node.parent and not node.parent.is_root:
            parent_ids = node_file_ids.get(id(node.parent))
            if parent_ids:
                parent_transform_id = parent_ids[_CLASS_ID_TRANSFORM]

        components: list[dict[str, Any]] = [{"component": {"fileID": transform_id}}]
        if _CLASS_ID_MESH_FILTER in ids:
            components.append({"component": {"fileID": ids[_CLASS_ID_MESH_FILTER]}})
        if _CLASS_ID_MESH_RENDERER in ids:
            components.append({"component": {"fileID": ids[_CLASS_ID_MESH_RENDERER]}})
        if _CLASS_ID_SKINNED_MESH_RENDERER in ids:
            components.append({"component": {"fileID": ids[_CLASS_ID_SKINNED_MESH_RENDERER]}})

        go_obj = UnityYAMLObject(
            class_id=_CLASS_ID_GAME_OBJECT,
            file_id=go_id,
            data={
                "GameObject": {
                    "m_Name": node.name or fbx_path.stem,
                    "m_Component": components,
                    "m_Layer": 0,
                    "m_IsActive": 1,
                }
            },
        )

        local_transform = node.local_transform
        transform_obj = UnityYAMLObject(
            class_id=_CLASS_ID_TRANSFORM,
            file_id=transform_id,
            data={
                "Transform": {
                    "m_GameObject": {"fileID": go_id},
                    "m_LocalPosition": {
                        "x": local_transform.translation.x,
                        "y": local_transform.translation.y,
                        "z": local_transform.translation.z,
                    },
                    "m_LocalRotation": {
                        "x": local_transform.rotation.x,
                        "y": local_transform.rotation.y,
                        "z": local_transform.rotation.z,
                        "w": local_transform.rotation.w,
                    },
                    "m_LocalScale": {
                        "x": local_transform.scale.x,
                        "y": local_transform.scale.y,
                        "z": local_transform.scale.z,
                    },
                    "m_Children": child_transform_ids,
                    "m_Father": {"fileID": parent_transform_id},
                }
            },
        )

        doc.objects.append(go_obj)
        doc.objects.append(transform_obj)

        if _CLASS_ID_MESH_FILTER in ids:
            doc.objects.append(
                UnityYAMLObject(
                    class_id=_CLASS_ID_MESH_FILTER,
                    file_id=ids[_CLASS_ID_MESH_FILTER],
                    data={"MeshFilter": {"m_GameObject": {"fileID": go_id}}},
                )
            )
        if _CLASS_ID_MESH_RENDERER in ids:
            doc.objects.append(
                UnityYAMLObject(
                    class_id=_CLASS_ID_MESH_RENDERER,
                    file_id=ids[_CLASS_ID_MESH_RENDERER],
                    data={"MeshRenderer": {"m_GameObject": {"fileID": go_id}}},
                )
            )
        if _CLASS_ID_SKINNED_MESH_RENDERER in ids:
            doc.objects.append(
                UnityYAMLObject(
                    class_id=_CLASS_ID_SKINNED_MESH_RENDERER,
                    file_id=ids[_CLASS_ID_SKINNED_MESH_RENDERER],
                    data={"SkinnedMeshRenderer": {"m_GameObject": {"fileID": go_id}}},
                )
            )

    return doc


def _collect_nodes_depth_first(root_node: Any) -> list[Any]:
    result: list[Any] = []

    def _walk(node: Any) -> None:
        if not node.is_root:
            result.append(node)
        for child in node.children:
            _walk(child)

    _walk(root_node)
    return result


def _node_class_ids(node: Any) -> list[int]:
    class_ids = [_CLASS_ID_GAME_OBJECT, _CLASS_ID_TRANSFORM]

    has_mesh = node.mesh is not None
    has_skin = has_mesh and node.mesh.skin_deformers

    if has_skin:
        class_ids.append(_CLASS_ID_SKINNED_MESH_RENDERER)
    elif has_mesh:
        class_ids.append(_CLASS_ID_MESH_FILTER)
        class_ids.append(_CLASS_ID_MESH_RENDERER)

    return class_ids


def _resolve_file_id(
    meta_mapping: dict[tuple[int, str], int],
    class_id: int,
    node_name: str,
    counters: dict[int, int],
) -> int:
    key = (class_id, node_name)
    if key in meta_mapping:
        return meta_mapping[key]

    idx = counters.get(class_id, 0)
    counters[class_id] = idx + 1
    return class_id * 100000 + 2 * idx


def _parse_fbx_meta(meta_path: Path) -> dict[tuple[int, str], int]:
    if not meta_path.exists():
        return {}

    try:
        content = meta_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    mapping = _parse_file_id_to_recycle_name(content)
    if mapping:
        return mapping

    return _parse_internal_id_to_name_table(content)


_RECYCLE_PATTERN = re.compile(r"^\s+(\d+):\s+(.+)$", re.MULTILINE)


def _parse_file_id_to_recycle_name(content: str) -> dict[tuple[int, str], int]:
    section_match = re.search(r"^\s+fileIDToRecycleName:\s*$", content, re.MULTILINE)
    if not section_match:
        return {}

    indent_len = len(section_match.group(0)) - len(section_match.group(0).lstrip())
    section_start = section_match.end()

    result: dict[tuple[int, str], int] = {}
    for line in content[section_start:].splitlines():
        if not line.strip():
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent <= indent_len and line.strip():
            break
        match = _RECYCLE_PATTERN.match(line)
        if match:
            file_id = int(match.group(1))
            name = match.group(2).strip()
            class_id = file_id // 100000
            result[(class_id, name)] = file_id

    return result


_INTERNAL_ID_PATTERN = re.compile(
    r"-\s+first:\s*\n\s+(\d+):\s*(-?\d+)\s*\n\s+second:\s*(.+)",
    re.MULTILINE,
)


def _parse_internal_id_to_name_table(content: str) -> dict[tuple[int, str], int]:
    result: dict[tuple[int, str], int] = {}
    for match in _INTERNAL_ID_PATTERN.finditer(content):
        class_id = int(match.group(1))
        file_id = int(match.group(2))
        name = match.group(3).strip()
        result[(class_id, name)] = file_id

    return result
