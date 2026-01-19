"""Unity Asset Reference Tracker.

Tracks references to binary assets (textures, meshes, etc.) in Unity YAML files.
Provides dependency analysis and reverse reference lookup.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from unityflow.git_utils import UNITY_EXTENSIONS

# Common binary asset extensions in Unity
BINARY_ASSET_EXTENSIONS = {
    # Textures
    ".png",
    ".jpg",
    ".jpeg",
    ".tga",
    ".psd",
    ".tiff",
    ".tif",
    ".gif",
    ".bmp",
    ".exr",
    ".hdr",
    # 3D Models
    ".fbx",
    ".obj",
    ".dae",
    ".3ds",
    ".blend",
    ".max",
    ".ma",
    ".mb",
    # Audio
    ".wav",
    ".mp3",
    ".ogg",
    ".aiff",
    ".aif",
    ".flac",
    ".m4a",
    # Video
    ".mp4",
    ".mov",
    ".avi",
    ".webm",
    # Fonts
    ".ttf",
    ".otf",
    ".fon",
    # Other
    ".dll",
    ".so",
    ".dylib",  # Native plugins
    ".shader",
    ".cginc",
    ".hlsl",
    ".glsl",  # Shaders
    ".compute",  # Compute shaders
    ".bytes",
    ".txt",
    ".json",
    ".xml",
    ".csv",  # Data files
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
    """Index mapping GUIDs to asset paths.

    Provides methods to resolve GUIDs to asset paths and names,
    enabling LLM-friendly access to Unity asset metadata.

    Example:
        >>> guid_index = build_guid_index("/path/to/unity/project")
        >>> path = guid_index.get_path("f4afdcb1cbadf954ba8b1cf465429e17")
        >>> print(path)  # Assets/Scripts/PlayerController.cs
        >>> name = guid_index.resolve_name("f4afdcb1cbadf954ba8b1cf465429e17")
        >>> print(name)  # PlayerController
    """

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

    def resolve_name(self, guid: str) -> str | None:
        """Resolve a GUID to an asset name (filename without extension).

        This is particularly useful for resolving MonoBehaviour script names
        from their m_Script GUID references.

        Args:
            guid: The GUID to resolve

        Returns:
            The asset name (stem), or None if GUID is not found

        Example:
            >>> name = guid_index.resolve_name("f4afdcb1cbadf954ba8b1cf465429e17")
            >>> print(name)  # "PlayerController"
        """
        path = self.guid_to_path.get(guid)
        if path is not None:
            return path.stem
        return None

    def resolve_path(self, guid: str) -> Path | None:
        """Resolve a GUID to an asset path.

        Alias for get_path() with a more descriptive name for LLM usage.

        Args:
            guid: The GUID to resolve

        Returns:
            The asset path, or None if GUID is not found

        Example:
            >>> path = guid_index.resolve_path("f4afdcb1cbadf954ba8b1cf465429e17")
            >>> print(path)  # Path("Assets/Scripts/PlayerController.cs")
        """
        return self.guid_to_path.get(guid)

    def batch_resolve_names(self, guids: set[str]) -> dict[str, str]:
        """Batch resolve multiple GUIDs to asset names.

        Efficiently resolves multiple GUIDs at once using simple dict lookups.
        This is more efficient than calling resolve_name() repeatedly when
        processing many components.

        Args:
            guids: Set of GUIDs to resolve

        Returns:
            Dict mapping GUID to asset name (filename without extension).
            GUIDs that couldn't be resolved are omitted from the result.

        Example:
            >>> names = guid_index.batch_resolve_names({"abc123...", "def456..."})
            >>> print(names)  # {"abc123...": "PlayerController", "def456...": "EnemyAI"}
        """
        result: dict[str, str] = {}
        for guid in guids:
            path = self.guid_to_path.get(guid)
            if path is not None:
                result[guid] = path.stem
        return result


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


def get_local_package_paths(project_root: Path) -> list[Path]:
    """Get paths to local packages referenced via file: in manifest.json.

    Parses Packages/manifest.json and extracts paths for dependencies
    that use the "file:" prefix (local filesystem packages).

    Examples of supported formats:
    - "file:../../NK.Packages/com.domybest.mybox@1.7.0"
    - "file:../SharedPackages/mypackage"

    Args:
        project_root: Path to Unity project root

    Returns:
        List of resolved absolute paths to local package directories.
    """
    manifest_path = project_root / "Packages" / "manifest.json"
    if not manifest_path.exists():
        return []

    local_paths: list[Path] = []
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        dependencies = manifest_data.get("dependencies", {})

        for _dep_name, dep_value in dependencies.items():
            if isinstance(dep_value, str) and dep_value.startswith("file:"):
                # Extract relative path: "file:../../NK.Packages/pkg" -> "../../NK.Packages/pkg"
                relative_path = dep_value[5:]  # Remove "file:" prefix

                # Resolve relative to Packages directory (where manifest.json lives)
                package_path = (project_root / "Packages" / relative_path).resolve()

                # Only add if it exists and is a directory
                if package_path.is_dir():
                    local_paths.append(package_path)

    except (OSError, json.JSONDecodeError, KeyError):
        pass

    return local_paths


def build_guid_index(
    project_root: Path,
    include_packages: bool = False,
    progress_callback: callable | None = None,
) -> GUIDIndex:
    """Build an index of all GUIDs in a Unity project.

    Scans:
    - Assets/ folder (always)
    - Packages/ folder (when include_packages=True, for embedded packages)
    - Library/PackageCache/ (when include_packages=True, for registry packages)
    - Local packages from manifest.json file: references (when include_packages=True)

    Args:
        project_root: Path to Unity project root
        include_packages: Whether to include Packages/ and Library/PackageCache/
        progress_callback: Optional callback for progress (current, total)

    Returns:
        GUIDIndex mapping GUIDs to asset paths
    """
    index = GUIDIndex(project_root=project_root)

    # Collect all .meta files
    search_paths = [project_root / "Assets"]
    if include_packages:
        # Embedded packages in Packages/ folder
        packages_dir = project_root / "Packages"
        if packages_dir.is_dir():
            search_paths.append(packages_dir)

        # Downloaded packages from Unity registry in Library/PackageCache/
        package_cache_dir = project_root / "Library" / "PackageCache"
        if package_cache_dir.is_dir():
            search_paths.append(package_cache_dir)

        # Local packages referenced via file: in manifest.json
        local_package_paths = get_local_package_paths(project_root)
        search_paths.extend(local_package_paths)

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
    from unityflow.parser import UnityYAMLDocument

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
    from unityflow.parser import UnityYAMLDocument

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
    texture_exts = {".png", ".jpg", ".jpeg", ".tga", ".psd", ".tiff", ".tif", ".gif", ".bmp", ".exr", ".hdr"}
    if ext in texture_exts:
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
        all_deps.values(), key=lambda d: (not d.is_resolved, d.asset_type or "", str(d.path or d.guid))
    )

    return DependencyReport(
        source_files=files,
        dependencies=sorted_deps,
        guid_index=guid_index,
    )


# ============================================================================
# GUID Cache System (SQLite-based)
# ============================================================================

CACHE_DIR_NAME = ".unityflow"
CACHE_DB_NAME = "guid_cache.db"
CACHE_VERSION = 2  # Bumped for SQLite migration

# Type alias for progress callback
ProgressCallback = Callable[[int, int], None] | None


def _parse_meta_file(meta_path: Path, project_root: Path) -> tuple[str, Path, float] | None:
    """Parse a single .meta file and extract GUID with mtime.

    Args:
        meta_path: Path to the .meta file
        project_root: Project root for relative path calculation

    Returns:
        Tuple of (guid, relative_path, mtime) or None if parsing fails
    """
    try:
        # Get mtime during read to avoid second stat() call
        mtime = meta_path.stat().st_mtime
        content = meta_path.read_text(encoding="utf-8", errors="replace")
        match = META_GUID_PATTERN.search(content)
        if match:
            guid = match.group(1)
            asset_path = meta_path.with_suffix("")

            # Store relative path from project root if possible
            try:
                rel_path = asset_path.relative_to(project_root)
                return (guid, rel_path, mtime)
            except ValueError:
                return (guid, asset_path, mtime)
    except (OSError, UnicodeDecodeError):
        pass
    return None


@dataclass
class CachedGUIDIndex:
    """GUID index with SQLite-based caching for performance.

    Caches GUID mappings using SQLite with WAL mode for:
    - Faster queries for large projects (170k+ assets)
    - Better concurrent read/write access
    - Incremental updates at file level (mtime tracking)

    Automatically invalidates cache when:
    - Package versions change
    - Cache file is missing or corrupted
    - Cache version mismatch
    - Individual file mtime changes (incremental update)
    """

    project_root: Path
    _index: GUIDIndex | None = field(default=None, repr=False)
    _cache_dir: Path | None = field(default=None, repr=False)
    _db_lock: Lock = field(default_factory=Lock, repr=False)

    def __post_init__(self):
        self._cache_dir = self.project_root / CACHE_DIR_NAME

    @property
    def cache_db(self) -> Path:
        """Path to the cache database."""
        return self._cache_dir / CACHE_DB_NAME

    def get_index(
        self,
        include_packages: bool = True,
        progress_callback: ProgressCallback = None,
        max_workers: int | None = None,
    ) -> GUIDIndex:
        """Get GUID index, using cache if available.

        Args:
            include_packages: Whether to include Library/PackageCache/
            progress_callback: Optional callback for progress (current, total)
            max_workers: Max threads for parallel processing (default: min(32, cpu_count + 4))

        Returns:
            GUIDIndex with GUID to path mappings
        """
        if self._index is not None:
            return self._index

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Check if we need full rebuild or incremental update
        package_versions = self._get_package_versions() if include_packages else {}

        if self._needs_full_rebuild(package_versions, include_packages):
            # Full rebuild
            self._index, db_entries = self._build_full_index(
                include_packages,
                progress_callback=progress_callback,
                max_workers=max_workers,
            )
            self._save_to_db(db_entries, package_versions, include_packages)
        else:
            # Try incremental update
            self._index = self._incremental_update(
                include_packages,
                progress_callback=progress_callback,
                max_workers=max_workers,
            )

        return self._index

    def invalidate(self) -> None:
        """Invalidate the cache."""
        self._index = None
        if self.cache_db.exists():
            self.cache_db.unlink()
        # Also remove WAL and SHM files if they exist
        wal_file = Path(str(self.cache_db) + "-wal")
        shm_file = Path(str(self.cache_db) + "-shm")
        if wal_file.exists():
            wal_file.unlink()
        if shm_file.exists():
            shm_file.unlink()

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get a database connection with WAL mode enabled."""
        conn = sqlite3.connect(str(self.cache_db), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        return conn

    def _init_db(self, conn: sqlite3.Connection) -> None:
        """Initialize database schema."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS guid_cache (
                guid TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                mtime REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_path ON guid_cache(path);
        """
        )
        conn.commit()

    def _needs_full_rebuild(
        self,
        current_package_versions: dict[str, str],
        include_packages: bool,
    ) -> bool:
        """Check if cache needs full rebuild."""
        if not self.cache_db.exists():
            return True

        try:
            with self._db_lock, self._get_db_connection() as conn:
                cursor = conn.execute("SELECT value FROM metadata WHERE key = 'version'")
                row = cursor.fetchone()
                if not row or int(row[0]) != CACHE_VERSION:
                    return True

                cursor = conn.execute("SELECT value FROM metadata WHERE key = 'include_packages'")
                row = cursor.fetchone()
                if not row or (row[0] == "1") != include_packages:
                    return True

                cursor = conn.execute("SELECT value FROM metadata WHERE key = 'package_versions'")
                row = cursor.fetchone()
                cached_versions = json.loads(row[0]) if row else {}
                if cached_versions != current_package_versions:
                    return True

                return False
        except (sqlite3.Error, ValueError, json.JSONDecodeError):
            return True

    def _save_to_db(
        self,
        db_entries: list[tuple[str, str, float]],
        package_versions: dict[str, str],
        include_packages: bool,
    ) -> None:
        """Save cache to SQLite database.

        Args:
            db_entries: List of (guid, path_str, mtime) tuples
            package_versions: Dict of package name -> version
            include_packages: Whether packages were included in scan
        """
        try:
            with self._db_lock, self._get_db_connection() as conn:
                self._init_db(conn)

                # Clear existing data
                conn.execute("DELETE FROM guid_cache")
                conn.execute("DELETE FROM metadata")

                # Save metadata
                conn.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("version", str(CACHE_VERSION)))
                conn.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)",
                    ("include_packages", "1" if include_packages else "0"),
                )
                conn.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)",
                    ("package_versions", json.dumps(package_versions)),
                )

                # Batch insert GUIDs with mtime (already calculated during scan)
                conn.executemany("INSERT OR REPLACE INTO guid_cache (guid, path, mtime) VALUES (?, ?, ?)", db_entries)
                conn.commit()
        except sqlite3.Error:
            pass  # Ignore cache write errors

    def _load_from_db(self) -> GUIDIndex | None:
        """Load cache from SQLite database."""
        if not self.cache_db.exists():
            return None

        try:
            index = GUIDIndex(project_root=self.project_root)
            with self._db_lock, self._get_db_connection() as conn:
                cursor = conn.execute("SELECT guid, path FROM guid_cache")
                for guid, path_str in cursor:
                    path = Path(path_str)
                    index.guid_to_path[guid] = path
                    index.path_to_guid[path] = guid
            return index
        except sqlite3.Error:
            return None

    def _incremental_update(
        self,
        include_packages: bool,
        progress_callback: ProgressCallback = None,
        max_workers: int | None = None,
    ) -> GUIDIndex:
        """Perform incremental cache update based on mtime changes."""
        # Load existing cache
        index = self._load_from_db()
        if index is None:
            index, _ = self._build_full_index(
                include_packages,
                progress_callback=progress_callback,
                max_workers=max_workers,
            )
            return index

        # Get all meta files and their current mtimes
        meta_files = self._collect_meta_files(include_packages)
        total = len(meta_files)

        # Load cached mtimes
        cached_mtimes: dict[str, float] = {}
        try:
            with self._db_lock, self._get_db_connection() as conn:
                cursor = conn.execute("SELECT path, mtime FROM guid_cache")
                for path_str, mtime in cursor:
                    cached_mtimes[path_str] = mtime
        except sqlite3.Error:
            pass

        # Find files that need updating (new, modified, or deleted)
        current_paths = set()
        files_to_process: list[Path] = []

        for meta_path in meta_files:
            asset_path = meta_path.with_suffix("")
            try:
                rel_path = asset_path.relative_to(self.project_root)
            except ValueError:
                rel_path = asset_path

            path_str = str(rel_path)
            current_paths.add(path_str)

            try:
                current_mtime = meta_path.stat().st_mtime
            except OSError:
                continue

            cached_mtime = cached_mtimes.get(path_str, -1)
            if current_mtime != cached_mtime:
                files_to_process.append(meta_path)

        # Find deleted files
        deleted_paths = set(cached_mtimes.keys()) - current_paths

        # If too many changes, do full rebuild
        change_ratio = (len(files_to_process) + len(deleted_paths)) / max(total, 1)
        if change_ratio > 0.3:  # More than 30% changed
            index, _ = self._build_full_index(
                include_packages,
                progress_callback=progress_callback,
                max_workers=max_workers,
            )
            return index

        # Process changed files
        db_updates: list[tuple[str, str, float]] = []
        if files_to_process:
            updates = self._parse_meta_files(
                files_to_process,
                progress_callback=progress_callback,
                max_workers=max_workers,
            )

            # Update index and collect DB entries
            for guid, path, mtime in updates:
                # Remove old entry if guid changed for this path
                old_guid = index.path_to_guid.get(path)
                if old_guid and old_guid != guid:
                    del index.guid_to_path[old_guid]

                index.guid_to_path[guid] = path
                index.path_to_guid[path] = guid
                db_updates.append((guid, str(path), mtime))

        # Remove deleted files from index
        for path_str in deleted_paths:
            path = Path(path_str)
            if path in index.path_to_guid:
                guid = index.path_to_guid.pop(path)
                if guid in index.guid_to_path:
                    del index.guid_to_path[guid]

        # Update cache with changes
        self._update_db_entries(db_updates, deleted_paths)

        return index

    def _update_db_entries(
        self,
        db_updates: list[tuple[str, str, float]],
        deleted_paths: set[str],
    ) -> None:
        """Update specific database entries.

        Args:
            db_updates: List of (guid, path_str, mtime) tuples to upsert
            deleted_paths: Set of path strings to delete
        """
        try:
            with self._db_lock, self._get_db_connection() as conn:
                # Delete removed entries
                if deleted_paths:
                    placeholders = ",".join("?" * len(deleted_paths))
                    conn.execute(f"DELETE FROM guid_cache WHERE path IN ({placeholders})", list(deleted_paths))

                # Update changed entries (already have mtime from parse)
                if db_updates:
                    conn.executemany(
                        "INSERT OR REPLACE INTO guid_cache (guid, path, mtime) VALUES (?, ?, ?)", db_updates
                    )

                conn.commit()
        except sqlite3.Error:
            pass

    def _collect_meta_files(self, include_packages: bool) -> list[Path]:
        """Collect all .meta files from relevant directories.

        Scans:
        - Assets/ folder (always)
        - Packages/ folder (always, for embedded packages)
        - Library/PackageCache/ (when include_packages=True, for registry packages)
        - Local package paths from manifest.json file: references (when include_packages=True)
        """
        meta_files: list[Path] = []

        # Scan Assets folder
        assets_dir = self.project_root / "Assets"
        if assets_dir.is_dir():
            meta_files.extend(assets_dir.rglob("*.meta"))

        # Scan Packages folder (embedded packages)
        packages_dir = self.project_root / "Packages"
        if packages_dir.is_dir():
            meta_files.extend(packages_dir.rglob("*.meta"))

        # Scan Library/PackageCache (downloaded packages from Unity registry)
        if include_packages:
            package_cache_dir = self.project_root / "Library" / "PackageCache"
            if package_cache_dir.is_dir():
                meta_files.extend(package_cache_dir.rglob("*.meta"))

            # Scan local packages referenced via file: in manifest.json
            # e.g., "file:../../NK.Packages/com.domybest.mybox@1.7.0"
            local_package_paths = self._get_local_package_paths()
            for package_path in local_package_paths:
                if package_path.is_dir():
                    meta_files.extend(package_path.rglob("*.meta"))

        return meta_files

    def _get_local_package_paths(self) -> list[Path]:
        """Get paths to local packages referenced via file: in manifest.json.

        Uses the shared get_local_package_paths() utility function.

        Returns:
            List of resolved absolute paths to local package directories.
        """
        return get_local_package_paths(self.project_root)

    def _parse_meta_files_sequential(
        self,
        meta_files: list[Path],
        progress_callback: ProgressCallback = None,
    ) -> list[tuple[str, Path, float]]:
        """Parse meta files sequentially (faster for local storage).

        Args:
            meta_files: List of .meta file paths to parse
            progress_callback: Optional callback for progress (current, total)

        Returns:
            List of (guid, path, mtime) tuples
        """
        if not meta_files:
            return []

        results: list[tuple[str, Path, float]] = []
        total = len(meta_files)

        for i, meta_path in enumerate(meta_files):
            if progress_callback:
                progress_callback(i + 1, total)

            result = _parse_meta_file(meta_path, self.project_root)
            if result:
                results.append(result)

        return results

    def _parse_meta_files_parallel(
        self,
        meta_files: list[Path],
        progress_callback: ProgressCallback = None,
        max_workers: int | None = None,
    ) -> list[tuple[str, Path, float]]:
        """Parse meta files in parallel using ThreadPoolExecutor.

        Note: Parallel processing has significant overhead and is only
        beneficial for network storage or very slow disks. For local SSDs,
        sequential processing is typically 2-3x faster.

        Args:
            meta_files: List of .meta file paths to parse
            progress_callback: Optional callback for progress (current, total)
            max_workers: Max threads (default: min(32, cpu_count + 4))

        Returns:
            List of (guid, path, mtime) tuples
        """
        if not meta_files:
            return []

        results: list[tuple[str, Path, float]] = []
        total = len(meta_files)
        completed = 0

        if max_workers is None:
            max_workers = min(32, (os.cpu_count() or 1) + 4)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_parse_meta_file, meta_path, self.project_root): meta_path for meta_path in meta_files
            }

            for future in as_completed(futures):
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

                result = future.result()
                if result:
                    results.append(result)

        return results

    def _parse_meta_files(
        self,
        meta_files: list[Path],
        progress_callback: ProgressCallback = None,
        max_workers: int | None = None,
    ) -> list[tuple[str, Path, float]]:
        """Parse meta files with automatic strategy selection.

        Uses sequential processing by default (faster for local storage).
        Set max_workers > 1 to force parallel processing (useful for network storage).

        Args:
            meta_files: List of .meta file paths to parse
            progress_callback: Optional callback for progress (current, total)
            max_workers: Set to > 1 to force parallel processing

        Returns:
            List of (guid, path, mtime) tuples
        """
        # Use parallel only if explicitly requested with max_workers > 1
        if max_workers is not None and max_workers > 1:
            return self._parse_meta_files_parallel(
                meta_files,
                progress_callback=progress_callback,
                max_workers=max_workers,
            )

        # Default: sequential processing (faster for local storage)
        return self._parse_meta_files_sequential(
            meta_files,
            progress_callback=progress_callback,
        )

    def _build_full_index(
        self,
        include_packages: bool,
        progress_callback: ProgressCallback = None,
        max_workers: int | None = None,
    ) -> tuple[GUIDIndex, list[tuple[str, str, float]]]:
        """Build full GUID index by scanning directories.

        Returns:
            Tuple of (GUIDIndex, list of (guid, path_str, mtime) for DB save)
        """
        index = GUIDIndex(project_root=self.project_root)

        # Collect all meta files
        meta_files = self._collect_meta_files(include_packages)

        # Parse files (sequential by default, parallel if max_workers > 1)
        results = self._parse_meta_files(
            meta_files,
            progress_callback=progress_callback,
            max_workers=max_workers,
        )

        # Build index and DB entries from results
        db_entries: list[tuple[str, str, float]] = []
        for guid, path, mtime in results:
            index.guid_to_path[guid] = path
            index.path_to_guid[path] = guid
            db_entries.append((guid, str(path), mtime))

        return index, db_entries

    def _get_package_versions(self) -> dict[str, str]:
        """Get installed package versions from Library/PackageCache and manifest.json.

        Includes:
        - Registry packages from Library/PackageCache (e.g., "com.unity.ugui@1.0.0")
        - Local packages from manifest.json file: references (e.g., "file:../../path@1.0.0")

        This ensures cache invalidation when any package changes.
        """
        versions = {}

        # Get versions from Library/PackageCache (registry packages)
        package_cache_dir = self.project_root / "Library" / "PackageCache"
        if package_cache_dir.is_dir():
            # Parse directory names like "com.unity.ugui@1.0.0"
            for entry in package_cache_dir.iterdir():
                if entry.is_dir() and "@" in entry.name:
                    parts = entry.name.rsplit("@", 1)
                    if len(parts) == 2:
                        package_name, version = parts
                        versions[package_name] = version

        # Get versions from manifest.json file: references (local packages)
        manifest_path = self.project_root / "Packages" / "manifest.json"
        if manifest_path.exists():
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                dependencies = manifest_data.get("dependencies", {})

                for dep_name, dep_value in dependencies.items():
                    if isinstance(dep_value, str) and dep_value.startswith("file:"):
                        # Use the full file: path as "version" to detect changes
                        # e.g., "file:../../NK.Packages/pkg@1.0.0" -> track the whole path
                        versions[f"local:{dep_name}"] = dep_value
            except (OSError, json.JSONDecodeError):
                pass

        return versions


