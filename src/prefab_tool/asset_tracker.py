"""Unity Asset Reference Tracker.

Tracks references to binary assets (textures, meshes, etc.) in Unity YAML files.
Provides dependency analysis and reverse reference lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from prefab_tool.git_utils import UNITY_EXTENSIONS


# Common binary asset extensions in Unity
BINARY_ASSET_EXTENSIONS = {
    # Textures
    ".png", ".jpg", ".jpeg", ".tga", ".psd", ".tiff", ".tif",
    ".gif", ".bmp", ".exr", ".hdr",
    # 3D Models
    ".fbx", ".obj", ".dae", ".3ds", ".blend", ".max", ".ma", ".mb",
    # Audio
    ".wav", ".mp3", ".ogg", ".aiff", ".aif", ".flac", ".m4a",
    # Video
    ".mp4", ".mov", ".avi", ".webm",
    # Fonts
    ".ttf", ".otf", ".fon",
    # Other
    ".dll", ".so", ".dylib",  # Native plugins
    ".shader", ".cginc", ".hlsl", ".glsl",  # Shaders
    ".compute",  # Compute shaders
    ".bytes", ".txt", ".json", ".xml", ".csv",  # Data files
}

# Pattern to extract GUID from .meta files
META_GUID_PATTERN = re.compile(r"^guid:\s*([a-f0-9]{32})\s*$", re.MULTILINE)


@dataclass
class AssetReference:
    """Represents a reference to an asset."""

    file_id: int
    guid: str
    ref_type: int | None = None
    source_path: str | None = None
    source_file_id: int | None = None
    property_path: str | None = None

    def __hash__(self) -> int:
        return hash((self.guid, self.file_id))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AssetReference):
            return False
        return self.guid == other.guid and self.file_id == other.file_id


@dataclass
class AssetDependency:
    """Represents a resolved asset dependency."""

    guid: str
    path: Path | None  # None if asset not found in project
    asset_type: str | None = None  # Extension-based type classification
    references: list[AssetReference] = field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        """Check if this dependency was resolved to an actual file."""
        return self.path is not None

    @property
    def is_binary(self) -> bool:
        """Check if this is a binary asset (texture, mesh, etc.)."""
        if self.path is None:
            return False
        return self.path.suffix.lower() in BINARY_ASSET_EXTENSIONS


@dataclass
class GUIDIndex:
    """Index mapping GUIDs to asset paths."""

    guid_to_path: dict[str, Path] = field(default_factory=dict)
    path_to_guid: dict[Path, str] = field(default_factory=dict)
    project_root: Path | None = None

    def __len__(self) -> int:
        return len(self.guid_to_path)

    def get_path(self, guid: str) -> Path | None:
        """Get the asset path for a GUID."""
        return self.guid_to_path.get(guid)

    def get_guid(self, path: Path) -> str | None:
        """Get the GUID for an asset path."""
        # Try both absolute and relative paths
        if path in self.path_to_guid:
            return self.path_to_guid[path]

        # Try resolving relative to project root
        if self.project_root:
            try:
                rel_path = path.relative_to(self.project_root)
                if rel_path in self.path_to_guid:
                    return self.path_to_guid[rel_path]
            except ValueError:
                pass

        return None


def find_unity_project_root(start_path: Path) -> Path | None:
    """Find the Unity project root by looking for Assets folder.

    Args:
        start_path: Starting path to search from

    Returns:
        Path to project root (parent of Assets folder), or None if not found
    """
    current = start_path.resolve()

    # If start_path is a file, start from its parent
    if current.is_file():
        current = current.parent

    # Search upward for Assets folder
    for _ in range(20):  # Limit search depth
        assets_dir = current / "Assets"
        if assets_dir.is_dir():
            # Verify this looks like a Unity project
            project_settings = current / "ProjectSettings"
            if project_settings.is_dir():
                return current
            # Even without ProjectSettings, Assets folder is a good indicator
            return current

        parent = current.parent
        if parent == current:  # Reached root
            break
        current = parent

    return None


def build_guid_index(
    project_root: Path,
    include_packages: bool = False,
    progress_callback: callable | None = None,
) -> GUIDIndex:
    """Build an index of all GUIDs in a Unity project.

    Args:
        project_root: Path to Unity project root
        include_packages: Whether to include Packages folder
        progress_callback: Optional callback for progress (current, total)

    Returns:
        GUIDIndex mapping GUIDs to asset paths
    """
    index = GUIDIndex(project_root=project_root)

    # Collect all .meta files
    search_paths = [project_root / "Assets"]
    if include_packages:
        packages_dir = project_root / "Packages"
        if packages_dir.is_dir():
            search_paths.append(packages_dir)

    meta_files: list[Path] = []
    for search_path in search_paths:
        if search_path.is_dir():
            meta_files.extend(search_path.rglob("*.meta"))

    total = len(meta_files)

    for i, meta_path in enumerate(meta_files):
        if progress_callback:
            progress_callback(i + 1, total)

        try:
            content = meta_path.read_text(encoding="utf-8", errors="replace")
            match = META_GUID_PATTERN.search(content)
            if match:
                guid = match.group(1)
                # Asset path is meta path without .meta extension
                asset_path = meta_path.with_suffix("")

                # Store relative path from project root
                try:
                    rel_path = asset_path.relative_to(project_root)
                    index.guid_to_path[guid] = rel_path
                    index.path_to_guid[rel_path] = guid
                except ValueError:
                    # Path is not relative to project root
                    index.guid_to_path[guid] = asset_path
                    index.path_to_guid[asset_path] = guid
        except (OSError, UnicodeDecodeError):
            # Skip unreadable files
            continue

    return index


def extract_guid_references(data: Any, source_path: str | None = None) -> Iterator[AssetReference]:
    """Extract all GUID references from parsed YAML data.

    Args:
        data: Parsed YAML data (dict or list)
        source_path: Optional property path for context

    Yields:
        AssetReference objects for each external reference found
    """
    if isinstance(data, dict):
        # Check if this is a reference object
        if "guid" in data and "fileID" in data:
            guid = data["guid"]
            file_id = data.get("fileID", 0)
            ref_type = data.get("type")

            if guid and isinstance(guid, str):
                yield AssetReference(
                    file_id=int(file_id) if file_id else 0,
                    guid=guid,
                    ref_type=int(ref_type) if ref_type else None,
                    property_path=source_path,
                )

        # Recurse into nested structures
        for key, value in data.items():
            child_path = f"{source_path}.{key}" if source_path else key
            yield from extract_guid_references(value, child_path)

    elif isinstance(data, list):
        for i, item in enumerate(data):
            child_path = f"{source_path}[{i}]" if source_path else f"[{i}]"
            yield from extract_guid_references(item, child_path)


def get_file_dependencies(
    file_path: Path,
    guid_index: GUIDIndex | None = None,
) -> list[AssetDependency]:
    """Get all asset dependencies for a Unity YAML file.

    Args:
        file_path: Path to the Unity YAML file
        guid_index: Optional pre-built GUID index for resolution

    Returns:
        List of AssetDependency objects
    """
    from prefab_tool.parser import UnityYAMLDocument

    # Parse the file
    doc = UnityYAMLDocument.load_auto(file_path)

    # Collect all references
    refs_by_guid: dict[str, list[AssetReference]] = {}

    for obj in doc.objects:
        for ref in extract_guid_references(obj.data):
            ref.source_file_id = obj.file_id
            ref.source_path = str(file_path)

            if ref.guid not in refs_by_guid:
                refs_by_guid[ref.guid] = []
            refs_by_guid[ref.guid].append(ref)

    # Build dependency list
    dependencies: list[AssetDependency] = []

    for guid, refs in refs_by_guid.items():
        resolved_path = None
        asset_type = None

        if guid_index:
            path = guid_index.get_path(guid)
            if path:
                resolved_path = path
                asset_type = _classify_asset_type(path)

        dep = AssetDependency(
            guid=guid,
            path=resolved_path,
            asset_type=asset_type,
            references=refs,
        )
        dependencies.append(dep)

    # Sort by resolved status and path
    dependencies.sort(key=lambda d: (not d.is_resolved, str(d.path or d.guid)))

    return dependencies


def find_references_to_asset(
    asset_path: Path,
    search_paths: list[Path],
    guid_index: GUIDIndex | None = None,
    extensions: set[str] | None = None,
    progress_callback: callable | None = None,
) -> list[tuple[Path, list[AssetReference]]]:
    """Find all files that reference a specific asset.

    Args:
        asset_path: Path to the asset to search for
        search_paths: Directories to search in
        guid_index: Optional pre-built GUID index
        extensions: File extensions to search (default: Unity YAML extensions)
        progress_callback: Optional callback for progress (current, total)

    Returns:
        List of (file_path, references) tuples
    """
    from prefab_tool.parser import UnityYAMLDocument

    if extensions is None:
        extensions = UNITY_EXTENSIONS

    # Get the GUID for the asset
    target_guid = None

    if guid_index:
        target_guid = guid_index.get_guid(asset_path)

    if not target_guid:
        # Try to read from .meta file
        meta_path = Path(str(asset_path) + ".meta")
        if meta_path.is_file():
            try:
                content = meta_path.read_text(encoding="utf-8")
                match = META_GUID_PATTERN.search(content)
                if match:
                    target_guid = match.group(1)
            except OSError:
                pass

    if not target_guid:
        return []

    # Collect all Unity YAML files to search
    files_to_search: list[Path] = []
    for search_path in search_paths:
        if search_path.is_file():
            if search_path.suffix.lower() in extensions:
                files_to_search.append(search_path)
        elif search_path.is_dir():
            for ext in extensions:
                files_to_search.extend(search_path.rglob(f"*{ext}"))

    # Remove duplicates
    files_to_search = list(set(files_to_search))
    total = len(files_to_search)

    results: list[tuple[Path, list[AssetReference]]] = []

    for i, file_path in enumerate(files_to_search):
        if progress_callback:
            progress_callback(i + 1, total)

        try:
            doc = UnityYAMLDocument.load_auto(file_path)

            refs_found: list[AssetReference] = []
            for obj in doc.objects:
                for ref in extract_guid_references(obj.data):
                    if ref.guid == target_guid:
                        ref.source_file_id = obj.file_id
                        ref.source_path = str(file_path)
                        refs_found.append(ref)

            if refs_found:
                results.append((file_path, refs_found))
        except Exception:
            # Skip files that can't be parsed
            continue

    # Sort by file path
    results.sort(key=lambda r: str(r[0]))

    return results


def _classify_asset_type(path: Path) -> str:
    """Classify an asset by its file extension.

    Args:
        path: Path to the asset

    Returns:
        Asset type classification string
    """
    ext = path.suffix.lower()

    # Textures
    if ext in {".png", ".jpg", ".jpeg", ".tga", ".psd", ".tiff", ".tif", ".gif", ".bmp", ".exr", ".hdr"}:
        return "Texture"

    # 3D Models
    if ext in {".fbx", ".obj", ".dae", ".3ds", ".blend", ".max", ".ma", ".mb"}:
        return "Model"

    # Audio
    if ext in {".wav", ".mp3", ".ogg", ".aiff", ".aif", ".flac", ".m4a"}:
        return "Audio"

    # Video
    if ext in {".mp4", ".mov", ".avi", ".webm"}:
        return "Video"

    # Fonts
    if ext in {".ttf", ".otf", ".fon"}:
        return "Font"

    # Shaders
    if ext in {".shader", ".cginc", ".hlsl", ".glsl", ".compute"}:
        return "Shader"

    # Scripts
    if ext in {".cs", ".js"}:
        return "Script"

    # Unity YAML assets
    if ext in UNITY_EXTENSIONS:
        return "UnityAsset"

    # Native plugins
    if ext in {".dll", ".so", ".dylib"}:
        return "Plugin"

    # Data files
    if ext in {".bytes", ".txt", ".json", ".xml", ".csv"}:
        return "Data"

    return "Unknown"


@dataclass
class DependencyReport:
    """Report of all dependencies for a file or set of files."""

    source_files: list[Path]
    dependencies: list[AssetDependency]
    guid_index: GUIDIndex | None = None

    @property
    def total_dependencies(self) -> int:
        return len(self.dependencies)

    @property
    def resolved_count(self) -> int:
        return sum(1 for d in self.dependencies if d.is_resolved)

    @property
    def unresolved_count(self) -> int:
        return sum(1 for d in self.dependencies if not d.is_resolved)

    @property
    def binary_count(self) -> int:
        return sum(1 for d in self.dependencies if d.is_binary)

    def get_by_type(self, asset_type: str) -> list[AssetDependency]:
        """Get dependencies of a specific type."""
        return [d for d in self.dependencies if d.asset_type == asset_type]

    def get_binary_dependencies(self) -> list[AssetDependency]:
        """Get only binary asset dependencies."""
        return [d for d in self.dependencies if d.is_binary]

    def get_unresolved(self) -> list[AssetDependency]:
        """Get unresolved dependencies."""
        return [d for d in self.dependencies if not d.is_resolved]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        deps_list = []
        for dep in self.dependencies:
            dep_dict = {
                "guid": dep.guid,
                "path": str(dep.path) if dep.path else None,
                "type": dep.asset_type,
                "resolved": dep.is_resolved,
                "binary": dep.is_binary,
                "reference_count": len(dep.references),
            }
            deps_list.append(dep_dict)

        return {
            "source_files": [str(f) for f in self.source_files],
            "summary": {
                "total": self.total_dependencies,
                "resolved": self.resolved_count,
                "unresolved": self.unresolved_count,
                "binary": self.binary_count,
            },
            "dependencies": deps_list,
        }


def analyze_dependencies(
    files: list[Path],
    project_root: Path | None = None,
    include_packages: bool = False,
    progress_callback: callable | None = None,
) -> DependencyReport:
    """Analyze dependencies for one or more Unity YAML files.

    Args:
        files: List of Unity YAML files to analyze
        project_root: Optional project root for GUID resolution
        include_packages: Whether to include Packages folder in GUID index
        progress_callback: Optional callback for progress

    Returns:
        DependencyReport with all dependencies
    """
    # Find project root if not provided
    if project_root is None and files:
        project_root = find_unity_project_root(files[0])

    # Build GUID index
    guid_index = None
    if project_root:
        guid_index = build_guid_index(
            project_root,
            include_packages=include_packages,
        )

    # Collect all dependencies
    all_deps: dict[str, AssetDependency] = {}

    for file_path in files:
        deps = get_file_dependencies(file_path, guid_index)
        for dep in deps:
            if dep.guid in all_deps:
                # Merge references
                all_deps[dep.guid].references.extend(dep.references)
            else:
                all_deps[dep.guid] = dep

    # Sort dependencies
    sorted_deps = sorted(
        all_deps.values(),
        key=lambda d: (not d.is_resolved, d.asset_type or "", str(d.path or d.guid))
    )

    return DependencyReport(
        source_files=files,
        dependencies=sorted_deps,
        guid_index=guid_index,
    )
