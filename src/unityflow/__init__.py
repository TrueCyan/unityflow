"""Unity Prefab Deterministic Serializer.

A tool for canonical serialization of Unity YAML files (prefabs, scenes, assets)
to eliminate non-deterministic changes and reduce VCS noise.
"""

from importlib.metadata import version

__version__ = version("unityflow")

from unityflow.asset_tracker import (
    BINARY_ASSET_EXTENSIONS,
    AssetDependency,
    AssetReference,
    DependencyReport,
    GUIDIndex,
    LazyGUIDIndex,
    analyze_dependencies,
    build_guid_index,
    extract_guid_references,
    find_references_to_asset,
    find_unity_project_root,
    get_cached_guid_index,
    get_file_dependencies,
    get_lazy_guid_index,
)
from unityflow.git_utils import (
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
from unityflow.hierarchy import (
    ComponentInfo,
    Hierarchy,
    HierarchyNode,
    build_hierarchy,
    get_prefab_instance_for_stripped,
    get_stripped_objects_for_prefab,
    resolve_game_object_for_component,
)
from unityflow.meta_generator import (
    EXTENSION_TO_TYPE,
    AssetType,
    MetaFileOptions,
    detect_asset_type,
    ensure_meta_file,
    generate_guid,
    generate_meta_content,
    generate_meta_file,
    generate_meta_files_recursive,
    get_guid_from_meta,
    get_meta_info,
    # Meta modification functions
    modify_meta_file,
    set_asset_bundle,
    set_script_execution_order,
    set_texture_max_size,
    set_texture_sprite_mode,
)
from unityflow.normalizer import UnityPrefabNormalizer
from unityflow.parser import UnityYAMLDocument, UnityYAMLObject
from unityflow.query import (
    QueryResult,
    get_value,
    merge_values,
    query_path,
    set_value,
)
from unityflow.script_parser import (
    ScriptFieldCache,
    ScriptInfo,
    SerializedField,
    get_script_field_order,
    parse_script,
    parse_script_file,
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
    "LazyGUIDIndex",
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
    "get_cached_guid_index",
    "get_file_dependencies",
    "get_lazy_guid_index",
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
    # Meta generator classes
    "AssetType",
    "MetaFileOptions",
    # Meta generator functions
    "generate_guid",
    "detect_asset_type",
    "generate_meta_content",
    "generate_meta_file",
    "generate_meta_files_recursive",
    "ensure_meta_file",
    "get_guid_from_meta",
    # Meta modification functions
    "modify_meta_file",
    "set_texture_sprite_mode",
    "set_texture_max_size",
    "set_script_execution_order",
    "set_asset_bundle",
    "get_meta_info",
    # Meta generator constants
    "EXTENSION_TO_TYPE",
    # Hierarchy classes
    "ComponentInfo",
    "HierarchyNode",
    "Hierarchy",
    # Hierarchy functions
    "build_hierarchy",
    "resolve_game_object_for_component",
    "get_prefab_instance_for_stripped",
    "get_stripped_objects_for_prefab",
]