def get_cached_guid_index(
    project_root: Path,
    include_packages: bool = True,
    progress_callback: ProgressCallback = None,
    max_workers: int | None = None,
) -> GUIDIndex:
    """Get GUID index with SQLite caching support.

    This is the recommended way to get a GUID index for performance.
    Uses SQLite with WAL mode for:
    - Faster queries for large projects (170k+ assets)
    - Better concurrent read/write access
    - Incremental updates based on file mtime (only re-parse changed files)

    Performance characteristics:
    - First run: Scans all .meta files and builds SQLite cache
    - Subsequent runs: Loads from cache (~2x faster than rescan)
    - Incremental updates: Only processes changed files (~1.5x faster)

    Args:
        project_root: Path to Unity project root
        include_packages: Whether to include Library/PackageCache/
        progress_callback: Optional callback for progress (current, total)
        max_workers: Set to > 1 to force parallel processing
                     (only useful for network storage; local SSDs are faster sequential)

    Returns:
        GUIDIndex with GUID to path mappings
    """
    cache = CachedGUIDIndex(project_root=project_root)
    return cache.get_index(
        include_packages=include_packages,
        progress_callback=progress_callback,
        max_workers=max_workers,
    )


# ============================================================================
# Lazy GUID Index (Memory-Optimized)
# ============================================================================


