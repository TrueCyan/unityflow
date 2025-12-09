"""Unity Prefab Deterministic Serializer.

A tool for canonical serialization of Unity YAML files (prefabs, scenes, assets)
to eliminate non-deterministic changes and reduce VCS noise.
"""

__version__ = "0.1.0"

from prefab_tool.normalizer import UnityPrefabNormalizer
from prefab_tool.parser import UnityYAMLDocument, UnityYAMLObject

__all__ = [
    "UnityPrefabNormalizer",
    "UnityYAMLDocument",
    "UnityYAMLObject",
]
