"""Unity Prefab Deterministic Serializer.

A tool for canonical serialization of Unity YAML files (prefabs, scenes, assets)
to eliminate non-deterministic changes and reduce VCS noise.
"""

__version__ = "0.1.2"

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

__all__ = [
    # Classes
    "UnityPrefabNormalizer",
    "UnityYAMLDocument",
    "UnityYAMLObject",
    # Asset tracking classes
    "AssetDependency",
    "AssetReference",
    "DependencyReport",
    "GUIDIndex",
    # Functions
    "get_changed_files",
    "get_files_changed_since",
    "get_repo_root",
    "is_git_repository",
    # Asset tracking functions
    "analyze_dependencies",
    "build_guid_index",
    "extract_guid_references",
    "find_references_to_asset",
    "find_unity_project_root",
    "get_file_dependencies",
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