@dataclass
class LazyGUIDIndex:
    """Memory-efficient GUID index that queries SQLite directly.

    Unlike GUIDIndex which loads all entries into memory, LazyGUIDIndex
    queries the SQLite database on-demand. This is ideal for large projects
    (170k+ assets) where loading the entire index would be slow and
    memory-intensive.

    Features:
    - O(1) initialization (no upfront loading)
    - O(log N) lookups via SQLite index
    - Optional LRU cache for frequently accessed GUIDs
    - Compatible with GUIDIndex API

    Performance characteristics:
    - Initial loading: O(1) vs O(N) for GUIDIndex
    - Memory usage: O(cache_size) vs O(N) for GUIDIndex
    - Lookup: O(log N) database query vs O(1) dict lookup
    - For typical usage patterns where only a subset of GUIDs are accessed,
      LazyGUIDIndex provides better overall performance.

    Example:
        >>> # Use lazy index for memory efficiency
        >>> lazy_index = get_lazy_guid_index("/path/to/unity/project")
        >>> path = lazy_index.get_path("f4afdcb1cbadf954ba8b1cf465429e17")
        >>> print(path)  # Assets/Scripts/PlayerController.cs
    """

    project_root: Path
    _db_path: Path = field(init=False)
    _conn: sqlite3.Connection | None = field(default=None, repr=False)
    _cache: dict[str, Path] = field(default_factory=dict, repr=False)
    _reverse_cache: dict[Path, str] = field(default_factory=dict, repr=False)
    _cache_size: int = field(default=1000, repr=False)
    _db_lock: Lock = field(default_factory=Lock, repr=False)

    def __post_init__(self) -> None:
        self._db_path = self.project_root / CACHE_DIR_NAME / CACHE_DB_NAME

    def __len__(self) -> int:
        """Return the total number of entries in the database."""
        if not self._db_path.exists():
            return 0
        try:
            with self._db_lock:
                conn = self._get_connection()
                cursor = conn.execute("SELECT COUNT(*) FROM guid_cache")
                row = cursor.fetchone()
                return row[0] if row else 0
        except sqlite3.Error:
            return 0

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), timeout=30.0)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-16000")  # 16MB cache
        return self._conn

    def _add_to_cache(self, guid: str, path: Path) -> None:
        """Add entry to LRU cache, evicting oldest if necessary."""
        if len(self._cache) >= self._cache_size:
            # Simple LRU: remove oldest entry (first inserted)
            oldest_guid = next(iter(self._cache))
            oldest_path = self._cache.pop(oldest_guid)
            self._reverse_cache.pop(oldest_path, None)

        self._cache[guid] = path
        self._reverse_cache[path] = guid

    def get_path(self, guid: str) -> Path | None:
        """Get the asset path for a GUID.

        Checks LRU cache first, then queries SQLite database.

        Args:
            guid: The GUID to look up

        Returns:
            Asset path, or None if not found
        """
        # Check cache first
        if guid in self._cache:
            # Move to end for LRU behavior (re-insert)
            path = self._cache.pop(guid)
            self._cache[guid] = path
            return path

        # Query database
        if not self._db_path.exists():
            return None

        try:
            with self._db_lock:
                conn = self._get_connection()
                cursor = conn.execute("SELECT path FROM guid_cache WHERE guid = ?", (guid,))
                row = cursor.fetchone()
                if row:
                    path = Path(row[0])
                    self._add_to_cache(guid, path)
                    return path
        except sqlite3.Error:
            pass

        return None

    def get_guid(self, path: Path) -> str | None:
        """Get the GUID for an asset path.

        Args:
            path: The asset path to look up

        Returns:
            GUID string, or None if not found
        """
        # Try both absolute and relative paths
        paths_to_check = [path]

        # Try resolving relative to project root
        if self.project_root:
            try:
                rel_path = path.relative_to(self.project_root)
                paths_to_check.append(rel_path)
            except ValueError:
                pass

        # Check cache first
        for p in paths_to_check:
            if p in self._reverse_cache:
                return self._reverse_cache[p]

        # Query database
        if not self._db_path.exists():
            return None

        try:
            with self._db_lock:
                conn = self._get_connection()
                for p in paths_to_check:
                    cursor = conn.execute("SELECT guid FROM guid_cache WHERE path = ?", (str(p),))
                    row = cursor.fetchone()
                    if row:
                        guid = row[0]
                        self._add_to_cache(guid, p)
                        return guid
        except sqlite3.Error:
            pass

        return None

    def resolve_name(self, guid: str) -> str | None:
        """Resolve a GUID to an asset name (filename without extension).

        This is particularly useful for resolving MonoBehaviour script names
        from their m_Script GUID references.

        Args:
            guid: The GUID to resolve

        Returns:
            The asset name (stem), or None if GUID is not found
        """
        path = self.get_path(guid)
        if path is not None:
            return path.stem
        return None

    def resolve_path(self, guid: str) -> Path | None:
        """Resolve a GUID to an asset path.

        Alias for get_path() with a more descriptive name for LLM usage.

        Args:
            guid: The GUID to resolve

        Returns:
            The asset path, or None if GUID is not found
        """
        return self.get_path(guid)

    def batch_resolve_names(self, guids: set[str]) -> dict[str, str]:
        """Batch resolve multiple GUIDs to asset names using a single SQL query.

        This is significantly faster than calling resolve_name() repeatedly
        when processing many components (e.g., in build_hierarchy).

        Performance: O(1) query instead of O(N) individual queries.
        Typical improvement: 1600ms -> 80ms for large prefabs with 100+ components.

        Args:
            guids: Set of GUIDs to resolve

        Returns:
            Dict mapping GUID to asset name (filename without extension).
            GUIDs that couldn't be resolved are omitted from the result.

        Example:
            >>> names = lazy_index.batch_resolve_names({"abc123...", "def456..."})
            >>> print(names)  # {"abc123...": "PlayerController", "def456...": "EnemyAI"}
        """
        if not guids:
            return {}

        result: dict[str, str] = {}

        # First check cache for already-resolved GUIDs
        uncached_guids: list[str] = []
        for guid in guids:
            if guid in self._cache:
                path = self._cache[guid]
                result[guid] = path.stem
            else:
                uncached_guids.append(guid)

        # If all GUIDs were cached, return early
        if not uncached_guids:
            return result

        # Query database for uncached GUIDs
        if not self._db_path.exists():
            return result

        try:
            with self._db_lock:
                conn = self._get_connection()
                # Use batched queries to avoid SQL variable limit (SQLite default 999)
                batch_size = 500
                for i in range(0, len(uncached_guids), batch_size):
                    batch = uncached_guids[i : i + batch_size]
                    placeholders = ",".join("?" * len(batch))
                    cursor = conn.execute(
                        f"SELECT guid, path FROM guid_cache WHERE guid IN ({placeholders})",
                        batch,
                    )
                    for guid, path_str in cursor:
                        path = Path(path_str)
                        # Add to cache
                        self._add_to_cache(guid, path)
                        result[guid] = path.stem
        except sqlite3.Error:
            pass

        return result

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def clear_cache(self) -> None:
        """Clear the in-memory LRU cache."""
        self._cache.clear()
        self._reverse_cache.clear()

    def __del__(self) -> None:
        """Clean up database connection on deletion."""
        self.close()


