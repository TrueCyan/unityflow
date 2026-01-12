"""Command-line interface for unityflow.

Provides commands for normalizing, diffing, and validating Unity YAML files.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click

from unityflow import __version__
from unityflow.asset_tracker import (
    find_unity_project_root,
)
from unityflow.git_utils import (
    get_changed_files,
    get_files_changed_since,
    get_repo_root,
    is_git_repository,
)
from unityflow.normalizer import UnityPrefabNormalizer
from unityflow.parser import UnityYAMLDocument
from unityflow.validator import PrefabValidator


def _normalize_single_file(args: tuple) -> tuple[Path, bool, str]:
    """Normalize a single file (for parallel processing).

    Args:
        args: Tuple of (file_path, normalizer_kwargs)

    Returns:
        Tuple of (file_path, success, message)
    """
    file_path, kwargs = args
    try:
        normalizer = UnityPrefabNormalizer(**kwargs)
        content = normalizer.normalize_file(file_path)
        file_path.write_text(content, encoding="utf-8", newline="\n")
        return (file_path, True, "")
    except Exception as e:
        return (file_path, False, str(e))


def create_progress_bar(
    total: int,
    label: str = "Processing",
    show_eta: bool = True,
) -> tuple[Callable[[int, int], None], Callable[[], None]]:
    """Create a progress bar and return update/close callbacks.

    Args:
        total: Total number of items
        label: Progress bar label
        show_eta: Whether to show ETA

    Returns:
        Tuple of (update_callback, close_callback)
    """
    bar = click.progressbar(
        length=total,
        label=label,
        show_eta=show_eta,
        show_percent=True,
    )
    bar.__enter__()

    def update(current: int, total: int) -> None:
        bar.update(1)

    def close() -> None:
        bar.__exit__(None, None, None)

    return update, close


@click.group()
@click.version_option(version=__version__, prog_name="unityflow")
def main() -> None:
    """Unity YAML Deterministic Serializer.

    A tool for canonical serialization of Unity YAML files (.prefab, .unity,
    .asset, etc.) to eliminate non-deterministic changes and reduce VCS noise.
    """
    pass


@main.command()
@click.argument("input_files", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (only for single file, default: overwrite input)",
)
@click.option(
    "--stdout",
    is_flag=True,
    help="Write to stdout instead of file (only for single file)",
)
@click.option(
    "--changed-only",
    is_flag=True,
    help="Normalize only files changed in git working tree",
)
@click.option(
    "--staged-only",
    is_flag=True,
    help="Normalize only staged files (use with --changed-only)",
)
@click.option(
    "--since",
    "since_ref",
    type=str,
    help="Normalize files changed since git reference (e.g., HEAD~5, main, v1.0)",
)
@click.option(
    "--pattern",
    type=str,
    help="Filter files by glob pattern (e.g., 'Assets/Prefabs/**/*.prefab')",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show files that would be normalized without making changes",
)
@click.option(
    "--hex-floats",
    is_flag=True,
    help="Use IEEE 754 hex format for floats (lossless)",
)
@click.option(
    "--precision",
    type=int,
    default=6,
    help="Decimal precision for float normalization (default: 6)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format (default: yaml)",
)
@click.option(
    "--progress",
    is_flag=True,
    help="Show progress bar for batch processing",
)
@click.option(
    "--parallel",
    "-j",
    "parallel_jobs",
    type=int,
    default=1,
    help="Number of parallel jobs for batch processing (default: 1)",
)
@click.option(
    "--in-place",
    is_flag=True,
    help="Modify files in place (same as not specifying -o)",
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, path_type=Path),
    help="Unity project root for script resolution (auto-detected if not specified)",
)
def normalize(
    input_files: tuple[Path, ...],
    output: Path | None,
    stdout: bool,
    changed_only: bool,
    staged_only: bool,
    since_ref: str | None,
    pattern: str | None,
    dry_run: bool,
    hex_floats: bool,
    precision: int,
    output_format: str,
    progress: bool,
    parallel_jobs: int,
    in_place: bool,
    project_root: Path | None,
) -> None:
    """Normalize Unity YAML files for deterministic serialization.

    INPUT_FILES are paths to .prefab, .unity, .asset, or other Unity YAML files.

    Examples:

        # Normalize in place
        unityflow normalize Player.prefab
        unityflow normalize MainScene.unity
        unityflow normalize GameConfig.asset

        # Normalize multiple files
        unityflow normalize *.prefab *.unity *.asset

        # Normalize to a new file
        unityflow normalize Player.prefab -o Player.normalized.prefab

        # Output to stdout
        unityflow normalize Player.prefab --stdout

    Incremental normalization (requires git):

        # Normalize changed files only
        unityflow normalize --changed-only

        # Normalize staged files only
        unityflow normalize --changed-only --staged-only

        # Normalize files changed since a commit
        unityflow normalize --since HEAD~5

        # Normalize files changed since a branch
        unityflow normalize --since main

        # Filter by pattern
        unityflow normalize --changed-only --pattern "Assets/**/*.unity"

        # Dry run to see what would be normalized
        unityflow normalize --changed-only --dry-run

    Script-based field sync (auto-enabled when project root is found):

        # With explicit project root for script resolution
        unityflow normalize Player.prefab --project-root /path/to/unity/project
    """
    # Collect files to normalize
    files_to_normalize: list[Path] = []

    # Git-based file selection
    if changed_only or since_ref:
        if not is_git_repository():
            click.echo("Error: Not in a git repository", err=True)
            sys.exit(1)

        if changed_only:
            files_to_normalize = get_changed_files(
                staged_only=staged_only,
                include_untracked=not staged_only,
            )
        elif since_ref:
            files_to_normalize = get_files_changed_since(since_ref)

        # Apply pattern filter (use PurePath.match for glob-style patterns)
        if pattern and files_to_normalize:
            repo_root = get_repo_root()
            filtered = []
            for f in files_to_normalize:
                try:
                    rel_path = f.relative_to(repo_root) if repo_root else f
                    # PurePath.match supports ** glob patterns
                    if rel_path.match(pattern):
                        filtered.append(f)
                except ValueError:
                    pass
            files_to_normalize = filtered

    # Explicit file arguments
    if input_files:
        explicit_files = list(input_files)
        # Apply pattern filter to explicit files too
        if pattern:
            explicit_files = [f for f in explicit_files if f.match(pattern)]
        files_to_normalize.extend(explicit_files)

    # No files to process
    if not files_to_normalize:
        if changed_only:
            click.echo("No changed Unity files found")
        elif since_ref:
            click.echo(f"No changed Unity files since {since_ref}")
        else:
            click.echo("Error: No input files specified", err=True)
            click.echo("Use --changed-only, --since, or provide file paths", err=True)
            sys.exit(1)
        return

    # Remove duplicates and sort
    files_to_normalize = sorted(set(files_to_normalize))

    # Dry run mode
    if dry_run:
        click.echo(f"Would normalize {len(files_to_normalize)} file(s):")
        for f in files_to_normalize:
            click.echo(f"  {f}")
        return

    # Validate options for batch mode
    if len(files_to_normalize) > 1:
        if output:
            click.echo("Error: --output cannot be used with multiple files", err=True)
            sys.exit(1)
        if stdout:
            click.echo("Error: --stdout cannot be used with multiple files", err=True)
            sys.exit(1)

    if output_format == "json":
        click.echo("Error: JSON format not yet implemented", err=True)
        sys.exit(1)

    normalizer_kwargs = {
        "use_hex_floats": hex_floats,
        "float_precision": precision,
        "project_root": project_root,
    }

    normalizer = UnityPrefabNormalizer(**normalizer_kwargs)

    # Process files
    success_count = 0
    error_count = 0

    # Parallel processing for batch mode
    if parallel_jobs > 1 and len(files_to_normalize) > 1 and not stdout and not output:
        file_count = len(files_to_normalize)
        click.echo(f"Processing {file_count} files with {parallel_jobs} parallel workers...")

        tasks = [(f, normalizer_kwargs) for f in files_to_normalize]

        with ProcessPoolExecutor(max_workers=parallel_jobs) as executor:
            futures = {executor.submit(_normalize_single_file, task): task[0] for task in tasks}

            if progress:
                with click.progressbar(
                    length=len(files_to_normalize),
                    label="Normalizing",
                    show_eta=True,
                    show_percent=True,
                ) as bar:
                    for future in as_completed(futures):
                        file_path, success, error_msg = future.result()
                        if success:
                            success_count += 1
                        else:
                            error_count += 1
                            click.echo(f"\nError: {file_path}: {error_msg}", err=True)
                        bar.update(1)
            else:
                for future in as_completed(futures):
                    file_path, success, error_msg = future.result()
                    if success:
                        success_count += 1
                        click.echo(f"Normalized: {file_path}")
                    else:
                        error_count += 1
                        click.echo(f"Error: {file_path}: {error_msg}", err=True)

    # Sequential processing
    else:
        if progress and len(files_to_normalize) > 1:
            files_iter = click.progressbar(
                files_to_normalize,
                label="Normalizing",
                show_eta=True,
                show_percent=True,
            )
        else:
            files_iter = files_to_normalize

        for input_file in files_iter:
            try:
                content = normalizer.normalize_file(input_file)

                if stdout:
                    click.echo(content, nl=False)
                elif output:
                    output.write_text(content, encoding="utf-8", newline="\n")
                    if not progress:
                        click.echo(f"Normalized: {input_file} -> {output}")
                else:
                    input_file.write_text(content, encoding="utf-8", newline="\n")
                    if not progress:
                        click.echo(f"Normalized: {input_file}")

                success_count += 1

            except Exception as e:
                if progress:
                    click.echo(f"\nError: Failed to normalize {input_file}: {e}", err=True)
                else:
                    click.echo(f"Error: Failed to normalize {input_file}: {e}", err=True)
                error_count += 1

    # Summary for batch mode
    if len(files_to_normalize) > 1:
        click.echo()
        click.echo(f"Completed: {success_count} normalized, {error_count} failed")


@main.command()
@click.argument("old_file", type=click.Path(exists=True, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--exit-code",
    is_flag=True,
    help="Exit with 1 if files differ, 0 if identical",
)
def diff(
    old_file: Path,
    new_file: Path,
    exit_code: bool,
) -> None:
    """Show differences between two Unity YAML files.

    Uses semantic diff which compares at property level,
    ignoring fileID changes and document order.

    Examples:

        # Compare two prefabs
        unityflow diff old.prefab new.prefab

        # Exit with status code (for scripts)
        unityflow diff old.prefab new.prefab --exit-code
    """
    from unityflow.semantic_diff import ChangeType, semantic_diff

    try:
        left_doc = UnityYAMLDocument.load(old_file)
        right_doc = UnityYAMLDocument.load(new_file)
    except Exception as e:
        click.echo(f"Error: Failed to load files: {e}", err=True)
        sys.exit(1)

    result = semantic_diff(left_doc, right_doc)

    if result.has_changes:
        # Format semantic diff output
        click.echo(f"--- {old_file}")
        click.echo(f"+++ {new_file}")
        click.echo()

        # Show object changes
        if result.object_changes:
            click.echo("Object Changes:")
            for change in result.object_changes:
                if change.change_type == ChangeType.ADDED:
                    prefix = "+"
                else:
                    prefix = "-"
                name_str = f" ({change.game_object_name})" if change.game_object_name else ""
                click.echo(f"  {prefix} {change.class_name} [fileID: {change.file_id}]{name_str}")
            click.echo()

        # Show property changes grouped by object
        if result.property_changes:
            click.echo("Property Changes:")
            # Group by file_id
            by_object: dict[int, list] = {}
            for change in result.property_changes:
                if change.file_id not in by_object:
                    by_object[change.file_id] = []
                by_object[change.file_id].append(change)

            for file_id, changes in sorted(by_object.items()):
                first = changes[0]
                name_str = f" ({first.game_object_name})" if first.game_object_name else ""
                click.echo(f"  {first.class_name} [fileID: {file_id}]{name_str}:")
                for change in changes:
                    if change.change_type == ChangeType.ADDED:
                        click.echo(f"    + {change.property_path}: {change.new_value}")
                    elif change.change_type == ChangeType.REMOVED:
                        click.echo(f"    - {change.property_path}: {change.old_value}")
                    else:  # MODIFIED
                        click.echo(f"    ~ {change.property_path}: {change.old_value} -> {change.new_value}")
            click.echo()

        # Summary
        click.echo(
            f"Summary: {result.added_count} added, {result.removed_count} removed, " f"{result.modified_count} modified"
        )

        if exit_code:
            sys.exit(1)
    else:
        click.echo("Files are identical")
        if exit_code:
            sys.exit(0)


@main.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Only output errors, suppress info and warnings",
)
def validate(
    files: tuple[Path, ...],
    strict: bool,
    output_format: str,
    quiet: bool,
) -> None:
    """Validate Unity YAML files for structural correctness.

    Checks for:
    - Valid YAML structure
    - Duplicate fileIDs
    - Missing required fields
    - Broken internal references

    Examples:

        # Validate a single file
        unityflow validate Player.prefab
        unityflow validate MainScene.unity
        unityflow validate GameConfig.asset

        # Validate multiple files
        unityflow validate *.prefab *.unity *.asset

        # Strict validation (warnings are errors)
        unityflow validate Player.prefab --strict
    """
    validator = PrefabValidator(strict=strict)
    any_invalid = False

    for file in files:
        result = validator.validate_file(file)

        if not result.is_valid:
            any_invalid = True

        if output_format == "json":
            import json

            output = {
                "path": str(file),
                "valid": result.is_valid,
                "issues": [
                    {
                        "severity": i.severity.value,
                        "message": i.message,
                        "fileID": i.file_id,
                        "propertyPath": i.property_path,
                        "suggestion": i.suggestion,
                    }
                    for i in result.issues
                ],
            }
            click.echo(json.dumps(output, indent=2))
        else:
            if quiet:
                if result.errors:
                    click.echo(f"{file}: INVALID")
                    for issue in result.errors:
                        click.echo(f"  {issue}")
            else:
                click.echo(result)
                click.echo()

    if any_invalid:
        sys.exit(1)


# ============================================================================
# Component GUID Mappings
# ============================================================================

PACKAGE_COMPONENT_GUIDS: dict[str, str] = {
    # Unity UI (com.unity.ugui)
    "Image": "fe87c0e1cc204ed48ad3b37840f39efc",
    "Button": "4e29b1a8efbd4b44bb3f3716e73f07ff",
    "ScrollRect": "1aa08ab6e0800fa44ae55d278d1423e3",
    "Mask": "31a19414c41e5ae4aae2af33fee712f6",
    "RectMask2D": "3312d7739989d2b4e91e6319e9a96d76",
    "GraphicRaycaster": "dc42784cf147c0c48a680349fa168899",
    "CanvasScaler": "0cd44c1031e13a943bb63640046fad76",
    "VerticalLayoutGroup": "59f8146938fff824cb5fd77236b75775",
    "HorizontalLayoutGroup": "30649d3a9faa99c48a7b1166b86bf2a0",
    "ContentSizeFitter": "3245ec927659c4140ac4f8d17403cc18",
    "TextMeshProUGUI": "f4688fdb7df04437aeb418b961361dc5",
    "TMP_InputField": "2da0c512f12947e489f739169773d7ca",
    "EventSystem": "76c392e42b5098c458856cdf6ecaaaa1",
    "InputSystemUIInputModule": "01614664b831546d2ae94a42149d80ac",
    # URP 2D Lighting
    "Light2D": "073797afb82c5a1438f328866b10b3f0",
}

# Built-in component types (native Unity components)
BUILTIN_COMPONENT_TYPES = [
    # Renderer
    "SpriteRenderer",
    "MeshRenderer",
    "TrailRenderer",
    "LineRenderer",
    "SkinnedMeshRenderer",
    # Camera & Light
    "Camera",
    "Light",
    # Audio
    "AudioSource",
    "AudioListener",
    # 3D Colliders
    "BoxCollider",
    "SphereCollider",
    "CapsuleCollider",
    "MeshCollider",
    # 2D Colliders
    "BoxCollider2D",
    "CircleCollider2D",
    "PolygonCollider2D",
    "EdgeCollider2D",
    "CapsuleCollider2D",
    "CompositeCollider2D",
    # Physics
    "Rigidbody",
    "Rigidbody2D",
    "CharacterController",
    # Animation
    "Animator",
    "Animation",
    # UI
    "Canvas",
    "CanvasGroup",
    "CanvasRenderer",
    # Misc
    "MeshFilter",
    "TextMesh",
    "ParticleSystem",
    "SpriteMask",
]

# All supported component types for --type option
ALL_COMPONENT_TYPES = BUILTIN_COMPONENT_TYPES + list(PACKAGE_COMPONENT_GUIDS.keys())


# ============================================================================
# Field Type Validation
# ============================================================================


class FieldType:
    """Unity field types for validation."""

    VECTOR2 = "Vector2"  # {x, y}
    VECTOR3 = "Vector3"  # {x, y, z}
    VECTOR4 = "Vector4"  # {x, y, z, w}
    QUATERNION = "Quaternion"  # {x, y, z, w}
    COLOR = "Color"  # {r, g, b, a}
    BOOL = "bool"  # 0 or 1
    INT = "int"  # integer
    FLOAT = "float"  # number
    STRING = "string"  # string
    ASSET_REF = "AssetRef"  # {fileID, guid, type}


# Field name to type mapping
FIELD_TYPES: dict[str, str] = {
    # Transform / RectTransform - Vector3
    "m_LocalPosition": FieldType.VECTOR3,
    "m_LocalScale": FieldType.VECTOR3,
    "m_LocalEulerAnglesHint": FieldType.VECTOR3,
    "localPosition": FieldType.VECTOR3,
    "localScale": FieldType.VECTOR3,
    # Transform - Quaternion
    "m_LocalRotation": FieldType.QUATERNION,
    "localRotation": FieldType.QUATERNION,
    # RectTransform - Vector2
    "m_AnchorMin": FieldType.VECTOR2,
    "m_AnchorMax": FieldType.VECTOR2,
    "m_AnchoredPosition": FieldType.VECTOR2,
    "m_SizeDelta": FieldType.VECTOR2,
    "m_Pivot": FieldType.VECTOR2,
    "anchorMin": FieldType.VECTOR2,
    "anchorMax": FieldType.VECTOR2,
    "anchoredPosition": FieldType.VECTOR2,
    "sizeDelta": FieldType.VECTOR2,
    "pivot": FieldType.VECTOR2,
    # RectTransform - Vector4
    "m_RaycastPadding": FieldType.VECTOR4,
    "m_margin": FieldType.VECTOR4,
    # Color fields
    "m_Color": FieldType.COLOR,
    "m_BackGroundColor": FieldType.COLOR,
    "m_NormalColor": FieldType.COLOR,
    "m_HighlightedColor": FieldType.COLOR,
    "m_PressedColor": FieldType.COLOR,
    "m_SelectedColor": FieldType.COLOR,
    "m_DisabledColor": FieldType.COLOR,
    # Common numeric fields
    "m_Enabled": FieldType.BOOL,
    "m_IsActive": FieldType.BOOL,
    "m_RaycastTarget": FieldType.BOOL,
    "m_Maskable": FieldType.BOOL,
    "m_PreserveAspect": FieldType.BOOL,
    "m_FillCenter": FieldType.BOOL,
    "m_UseSpriteMesh": FieldType.BOOL,
    # Asset reference fields
    "m_Sprite": FieldType.ASSET_REF,
    "m_Material": FieldType.ASSET_REF,
    "m_Script": FieldType.ASSET_REF,
}


def _validate_field_value(field_name: str, value) -> tuple[bool, str | None]:
    """Validate a value against its expected field type.

    Args:
        field_name: The field name (e.g., "m_LocalPosition")
        value: The value to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    field_type = FIELD_TYPES.get(field_name)

    if field_type is None:
        # Unknown field, skip validation
        return True, None

    if field_type == FieldType.VECTOR2:
        fmt = '{"x": 0, "y": 0}'
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Vector2 형식이어야 합니다: {fmt}"
        required = {"x", "y"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}"
        for k in ["x", "y"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.VECTOR3:
        fmt = '{"x": 0, "y": 0, "z": 0}'
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Vector3 형식이어야 합니다: {fmt}"
        required = {"x", "y", "z"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}"
        for k in ["x", "y", "z"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.VECTOR4:
        fmt = '{"x": 0, "y": 0, "z": 0, "w": 0}'
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Vector4 형식이어야 합니다: {fmt}"
        required = {"x", "y", "z", "w"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}"
        for k in ["x", "y", "z", "w"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.QUATERNION:
        fmt = '{"x": 0, "y": 0, "z": 0, "w": 1}'
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Quaternion 형식이어야 합니다: {fmt}"
        required = {"x", "y", "z", "w"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}"
        for k in ["x", "y", "z", "w"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.COLOR:
        fmt = '{"r": 1, "g": 1, "b": 1, "a": 1}'
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Color 형식이어야 합니다: {fmt}"
        required = {"r", "g", "b", "a"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}"
        for k in ["r", "g", "b", "a"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.BOOL:
        if value not in (0, 1, True, False):
            return False, f"'{field_name}'은(는) bool 형식이어야 합니다: 0 또는 1"
        return True, None

    if field_type == FieldType.INT:
        if not isinstance(value, int) or isinstance(value, bool):
            return False, f"'{field_name}'은(는) 정수여야 합니다"
        return True, None

    if field_type == FieldType.FLOAT:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False, f"'{field_name}'은(는) 숫자여야 합니다"
        return True, None

    if field_type == FieldType.STRING:
        if not isinstance(value, str):
            return False, f"'{field_name}'은(는) 문자열이어야 합니다"
        return True, None

    if field_type == FieldType.ASSET_REF:
        # Asset references are validated separately by asset_resolver
        # Skip validation here if it's already a resolved reference
        if isinstance(value, dict) and "fileID" in value:
            return True, None
        # If it's a string starting with @, it will be resolved later
        if isinstance(value, str) and value.startswith("@"):
            return True, None
        return False, f"'{field_name}'은(는) 에셋 참조여야 합니다: @Assets/path.ext"

    return True, None


# ============================================================================
# Path Resolution Helpers
# ============================================================================


def _resolve_gameobject_by_path(
    doc: UnityYAMLDocument,
    path_spec: str,
) -> tuple[int | None, str | None]:
    """Resolve a GameObject by path specification.

    Args:
        doc: The Unity YAML document
        path_spec: Path like "Canvas/Panel/Button" or "Canvas/Panel/Button[1]"

    Returns:
        Tuple of (fileID, error_message). If successful, error_message is None.
        If failed, fileID is None and error_message contains the error.
    """
    import re

    # Parse path and optional index
    index_match = re.match(r"^(.+)\[(\d+)\]$", path_spec)
    if index_match:
        path = index_match.group(1)
        index = int(index_match.group(2))
    else:
        path = path_spec
        index = None

    # Build transform hierarchy
    transforms: dict[int, dict] = {}  # transform_id -> {gameObject, parent}
    go_names: dict[int, str] = {}  # go_id -> name
    go_transforms: dict[int, int] = {}  # go_id -> transform_id

    for obj in doc.objects:
        if obj.class_id == 4 or obj.class_id == 224:  # Transform or RectTransform
            content = obj.get_content()
            if content:
                go_ref = content.get("m_GameObject", {})
                go_id = go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
                father = content.get("m_Father", {})
                father_id = father.get("fileID", 0) if isinstance(father, dict) else 0
                transforms[obj.file_id] = {
                    "gameObject": go_id,
                    "parent": father_id,
                }
                if go_id:
                    go_transforms[go_id] = obj.file_id

    for obj in doc.objects:
        if obj.class_id == 1:  # GameObject
            content = obj.get_content()
            if content:
                go_names[obj.file_id] = content.get("m_Name", "")

    # Build path for each GameObject
    def build_path(transform_id: int, visited: set[int]) -> str:
        if transform_id in visited or transform_id not in transforms:
            return ""
        visited.add(transform_id)

        t = transforms[transform_id]
        name = go_names.get(t["gameObject"], "")

        if t["parent"] == 0:
            return name
        else:
            parent_path = build_path(t["parent"], visited)
            if parent_path:
                return f"{parent_path}/{name}"
            return name

    # Find all GameObjects matching the path
    matches: list[tuple[int, str]] = []  # (go_id, full_path)
    for go_id, transform_id in go_transforms.items():
        full_path = build_path(transform_id, set())
        if full_path == path:
            matches.append((go_id, full_path))

    if not matches:
        return None, f"GameObject not found at path '{path}'"

    if len(matches) == 1:
        return matches[0][0], None

    # Multiple matches
    if index is not None:
        if index < len(matches):
            return matches[index][0], None
        else:
            count = len(matches)
            return None, f"Index [{index}] out of range. Found {count} GameObjects at '{path}'"

    # No index specified, show options
    error_lines = [f"Multiple GameObjects at path '{path}'."]
    error_lines.append(f'Use index to select: --to "{path}[0]" (0 to {len(matches) - 1})')
    return None, "\n".join(error_lines)


def _resolve_component_path(
    doc: UnityYAMLDocument,
    path_spec: str,
) -> tuple[str | None, str | None]:
    """Resolve a component path to the internal format.

    Converts paths like:
        "Player/SpriteRenderer/m_Color" -> "components/12345/m_Color"
        "Canvas/Panel/Button/Image/m_Sprite" -> "components/67890/m_Sprite"
        "Canvas/Button/Image[1]/m_Color" -> "components/11111/m_Color"
        "Player/name" -> "gameObjects/12345/name"
        "Canvas/Panel/RectTransform" -> "components/12345" (for batch mode)

    Args:
        doc: The Unity YAML document
        path_spec: Path like "Player/SpriteRenderer/m_Color"

    Returns:
        Tuple of (resolved_path, error_message). If successful, error_message is None.
    """
    import re

    from unityflow.parser import CLASS_IDS

    # Check if already in internal format (components/12345/... or gameObjects/12345/...)
    if re.match(r"^(components|gameObjects)/\d+", path_spec):
        return path_spec, None

    parts = path_spec.split("/")
    if len(parts) < 2:
        return None, f"Invalid path format: {path_spec}"

    # Build reverse mapping: class name -> class IDs
    name_to_ids: dict[str, list[int]] = {}
    for class_id, class_name in CLASS_IDS.items():
        name_lower = class_name.lower()
        if name_lower not in name_to_ids:
            name_to_ids[name_lower] = []
        name_to_ids[name_lower].append(class_id)

    # Also add package component names (they're MonoBehaviour)
    package_components = {
        "image",
        "button",
        "scrollrect",
        "mask",
        "rectmask2d",
        "graphicraycaster",
        "canvasscaler",
        "verticallayoutgroup",
        "horizontallayoutgroup",
        "contentsizefitter",
        "textmeshprougui",
        "tmp_inputfield",
        "eventsystem",
        "inputsystemuiinputmodule",
        "light2d",
    }

    # Check if the LAST part is a component type (for batch mode - path ends with component)
    # e.g., "Canvas/Panel/RectTransform" -> path to the component itself, no property
    last_part_match = re.match(r"^([A-Za-z][A-Za-z0-9]*)(?:\[(\d+)\])?$", parts[-1])
    if last_part_match:
        last_component_type = last_part_match.group(1)
        last_component_index = int(last_part_match.group(2)) if last_part_match.group(2) else None
        last_component_type_lower = last_component_type.lower()

        # Check if last part is a known component type
        last_is_component = (
            last_component_type_lower in name_to_ids
            or last_component_type_lower in package_components
            or last_component_type == "MonoBehaviour"
        )

        if last_is_component:
            # Path format: GameObject.../ComponentType (no property - for batch mode)
            go_path = "/".join(parts[:-1])
            if not go_path:
                return None, f"Invalid path: missing GameObject path before {last_component_type}"

            # Resolve GameObject
            go_id, error = _resolve_gameobject_by_path(doc, go_path)
            if error:
                return None, error

            # Find the component
            go = doc.get_by_file_id(go_id)
            if not go:
                return None, "GameObject not found"

            go_content = go.get_content()
            if not go_content or "m_Component" not in go_content:
                return None, "GameObject has no components"

            # Find matching components
            matching_components: list[int] = []
            for comp_ref in go_content["m_Component"]:
                comp_id = comp_ref.get("component", {}).get("fileID", 0)
                comp = doc.get_by_file_id(comp_id)
                if not comp:
                    continue

                # Check if component matches the type
                comp_class_name = comp.class_name.lower()

                # For package components (MonoBehaviour), check script GUID
                if last_component_type_lower in package_components:
                    if comp.class_id == 114:  # MonoBehaviour
                        comp_content = comp.get_content()
                        if comp_content:
                            script_ref = comp_content.get("m_Script", {})
                            if isinstance(script_ref, dict):
                                script_guid = script_ref.get("guid", "")
                            else:
                                script_guid = ""
                            # Check if GUID matches the package component
                            # Use case-insensitive key lookup
                            expected_guid = ""
                            for key, guid in PACKAGE_COMPONENT_GUIDS.items():
                                if key.lower() == last_component_type_lower:
                                    expected_guid = guid.lower()
                                    break
                            if script_guid.lower() == expected_guid:
                                matching_components.append(comp_id)
                elif comp_class_name == last_component_type_lower:
                    matching_components.append(comp_id)

            if not matching_components:
                return None, f"Component '{last_component_type}' not found on '{go_path}'"

            if len(matching_components) == 1:
                # Return component path without property (for batch mode)
                return f"components/{matching_components[0]}", None

            # Multiple matches
            if last_component_index is not None:
                if last_component_index < len(matching_components):
                    comp_id = matching_components[last_component_index]
                    return f"components/{comp_id}", None
                else:
                    count = len(matching_components)
                    idx = last_component_index
                    return None, f"Index [{idx}] out of range. Found {count} components"

            # No index specified
            comp_type = last_component_type
            error_lines = [f"Multiple '{comp_type}' components on '{go_path}'."]
            max_idx = len(matching_components) - 1
            error_lines.append(f'Use index: "{go_path}/{comp_type}[0]" (0-{max_idx})')
            return None, "\n".join(error_lines)

    # Last part is the property name
    property_name = parts[-1]

    # Check if second-to-last part is a component type (with optional index)
    component_match = re.match(r"^([A-Za-z][A-Za-z0-9]*)(?:\[(\d+)\])?$", parts[-2])

    if component_match:
        component_type = component_match.group(1)
        component_index = int(component_match.group(2)) if component_match.group(2) else None
        component_type_lower = component_type.lower()

        # Check if it's a known component type
        is_component = (
            component_type_lower in name_to_ids
            or component_type_lower in package_components
            or component_type == "MonoBehaviour"
        )

        if is_component:
            # Path format: GameObject.../ComponentType/property
            go_path = "/".join(parts[:-2])
            if not go_path:
                return None, f"Invalid path: missing GameObject path before {component_type}"

            # Resolve GameObject
            go_id, error = _resolve_gameobject_by_path(doc, go_path)
            if error:
                return None, error

            # Find the component
            go = doc.get_by_file_id(go_id)
            if not go:
                return None, "GameObject not found"

            go_content = go.get_content()
            if not go_content or "m_Component" not in go_content:
                return None, "GameObject has no components"

            # Find matching components
            matching_components: list[int] = []
            for comp_ref in go_content["m_Component"]:
                comp_id = comp_ref.get("component", {}).get("fileID", 0)
                comp = doc.get_by_file_id(comp_id)
                if not comp:
                    continue

                # Check if component matches the type
                comp_class_name = comp.class_name.lower()

                # For package components (MonoBehaviour), check script GUID
                if component_type_lower in package_components:
                    if comp.class_id == 114:  # MonoBehaviour
                        comp_content = comp.get_content()
                        if comp_content:
                            script_ref = comp_content.get("m_Script", {})
                            if isinstance(script_ref, dict):
                                script_guid = script_ref.get("guid", "")
                            else:
                                script_guid = ""
                            # Check if GUID matches the package component
                            # Use case-insensitive key lookup
                            expected_guid = ""
                            for key, guid in PACKAGE_COMPONENT_GUIDS.items():
                                if key.lower() == component_type_lower:
                                    expected_guid = guid.lower()
                                    break
                            if script_guid.lower() == expected_guid:
                                matching_components.append(comp_id)
                elif comp_class_name == component_type_lower:
                    matching_components.append(comp_id)

            if not matching_components:
                return None, f"Component '{component_type}' not found on '{go_path}'"

            if len(matching_components) == 1:
                return f"components/{matching_components[0]}/{property_name}", None

            # Multiple matches
            if component_index is not None:
                if component_index < len(matching_components):
                    comp_id = matching_components[component_index]
                    return f"components/{comp_id}/{property_name}", None
                else:
                    count = len(matching_components)
                    return None, f"Index [{component_index}] out of range. Found {count}"

            # No index specified
            comp_type = component_type
            error_lines = [f"Multiple '{comp_type}' components on '{go_path}'."]
            max_idx = len(matching_components) - 1
            error_lines.append(f'Use index: "{go_path}/{comp_type}[0]/..." (0-{max_idx})')
            return None, "\n".join(error_lines)

    # Not a component path - treat as GameObject property
    # Path format: GameObject.../property
    go_path = "/".join(parts[:-1])
    go_id, error = _resolve_gameobject_by_path(doc, go_path)
    if error:
        return None, error

    return f"gameObjects/{go_id}/{property_name}", None


@main.command(name="get")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.argument("path_spec", type=str)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format (default: json)",
)
def get_value_cmd(
    file: Path,
    path_spec: str,
    output_format: str,
) -> None:
    """Get a value at a specific path in a Unity YAML file.

    Path Format:
        GameObject/ComponentType/property - Component property
        GameObject/property               - GameObject property

    Examples:

        # Get Transform position
        unityflow get Player.prefab "Player/Transform/localPosition"

        # Get SpriteRenderer color
        unityflow get Player.prefab "Player/SpriteRenderer/m_Color"

        # Get GameObject name
        unityflow get Player.prefab "Player/name"

        # Get all properties of a component
        unityflow get Player.prefab "Player/Transform"

        # When multiple components of same type exist, use index
        unityflow get Scene.unity "Canvas/Panel/Image[1]/m_Color"

        # Output as text (for simple values)
        unityflow get Player.prefab "Player/Transform/localPosition" --format text
    """
    import json

    from unityflow.parser import UnityYAMLDocument
    from unityflow.query import get_value

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    # Resolve path (convert "Player/Transform/localPosition" to "components/12345/localPosition")
    resolved_path, error = _resolve_component_path(doc, path_spec)
    if error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    # Get the value
    value = get_value(doc, resolved_path)
    if value is None:
        click.echo(f"Error: No value found at path '{path_spec}'", err=True)
        sys.exit(1)

    # Output
    if output_format == "json":
        click.echo(json.dumps(value, indent=2, default=str))
    else:
        # Text format - simple representation
        if isinstance(value, dict):
            for k, v in value.items():
                click.echo(f"{k}: {v}")
        elif isinstance(value, list):
            for item in value:
                click.echo(str(item))
        else:
            click.echo(str(value))


@main.command(name="set")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--path",
    "-p",
    "set_path",
    required=True,
    help="Path to the value (e.g., 'Player/Transform/localPosition')",
)
@click.option(
    "--value",
    "-v",
    default=None,
    help="Value to set (JSON format for complex values)",
)
@click.option(
    "--batch",
    "-b",
    "batch_values_json",
    default=None,
    help="JSON object with multiple key-value pairs to set at once",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
def set_value_cmd(
    file: Path,
    set_path: str,
    value: str | None,
    batch_values_json: str | None,
    output: Path | None,
) -> None:
    """Set a value at a specific path in a Unity YAML file.

    Path Format:
        GameObject/ComponentType/property - Component property
        GameObject/property               - GameObject property

    Examples:

        # Set Transform position
        unityflow set Player.prefab \\
            --path "Player/Transform/localPosition" \\
            --value '{"x": 0, "y": 5, "z": 0}'

        # Set SpriteRenderer color
        unityflow set Player.prefab \\
            --path "Player/SpriteRenderer/m_Color" \\
            --value '{"r": 1, "g": 0, "b": 0, "a": 1}'

        # Set Image sprite (with asset reference)
        unityflow set Scene.unity \\
            --path "Canvas/Panel/Button/Image/m_Sprite" \\
            --value "@Assets/Sprites/icon.png"

        # Set GameObject name
        unityflow set Player.prefab \\
            --path "Player/name" \\
            --value '"NewName"'

        # When multiple components of same type exist, use index
        unityflow set Scene.unity \\
            --path "Canvas/Panel/Image[1]/m_Color" \\
            --value '{"r": 0, "g": 1, "b": 0, "a": 1}'

        # Set multiple fields at once (batch mode)
        unityflow set Scene.unity \\
            --path "Player/MonoBehaviour" \\
            --batch '{"speed": 5.0, "health": 100}'

    Asset References:
        Use @ prefix to reference assets by path:
            "@Assets/Sprites/icon.png"          -> Sprite reference
            "@Assets/Sprites/atlas.png:idle_0"  -> Sub-sprite
            "@Assets/Prefabs/Enemy.prefab"      -> Prefab reference
    """
    import json

    from unityflow.asset_resolver import (
        AssetTypeMismatchError,
        is_asset_reference,
        resolve_value,
    )
    from unityflow.parser import UnityYAMLDocument
    from unityflow.query import merge_values, set_value

    # Count how many value modes are specified
    value_modes = sum(
        [
            value is not None,
            batch_values_json is not None,
        ]
    )

    # Validate options
    if value_modes == 0:
        click.echo("Error: One of --value or --batch is required", err=True)
        sys.exit(1)
    if value_modes > 1:
        click.echo("Error: Cannot use multiple value modes (--value, --batch)", err=True)
        sys.exit(1)

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file
    project_root = find_unity_project_root(file)

    # Resolve path (convert "Player/Transform/localPosition" to "components/12345/localPosition")
    original_path = set_path
    resolved_path, error = _resolve_component_path(doc, set_path)
    if error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)
    set_path = resolved_path

    # Extract field name from path for type validation
    # e.g., "components/12345/m_Sprite" -> "m_Sprite"
    field_name = set_path.rsplit("/", 1)[-1] if "/" in set_path else set_path

    if batch_values_json is not None:
        # Batch mode - field names are the dict keys
        try:
            parsed_values = json.loads(batch_values_json)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --batch: {e}", err=True)
            sys.exit(1)

        if not isinstance(parsed_values, dict):
            click.echo("Error: --batch value must be a JSON object", err=True)
            sys.exit(1)

        # Validate field types in batch values
        for batch_field_name, batch_value in parsed_values.items():
            is_valid, error_msg = _validate_field_value(batch_field_name, batch_value)
            if not is_valid:
                click.echo(f"Error: {error_msg}", err=True)
                sys.exit(1)

        # Resolve asset references in batch values (keys are used as field names)
        try:
            resolved_values = resolve_value(parsed_values, project_root)
        except AssetTypeMismatchError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        updated, created = merge_values(doc, set_path, resolved_values, create=True)

        if updated == 0 and created == 0:
            click.echo(f"Error: Path not found or no fields set: {original_path}", err=True)
            sys.exit(1)

        doc.save(output_path)
        click.echo(f"Set {updated + created} fields at {original_path}")
        click.echo(f"  Updated: {updated}, Created: {created}")

    else:
        # Single value mode
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value

        # Validate field type
        is_valid, error_msg = _validate_field_value(field_name, parsed_value)
        if not is_valid:
            click.echo(f"Error: {error_msg}", err=True)
            sys.exit(1)

        # Resolve asset references with field name for type validation
        try:
            resolved_value = resolve_value(parsed_value, project_root, field_name=field_name)
        except AssetTypeMismatchError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Show resolved asset info if it was an asset reference
        is_asset_ref = is_asset_reference(value) if isinstance(value, str) else False

        if set_value(doc, set_path, resolved_value, create=True):
            doc.save(output_path)
            if is_asset_ref:
                click.echo(f"Set {original_path} = {value[1:]}")  # Remove @ prefix for display
            else:
                click.echo(f"Set {original_path} = {value}")
        else:
            click.echo(f"Error: Path not found: {original_path}", err=True)
            sys.exit(1)

    if output:
        click.echo(f"Saved to: {output}")


@main.command(name="git-textconv")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
def git_textconv(file: Path) -> None:
    """Output normalized content for git diff textconv.

    This command is designed to be used as a git textconv filter.
    It outputs the normalized YAML to stdout for git to compare.

    Setup in .gitconfig:

        [diff "unity"]
            textconv = unityflow git-textconv

    Setup in .gitattributes:

        *.prefab diff=unity
        *.unity diff=unity
        *.asset diff=unity
    """
    normalizer = UnityPrefabNormalizer()

    try:
        content = normalizer.normalize_file(file)
        # Output to stdout without trailing message
        sys.stdout.write(content)
    except Exception as e:
        # On error, output original file content so git can still diff
        click.echo(f"# Error normalizing: {e}", err=True)
        sys.stdout.write(file.read_text(encoding="utf-8"))


@main.command(name="merge")
@click.argument("base", type=click.Path(exists=True, path_type=Path))
@click.argument("ours", type=click.Path(exists=True, path_type=Path))
@click.argument("theirs", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: write to 'ours' file for git merge driver)",
)
@click.option(
    "--path",
    "file_path",
    help="Original file path (for git merge driver %P)",
)
def merge_files(
    base: Path,
    ours: Path,
    theirs: Path,
    output: Path | None,
    file_path: str | None,
) -> None:
    """Semantic three-way merge of Unity YAML files.

    Uses property-level merge which enables accurate conflict detection
    and automatic merging of non-conflicting changes.

    This command is designed to work as a git merge driver.

    BASE is the common ancestor file (%O).
    OURS is the current branch version (%A).
    THEIRS is the version being merged (%B).

    Exit codes:
        0 = merge successful
        1 = conflict (manual resolution needed)

    Setup in .gitconfig:

        [merge "unity"]
            name = Unity YAML Merge
            driver = unityflow merge %O %A %B -o %A --path %P

    Setup in .gitattributes:

        *.prefab merge=unity
        *.unity merge=unity
        *.asset merge=unity
    """
    from unityflow.semantic_merge import semantic_three_way_merge

    try:
        base_doc = UnityYAMLDocument.load(base)
        ours_doc = UnityYAMLDocument.load(ours)
        theirs_doc = UnityYAMLDocument.load(theirs)
    except Exception as e:
        click.echo(f"Error: Failed to load files: {e}", err=True)
        sys.exit(1)

    # Perform semantic 3-way merge
    result = semantic_three_way_merge(base_doc, ours_doc, theirs_doc)

    output_path = output or ours
    result.merged_document.save(output_path)

    display_path = file_path or str(output_path)

    if result.has_conflicts:
        click.echo(f"Conflict: {display_path} ({result.conflict_count} conflicts)", err=True)
        for conflict in result.property_conflicts:
            name_str = f" ({conflict.game_object_name})" if conflict.game_object_name else ""
            click.echo(f"  - {conflict.class_name}.{conflict.property_path}{name_str}", err=True)
        sys.exit(1)
    else:
        # Silent success for git integration (git expects no output on success)
        sys.exit(0)


@main.command(name="setup")
@click.option(
    "--global",
    "use_global",
    is_flag=True,
    help="Configure globally (~/.gitconfig) instead of locally",
)
@click.option(
    "--with-hooks",
    is_flag=True,
    help="Also install pre-commit hooks (native git hooks)",
)
@click.option(
    "--with-pre-commit",
    is_flag=True,
    help="Also install pre-commit framework hooks",
)
@click.option(
    "--with-difftool",
    is_flag=True,
    help="Also configure git difftool for Git Fork and other GUI clients",
)
@click.option(
    "--difftool-backend",
    type=click.Choice(["vscode", "meld", "kdiff3", "opendiff", "html", "auto"]),
    default="auto",
    help="Backend for difftool (default: auto-detect)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing configuration",
)
def setup(
    use_global: bool,
    with_hooks: bool,
    with_pre_commit: bool,
    with_difftool: bool,
    difftool_backend: str,
    force: bool,
) -> None:
    """Set up Git integration with a single command.

    Configures git diff/merge drivers and .gitattributes for Unity files.
    Run this from your Unity project root.

    Examples:

        # Basic setup (local to current repo)
        unityflow setup

        # Global setup (applies to all repos)
        unityflow setup --global

        # Setup with pre-commit hooks
        unityflow setup --with-hooks

        # Setup with pre-commit framework
        unityflow setup --with-pre-commit

        # Setup with difftool for Git Fork
        unityflow setup --with-difftool

        # Setup difftool with specific backend
        unityflow setup --with-difftool --difftool-backend vscode
    """
    import subprocess

    click.echo("=== unityflow Git Integration Setup ===")
    click.echo()

    # Check if we're in a git repo (required for local setup)
    if not use_global and not is_git_repository():
        click.echo("Error: Not in a git repository", err=True)
        click.echo("Run from your Unity project root, or use --global", err=True)
        sys.exit(1)

    repo_root = get_repo_root() if not use_global else None

    # Determine git config scope
    if use_global:
        click.echo("Setting up GLOBAL git configuration...")
        git_config_cmd = ["git", "config", "--global"]
    else:
        click.echo("Setting up LOCAL git configuration...")
        git_config_cmd = ["git", "config"]

    # Configure diff driver
    click.echo("  Configuring diff driver...")
    subprocess.run([*git_config_cmd, "diff.unity.textconv", "unityflow git-textconv"], check=True)
    subprocess.run([*git_config_cmd, "diff.unity.cachetextconv", "true"], check=True)

    # Configure merge driver
    click.echo("  Configuring merge driver...")
    merge_name = "Unity YAML Merge (unityflow)"
    merge_driver = "unityflow merge %O %A %B -o %A --path %P"
    subprocess.run([*git_config_cmd, "merge.unity.name", merge_name], check=True)
    subprocess.run([*git_config_cmd, "merge.unity.driver", merge_driver], check=True)
    subprocess.run([*git_config_cmd, "merge.unity.recursive", "binary"], check=True)

    # Configure difftool (for Git Fork and other GUI clients)
    if with_difftool:
        click.echo("  Configuring difftool...")

        # Determine backend option
        if difftool_backend == "auto":
            backend_arg = ""
        else:
            backend_arg = f" --tool {difftool_backend}"

        # Set up difftool
        subprocess.run([*git_config_cmd, "diff.tool", "prefab-unity"], check=True)
        difftool_cmd = f'unityflow difftool{backend_arg} "$LOCAL" "$REMOTE"'
        subprocess.run(
            [*git_config_cmd, "difftool.prefab-unity.cmd", difftool_cmd],
            check=True,
        )

        # Also configure for Unity file types specifically
        subprocess.run([*git_config_cmd, "difftool.prompt", "false"], check=True)

        click.echo("  Difftool configured for Git Fork and GUI clients")
        click.echo()
        click.echo("  Git Fork setup:")
        click.echo("    1. Open Git Fork → Repository → Settings → Git Config")
        click.echo("    2. Or use: git difftool <file>")
        click.echo()

    click.echo()

    # Setup .gitattributes (only for local setup)
    if not use_global and repo_root:
        gitattributes_path = repo_root / ".gitattributes"
        gitattributes_content = """\
# Unity YAML files - use unityflow for diff and merge
*.prefab diff=unity merge=unity text eol=lf
*.unity diff=unity merge=unity text eol=lf
*.asset diff=unity merge=unity text eol=lf
*.mat diff=unity merge=unity text eol=lf
*.controller diff=unity merge=unity text eol=lf
*.anim diff=unity merge=unity text eol=lf
*.overrideController diff=unity merge=unity text eol=lf
*.playable diff=unity merge=unity text eol=lf
*.mask diff=unity merge=unity text eol=lf
*.signal diff=unity merge=unity text eol=lf
*.renderTexture diff=unity merge=unity text eol=lf
*.flare diff=unity merge=unity text eol=lf
*.shadervariants diff=unity merge=unity text eol=lf
*.spriteatlas diff=unity merge=unity text eol=lf
*.cubemap diff=unity merge=unity text eol=lf
*.physicMaterial diff=unity merge=unity text eol=lf
*.physicsMaterial2D diff=unity merge=unity text eol=lf
*.terrainlayer diff=unity merge=unity text eol=lf
*.brush diff=unity merge=unity text eol=lf
*.mixer diff=unity merge=unity text eol=lf
*.guiskin diff=unity merge=unity text eol=lf
*.fontsettings diff=unity merge=unity text eol=lf
*.preset diff=unity merge=unity text eol=lf
*.giparams diff=unity merge=unity text eol=lf

# Unity meta files
*.meta text eol=lf
"""

        if gitattributes_path.exists():
            existing = gitattributes_path.read_text()
            if "diff=unity" in existing:
                click.echo("  .gitattributes already configured")
            else:
                click.echo("  Appending to .gitattributes...")
                with open(gitattributes_path, "a") as f:
                    f.write("\n" + gitattributes_content)
        else:
            click.echo("  Creating .gitattributes...")
            gitattributes_path.write_text(gitattributes_content)

        # Setup .gitignore for .unityflow cache directory
        gitignore_path = repo_root / ".gitignore"
        unityflow_ignore_entry = ".unityflow/"

        if gitignore_path.exists():
            existing_gitignore = gitignore_path.read_text()
            if unityflow_ignore_entry in existing_gitignore or ".unityflow" in existing_gitignore:
                click.echo("  .gitignore already includes .unityflow/")
            else:
                click.echo("  Adding .unityflow/ to .gitignore...")
                with open(gitignore_path, "a") as f:
                    f.write(f"\n# unityflow cache\n{unityflow_ignore_entry}\n")
        else:
            click.echo("  Creating .gitignore with .unityflow/...")
            gitignore_path.write_text(f"# unityflow cache\n{unityflow_ignore_entry}\n")

    # Install hooks if requested
    if with_hooks and repo_root:
        click.echo()
        click.echo("Installing git pre-commit hook...")
        hooks_dir = repo_root / ".git" / "hooks"
        hook_path = hooks_dir / "pre-commit"

        if hook_path.exists() and not force:
            click.echo(f"  Warning: Hook already exists at {hook_path}", err=True)
            click.echo("  Use --force to overwrite", err=True)
        else:
            hook_content = """\
#!/bin/bash
# unityflow pre-commit hook
# Automatically normalize Unity YAML files before commit

set -e

# Get list of staged Unity files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | \\
  grep -E '\\.(prefab|unity|asset)$' || true)

if [ -n "$STAGED_FILES" ]; then
    echo "Normalizing Unity files..."

    for file in $STAGED_FILES; do
        if [ -f "$file" ]; then
            unityflow normalize "$file" --in-place
            git add "$file"
        fi
    done

    echo "Unity files normalized."
fi
"""
            hook_path.write_text(hook_content)
            hook_path.chmod(0o755)
            click.echo(f"  Created: {hook_path}")

    if with_pre_commit and repo_root:
        click.echo()
        click.echo("Setting up pre-commit framework...")

        # Check if pre-commit is installed
        try:
            subprocess.run(["pre-commit", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            click.echo("  Error: pre-commit is not installed", err=True)
            click.echo("  Install it with: pip install pre-commit", err=True)
            sys.exit(1)

        config_path = repo_root / ".pre-commit-config.yaml"
        config_content = """\
# See https://pre-commit.com for more information
repos:
  # Unity Prefab Normalizer
  - repo: https://github.com/TrueCyan/unityflow
    rev: v0.1.0
    hooks:
      - id: prefab-normalize
      # - id: prefab-validate  # Optional: add validation
"""

        if config_path.exists() and not force:
            existing = config_path.read_text()
            if "unityflow" in existing:
                click.echo("  pre-commit already configured for unityflow")
            else:
                click.echo("  Warning: .pre-commit-config.yaml exists", err=True)
                click.echo("  Use --force to overwrite", err=True)
        else:
            config_path.write_text(config_content)
            click.echo(f"  Created: {config_path}")

            try:
                subprocess.run(["pre-commit", "install"], cwd=repo_root, check=True)
                click.echo("  Installed pre-commit hooks")
            except subprocess.CalledProcessError:
                click.echo("  Warning: Failed to run 'pre-commit install'", err=True)

    click.echo()
    click.echo("=== Setup Complete ===")
    click.echo()
    click.echo("Git is now configured to use unityflow for Unity files.")
    click.echo()
    click.echo("Test with:")
    click.echo("  git diff HEAD~1 -- '*.prefab'")
    click.echo()


@main.command(name="hierarchy")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--depth",
    "-d",
    type=int,
    default=None,
    help="Maximum depth to display (default: unlimited)",
)
@click.option(
    "--root",
    "-r",
    "root_path",
    type=str,
    default=None,
    help="Start from a specific object path (e.g., 'Player/Body')",
)
@click.option(
    "--no-components",
    is_flag=True,
    help="Hide component information",
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, path_type=Path),
    help="Unity project root (auto-detected if not specified)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["tree", "json"]),
    default="tree",
    help="Output format (default: tree)",
)
def hierarchy_cmd(
    file: Path,
    depth: int | None,
    root_path: str | None,
    no_components: bool,
    project_root: Path | None,
    output_format: str,
) -> None:
    """Show hierarchy structure of a Unity YAML file.

    Displays the GameObject hierarchy in a tree format, showing:
    - Object names and parent-child relationships
    - Components attached to each object (with script names resolved)
    - Inactive objects marked with (inactive)
    - PrefabInstance nodes with their source prefab

    Examples:

        # Show full hierarchy
        unityflow hierarchy Player.prefab

        # Limit depth
        unityflow hierarchy Scene.unity --depth 2

        # Start from specific object
        unityflow hierarchy Player.prefab --root "Body/Armature"

        # Hide components
        unityflow hierarchy Player.prefab --no-components

        # Output as JSON
        unityflow hierarchy Player.prefab --format json
    """
    import json as json_module

    from unityflow import UnityYAMLDocument, build_hierarchy
    from unityflow.asset_tracker import find_unity_project_root, get_lazy_guid_index

    # Load document
    try:
        doc = UnityYAMLDocument.load_auto(file)
    except Exception as e:
        click.echo(f"Error: Failed to load file: {e}", err=True)
        sys.exit(1)

    # Find project root and build GUID index
    resolved_project_root = project_root
    if resolved_project_root is None:
        resolved_project_root = find_unity_project_root(file)

    guid_index = None
    if resolved_project_root:
        try:
            guid_index = get_lazy_guid_index(resolved_project_root, include_packages=True)
        except Exception:
            pass  # Continue without GUID index

    # Build hierarchy
    try:
        hier = build_hierarchy(doc, guid_index=guid_index)
    except Exception as e:
        click.echo(f"Error: Failed to build hierarchy: {e}", err=True)
        sys.exit(1)

    # Find starting node if root_path specified
    root_nodes = hier.root_objects
    if root_path:
        found = hier.find(root_path)
        if found is None:
            click.echo(f"Error: Object not found: {root_path}", err=True)
            sys.exit(1)
        root_nodes = [found]

    # Helper function to get active state from document
    def get_active_state(node) -> bool:
        """Get the active state of a node from the document."""
        if node._document is None:
            return True
        go_obj = node._document.get_by_file_id(node.file_id)
        if go_obj and go_obj.class_id == 1:  # GameObject
            content = go_obj.get_content()
            if content:
                return content.get("m_IsActive", 1) == 1
        return True

    # Output
    if output_format == "json":

        def node_to_dict(node, current_depth: int = 0):
            result = {
                "name": node.name,
                "path": node.path,
                "active": get_active_state(node),
            }
            if not no_components and node.components:
                result["components"] = [
                    {
                        "type": c.script_name or c.class_name,
                        "class_id": c.class_id,
                    }
                    for c in node.components
                ]
            if node.is_prefab_instance:
                result["is_prefab_instance"] = True
                if node.source_guid:
                    result["source_guid"] = node.source_guid

            if depth is None or current_depth < depth:
                if node.children:
                    result["children"] = [node_to_dict(child, current_depth + 1) for child in node.children]
            return result

        output_data = [node_to_dict(n) for n in root_nodes]
        click.echo(json_module.dumps(output_data, indent=2))
    else:
        # Tree output
        def print_tree(node, prefix: str = "", is_last: bool = True, current_depth: int = 0):
            # Determine connector
            connector = "└── " if is_last else "├── "

            # Build node line
            name = node.name
            if not get_active_state(node):
                name += " (inactive)"
            if node.is_prefab_instance:
                name += " [Prefab]"

            # Component info
            comp_str = ""
            if not no_components and node.components:
                comp_names = []
                for c in node.components:
                    if c.script_name:
                        comp_names.append(c.script_name)
                    elif c.class_name and c.class_name not in ("Transform", "RectTransform"):
                        comp_names.append(c.class_name)
                if comp_names:
                    comp_str = f" [{', '.join(comp_names)}]"

            click.echo(f"{prefix}{connector}{name}{comp_str}")

            # Check depth limit
            if depth is not None and current_depth >= depth:
                return

            # Print children
            children = node.children
            child_prefix = prefix + ("    " if is_last else "│   ")
            for i, child in enumerate(children):
                print_tree(child, child_prefix, i == len(children) - 1, current_depth + 1)

        # Print header
        click.echo(f"Hierarchy: {file.name}")
        click.echo()

        # Print each root
        for i, root in enumerate(root_nodes):
            is_last_root = i == len(root_nodes) - 1
            # Root node is special - no prefix
            name = root.name
            if not get_active_state(root):
                name += " (inactive)"
            if root.is_prefab_instance:
                name += " [Prefab]"

            comp_str = ""
            if not no_components and root.components:
                comp_names = []
                for c in root.components:
                    if c.script_name:
                        comp_names.append(c.script_name)
                    elif c.class_name and c.class_name not in ("Transform", "RectTransform"):
                        comp_names.append(c.class_name)
                if comp_names:
                    comp_str = f" [{', '.join(comp_names)}]"

            click.echo(f"{name}{comp_str}")

            # Print children
            children = root.children
            for j, child in enumerate(children):
                print_tree(child, "", j == len(children) - 1, 1)

            if not is_last_root:
                click.echo()


@main.command(name="inspect")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.argument("object_path", type=str, required=False, default=None)
@click.option(
    "--project-root",
    type=click.Path(exists=True, path_type=Path),
    help="Unity project root (auto-detected if not specified)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def inspect_cmd(
    file: Path,
    object_path: str | None,
    project_root: Path | None,
    output_format: str,
) -> None:
    """Inspect a GameObject or component in detail.

    Shows detailed information about a specific GameObject including:
    - Name, path, and active state
    - Layer and tag
    - All components with their properties

    If no object_path is provided, shows the root object(s).

    Examples:

        # Inspect root object
        unityflow inspect Player.prefab

        # Inspect specific object by path
        unityflow inspect Player.prefab "Body/Armature/Spine"

        # Output as JSON
        unityflow inspect Player.prefab "Canvas" --format json
    """
    import json as json_module

    from unityflow import UnityYAMLDocument, build_hierarchy
    from unityflow.asset_tracker import find_unity_project_root, get_lazy_guid_index

    # Load document
    try:
        doc = UnityYAMLDocument.load_auto(file)
    except Exception as e:
        click.echo(f"Error: Failed to load file: {e}", err=True)
        sys.exit(1)

    # Find project root and build GUID index
    resolved_project_root = project_root
    if resolved_project_root is None:
        resolved_project_root = find_unity_project_root(file)

    guid_index = None
    if resolved_project_root:
        try:
            guid_index = get_lazy_guid_index(resolved_project_root, include_packages=True)
        except Exception:
            pass

    # Build hierarchy
    try:
        hier = build_hierarchy(doc, guid_index=guid_index)
    except Exception as e:
        click.echo(f"Error: Failed to build hierarchy: {e}", err=True)
        sys.exit(1)

    # Find target node
    if object_path:
        node = hier.find(object_path)
        if node is None:
            click.echo(f"Error: Object not found: {object_path}", err=True)
            sys.exit(1)
    else:
        # Use first root
        if not hier.root_objects:
            click.echo("Error: No root objects found", err=True)
            sys.exit(1)
        node = hier.root_objects[0]

    # Get GameObject data
    go_obj = doc.get_by_file_id(node.file_id)
    go_content = go_obj.get_content() if go_obj else {}

    # Get active state from GameObject content
    is_active = go_content.get("m_IsActive", 1) == 1

    if output_format == "json":
        result = {
            "name": node.name,
            "path": node.path,
            "file_id": node.file_id,
            "active": is_active,
            "layer": go_content.get("m_Layer", 0),
            "tag": go_content.get("m_TagString", "Untagged"),
            "is_prefab_instance": node.is_prefab_instance,
        }
        if node.source_guid:
            result["source_guid"] = node.source_guid

        # Add transform info
        if node.transform_id:
            transform_obj = doc.get_by_file_id(node.transform_id)
            if transform_obj:
                transform_content = transform_obj.get_content() or {}
                result["transform"] = {
                    "type": "RectTransform" if transform_obj.class_id == 224 else "Transform",
                    "localPosition": transform_content.get("m_LocalPosition"),
                    "localRotation": transform_content.get("m_LocalRotation"),
                    "localScale": transform_content.get("m_LocalScale"),
                }
                if transform_obj.class_id == 224:
                    t = result["transform"]
                    t["anchoredPosition"] = transform_content.get("m_AnchoredPosition")
                    t["sizeDelta"] = transform_content.get("m_SizeDelta")
                    t["anchorMin"] = transform_content.get("m_AnchorMin")
                    t["anchorMax"] = transform_content.get("m_AnchorMax")
                    t["pivot"] = transform_content.get("m_Pivot")

        # Add components
        result["components"] = []
        for comp in node.components:
            comp_data = {
                "type": comp.script_name or comp.class_name,
                "class_id": comp.class_id,
                "file_id": comp.file_id,
            }
            if comp.script_guid:
                comp_data["script_guid"] = comp.script_guid
            # Include component properties
            comp_data["properties"] = comp.data
            result["components"].append(comp_data)

        click.echo(json_module.dumps(result, indent=2, default=str))
    else:
        # Text output - Inspector-like format
        click.echo(f"GameObject: {node.name}")
        click.echo(f"Path: {node.path}")
        click.echo(f"FileID: {node.file_id}")
        click.echo(f"Active: {is_active}")
        click.echo(f"Layer: {go_content.get('m_Layer', 0)}")
        click.echo(f"Tag: {go_content.get('m_TagString', 'Untagged')}")

        if node.is_prefab_instance:
            click.echo("Is Prefab Instance: Yes")
            if node.source_guid:
                click.echo(f"Source GUID: {node.source_guid}")

        click.echo()

        # Transform info
        if node.transform_id:
            transform_obj = doc.get_by_file_id(node.transform_id)
            if transform_obj:
                transform_content = transform_obj.get_content() or {}
                transform_type = "RectTransform" if transform_obj.class_id == 224 else "Transform"
                click.echo(f"[{transform_type}]")

                def fmt_vec3(v: dict, dx=0, dy=0, dz=0) -> str:
                    return f"({v.get('x', dx)}, {v.get('y', dy)}, {v.get('z', dz)})"

                def fmt_vec4(v: dict, dx=0, dy=0, dz=0, dw=1) -> str:
                    return f"({v.get('x', dx)}, {v.get('y', dy)}, {v.get('z', dz)}, {v.get('w', dw)})"

                def fmt_vec2(v: dict, dx=0, dy=0) -> str:
                    return f"({v.get('x', dx)}, {v.get('y', dy)})"

                pos = transform_content.get("m_LocalPosition", {})
                if isinstance(pos, dict):
                    click.echo(f"  localPosition: {fmt_vec3(pos)}")

                rot = transform_content.get("m_LocalRotation", {})
                if isinstance(rot, dict):
                    click.echo(f"  localRotation: {fmt_vec4(rot)}")

                scale = transform_content.get("m_LocalScale", {})
                if isinstance(scale, dict):
                    click.echo(f"  localScale: {fmt_vec3(scale, 1, 1, 1)}")

                # RectTransform specific
                if transform_obj.class_id == 224:
                    anchor_pos = transform_content.get("m_AnchoredPosition", {})
                    if isinstance(anchor_pos, dict):
                        click.echo(f"  anchoredPosition: {fmt_vec2(anchor_pos)}")

                    size = transform_content.get("m_SizeDelta", {})
                    if isinstance(size, dict):
                        click.echo(f"  sizeDelta: {fmt_vec2(size)}")

                    anchor_min = transform_content.get("m_AnchorMin", {})
                    if isinstance(anchor_min, dict):
                        click.echo(f"  anchorMin: {fmt_vec2(anchor_min)}")

                    anchor_max = transform_content.get("m_AnchorMax", {})
                    if isinstance(anchor_max, dict):
                        click.echo(f"  anchorMax: {fmt_vec2(anchor_max)}")

                    pivot = transform_content.get("m_Pivot", {})
                    if isinstance(pivot, dict):
                        click.echo(f"  pivot: {fmt_vec2(pivot, 0.5, 0.5)}")

                click.echo()

        # Other components
        for comp in node.components:
            comp_type = comp.script_name or comp.class_name
            click.echo(f"[{comp_type}]")

            if comp.script_guid:
                click.echo(f"  script_guid: {comp.script_guid}")

            # Show key properties (excluding internal Unity fields)
            skip_keys = {
                "m_ObjectHideFlags",
                "m_CorrespondingSourceObject",
                "m_PrefabInstance",
                "m_PrefabAsset",
                "m_GameObject",
                "m_Enabled",
                "m_Script",
            }
            for key, value in comp.data.items():
                if key not in skip_keys:
                    # Format value for display
                    if isinstance(value, dict) and "fileID" in value:
                        # Reference field
                        file_id = value.get("fileID", 0)
                        guid = value.get("guid", "")
                        if guid:
                            click.echo(f"  {key}: (GUID: {guid}, fileID: {file_id})")
                        elif file_id:
                            click.echo(f"  {key}: (fileID: {file_id})")
                        else:
                            click.echo(f"  {key}: None")
                    elif isinstance(value, (dict, list)):
                        # Complex value - show abbreviated
                        if isinstance(value, list):
                            click.echo(f"  {key}: [{len(value)} items]")
                        else:
                            click.echo(f"  {key}: {{...}}")
                    else:
                        click.echo(f"  {key}: {value}")

            click.echo()


if __name__ == "__main__":
    main()
