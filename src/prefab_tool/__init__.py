"""Unity Prefab Deterministic Serializer.

A tool for canonical serialization of Unity YAML files (prefabs, scenes, assets)
to eliminate non-deterministic changes and reduce VCS noise.
"""

from importlib.metadata import version

__version__ = version("prefab-tool")

from prefab_tool.git_utils import (
    UNITY_ANIMATION_EXTENSIONS,
    UNITY_AUDIO_EXTENSIONS,
    UNITY_CORE_EXTENSIONS,
    UNITY_EXTENSIONS,
    UNITY_PHYSICS_EXTENSIONS,
    UNITY_RENDERING_EXTENSIONS,
    UNITY_TERRAIN_EXTENSIONS,
    UNITY_UI_EXTENSIONS,
    get_changed_files,
    get_files_changed_since,
    get_repo_root,
    is_git_repository,
)
from prefab_tool.normalizer import UnityPrefabNormalizer
from prefab_tool.parser import UnityYAMLDocument, UnityYAMLObject
from prefab_tool.asset_tracker import (
    BINARY_ASSET_EXTENSIONS,
    AssetDependency,
    AssetReference,
    DependencyReport,
    GUIDIndex,
    analyze_dependencies,
    build_guid_index,
    extract_guid_references,
    find_references_to_asset,
    find_unity_project_root,
    get_file_dependencies,
)
from prefab_tool.query import (
    QueryResult,
    query_path,
    set_value,
    get_value,
    merge_values,
)
from prefab_tool.script_parser import (
    ScriptInfo,
    SerializedField,
    ScriptFieldCache,
    parse_script,
    parse_script_file,
    get_script_field_order,
    reorder_fields,
)

__all__ = [
    # Classes
    "UnityPrefabNormalizer",
    "UnityYAMLDocument",
    "UnityYAMLObject",
    "QueryResult",
    # Asset tracking classes
    "AssetDependency",
    "AssetReference",
    "DependencyReport",
    "GUIDIndex",
    # Script parsing classes
    "ScriptInfo",
    "SerializedField",
    "ScriptFieldCache",
    # Functions
    "get_changed_files",
    "get_files_changed_since",
    "get_repo_root",
    "is_git_repository",
    # Query functions
    "query_path",
    "set_value",
    "get_value",
    "merge_values",
    # Asset tracking functions
    "analyze_dependencies",
    "build_guid_index",
    "extract_guid_references",
    "find_references_to_asset",
    "find_unity_project_root",
    "get_file_dependencies",
    # Script parsing functions
    "parse_script",
    "parse_script_file",
    "get_script_field_order",
    "reorder_fields",
    # Extension sets
    "UNITY_EXTENSIONS",
    "UNITY_CORE_EXTENSIONS",
    "UNITY_ANIMATION_EXTENSIONS",
    "UNITY_RENDERING_EXTENSIONS",
    "UNITY_PHYSICS_EXTENSIONS",
    "UNITY_TERRAIN_EXTENSIONS",
    "UNITY_AUDIO_EXTENSIONS",
    "UNITY_UI_EXTENSIONS",
    "BINARY_ASSET_EXTENSIONS",
]