def get_lazy_guid_index(
    project_root: Path,
    include_packages: bool = True,
    progress_callback: ProgressCallback = None,
    max_workers: int | None = None,
    cache_size: int = 1000,
) -> LazyGUIDIndex:
    """Get a memory-efficient lazy GUID index.

    This function ensures the SQLite cache exists (building it if necessary)
    and returns a LazyGUIDIndex that queries the database on-demand.

    This is the recommended approach for large projects (170k+ assets)
    where loading the entire index into memory would be slow.

    Performance comparison with get_cached_guid_index():
    - Initial loading: O(1) vs O(N) - LazyGUIDIndex is instant
    - Memory usage: O(cache_size) vs O(N) - LazyGUIDIndex uses minimal memory
    - Lookup: O(log N) vs O(1) - GUIDIndex is faster for individual lookups
    - Overall: LazyGUIDIndex is better when accessing a subset of GUIDs

    Args:
        project_root: Path to Unity project root
        include_packages: Whether to include Library/PackageCache/
        progress_callback: Optional callback for progress during cache build
        max_workers: Set to > 1 to force parallel processing during cache build
        cache_size: Maximum number of entries to keep in memory cache (default: 1000)

    Returns:
        LazyGUIDIndex for memory-efficient GUID lookups

    Example:
        >>> lazy_index = get_lazy_guid_index("/path/to/unity/project")
        >>> path = lazy_index.get_path("f4afdcb1cbadf954ba8b1cf465429e17")
        >>> name = lazy_index.resolve_name("f4afdcb1cbadf954ba8b1cf465429e17")
    """
    project_root = Path(project_root)
    cache_db = project_root / CACHE_DIR_NAME / CACHE_DB_NAME

    # Ensure cache exists
    if not cache_db.exists():
        # Build the cache first
        cache = CachedGUIDIndex(project_root=project_root)
        cache.get_index(
            include_packages=include_packages,
            progress_callback=progress_callback,
            max_workers=max_workers,
        )

    # Create lazy index
    lazy_index = LazyGUIDIndex(project_root=project_root)
    lazy_index._cache_size = cache_size
    return lazy_index
