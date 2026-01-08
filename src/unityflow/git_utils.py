"""Git utilities for incremental normalization.

Provides functions to detect changed Unity files based on git status or commit history.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

# Unity YAML file extensions that can be normalized
# Core assets
UNITY_CORE_EXTENSIONS = {
    ".prefab",  # Prefab files
    ".unity",  # Scene files
    ".asset",  # ScriptableObject and generic assets
}

# Animation & control
UNITY_ANIMATION_EXTENSIONS = {
    ".anim",  # Animation clips
    ".controller",  # Animator Controller
    ".overrideController",  # Animator Override Controller
    ".playable",  # Playable assets (Timeline, etc.)
    ".mask",  # Avatar masks
    ".signal",  # Timeline Signal assets
}

# Materials & rendering
UNITY_RENDERING_EXTENSIONS = {
    ".mat",  # Materials
    ".renderTexture",  # Render Textures
    ".flare",  # Lens flare assets
    ".shadervariants",  # Shader variant collections
    ".spriteatlas",  # Sprite atlases
    ".cubemap",  # Cubemap assets
}

# Physics
UNITY_PHYSICS_EXTENSIONS = {
    ".physicMaterial",  # 3D Physics materials
    ".physicsMaterial2D",  # 2D Physics materials
}

# Terrain
UNITY_TERRAIN_EXTENSIONS = {
    ".terrainlayer",  # Terrain layer assets
    ".brush",  # Terrain brush assets
}

# Audio
UNITY_AUDIO_EXTENSIONS = {
    ".mixer",  # Audio Mixer assets
}

# UI & Editor
UNITY_UI_EXTENSIONS = {
    ".guiskin",  # GUI Skin assets
    ".fontsettings",  # Font settings
    ".preset",  # Presets
    ".giparams",  # Global Illumination parameters
}

# All Unity YAML extensions combined
UNITY_EXTENSIONS = (
    UNITY_CORE_EXTENSIONS
    | UNITY_ANIMATION_EXTENSIONS
    | UNITY_RENDERING_EXTENSIONS
    | UNITY_PHYSICS_EXTENSIONS
    | UNITY_TERRAIN_EXTENSIONS
    | UNITY_AUDIO_EXTENSIONS
    | UNITY_UI_EXTENSIONS
)


def get_repo_root(path: Path | None = None) -> Path | None:
    """Get the root directory of the git repository.

    Args:
        path: Starting path to search from (default: current directory)

    Returns:
        Path to repository root, or None if not in a git repository
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def is_git_repository(path: Path | None = None) -> bool:
    """Check if the given path is inside a git repository.

    Args:
        path: Path to check (default: current directory)

    Returns:
        True if inside a git repository
    """
    return get_repo_root(path) is not None


def get_changed_files(
    extensions: Sequence[str] | None = None,
    staged_only: bool = False,
    include_untracked: bool = True,
    cwd: Path | None = None,
) -> list[Path]:
    """Get list of changed files from git status.

    Args:
        extensions: File extensions to filter (default: Unity extensions)
        staged_only: Only include staged files
        include_untracked: Include untracked files
        cwd: Working directory (default: current directory)

    Returns:
        List of paths to changed files
    """
    if extensions is None:
        extensions = list(UNITY_EXTENSIONS)

    repo_root = get_repo_root(cwd)
    if repo_root is None:
        return []

    changed_files: list[Path] = []

    # Get staged and unstaged changes
    # --porcelain=v1 gives stable, parseable output
    # -uall shows individual files in untracked directories (not just directory names)
    cmd = ["git", "status", "--porcelain=v1"]
    if include_untracked:
        cmd.append("-uall")
    else:
        cmd.append("--untracked-files=no")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []

    for line in result.stdout.split("\n"):
        if not line or len(line) < 4:
            continue

        # Porcelain format: XY filename (XY = 2 chars, space, then filename)
        # X = index status, Y = worktree status
        status_index = line[0]
        status_worktree = line[1]
        # Skip the space at position 2, filename starts at position 3
        filepath = line[3:]

        # Handle renames: "R  old -> new"
        if " -> " in filepath:
            filepath = filepath.split(" -> ")[1]

        # Filter by staged_only
        if staged_only:
            # Only include if index has changes (X is not ' ' or '?')
            if status_index in (" ", "?"):
                continue
        else:
            # Include both staged and unstaged, but not deleted
            if status_index == "D" or status_worktree == "D":
                continue

        file_path = repo_root / filepath

        # Filter by extension
        if file_path.suffix.lower() in extensions:
            if file_path.exists():
                changed_files.append(file_path)

    return changed_files


def get_files_changed_since(
    ref: str,
    extensions: Sequence[str] | None = None,
    cwd: Path | None = None,
) -> list[Path]:
    """Get list of files changed since a git reference (commit, tag, branch).

    Args:
        ref: Git reference (e.g., "HEAD~5", "main", "v1.0.0")
        extensions: File extensions to filter (default: Unity extensions)
        cwd: Working directory (default: current directory)

    Returns:
        List of paths to changed files
    """
    if extensions is None:
        extensions = list(UNITY_EXTENSIONS)

    repo_root = get_repo_root(cwd)
    if repo_root is None:
        return []

    # Get files changed between ref and HEAD
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref, "HEAD"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []

    changed_files: list[Path] = []

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        file_path = repo_root / line

        # Filter by extension
        if file_path.suffix.lower() in extensions:
            if file_path.exists():
                changed_files.append(file_path)

    return changed_files


def get_files_in_commit(
    commit: str,
    extensions: Sequence[str] | None = None,
    cwd: Path | None = None,
) -> list[Path]:
    """Get list of files changed in a specific commit.

    Args:
        commit: Git commit hash or reference
        extensions: File extensions to filter (default: Unity extensions)
        cwd: Working directory (default: current directory)

    Returns:
        List of paths to changed files
    """
    if extensions is None:
        extensions = list(UNITY_EXTENSIONS)

    repo_root = get_repo_root(cwd)
    if repo_root is None:
        return []

    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []

    changed_files: list[Path] = []

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        file_path = repo_root / line

        # Filter by extension
        if file_path.suffix.lower() in extensions:
            if file_path.exists():
                changed_files.append(file_path)

    return changed_files


def filter_unity_files(
    paths: Sequence[Path],
    extensions: Sequence[str] | None = None,
) -> list[Path]:
    """Filter paths to only include Unity YAML files.

    Args:
        paths: List of paths to filter
        extensions: File extensions to include (default: Unity extensions)

    Returns:
        Filtered list of paths
    """
    if extensions is None:
        extensions = list(UNITY_EXTENSIONS)

    return [p for p in paths if p.suffix.lower() in extensions and p.exists()]
