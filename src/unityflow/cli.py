"""Command-line interface for unityflow.

Provides commands for normalizing, diffing, and validating Unity YAML files.
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import click

from unityflow import __version__
from unityflow.diff import DiffFormat, PrefabDiff
from unityflow.git_utils import (
    UNITY_EXTENSIONS,
    get_changed_files,
    get_files_changed_since,
    get_repo_root,
    is_git_repository,
)
from unityflow.normalizer import UnityPrefabNormalizer
from unityflow.validator import PrefabValidator
from unityflow.asset_tracker import (
    analyze_dependencies,
    find_references_to_asset,
    find_unity_project_root,
    build_guid_index,
    BINARY_ASSET_EXTENSIONS,
)


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
        click.echo(f"Processing {len(files_to_normalize)} files with {parallel_jobs} parallel workers...")

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
    "--no-normalize",
    is_flag=True,
    help="Don't normalize files before diffing",
)
@click.option(
    "--context",
    "-C",
    type=int,
    default=3,
    help="Number of context lines (default: 3)",
)
@click.option(
    "--format",
    "diff_format",
    type=click.Choice(["unified", "context", "summary"]),
    default="unified",
    help="Diff output format (default: unified)",
)
@click.option(
    "--exit-code",
    is_flag=True,
    help="Exit with 1 if files differ, 0 if identical",
)
def diff(
    old_file: Path,
    new_file: Path,
    no_normalize: bool,
    context: int,
    diff_format: str,
    exit_code: bool,
) -> None:
    """Show differences between two Unity YAML files.

    Normalizes both files before comparison to eliminate noise
    from Unity's non-deterministic serialization.

    Examples:

        # Compare two prefabs
        unityflow diff old.prefab new.prefab

        # Show raw diff without normalization
        unityflow diff old.prefab new.prefab --no-normalize

        # Exit with status code (for scripts)
        unityflow diff old.prefab new.prefab --exit-code
    """
    format_map = {
        "unified": DiffFormat.UNIFIED,
        "context": DiffFormat.CONTEXT,
        "summary": DiffFormat.SUMMARY,
    }

    differ = PrefabDiff(
        normalize=not no_normalize,
        context_lines=context,
        format=format_map[diff_format],
    )

    try:
        result = differ.diff_files(old_file, new_file)
    except Exception as e:
        click.echo(f"Error: Failed to diff files: {e}", err=True)
        sys.exit(1)

    if result.has_changes:
        click.echo("\n".join(result.diff_lines))
        if exit_code:
            sys.exit(1)
    else:
        click.echo("Files are identical (after normalization)")
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


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--path",
    "-p",
    "query_path_str",
    help="Path to query (e.g., 'gameObjects/*/name', 'components/*/type')",
)
@click.option(
    "--find-name",
    type=str,
    default=None,
    help="Find GameObjects by name pattern (supports * wildcard)",
)
@click.option(
    "--find-component",
    type=str,
    default=None,
    help="Find GameObjects with specific component type (e.g., 'Light2D', 'SpriteRenderer')",
)
@click.option(
    "--find-script",
    type=str,
    default=None,
    help="Find GameObjects with specific MonoBehaviour script",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def query(
    file: Path,
    query_path_str: str | None,
    find_name: str | None,
    find_component: str | None,
    find_script: str | None,
    output_format: str,
) -> None:
    """Query data from a Unity YAML file.

    Path syntax:
        gameObjects/*/name      - all GameObject names
        gameObjects/12345/name  - specific GameObject's name
        components/*/type       - all component types
        components/*/localPosition - all positions

    Examples:

        # List all GameObjects
        unityflow query Player.prefab --path "gameObjects/*/name"

        # Get all component types as JSON
        unityflow query Player.prefab --path "components/*/type" --format json

        # Show summary (no path)
        unityflow query Player.prefab

        # Find GameObjects by name (supports wildcards)
        unityflow query Scene.unity --find-name "Player*"
        unityflow query Scene.unity --find-name "*Enemy*"

        # Find GameObjects with specific component
        unityflow query Scene.unity --find-component "Light2D"
        unityflow query Scene.unity --find-component "SpriteRenderer"

        # Find GameObjects with specific MonoBehaviour script
        unityflow query Scene.unity --find-script PlayerController
    """
    from unityflow.parser import UnityYAMLDocument, CLASS_IDS
    from unityflow.query import query_path as do_query
    from unityflow.formats import get_summary
    import json
    import fnmatch

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    # Handle find-name query
    if find_name is not None:
        results = _find_by_name(doc, find_name)
        if not results:
            click.echo(f"No GameObjects found matching: {find_name}")
            return

        if output_format == "json":
            click.echo(json.dumps(results, indent=2))
        else:
            click.echo(f"Found {len(results)} GameObject(s) matching '{find_name}':")
            for r in results:
                click.echo(f"  {r['name']}")
                if r.get("components"):
                    click.echo(f"    Components: {', '.join(r['components'])}")
        return

    # Handle find-component query
    if find_component is not None:
        results = _find_by_component(doc, find_component)
        if not results:
            click.echo(f"No GameObjects found with component: {find_component}")
            return

        if output_format == "json":
            click.echo(json.dumps(results, indent=2))
        else:
            click.echo(f"Found {len(results)} GameObject(s) with '{find_component}':")
            for r in results:
                click.echo(f"  {r['name']}")
        return

    # Handle find-script query
    if find_script is not None:
        # Resolve script name to GUID if needed
        script_guid, error = _resolve_script_to_guid(find_script, file)
        if error:
            # If can't resolve, try using it directly (might be partial GUID)
            script_guid = find_script

        results = _find_by_script(doc, script_guid)
        if not results:
            click.echo(f"No GameObjects found with script: {find_script}")
            return

        if output_format == "json":
            click.echo(json.dumps(results, indent=2))
        else:
            click.echo(f"Found {len(results)} GameObject(s) with script '{find_script}':")
            for r in results:
                click.echo(f"  {r['name']}")
        return

    if not query_path_str:
        # Show summary
        summary = get_summary(doc)
        if output_format == "json":
            click.echo(json.dumps(summary, indent=2))
        else:
            s = summary["summary"]
            click.echo(f"File: {file}")
            click.echo(f"GameObjects: {s['totalGameObjects']}")
            click.echo(f"Components: {s['totalComponents']}")
            click.echo()
            click.echo("Types:")
            for type_name, count in sorted(s["typeCounts"].items()):
                click.echo(f"  {type_name}: {count}")
            if s["hierarchy"]:
                click.echo()
                click.echo("Hierarchy:")
                for h in s["hierarchy"][:20]:
                    click.echo(f"  {h}")
                if len(s["hierarchy"]) > 20:
                    click.echo(f"  ... and {len(s['hierarchy']) - 20} more")
        return

    # Execute query
    results = do_query(doc, query_path_str)

    if not results:
        click.echo(f"No results for path: {query_path_str}")
        return

    if output_format == "json":
        output = [{"path": r.path, "value": r.value} for r in results]
        click.echo(json.dumps(output, indent=2))
    else:
        for r in results:
            if isinstance(r.value, (dict, list)):
                click.echo(f"{r.path}: {json.dumps(r.value)}")
            else:
                click.echo(f"{r.path}: {r.value}")


def _resolve_gameobject_by_path(
    doc: "UnityYAMLDocument",
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
            return None, f"Index [{index}] out of range. Found {len(matches)} GameObjects at path '{path}'"

    # No index specified, show options
    error_lines = [f"Multiple GameObjects at path '{path}'."]
    error_lines.append(f"Use index to select: --to \"{path}[0]\" (0 to {len(matches) - 1})")
    return None, "\n".join(error_lines)


def _resolve_component_path(
    doc: "UnityYAMLDocument",
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
        "image", "button", "scrollrect", "mask", "rectmask2d",
        "graphicraycaster", "canvasscaler", "verticallayoutgroup",
        "horizontallayoutgroup", "contentsizefitter", "textmeshprougui",
        "tmp_inputfield", "eventsystem", "inputsystemuiinputmodule", "light2d"
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
            last_component_type_lower in name_to_ids or
            last_component_type_lower in package_components or
            last_component_type == "MonoBehaviour"
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
                return None, f"GameObject not found"

            go_content = go.get_content()
            if not go_content or "m_Component" not in go_content:
                return None, f"GameObject has no components"

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
                            script_guid = script_ref.get("guid", "") if isinstance(script_ref, dict) else ""
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
                    return f"components/{matching_components[last_component_index]}", None
                else:
                    return None, f"Index [{last_component_index}] out of range. Found {len(matching_components)} {last_component_type} components"

            # No index specified
            error_lines = [f"Multiple '{last_component_type}' components on '{go_path}'."]
            error_lines.append(f"Use index to select: \"{go_path}/{last_component_type}[0]\" (0 to {len(matching_components) - 1})")
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
            component_type_lower in name_to_ids or
            component_type_lower in package_components or
            component_type == "MonoBehaviour"
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
                return None, f"GameObject not found"

            go_content = go.get_content()
            if not go_content or "m_Component" not in go_content:
                return None, f"GameObject has no components"

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
                            script_guid = script_ref.get("guid", "") if isinstance(script_ref, dict) else ""
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
                    return f"components/{matching_components[component_index]}/{property_name}", None
                else:
                    return None, f"Index [{component_index}] out of range. Found {len(matching_components)} {component_type} components"

            # No index specified
            error_lines = [f"Multiple '{component_type}' components on '{go_path}'."]
            error_lines.append(f"Use index to select: \"{go_path}/{component_type}[0]/{property_name}\" (0 to {len(matching_components) - 1})")
            return None, "\n".join(error_lines)

    # Not a component path - treat as GameObject property
    # Path format: GameObject.../property
    go_path = "/".join(parts[:-1])
    go_id, error = _resolve_gameobject_by_path(doc, go_path)
    if error:
        return None, error

    return f"gameObjects/{go_id}/{property_name}", None


def _find_by_name(doc: "UnityYAMLDocument", pattern: str) -> list[dict]:
    """Find GameObjects by name pattern."""
    import fnmatch

    results = []
    game_objects = doc.get_game_objects()

    for go in game_objects:
        content = go.get_content()
        if not content:
            continue

        name = content.get("m_Name", "")
        if fnmatch.fnmatch(name, pattern):
            # Get component types
            component_types = []
            for comp_ref in content.get("m_Component", []):
                comp_id = comp_ref.get("component", {}).get("fileID", 0)
                if comp_id:
                    comp = doc.get_by_file_id(comp_id)
                    if comp:
                        component_types.append(comp.class_name)

            results.append({
                "name": name,
                "fileID": go.file_id,
                "layer": content.get("m_Layer", 0),
                "tag": content.get("m_TagString", "Untagged"),
                "isActive": content.get("m_IsActive", 1) == 1,
                "components": component_types,
            })

    return results


def _find_by_component(doc: "UnityYAMLDocument", component_type: str) -> list[dict]:
    """Find GameObjects with a specific component type."""
    from unityflow.parser import CLASS_IDS

    results = []

    # Build reverse mapping: class name -> class IDs
    name_to_ids: dict[str, list[int]] = {}
    for class_id, class_name in CLASS_IDS.items():
        name_lower = class_name.lower()
        if name_lower not in name_to_ids:
            name_to_ids[name_lower] = []
        name_to_ids[name_lower].append(class_id)

    # Find matching class IDs
    search_lower = component_type.lower()
    matching_class_ids = set()
    for name, ids in name_to_ids.items():
        if search_lower in name or name in search_lower:
            matching_class_ids.update(ids)

    # Also check for MonoBehaviour scripts with matching name in m_Script
    check_monobehaviour = not matching_class_ids or "mono" in search_lower or "script" in search_lower

    game_objects = doc.get_game_objects()

    for go in game_objects:
        content = go.get_content()
        if not content:
            continue

        for comp_ref in content.get("m_Component", []):
            comp_id = comp_ref.get("component", {}).get("fileID", 0)
            if not comp_id:
                continue

            comp = doc.get_by_file_id(comp_id)
            if not comp:
                continue

            # Check class ID match
            if comp.class_id in matching_class_ids:
                results.append({
                    "name": content.get("m_Name", ""),
                    "fileID": go.file_id,
                    "componentFileID": comp_id,
                    "componentType": comp.class_name,
                })
                break

            # Check MonoBehaviour with script name
            if check_monobehaviour and comp.class_id == 114:  # MonoBehaviour
                comp_content = comp.get_content()
                if comp_content:
                    # Try to get script reference for additional matching
                    script_ref = comp_content.get("m_Script", {})
                    if script_ref:
                        results.append({
                            "name": content.get("m_Name", ""),
                            "fileID": go.file_id,
                            "componentFileID": comp_id,
                            "componentType": "MonoBehaviour",
                            "scriptGUID": script_ref.get("guid", ""),
                        })
                        break

    return results


def _find_by_script(doc: "UnityYAMLDocument", script_guid: str) -> list[dict]:
    """Find GameObjects with MonoBehaviour by script GUID."""
    results = []
    game_objects = doc.get_game_objects()

    for go in game_objects:
        content = go.get_content()
        if not content:
            continue

        for comp_ref in content.get("m_Component", []):
            comp_id = comp_ref.get("component", {}).get("fileID", 0)
            if not comp_id:
                continue

            comp = doc.get_by_file_id(comp_id)
            if not comp or comp.class_id != 114:  # MonoBehaviour
                continue

            comp_content = comp.get_content()
            if not comp_content:
                continue

            script_ref = comp_content.get("m_Script", {})
            guid = script_ref.get("guid", "")

            if guid and (guid == script_guid or guid.startswith(script_guid)):
                results.append({
                    "name": content.get("m_Name", ""),
                    "fileID": go.file_id,
                    "componentFileID": comp_id,
                    "scriptGUID": guid,
                })
                break

    return results


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json"]),
    default="json",
    help="Output format (default: json)",
)
@click.option(
    "--no-raw",
    is_flag=True,
    help="Exclude _rawFields (smaller output, may lose round-trip fidelity)",
)
@click.option(
    "--indent",
    type=int,
    default=2,
    help="JSON indentation (default: 2)",
)
def export(
    file: Path,
    output: Path | None,
    output_format: str,
    no_raw: bool,
    indent: int,
) -> None:
    """Export a Unity YAML file to JSON format.

    The JSON format is designed for LLM manipulation:
    - Structured gameObjects and components sections
    - _rawFields preserves unknown fields for round-trip fidelity

    Examples:

        # Export prefab to JSON
        unityflow export Player.prefab -o player.json

        # Export scene to JSON
        unityflow export MainScene.unity -o scene.json

        # Export ScriptableObject to JSON
        unityflow export GameConfig.asset -o config.json

        # Export to stdout
        unityflow export Player.prefab

        # Compact output without raw fields
        unityflow export Player.prefab --no-raw --indent 0
    """
    from unityflow.formats import export_file_to_json

    try:
        json_str = export_file_to_json(
            file,
            output_path=output,
            include_raw=not no_raw,
            indent=indent,
        )
    except Exception as e:
        click.echo(f"Error: Failed to export {file}: {e}", err=True)
        sys.exit(1)

    if output:
        click.echo(f"Exported: {file} -> {output}")
    else:
        click.echo(json_str)


@main.command(name="import")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (required)",
    required=True,
)
def import_json(
    file: Path,
    output: Path,
) -> None:
    """Import a JSON file back to Unity YAML format.

    This enables round-trip conversion: YAML -> JSON (edit) -> YAML
    LLMs can modify the JSON and this command converts it back.

    Examples:

        # Import JSON to prefab
        unityflow import player.json -o Player.prefab

        # Import JSON to scene
        unityflow import scene.json -o MainScene.unity

        # Import JSON to ScriptableObject
        unityflow import config.json -o GameConfig.asset

        # Round-trip workflow
        unityflow export Player.prefab -o player.json
        # ... edit player.json ...
        unityflow import player.json -o Player.prefab
    """
    from unityflow.formats import import_file_from_json

    try:
        doc = import_file_from_json(file, output_path=output)
        click.echo(f"Imported: {file} -> {output}")
        click.echo(f"  Objects: {len(doc.objects)}")
    except Exception as e:
        click.echo(f"Error: Failed to import {file}: {e}", err=True)
        sys.exit(1)


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
    from unityflow.parser import UnityYAMLDocument
    from unityflow.query import get_value
    import json

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
    from unityflow.parser import UnityYAMLDocument
    from unityflow.query import set_value, merge_values
    from unityflow.asset_resolver import (
        resolve_value,
        is_asset_reference,
        AssetTypeMismatchError,
    )
    import json

    # Count how many value modes are specified
    value_modes = sum([
        value is not None,
        batch_values_json is not None,
    ])

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


@main.command(name="difftool")
@click.argument("old_file", type=click.Path(exists=True, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--tool",
    "-t",
    "tool_name",
    type=click.Choice(["vscode", "meld", "kdiff3", "opendiff", "vimdiff", "html"]),
    default=None,
    help="Diff tool to use (default: auto-detect or html)",
)
@click.option(
    "--no-normalize",
    is_flag=True,
    help="Don't normalize files before comparing",
)
@click.option(
    "--wait/--no-wait",
    default=True,
    help="Wait for diff tool to close (default: wait)",
)
def difftool(
    old_file: Path,
    new_file: Path,
    tool_name: str | None,
    no_normalize: bool,
    wait: bool,
) -> None:
    """Open normalized Unity files in an external diff tool.

    This command normalizes both files and opens them in a visual diff tool.
    Designed to be used as a git difftool or from Git Fork.

    Setup as git difftool:

        git config diff.tool prefab-unity
        git config difftool.prefab-unity.cmd 'unityflow difftool "$LOCAL" "$REMOTE"'

    Or use 'unityflow setup --with-difftool' for automatic configuration.

    Git Fork setup:

        1. Open Git Fork → Settings → Integration
        2. Set External Diff Tool to: Custom
        3. Path: unityflow
        4. Arguments: difftool "$LOCAL" "$REMOTE"

    Examples:

        # Compare with auto-detected tool
        unityflow difftool old.prefab new.prefab

        # Use VS Code
        unityflow difftool old.prefab new.prefab --tool vscode

        # Open HTML diff in browser
        unityflow difftool old.prefab new.prefab --tool html

        # Compare without normalization
        unityflow difftool old.prefab new.prefab --no-normalize
    """
    import shutil
    import subprocess
    import tempfile
    import webbrowser
    from html import escape

    normalizer = UnityPrefabNormalizer()

    # Normalize files or read as-is
    if no_normalize:
        old_content = old_file.read_text(encoding="utf-8")
        new_content = new_file.read_text(encoding="utf-8")
    else:
        try:
            old_content = normalizer.normalize_file(old_file)
        except Exception as e:
            click.echo(f"Warning: Could not normalize {old_file}: {e}", err=True)
            old_content = old_file.read_text(encoding="utf-8")

        try:
            new_content = normalizer.normalize_file(new_file)
        except Exception as e:
            click.echo(f"Warning: Could not normalize {new_file}: {e}", err=True)
            new_content = new_file.read_text(encoding="utf-8")

    # Auto-detect tool if not specified
    if tool_name is None:
        tool_name = _detect_diff_tool()

    if tool_name == "html":
        # Generate HTML diff and open in browser
        html_content = _generate_html_diff(
            old_content, new_content,
            old_label=str(old_file),
            new_label=str(new_file),
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(html_content)
            html_path = f.name

        click.echo(f"Opening diff in browser: {html_path}")
        webbrowser.open(f"file://{html_path}")
        return

    # Create temp files for external tool
    with tempfile.TemporaryDirectory() as tmpdir:
        old_tmp = Path(tmpdir) / f"old_{old_file.name}"
        new_tmp = Path(tmpdir) / f"new_{new_file.name}"

        old_tmp.write_text(old_content, encoding="utf-8")
        new_tmp.write_text(new_content, encoding="utf-8")

        # Build command for external tool
        cmd = _build_difftool_cmd(tool_name, old_tmp, new_tmp, wait)

        if cmd is None:
            click.echo(f"Error: Diff tool '{tool_name}' not found", err=True)
            click.echo("Available tools: vscode, meld, kdiff3, opendiff, vimdiff, html", err=True)
            sys.exit(1)

        try:
            if wait:
                subprocess.run(cmd, check=True)
            else:
                subprocess.Popen(cmd)
        except FileNotFoundError:
            click.echo(f"Error: Could not start {tool_name}", err=True)
            click.echo("Make sure the tool is installed and in your PATH", err=True)
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            # Some diff tools exit with non-zero when files differ
            pass


def _detect_diff_tool() -> str:
    """Auto-detect available diff tool."""
    import shutil

    tools = [
        ("code", "vscode"),
        ("meld", "meld"),
        ("kdiff3", "kdiff3"),
        ("opendiff", "opendiff"),  # macOS FileMerge
    ]

    for cmd, name in tools:
        if shutil.which(cmd):
            return name

    # Fallback to HTML if no tool found
    return "html"


def _build_difftool_cmd(
    tool: str,
    old_path: Path,
    new_path: Path,
    wait: bool,
) -> list[str] | None:
    """Build command line for diff tool."""
    import shutil

    if tool == "vscode":
        code_cmd = shutil.which("code")
        if not code_cmd:
            return None
        cmd = [code_cmd, "--diff", str(old_path), str(new_path)]
        if wait:
            cmd.append("--wait")
        return cmd

    elif tool == "meld":
        meld_cmd = shutil.which("meld")
        if not meld_cmd:
            return None
        return [meld_cmd, str(old_path), str(new_path)]

    elif tool == "kdiff3":
        kdiff3_cmd = shutil.which("kdiff3")
        if not kdiff3_cmd:
            return None
        return [kdiff3_cmd, str(old_path), str(new_path)]

    elif tool == "opendiff":
        opendiff_cmd = shutil.which("opendiff")
        if not opendiff_cmd:
            return None
        return [opendiff_cmd, str(old_path), str(new_path)]

    elif tool == "vimdiff":
        vimdiff_cmd = shutil.which("vimdiff")
        if not vimdiff_cmd:
            return None
        return [vimdiff_cmd, str(old_path), str(new_path)]

    return None


def _generate_html_diff(
    old_content: str,
    new_content: str,
    old_label: str,
    new_label: str,
) -> str:
    """Generate HTML side-by-side diff."""
    import difflib
    from html import escape

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    differ = difflib.HtmlDiff(tabsize=2, wrapcolumn=80)
    table = differ.make_table(
        old_lines,
        new_lines,
        fromdesc=escape(old_label),
        todesc=escape(new_label),
        context=True,
        numlines=5,
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Unity Prefab Diff</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #1e1e1e;
            color: #d4d4d4;
        }}
        h1 {{
            color: #569cd6;
            font-size: 18px;
            margin-bottom: 20px;
        }}
        table.diff {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            border-collapse: collapse;
            width: 100%;
            background: #252526;
        }}
        .diff th {{
            background: #333333;
            color: #cccccc;
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #404040;
        }}
        .diff td {{
            padding: 2px 8px;
            vertical-align: top;
            border-bottom: 1px solid #333333;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .diff_header {{
            background: #333333;
            color: #888888;
            font-weight: normal;
        }}
        .diff_next {{
            background: #333333;
        }}
        .diff_add {{
            background: #234023;
            color: #89d185;
        }}
        .diff_chg {{
            background: #3d3d00;
            color: #dcdcaa;
        }}
        .diff_sub {{
            background: #402020;
            color: #f48771;
        }}
        td.diff_header {{
            text-align: right;
            width: 40px;
            color: #6e7681;
            user-select: none;
        }}
        .legend {{
            margin-top: 20px;
            padding: 10px;
            background: #252526;
            border-radius: 4px;
        }}
        .legend span {{
            display: inline-block;
            padding: 2px 8px;
            margin-right: 10px;
            border-radius: 2px;
        }}
        .legend .add {{ background: #234023; color: #89d185; }}
        .legend .change {{ background: #3d3d00; color: #dcdcaa; }}
        .legend .delete {{ background: #402020; color: #f48771; }}
    </style>
</head>
<body>
    <h1>Unity Prefab Diff (Normalized)</h1>
    {table}
    <div class="legend">
        <span class="add">+ Added</span>
        <span class="change">~ Changed</span>
        <span class="delete">- Deleted</span>
    </div>
</body>
</html>
"""
    return html


@main.command(name="install-hooks")
@click.option(
    "--pre-commit",
    "use_pre_commit",
    is_flag=True,
    help="Install using pre-commit framework (requires pre-commit)",
)
@click.option(
    "--git-hooks",
    is_flag=True,
    help="Install native git pre-commit hook (no dependencies)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing hooks",
)
def install_hooks(
    use_pre_commit: bool,
    git_hooks: bool,
    force: bool,
) -> None:
    """Install pre-commit hooks for automatic normalization.

    Two installation methods are available:

    1. pre-commit framework (recommended):
       Requires the 'pre-commit' package to be installed.
       Creates a .pre-commit-config.yaml file.

    2. Native git hooks:
       Creates a git pre-commit hook directly.
       No additional dependencies required.

    Examples:

        # Install using pre-commit framework
        unityflow install-hooks --pre-commit

        # Install native git hook
        unityflow install-hooks --git-hooks

        # Overwrite existing hooks
        unityflow install-hooks --git-hooks --force
    """
    import subprocess

    if not is_git_repository():
        click.echo("Error: Not in a git repository", err=True)
        sys.exit(1)

    repo_root = get_repo_root()
    if not repo_root:
        click.echo("Error: Could not find git repository root", err=True)
        sys.exit(1)

    if not use_pre_commit and not git_hooks:
        click.echo("Error: Specify --pre-commit or --git-hooks", err=True)
        click.echo()
        click.echo("Options:")
        click.echo("  --pre-commit  Use pre-commit framework (recommended)")
        click.echo("  --git-hooks   Use native git hook (no dependencies)")
        sys.exit(1)

    if use_pre_commit:
        # Check if pre-commit is installed
        try:
            subprocess.run(["pre-commit", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            click.echo("Error: pre-commit is not installed", err=True)
            click.echo("Install it with: pip install pre-commit", err=True)
            sys.exit(1)

        config_path = repo_root / ".pre-commit-config.yaml"
        if config_path.exists() and not force:
            content = config_path.read_text()
            if "unityflow" in content:
                click.echo("unityflow hook already configured in .pre-commit-config.yaml")
                return
            click.echo("Found existing .pre-commit-config.yaml")
            click.echo("Add unityflow manually or use --force to overwrite")
            sys.exit(1)

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
        config_path.write_text(config_content)
        click.echo(f"Created: {config_path}")

        # Run pre-commit install
        try:
            subprocess.run(["pre-commit", "install"], cwd=repo_root, check=True)
            click.echo("Installed pre-commit hooks")
        except subprocess.CalledProcessError:
            click.echo("Warning: Failed to run 'pre-commit install'", err=True)
            click.echo("Run it manually: pre-commit install", err=True)

        click.echo()
        click.echo("Pre-commit hook installed successfully!")
        click.echo("Test with: pre-commit run --all-files")

    if git_hooks:
        hooks_dir = repo_root / ".git" / "hooks"
        hook_path = hooks_dir / "pre-commit"

        if hook_path.exists() and not force:
            click.echo(f"Error: Hook already exists: {hook_path}", err=True)
            click.echo("Use --force to overwrite", err=True)
            sys.exit(1)

        hook_content = """\
#!/bin/bash
# unityflow pre-commit hook
# Automatically normalize Unity YAML files before commit

set -e

# Get list of staged Unity files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.(prefab|unity|asset)$' || true)

if [ -n "$STAGED_FILES" ]; then
    echo "Normalizing Unity files..."

    # Normalize each staged file
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
        click.echo(f"Created: {hook_path}")
        click.echo()
        click.echo("Git pre-commit hook installed successfully!")
        click.echo("Unity files will be normalized automatically on commit.")


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
    """Three-way merge of Unity YAML files.

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
    from unityflow.merge import three_way_merge

    normalizer = UnityPrefabNormalizer()

    try:
        base_content = normalizer.normalize_file(base)
        ours_content = normalizer.normalize_file(ours)
        theirs_content = normalizer.normalize_file(theirs)
    except Exception as e:
        click.echo(f"Error: Failed to normalize files: {e}", err=True)
        sys.exit(1)

    # Perform 3-way merge
    result, has_conflict = three_way_merge(base_content, ours_content, theirs_content)

    output_path = output or ours
    output_path.write_text(result, encoding="utf-8", newline="\n")

    display_path = file_path or str(output_path)

    if has_conflict:
        click.echo(f"Conflict: {display_path} (manual resolution needed)", err=True)
        sys.exit(1)
    else:
        # Silent success for git integration (git expects no output on success)
        sys.exit(0)


@main.command(name="stats")
@click.argument("files", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def stats(
    files: tuple[Path, ...],
    output_format: str,
) -> None:
    """Show statistics for Unity YAML files.

    This is a fast operation that scans file headers without full parsing.
    Useful for analyzing large files before processing.

    Examples:

        # Show stats for a single file
        unityflow stats Boss.unity

        # Show stats for multiple files
        unityflow stats *.prefab

        # Output as JSON
        unityflow stats Boss.unity --format json
    """
    from unityflow.parser import UnityYAMLDocument, CLASS_IDS
    import json

    all_stats = []

    for file in files:
        file_stats = UnityYAMLDocument.get_stats(file)
        file_stats["path"] = str(file)

        # Map class IDs to names
        class_names = {}
        for class_id, count in file_stats["class_counts"].items():
            name = CLASS_IDS.get(class_id, f"Unknown({class_id})")
            class_names[name] = count
        file_stats["class_names"] = class_names

        all_stats.append(file_stats)

    if output_format == "json":
        click.echo(json.dumps(all_stats, indent=2))
    else:
        for stats in all_stats:
            click.echo(f"File: {stats['path']}")
            click.echo(f"  Size: {stats['file_size_mb']:.2f} MB ({stats['file_size']:,} bytes)")
            click.echo(f"  Documents: {stats['document_count']}")
            if stats["is_large_file"]:
                click.echo("  Status: Large file (streaming mode recommended)")
            click.echo("  Types:")
            for name, count in sorted(stats["class_names"].items(), key=lambda x: -x[1]):
                click.echo(f"    {name}: {count}")
            click.echo()


@main.command(name="deps")
@click.argument("files", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--project-root",
    type=click.Path(exists=True, path_type=Path),
    help="Unity project root (auto-detected if not specified)",
)
@click.option(
    "--binary-only",
    is_flag=True,
    help="Show only binary asset dependencies (textures, meshes, etc.)",
)
@click.option(
    "--unresolved-only",
    is_flag=True,
    help="Show only unresolved dependencies (missing assets)",
)
@click.option(
    "--type",
    "asset_type",
    type=str,
    help="Filter by asset type (Texture, Model, Audio, Script, etc.)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--include-packages",
    is_flag=True,
    help="Include Packages folder in GUID resolution",
)
def deps(
    files: tuple[Path, ...],
    project_root: Path | None,
    binary_only: bool,
    unresolved_only: bool,
    asset_type: str | None,
    output_format: str,
    include_packages: bool,
) -> None:
    """Show asset dependencies for Unity YAML files.

    Analyzes prefab, scene, or asset files and lists all referenced
    external assets (textures, meshes, scripts, other prefabs, etc.).

    Dependencies are resolved using the project's .meta files to map
    GUIDs to actual file paths.

    Examples:

        # Show all dependencies
        unityflow deps Player.prefab

        # Show only binary assets (textures, meshes, audio)
        unityflow deps Player.prefab --binary-only

        # Show only unresolved (missing) dependencies
        unityflow deps Player.prefab --unresolved-only

        # Filter by type
        unityflow deps Player.prefab --type Texture

        # Output as JSON
        unityflow deps Player.prefab --format json

        # Analyze multiple files
        unityflow deps *.prefab
    """
    import json

    # Analyze dependencies
    try:
        report = analyze_dependencies(
            files=list(files),
            project_root=project_root,
            include_packages=include_packages,
        )
    except Exception as e:
        click.echo(f"Error: Failed to analyze dependencies: {e}", err=True)
        sys.exit(1)

    # Apply filters
    deps_to_show = report.dependencies

    if binary_only:
        deps_to_show = [d for d in deps_to_show if d.is_binary]
    if unresolved_only:
        deps_to_show = [d for d in deps_to_show if not d.is_resolved]
    if asset_type:
        deps_to_show = [d for d in deps_to_show if d.asset_type and d.asset_type.lower() == asset_type.lower()]

    # Output
    if output_format == "json":
        output_data = report.to_dict()
        if binary_only or unresolved_only or asset_type:
            # Filter the JSON output too
            output_data["dependencies"] = [
                d for d in output_data["dependencies"]
                if (not binary_only or d.get("binary"))
                and (not unresolved_only or not d.get("resolved"))
                and (not asset_type or (d.get("type") or "").lower() == asset_type.lower())
            ]
        click.echo(json.dumps(output_data, indent=2))
    else:
        # Text output
        click.echo(f"Dependencies for: {', '.join(str(f) for f in files)}")
        click.echo()

        if report.guid_index:
            click.echo(f"Project root: {report.guid_index.project_root}")
            click.echo(f"GUID index: {len(report.guid_index)} assets indexed")
        else:
            click.echo("Warning: Project root not found, dependencies cannot be resolved")
        click.echo()

        click.echo(f"Summary:")
        click.echo(f"  Total dependencies: {report.total_dependencies}")
        click.echo(f"  Resolved: {report.resolved_count}")
        click.echo(f"  Unresolved: {report.unresolved_count}")
        click.echo(f"  Binary assets: {report.binary_count}")
        click.echo()

        if not deps_to_show:
            if binary_only or unresolved_only or asset_type:
                click.echo("No dependencies match the specified filters.")
            else:
                click.echo("No external dependencies found.")
            return

        click.echo("Dependencies:")
        for dep in deps_to_show:
            if dep.is_resolved:
                status = "✓" if dep.is_binary else "○"
                path_str = str(dep.path)
                type_str = f" [{dep.asset_type}]" if dep.asset_type else ""
                click.echo(f"  {status} {path_str}{type_str}")
            else:
                click.echo(f"  ✗ {dep.guid} [UNRESOLVED]")

        # Show type breakdown
        if deps_to_show and not asset_type:
            click.echo()
            click.echo("By type:")
            type_counts: dict[str, int] = {}
            for dep in deps_to_show:
                t = dep.asset_type or "Unknown"
                type_counts[t] = type_counts.get(t, 0) + 1
            for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                click.echo(f"  {t}: {count}")


@main.command(name="find-refs")
@click.argument("asset", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--search-path",
    type=click.Path(exists=True, path_type=Path),
    multiple=True,
    help="Directory to search in (can be specified multiple times)",
)
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
@click.option(
    "--progress",
    is_flag=True,
    help="Show progress bar",
)
def find_refs(
    asset: Path,
    search_path: tuple[Path, ...],
    project_root: Path | None,
    output_format: str,
    progress: bool,
) -> None:
    """Find files that reference a specific asset.

    Searches Unity YAML files for references to the specified asset
    using its GUID from the .meta file.

    Examples:

        # Find all files referencing a texture
        unityflow find-refs Textures/player.png

        # Search in specific directories
        unityflow find-refs Textures/player.png --search-path Assets/Prefabs

        # Output as JSON
        unityflow find-refs Textures/player.png --format json

        # Show progress
        unityflow find-refs Textures/player.png --progress
    """
    import json

    # Determine search paths
    search_paths = list(search_path) if search_path else []

    # Find project root if not specified
    if project_root is None:
        project_root = find_unity_project_root(asset)

    # If no search paths specified, search Assets folder
    if not search_paths and project_root:
        assets_dir = project_root / "Assets"
        if assets_dir.is_dir():
            search_paths.append(assets_dir)

    if not search_paths:
        click.echo("Error: No search paths specified and project root not found", err=True)
        click.echo("Use --search-path to specify directories to search", err=True)
        sys.exit(1)

    # Build GUID index for resolution
    guid_index = None
    if project_root:
        guid_index = build_guid_index(project_root)

    # Set up progress callback
    progress_callback = None
    progress_bar = None
    if progress:
        def progress_callback(current: int, total: int) -> None:
            nonlocal progress_bar
            if progress_bar is None:
                progress_bar = click.progressbar(
                    length=total,
                    label="Searching",
                    show_eta=True,
                    show_percent=True,
                )
                progress_bar.__enter__()
            progress_bar.update(1)

    try:
        results = find_references_to_asset(
            asset_path=asset,
            search_paths=search_paths,
            guid_index=guid_index,
            progress_callback=progress_callback,
        )
    except Exception as e:
        click.echo(f"Error: Failed to search for references: {e}", err=True)
        sys.exit(1)
    finally:
        if progress_bar:
            progress_bar.__exit__(None, None, None)

    # Output
    if output_format == "json":
        output_data = {
            "asset": str(asset),
            "search_paths": [str(p) for p in search_paths],
            "reference_count": len(results),
            "references": [
                {
                    "file": str(file_path),
                    "occurrences": len(refs),
                    "locations": [
                        {
                            "file_id": ref.source_file_id,
                            "property_path": ref.property_path,
                        }
                        for ref in refs
                    ],
                }
                for file_path, refs in results
            ],
        }
        click.echo(json.dumps(output_data, indent=2))
    else:
        click.echo(f"References to: {asset}")
        click.echo()

        if not results:
            click.echo("No references found.")
            return

        click.echo(f"Found {len(results)} file(s) with references:")
        click.echo()

        for file_path, refs in results:
            # Try to show relative path
            rel_path = file_path
            if project_root:
                try:
                    rel_path = file_path.relative_to(project_root)
                except ValueError:
                    pass

            click.echo(f"  {rel_path}")
            click.echo(f"    {len(refs)} reference(s)")


@main.command(name="scan-scripts")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    help="Recursively scan directories for Unity files",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--show-properties",
    is_flag=True,
    help="Show property keys for each script (useful for understanding structure)",
)
@click.option(
    "--group-by-guid",
    is_flag=True,
    help="Group results by GUID instead of by file",
)
def scan_scripts(
    paths: tuple[Path, ...],
    recursive: bool,
    output_format: str,
    show_properties: bool,
    group_by_guid: bool,
) -> None:
    """Scan Unity files and extract all script GUIDs.

    Extracts GUIDs from MonoBehaviour components (classId=114) to help
    identify package components like Light2D, TextMeshPro, etc.

    This is useful for:
    - Discovering GUIDs of package components used in your project
    - Building a reference table for programmatic prefab creation
    - Analyzing which scripts are used across prefabs/scenes

    Examples:

        # Scan a single file
        unityflow scan-scripts Player.prefab

        # Scan a directory recursively
        unityflow scan-scripts Assets/Prefabs -r

        # Show property keys (to understand component structure)
        unityflow scan-scripts Scene.unity --show-properties

        # Group by GUID to see all usages
        unityflow scan-scripts Assets/ -r --group-by-guid

        # Output as JSON for further processing
        unityflow scan-scripts *.prefab --format json
    """
    from unityflow.parser import UnityYAMLDocument
    import json

    # Collect files to scan
    files_to_scan: list[Path] = []

    for path in paths:
        if path.is_file():
            files_to_scan.append(path)
        elif path.is_dir():
            if recursive:
                for ext in UNITY_EXTENSIONS:
                    files_to_scan.extend(path.rglob(f"*{ext}"))
            else:
                for ext in UNITY_EXTENSIONS:
                    files_to_scan.extend(path.glob(f"*{ext}"))

    if not files_to_scan:
        click.echo("No Unity files found to scan.", err=True)
        sys.exit(1)

    # Remove duplicates and sort
    files_to_scan = sorted(set(files_to_scan))

    # Data structures for results
    # guid_info: {guid: {fileID, type, files: set, properties: set}}
    guid_info: dict[str, dict] = {}
    # file_scripts: {file: [{guid, fileID, properties}]}
    file_scripts: dict[Path, list[dict]] = {}

    # Scan files
    for file_path in files_to_scan:
        try:
            doc = UnityYAMLDocument.load(file_path)
        except Exception as e:
            click.echo(f"Warning: Failed to parse {file_path}: {e}", err=True)
            continue

        file_scripts[file_path] = []

        for obj in doc.objects:
            if obj.class_id != 114:  # MonoBehaviour only
                continue

            content = obj.get_content()
            if not content:
                continue

            script_ref = content.get("m_Script", {})
            if not isinstance(script_ref, dict):
                continue

            guid = script_ref.get("guid", "")
            if not guid:
                continue

            file_id = script_ref.get("fileID", 0)
            ref_type = script_ref.get("type", 0)

            # Extract property keys (exclude common Unity fields)
            skip_keys = {
                "m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
                "m_PrefabAsset", "m_GameObject", "m_Enabled", "m_Script",
                "m_EditorHideFlags", "m_EditorClassIdentifier"
            }
            properties = [k for k in content.keys() if k not in skip_keys]

            # Update guid_info
            if guid not in guid_info:
                guid_info[guid] = {
                    "fileID": file_id,
                    "type": ref_type,
                    "files": set(),
                    "properties": set(),
                    "count": 0,
                }
            guid_info[guid]["files"].add(str(file_path))
            guid_info[guid]["properties"].update(properties)
            guid_info[guid]["count"] += 1

            # Update file_scripts
            file_scripts[file_path].append({
                "guid": guid,
                "fileID": file_id,
                "properties": properties,
            })

    # Output results
    if output_format == "json":
        if group_by_guid:
            output_data = {
                "scripts": [
                    {
                        "guid": guid,
                        "fileID": info["fileID"],
                        "type": info["type"],
                        "usageCount": info["count"],
                        "files": sorted(info["files"]),
                        "properties": sorted(info["properties"]) if show_properties else None,
                    }
                    for guid, info in sorted(guid_info.items(), key=lambda x: -x[1]["count"])
                ],
                "summary": {
                    "totalScripts": len(guid_info),
                    "filesScanned": len(files_to_scan),
                }
            }
            # Remove None properties if not requested
            if not show_properties:
                for script in output_data["scripts"]:
                    del script["properties"]
        else:
            output_data = {
                "files": [
                    {
                        "path": str(file_path),
                        "scripts": scripts,
                    }
                    for file_path, scripts in file_scripts.items()
                    if scripts
                ],
                "summary": {
                    "totalScripts": len(guid_info),
                    "filesScanned": len(files_to_scan),
                }
            }

        click.echo(json.dumps(output_data, indent=2))
    else:
        # Text output
        click.echo(f"Scanned {len(files_to_scan)} file(s)")
        click.echo(f"Found {len(guid_info)} unique script GUID(s)")
        click.echo()

        if group_by_guid:
            click.echo("Scripts by GUID:")
            click.echo("-" * 60)

            for guid, info in sorted(guid_info.items(), key=lambda x: -x[1]["count"]):
                click.echo(f"\nGUID: {guid}")
                click.echo(f"  fileID: {info['fileID']}")
                click.echo(f"  type: {info['type']}")
                click.echo(f"  Usage count: {info['count']}")
                click.echo(f"  Found in {len(info['files'])} file(s):")
                for f in sorted(info["files"])[:5]:
                    click.echo(f"    - {f}")
                if len(info["files"]) > 5:
                    click.echo(f"    ... and {len(info['files']) - 5} more")

                if show_properties and info["properties"]:
                    click.echo(f"  Properties: {', '.join(sorted(info['properties']))}")
        else:
            click.echo("Scripts by file:")
            click.echo("-" * 60)

            for file_path, scripts in file_scripts.items():
                if not scripts:
                    continue

                click.echo(f"\n{file_path}:")
                for script in scripts:
                    click.echo(f"  GUID: {script['guid']}")
                    click.echo(f"    fileID: {script['fileID']}")
                    if show_properties and script["properties"]:
                        props_str = ", ".join(script["properties"][:10])
                        if len(script["properties"]) > 10:
                            props_str += f", ... (+{len(script['properties']) - 10} more)"
                        click.echo(f"    Properties: {props_str}")

        # Show summary table
        if guid_info:
            click.echo()
            click.echo("=" * 60)
            click.echo("GUID Summary Table (for SKILL.md):")
            click.echo("-" * 60)
            click.echo("| GUID | fileID | Usage Count |")
            click.echo("|------|--------|-------------|")
            for guid, info in sorted(guid_info.items(), key=lambda x: -x[1]["count"]):
                click.echo(f"| `{guid}` | {info['fileID']} | {info['count']} |")


@main.command(name="scan-meta")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    help="Recursively scan directories for .meta files",
)
@click.option(
    "--scripts-only",
    is_flag=True,
    help="Only show C# script (.cs) files",
)
@click.option(
    "--filter",
    "name_filter",
    type=str,
    help="Filter by filename pattern (e.g., 'Light', 'Camera')",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def scan_meta(
    paths: tuple[Path, ...],
    recursive: bool,
    scripts_only: bool,
    name_filter: str | None,
    output_format: str,
) -> None:
    """Scan .meta files to extract asset GUIDs.

    Directly scans Unity package folders or any directory containing .meta files
    to extract GUIDs. Useful for finding package component GUIDs without needing
    a prefab/scene that uses them.

    This is useful for:
    - Finding GUIDs of package scripts (Light2D, TextMeshPro, etc.)
    - Building a complete GUID reference for a package
    - Discovering available components in a package

    Examples:

        # Scan URP package for scripts
        unityflow scan-meta "Library/PackageCache/com.unity.render-pipelines.universal@*" -r --scripts-only

        # Find Light-related scripts
        unityflow scan-meta "Library/PackageCache/com.unity.render-pipelines.universal@*" -r --filter Light

        # Scan TextMeshPro package
        unityflow scan-meta "Library/PackageCache/com.unity.textmeshpro@*" -r --scripts-only

        # Scan local Assets folder
        unityflow scan-meta Assets/Scripts -r

        # Output as JSON
        unityflow scan-meta "Library/PackageCache/com.unity.cinemachine@*" -r --scripts-only --format json
    """
    import re
    import json

    # Collect .meta files to scan
    meta_files: list[Path] = []

    for path in paths:
        if path.is_file() and path.suffix == ".meta":
            meta_files.append(path)
        elif path.is_dir():
            if recursive:
                meta_files.extend(path.rglob("*.meta"))
            else:
                meta_files.extend(path.glob("*.meta"))

    if not meta_files:
        click.echo("No .meta files found to scan.", err=True)
        sys.exit(1)

    # Filter for scripts only if requested
    if scripts_only:
        meta_files = [f for f in meta_files if f.name.endswith(".cs.meta")]

    # Apply name filter
    if name_filter:
        pattern = re.compile(name_filter, re.IGNORECASE)
        meta_files = [f for f in meta_files if pattern.search(f.stem)]

    if not meta_files:
        click.echo("No matching .meta files found after filtering.", err=True)
        sys.exit(1)

    # Remove duplicates and sort
    meta_files = sorted(set(meta_files))

    # Extract GUIDs from meta files
    results: list[dict] = []
    guid_pattern = re.compile(r"^guid:\s*([a-f0-9]{32})\s*$", re.MULTILINE)

    for meta_file in meta_files:
        try:
            content = meta_file.read_text(encoding="utf-8")
            match = guid_pattern.search(content)
            if match:
                guid = match.group(1)
                # Get the asset name (remove .meta extension)
                asset_name = meta_file.stem  # e.g., "Light2D.cs"
                asset_path = str(meta_file.parent / asset_name)

                # Determine asset type
                if asset_name.endswith(".cs"):
                    asset_type = "Script"
                    script_name = asset_name[:-3]  # Remove .cs
                elif asset_name.endswith(".shader"):
                    asset_type = "Shader"
                    script_name = asset_name
                elif asset_name.endswith(".prefab"):
                    asset_type = "Prefab"
                    script_name = asset_name
                else:
                    asset_type = "Asset"
                    script_name = asset_name

                results.append({
                    "name": script_name,
                    "guid": guid,
                    "type": asset_type,
                    "path": asset_path,
                    "metaFile": str(meta_file),
                })
        except Exception as e:
            click.echo(f"Warning: Failed to read {meta_file}: {e}", err=True)

    if not results:
        click.echo("No GUIDs found in scanned files.", err=True)
        sys.exit(1)

    # Detect package name from path
    package_name = None
    if results:
        first_path = results[0]["path"]
        if "PackageCache" in first_path:
            # Extract package name from path like "Library/PackageCache/com.unity.xxx@version/..."
            parts = first_path.split("/")
            for i, part in enumerate(parts):
                if part == "PackageCache" and i + 1 < len(parts):
                    pkg_part = parts[i + 1]
                    # Remove version suffix
                    if "@" in pkg_part:
                        package_name = pkg_part.split("@")[0]
                    else:
                        package_name = pkg_part
                    break

    # Output results
    if output_format == "json":
        output_data = {
            "package": package_name,
            "assets": results,
            "summary": {
                "totalAssets": len(results),
                "scripts": len([r for r in results if r["type"] == "Script"]),
            }
        }
        click.echo(json.dumps(output_data, indent=2))
    else:
        if package_name:
            click.echo(f"Package: {package_name}")
        click.echo(f"Scanned {len(meta_files)} .meta file(s)")
        click.echo(f"Found {len(results)} asset(s) with GUIDs")
        click.echo()

        # Group by type
        scripts = [r for r in results if r["type"] == "Script"]
        others = [r for r in results if r["type"] != "Script"]

        if scripts:
            click.echo("Scripts:")
            click.echo("-" * 70)
            click.echo(f"{'Name':<40} {'GUID':<34}")
            click.echo("-" * 70)
            for r in sorted(scripts, key=lambda x: x["name"]):
                click.echo(f"{r['name']:<40} {r['guid']}")

        if others and not scripts_only:
            click.echo()
            click.echo("Other Assets:")
            click.echo("-" * 70)
            for r in sorted(others, key=lambda x: x["name"]):
                click.echo(f"{r['name']:<40} {r['guid']} [{r['type']}]")

        # Show markdown table for scripts
        if scripts:
            click.echo()
            click.echo("=" * 70)
            click.echo("Markdown Table (for documentation):")
            click.echo("-" * 70)
            click.echo("| Script | GUID |")
            click.echo("|--------|------|")
            for r in sorted(scripts, key=lambda x: x["name"]):
                click.echo(f"| {r['name']} | `{r['guid']}` |")


@main.command(name="parse-script")
@click.argument("script_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def parse_script_cmd(
    script_path: Path,
    output_format: str,
) -> None:
    """Parse a C# script and show serialized field order.

    Extracts serialized fields from MonoBehaviour or ScriptableObject scripts
    and shows them in declaration order. Useful for understanding the expected
    field order in Unity YAML files.

    Examples:

        # Parse a script and show field order
        unityflow parse-script Assets/Scripts/Player.cs

        # Output as JSON
        unityflow parse-script Assets/Scripts/Player.cs --format json
    """
    from unityflow.script_parser import parse_script_file
    import json

    info = parse_script_file(script_path)

    if info is None:
        click.echo(f"Error: Failed to parse {script_path}", err=True)
        click.echo("Make sure it's a valid C# class file.", err=True)
        sys.exit(1)

    if output_format == "json":
        output_data = {
            "path": str(script_path),
            "className": info.class_name,
            "namespace": info.namespace,
            "baseClass": info.base_class,
            "fields": [
                {
                    "name": f.name,
                    "unityName": f.unity_name,
                    "type": f.field_type,
                    "isPublic": f.is_public,
                    "hasSerializeField": f.has_serialize_field,
                    "lineNumber": f.line_number,
                }
                for f in info.fields
            ],
            "fieldOrder": info.get_field_order(),
        }
        click.echo(json.dumps(output_data, indent=2))
    else:
        click.echo(f"Script: {script_path}")
        click.echo(f"Class: {info.class_name}")
        if info.namespace:
            click.echo(f"Namespace: {info.namespace}")
        if info.base_class:
            click.echo(f"Base Class: {info.base_class}")
        click.echo()

        if not info.fields:
            click.echo("No serialized fields found.")
            return

        click.echo(f"Serialized Fields ({len(info.fields)}):")
        click.echo("-" * 60)
        click.echo(f"{'#':<4} {'Name':<25} {'Unity Name':<25} {'Type'}")
        click.echo("-" * 60)

        for i, f in enumerate(info.fields, 1):
            access = "public" if f.is_public else "[SerializeField]"
            click.echo(f"{i:<4} {f.name:<25} {f.unity_name:<25} {f.field_type}")

        click.echo()
        click.echo("Expected field order in Unity YAML:")
        for name in info.get_field_order():
            click.echo(f"  - {name}")


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
    subprocess.run([*git_config_cmd, "merge.unity.name", "Unity YAML Merge (unityflow)"], check=True)
    subprocess.run([*git_config_cmd, "merge.unity.driver", "unityflow merge %O %A %B -o %A --path %P"], check=True)
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
        subprocess.run(
            [*git_config_cmd, "difftool.prefab-unity.cmd", f'unityflow difftool{backend_arg} "$LOCAL" "$REMOTE"'],
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
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.(prefab|unity|asset)$' || true)

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


@main.command(name="sprite-info")
@click.argument("sprite", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def sprite_info_cmd(
    sprite: Path,
    output_format: str,
) -> None:
    """Show sprite import information from meta file.

    Displays the sprite mode and available sub-sprites (for Multiple mode).
    This is useful for determining what fileID to use when linking sprites.

    Examples:

        # Show sprite info
        unityflow sprite-info Assets/Sprites/player.png

        # Output as JSON
        unityflow sprite-info Assets/Sprites/atlas.png --format json
    """
    from unityflow.sprite import get_sprite_info, SPRITE_SINGLE_MODE_FILE_ID
    import json

    info = get_sprite_info(sprite)
    if not info:
        click.echo(f"Error: Could not read sprite info for: {sprite}", err=True)
        if not Path(str(sprite) + ".meta").exists():
            click.echo("Meta file not found", err=True)
        sys.exit(1)

    if output_format == "json":
        output = {
            "path": str(sprite),
            "guid": info.guid,
            "spriteMode": info.sprite_mode,
            "spriteModeString": "Single" if info.is_single else "Multiple",
            "fileID": SPRITE_SINGLE_MODE_FILE_ID if info.is_single else None,
            "subSprites": [
                {"name": s["name"], "internalID": s["internalID"]}
                for s in info.sprites
            ] if info.is_multiple else [],
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"Sprite: {sprite}")
        click.echo(f"Mode: {'Single' if info.is_single else 'Multiple'}")
        click.echo()

        if info.is_single:
            click.echo("Usage:")
            click.echo(f"  unityflow set <file> \"<path>/m_Sprite\" \"@{sprite}\"")
        else:
            click.echo(f"Sub-sprites ({len(info.sprites)}):")
            for s in info.sprites:
                click.echo(f"  {s['name']}")

            if info.sprites:
                first_sprite = info.sprites[0]
                click.echo()
                click.echo("Usage (first sub-sprite):")
                click.echo(f"  unityflow set <file> \"<path>/m_Sprite\" \"@{sprite}#{first_sprite['name']}\"")


@main.command(name="add-object")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--name",
    "-n",
    "obj_name",
    type=str,
    default="NewGameObject",
    help="Name for the new GameObject (default: NewGameObject)",
)
@click.option(
    "--parent",
    "-p",
    "parent_path",
    type=str,
    default=None,
    help="Parent GameObject path (e.g., 'Canvas/Panel')",
)
@click.option(
    "--position",
    type=str,
    default=None,
    help="Local position as 'x,y,z' (default: 0,0,0)",
)
@click.option(
    "--layer",
    type=int,
    default=0,
    help="Layer number (default: 0)",
)
@click.option(
    "--tag",
    type=str,
    default="Untagged",
    help="Tag string (default: Untagged)",
)
@click.option(
    "--ui",
    is_flag=True,
    help="Create UI GameObject (uses RectTransform instead of Transform)",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
def add_object(
    file: Path,
    obj_name: str,
    parent_path: str | None,
    position: str | None,
    layer: int,
    tag: str,
    ui: bool,
    output: Path | None,
) -> None:
    """Add a new GameObject to a Unity YAML file.

    Creates a new GameObject with a Transform (or RectTransform for UI).

    Examples:

        # Add a new GameObject at root
        unityflow add-object Scene.unity --name "Player"

        # Add with parent
        unityflow add-object Scene.unity --name "Child" --parent "Canvas"

        # Add with position
        unityflow add-object Scene.unity --name "Enemy" --position "10,0,5"

        # Add UI GameObject (RectTransform)
        unityflow add-object Scene.unity --name "Button" --ui --parent "Canvas/Panel"

        # Add with layer and tag
        unityflow add-object Scene.unity --name "Enemy" --layer 8 --tag "Enemy"
    """
    from unityflow.parser import (
        UnityYAMLDocument,
        create_game_object,
        create_transform,
        create_rect_transform,
    )

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Resolve parent path to Transform ID
    parent_transform_id = 0
    if parent_path:
        parent_go_id, error = _resolve_gameobject_by_path(doc, parent_path)
        if error:
            click.echo(f"Error: {error}", err=True)
            sys.exit(1)

        # Find the Transform component of the parent GameObject
        parent_go = doc.get_by_file_id(parent_go_id)
        if parent_go:
            go_content = parent_go.get_content()
            if go_content and "m_Component" in go_content:
                for comp_ref in go_content["m_Component"]:
                    comp_id = comp_ref.get("component", {}).get("fileID", 0)
                    comp = doc.get_by_file_id(comp_id)
                    if comp and comp.class_id in (4, 224):  # Transform or RectTransform
                        parent_transform_id = comp_id
                        break

        if parent_transform_id == 0:
            click.echo(f"Error: Could not find Transform for parent '{parent_path}'", err=True)
            sys.exit(1)

    # Parse position
    pos = None
    if position:
        try:
            x, y, z = map(float, position.split(","))
            pos = {"x": x, "y": y, "z": z}
        except ValueError:
            click.echo(f"Error: Invalid position format: {position}", err=True)
            click.echo("Expected format: x,y,z (e.g., '10,0,5')", err=True)
            sys.exit(1)

    # Create new GameObject
    go_id = doc.generate_unique_file_id()
    transform_id = doc.generate_unique_file_id()

    # Create Transform or RectTransform
    if ui:
        transform = create_rect_transform(
            game_object_id=go_id,
            file_id=transform_id,
            position=pos,
            parent_id=parent_transform_id,
        )
    else:
        transform = create_transform(
            game_object_id=go_id,
            file_id=transform_id,
            position=pos,
            parent_id=parent_transform_id,
        )

    # Create GameObject
    go = create_game_object(
        name=obj_name,
        file_id=go_id,
        layer=layer,
        tag=tag,
        components=[transform_id],
    )

    # Add to document
    doc.add_object(go)
    doc.add_object(transform)

    # Update parent's children list if parent specified
    if parent_transform_id != 0:
        parent_obj = doc.get_by_file_id(parent_transform_id)
        if parent_obj:
            content = parent_obj.get_content()
            if content and "m_Children" in content:
                content["m_Children"].append({"fileID": transform_id})

    doc.save(output_path)
    click.echo(f"Added GameObject '{obj_name}'")

    if output:
        click.echo(f"Saved to: {output}")


# Package component name to GUID mapping
# These are MonoBehaviour components from Unity packages
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
    "SpriteRenderer", "MeshRenderer", "TrailRenderer", "LineRenderer", "SkinnedMeshRenderer",
    # Camera & Light
    "Camera", "Light",
    # Audio
    "AudioSource", "AudioListener",
    # 3D Colliders
    "BoxCollider", "SphereCollider", "CapsuleCollider", "MeshCollider",
    # 2D Colliders
    "BoxCollider2D", "CircleCollider2D", "PolygonCollider2D", "EdgeCollider2D",
    "CapsuleCollider2D", "CompositeCollider2D",
    # Physics
    "Rigidbody", "Rigidbody2D", "CharacterController",
    # Animation
    "Animator", "Animation",
    # UI
    "Canvas", "CanvasGroup", "CanvasRenderer",
    # Misc
    "MeshFilter", "TextMesh", "ParticleSystem", "SpriteMask",
]

# All supported component types for --type option
ALL_COMPONENT_TYPES = BUILTIN_COMPONENT_TYPES + list(PACKAGE_COMPONENT_GUIDS.keys())


# ============================================================================
# Field Type Validation
# ============================================================================

class FieldType:
    """Unity field types for validation."""
    VECTOR2 = "Vector2"      # {x, y}
    VECTOR3 = "Vector3"      # {x, y, z}
    VECTOR4 = "Vector4"      # {x, y, z, w}
    QUATERNION = "Quaternion"  # {x, y, z, w}
    COLOR = "Color"          # {r, g, b, a}
    BOOL = "bool"            # 0 or 1
    INT = "int"              # integer
    FLOAT = "float"          # number
    STRING = "string"        # string
    ASSET_REF = "AssetRef"   # {fileID, guid, type}


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
    "m_maskOffset": FieldType.VECTOR4,

    # Color fields
    "m_Color": FieldType.COLOR,
    "m_fontColor": FieldType.COLOR,
    "color": FieldType.COLOR,

    # Bool fields (0 or 1)
    "m_IsActive": FieldType.BOOL,
    "m_Enabled": FieldType.BOOL,
    "m_RaycastTarget": FieldType.BOOL,
    "m_Maskable": FieldType.BOOL,
    "m_isRightToLeft": FieldType.BOOL,
    "m_isRichText": FieldType.BOOL,
    "m_isOrthographic": FieldType.BOOL,
    "m_CullTransparentMesh": FieldType.BOOL,
    "m_ShowMaskGraphic": FieldType.BOOL,
    "m_FlipX": FieldType.BOOL,
    "m_FlipY": FieldType.BOOL,
    "m_ConstrainProportionsScale": FieldType.BOOL,
    "isActive": FieldType.BOOL,
    "enabled": FieldType.BOOL,

    # Int fields
    "m_Layer": FieldType.INT,
    "m_SortingOrder": FieldType.INT,
    "m_SortingLayerID": FieldType.INT,
    "m_ObjectHideFlags": FieldType.INT,
    "m_NavMeshLayer": FieldType.INT,
    "m_StaticEditorFlags": FieldType.INT,
    "m_HorizontalAlignment": FieldType.INT,
    "m_VerticalAlignment": FieldType.INT,
    "m_fontStyle": FieldType.INT,
    "m_overflowMode": FieldType.INT,
    "sortingOrder": FieldType.INT,
    "layer": FieldType.INT,

    # Float fields
    "m_fontSize": FieldType.FLOAT,
    "m_fontSizeBase": FieldType.FLOAT,
    "m_fontSizeMin": FieldType.FLOAT,
    "m_fontSizeMax": FieldType.FLOAT,
    "m_characterSpacing": FieldType.FLOAT,
    "m_wordSpacing": FieldType.FLOAT,
    "m_lineSpacing": FieldType.FLOAT,
    "m_paragraphSpacing": FieldType.FLOAT,
    "m_FillAmount": FieldType.FLOAT,
    "fontSize": FieldType.FLOAT,
    "fillAmount": FieldType.FLOAT,

    # String fields
    "m_Name": FieldType.STRING,
    "m_TagString": FieldType.STRING,
    "m_text": FieldType.STRING,
    "name": FieldType.STRING,
    "text": FieldType.STRING,

    # Asset reference fields
    "m_Sprite": FieldType.ASSET_REF,
    "m_Material": FieldType.ASSET_REF,
    "m_Script": FieldType.ASSET_REF,
    "m_fontAsset": FieldType.ASSET_REF,
    "m_sharedMaterial": FieldType.ASSET_REF,
    "sprite": FieldType.ASSET_REF,
    "material": FieldType.ASSET_REF,
}


def _validate_field_value(field_name: str, value: any) -> tuple[bool, str | None]:
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
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Vector2 형식이어야 합니다: {{\"x\": 0, \"y\": 0}}"
        required = {"x", "y"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}. 형식: {{\"x\": 0, \"y\": 0}}"
        for k in ["x", "y"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.VECTOR3:
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Vector3 형식이어야 합니다: {{\"x\": 0, \"y\": 0, \"z\": 0}}"
        required = {"x", "y", "z"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}. 형식: {{\"x\": 0, \"y\": 0, \"z\": 0}}"
        for k in ["x", "y", "z"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.VECTOR4:
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Vector4 형식이어야 합니다: {{\"x\": 0, \"y\": 0, \"z\": 0, \"w\": 0}}"
        required = {"x", "y", "z", "w"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}. 형식: {{\"x\": 0, \"y\": 0, \"z\": 0, \"w\": 0}}"
        for k in ["x", "y", "z", "w"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.QUATERNION:
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Quaternion 형식이어야 합니다: {{\"x\": 0, \"y\": 0, \"z\": 0, \"w\": 1}}"
        required = {"x", "y", "z", "w"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}. 형식: {{\"x\": 0, \"y\": 0, \"z\": 0, \"w\": 1}}"
        for k in ["x", "y", "z", "w"]:
            if not isinstance(value.get(k), (int, float)):
                return False, f"'{field_name}.{k}'는 숫자여야 합니다"
        return True, None

    if field_type == FieldType.COLOR:
        if not isinstance(value, dict):
            return False, f"'{field_name}'은(는) Color 형식이어야 합니다: {{\"r\": 1, \"g\": 1, \"b\": 1, \"a\": 1}}"
        required = {"r", "g", "b", "a"}
        if not required.issubset(value.keys()):
            missing = required - set(value.keys())
            return False, f"'{field_name}'에 필수 키가 없습니다: {missing}. 형식: {{\"r\": 1, \"g\": 1, \"b\": 1, \"a\": 1}}"
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
        return False, f"'{field_name}'은(는) 에셋 참조 형식이어야 합니다: \"@Assets/path/to/asset.ext\""

    return True, None


def _resolve_script_to_guid(
    script_ref: str,
    file_path: Path,
    include_packages: bool = True,
) -> tuple[str | None, str | None]:
    """Resolve a script reference (GUID or name) to a GUID.

    Searches in order:
    1. Assets/ folder (user scripts)
    2. Packages/ folder (local packages)
    3. Library/PackageCache/ (downloaded packages) - if include_packages=True

    Args:
        script_ref: Either a 32-char hex GUID or a script class name
        file_path: Path to the Unity file being edited (for project root detection)
        include_packages: Whether to search in Library/PackageCache/

    Returns:
        Tuple of (guid, error_message). If successful, error_message is None.
    """
    import re

    # Check if it's already a GUID (32 hex characters)
    if re.match(r"^[a-f0-9]{32}$", script_ref, re.IGNORECASE):
        return script_ref, None

    # It's a script name - search for matching .cs file
    from unityflow.asset_tracker import find_unity_project_root, get_cached_guid_index

    project_root = find_unity_project_root(file_path)
    if not project_root:
        return None, f"Unity 프로젝트 루트를 찾을 수 없습니다."

    # Search for matching .cs files
    script_name = script_ref
    if script_name.endswith(".cs"):
        script_name = script_name[:-3]

    # Use cached GUID index for faster lookup
    guid_index = get_cached_guid_index(project_root, include_packages=include_packages)

    # Search by script name in the index
    matches: list[tuple[Path, str]] = []
    guid_pattern = re.compile(r"^guid:\s*([a-f0-9]{32})\s*$", re.MULTILINE)

    # Define search directories in priority order
    search_dirs = [project_root / "Assets"]
    if (project_root / "Packages").is_dir():
        search_dirs.append(project_root / "Packages")
    if include_packages and (project_root / "Library" / "PackageCache").is_dir():
        search_dirs.append(project_root / "Library" / "PackageCache")

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        for cs_file in search_dir.rglob(f"{script_name}.cs"):
            meta_file = cs_file.with_suffix(".cs.meta")
            if meta_file.exists():
                try:
                    meta_content = meta_file.read_text(encoding="utf-8")
                    guid_match = guid_pattern.search(meta_content)
                    if guid_match:
                        matches.append((cs_file, guid_match.group(1)))
                except Exception:
                    pass

    if not matches:
        search_locations = "Assets/"
        if include_packages:
            search_locations += ", Packages/, Library/PackageCache/"
        return None, f"스크립트를 찾을 수 없습니다: '{script_name}'. 검색 위치: {search_locations}"

    if len(matches) > 1:
        # Prefer Assets/ over packages
        assets_matches = [m for m in matches if "Assets" in str(m[0])]
        if len(assets_matches) == 1:
            return assets_matches[0][1], None

        paths = "\n  ".join(str(m[0].relative_to(project_root)) for m in matches)
        return None, f"'{script_name}' 이름의 스크립트가 여러 개 있습니다:\n  {paths}\nGUID를 직접 지정하세요."

    return matches[0][1], None


def _get_script_default_properties(
    script_guid: str,
    project_root: Path,
) -> dict | None:
    """Get default property values from a script by parsing the C# source.

    Args:
        script_guid: GUID of the script
        project_root: Unity project root path

    Returns:
        Dict of property name -> default value, or None if not found
    """
    from unityflow.asset_tracker import get_cached_guid_index
    from unityflow.script_parser import parse_script_file

    # Get script path from GUID
    guid_index = get_cached_guid_index(project_root, include_packages=True)
    script_path = guid_index.get_path(script_guid)

    if script_path is None:
        return None

    # Resolve to absolute path
    if not script_path.is_absolute():
        script_path = project_root / script_path

    # Only parse C# scripts
    if script_path.suffix.lower() != ".cs":
        return None

    # Parse script
    script_info = parse_script_file(script_path)
    if script_info is None:
        return None

    # Extract default values from fields
    defaults = {}
    for field in script_info.fields:
        if field.default_value is not None:
            defaults[field.unity_name] = field.default_value

    return defaults if defaults else None


@main.command(name="add-component")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--to",
    "-t",
    "target_path",
    type=str,
    required=True,
    help="Target GameObject path (e.g., 'Canvas/Panel/Button')",
)
@click.option(
    "--type",
    "component_type",
    type=click.Choice(ALL_COMPONENT_TYPES),
    default=None,
    help="Component type to add (built-in or package component)",
)
@click.option(
    "--script",
    "script_ref",
    type=str,
    default=None,
    help="Script name to add (e.g., 'PlayerController')",
)
@click.option(
    "--props",
    type=str,
    default=None,
    help="JSON object with component properties",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
def add_component(
    file: Path,
    target_path: str,
    component_type: str | None,
    script_ref: str | None,
    props: str | None,
    output: Path | None,
) -> None:
    """Add a component to an existing GameObject.

    Requires either --type for components or --script for custom MonoBehaviour.

    Supported component types include:
    - Built-in: SpriteRenderer, Camera, Light, AudioSource, BoxCollider2D, etc.
    - Package: Image, Button, TextMeshProUGUI, Light2D, EventSystem, etc.

    Examples:

        # Add a built-in component
        unityflow add-component Scene.unity --to "Player" --type SpriteRenderer

        # Add to nested GameObject
        unityflow add-component Scene.unity --to "Canvas/Panel/Button" --type Image

        # When multiple GameObjects have the same path, use index
        unityflow add-component Scene.unity --to "Canvas/Panel/Button[1]" --type Image

        # Add a custom MonoBehaviour by script name
        unityflow add-component Scene.unity --to "Player" --script PlayerController

        # Add with properties
        unityflow add-component Scene.unity --to "Canvas/Panel" --type Image \\
            --props '{"m_Color": {"r": 1, "g": 0, "b": 0, "a": 1}}'
    """
    from unityflow.parser import (
        UnityYAMLDocument,
        create_mono_behaviour,
    )
    import json

    if not component_type and not script_ref:
        click.echo("Error: Specify --type or --script", err=True)
        sys.exit(1)

    if component_type and script_ref:
        click.echo("Error: Cannot use both --type and --script", err=True)
        sys.exit(1)

    # Resolve script reference to GUID if specified
    script_guid = None
    if script_ref:
        script_guid, error = _resolve_script_to_guid(script_ref, file)
        if error:
            click.echo(f"Error: {error}", err=True)
            sys.exit(1)

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Parse user-provided properties
    user_properties = None
    if props:
        try:
            user_properties = json.loads(props)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --props: {e}", err=True)
            sys.exit(1)

    # Resolve target GameObject by path
    target_id, error = _resolve_gameobject_by_path(doc, target_path)
    if error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    target_go = doc.get_by_file_id(target_id)
    if target_go is None or target_go.class_id != 1:
        click.echo(f"Error: Failed to resolve GameObject at '{target_path}'", err=True)
        sys.exit(1)

    component_id = doc.generate_unique_file_id()

    # Get project root for script parsing
    from unityflow.asset_tracker import find_unity_project_root
    project_root = find_unity_project_root(file)

    if script_guid:
        # Get default values from script
        properties = {}
        if project_root:
            script_defaults = _get_script_default_properties(script_guid, project_root)
            if script_defaults:
                properties.update(script_defaults)

        # User properties override script defaults
        if user_properties:
            properties.update(user_properties)

        # Create MonoBehaviour with explicit script GUID
        component = create_mono_behaviour(
            game_object_id=target_id,
            script_guid=script_guid,
            file_id=component_id,
            properties=properties if properties else None,
        )
        click.echo(f"Added MonoBehaviour component")
    elif component_type in PACKAGE_COMPONENT_GUIDS:
        # Get default values from package script
        package_guid = PACKAGE_COMPONENT_GUIDS[component_type]
        properties = {}
        if project_root:
            script_defaults = _get_script_default_properties(package_guid, project_root)
            if script_defaults:
                properties.update(script_defaults)

        # User properties override script defaults
        if user_properties:
            properties.update(user_properties)

        # Create package component (MonoBehaviour with known GUID)
        component = create_mono_behaviour(
            game_object_id=target_id,
            script_guid=package_guid,
            file_id=component_id,
            properties=properties if properties else None,
        )
        click.echo(f"Added {component_type} component (package)")
    else:
        # Create built-in component
        component = _create_builtin_component(
            component_type=component_type,
            game_object_id=target_id,
            file_id=component_id,
            properties=user_properties,
        )
        click.echo(f"Added {component_type} component")

    # Add component to document
    doc.add_object(component)

    # Update GameObject's component list
    go_content = target_go.get_content()
    if go_content and "m_Component" in go_content:
        go_content["m_Component"].append({"component": {"fileID": component_id}})

    doc.save(output_path)
    click.echo(f"  Target: {target_path}")

    if output:
        click.echo(f"Saved to: {output}")


def _create_builtin_component(
    component_type: str,
    game_object_id: int,
    file_id: int,
    properties: dict | None = None,
) -> "UnityYAMLObject":
    """Create a built-in Unity component."""
    from unityflow.parser import UnityYAMLObject

    # Class ID mapping for built-in components
    class_ids = {
        "Transform": 4,
        "RectTransform": 224,
        "MonoBehaviour": 114,
        # Renderer
        "SpriteRenderer": 212,
        "MeshRenderer": 23,
        "TrailRenderer": 96,
        "LineRenderer": 120,
        "SkinnedMeshRenderer": 137,
        # Camera & Light
        "Camera": 20,
        "Light": 108,
        # Audio
        "AudioSource": 82,
        "AudioListener": 81,
        # 3D Colliders
        "BoxCollider": 65,
        "SphereCollider": 135,
        "CapsuleCollider": 136,
        "MeshCollider": 64,
        # 2D Colliders
        "BoxCollider2D": 61,
        "CircleCollider2D": 58,
        "PolygonCollider2D": 60,
        "EdgeCollider2D": 68,
        "CapsuleCollider2D": 70,
        "CompositeCollider2D": 66,
        # Physics
        "Rigidbody": 54,
        "Rigidbody2D": 50,
        "CharacterController": 144,
        # Animation
        "Animator": 95,
        "Animation": 111,
        # UI
        "Canvas": 223,
        "CanvasGroup": 225,
        "CanvasRenderer": 222,
        # Misc
        "MeshFilter": 33,
        "TextMesh": 102,
        "ParticleSystem": 180,
        "SpriteMask": 199,
    }

    class_id = class_ids.get(component_type, 114)

    # Base content for components
    content = {
        "m_ObjectHideFlags": 0,
        "m_CorrespondingSourceObject": {"fileID": 0},
        "m_PrefabInstance": {"fileID": 0},
        "m_PrefabAsset": {"fileID": 0},
        "m_GameObject": {"fileID": game_object_id},
        "m_Enabled": 1,
    }

    # Add type-specific defaults
    if component_type == "SpriteRenderer":
        content.update({
            "m_CastShadows": 0,
            "m_ReceiveShadows": 0,
            "m_DynamicOccludee": 1,
            "m_StaticShadowCaster": 0,
            "m_MotionVectors": 1,
            "m_LightProbeUsage": 1,
            "m_ReflectionProbeUsage": 1,
            "m_RenderingLayerMask": 1,
            "m_RendererPriority": 0,
            "m_Sprite": {"fileID": 0},
            "m_Color": {"r": 1, "g": 1, "b": 1, "a": 1},
            "m_FlipX": 0,
            "m_FlipY": 0,
            "m_DrawMode": 0,
            "m_MaskInteraction": 0,
            "m_SpriteSortPoint": 0,
        })
    elif component_type == "Camera":
        content.update({
            "m_ClearFlags": 1,
            "m_BackGroundColor": {"r": 0.19215687, "g": 0.3019608, "b": 0.4745098, "a": 0},
            "m_projectionMatrixMode": 1,
            "m_GateFitMode": 2,
            "m_FOVAxisMode": 0,
            "m_NearClipPlane": 0.3,
            "m_FarClipPlane": 1000,
            "m_FieldOfView": 60,
            "m_Orthographic": 0,
            "m_OrthographicSize": 5,
            "m_Depth": 0,
        })
    elif component_type == "Light":
        content.update({
            "m_Type": 1,
            "m_Shape": 0,
            "m_Color": {"r": 1, "g": 0.95686275, "b": 0.8392157, "a": 1},
            "m_Intensity": 1,
            "m_Range": 10,
            "m_SpotAngle": 30,
            "m_InnerSpotAngle": 21.80208,
            "m_CookieSize": 10,
            "m_Shadows": {"m_Type": 2, "m_Resolution": -1, "m_CustomResolution": -1},
        })
    elif component_type == "AudioSource":
        content.update({
            "m_AudioClip": {"fileID": 0},
            "m_PlayOnAwake": 1,
            "m_Volume": 1,
            "m_Pitch": 1,
            "m_Loop": 0,
            "m_Mute": 0,
            "m_Spatialize": 0,
            "m_SpatializePostEffects": 0,
            "m_Priority": 128,
            "m_DopplerLevel": 1,
            "m_MinDistance": 1,
            "m_MaxDistance": 500,
            "m_Pan2D": 0,
        })
    elif component_type in ("BoxCollider2D", "CircleCollider2D"):
        content.update({
            "m_Density": 1,
            "m_Material": {"fileID": 0},
            "m_IsTrigger": 0,
            "m_UsedByEffector": 0,
            "m_UsedByComposite": 0,
            "m_Offset": {"x": 0, "y": 0},
        })
        if component_type == "BoxCollider2D":
            content["m_Size"] = {"x": 1, "y": 1}
            content["m_EdgeRadius"] = 0
        else:
            content["m_Radius"] = 0.5
    elif component_type == "Rigidbody2D":
        content.update({
            "m_BodyType": 0,
            "m_Simulated": 1,
            "m_UseFullKinematicContacts": 0,
            "m_UseAutoMass": 0,
            "m_Mass": 1,
            "m_LinearDamping": 0,
            "m_AngularDamping": 0.05,
            "m_GravityScale": 1,
            "m_Material": {"fileID": 0},
            "m_Interpolate": 0,
            "m_SleepingMode": 1,
            "m_CollisionDetection": 0,
            "m_Constraints": 0,
        })
    elif component_type == "Canvas":
        content.update({
            "m_RenderMode": 0,
            "m_Camera": {"fileID": 0},
            "m_PlaneDistance": 100,
            "m_PixelPerfect": 0,
            "m_ReceivesEvents": 1,
            "m_OverrideSorting": 0,
            "m_OverridePixelPerfect": 0,
            "m_SortingBucketNormalizedSize": 0,
            "m_VertexColorAlwaysGammaSpace": 0,
            "m_AdditionalShaderChannelsFlag": 25,
            "m_UpdateRectTransformForStandalone": 0,
            "m_SortingLayerID": 0,
            "m_SortingOrder": 0,
            "m_TargetDisplay": 0,
        })
    elif component_type == "CanvasGroup":
        content.update({
            "m_Alpha": 1,
            "m_Interactable": 1,
            "m_BlocksRaycasts": 1,
            "m_IgnoreParentGroups": 0,
        })
    elif component_type == "CanvasRenderer":
        content.update({
            "m_CullTransparentMesh": 1,
        })
    # Renderer components
    elif component_type == "MeshRenderer":
        content.update({
            "m_CastShadows": 1,
            "m_ReceiveShadows": 1,
            "m_DynamicOccludee": 1,
            "m_StaticShadowCaster": 0,
            "m_MotionVectors": 1,
            "m_LightProbeUsage": 1,
            "m_ReflectionProbeUsage": 1,
            "m_RenderingLayerMask": 1,
            "m_RendererPriority": 0,
            "m_Materials": [],
        })
    elif component_type == "TrailRenderer":
        content.update({
            "m_CastShadows": 0,
            "m_ReceiveShadows": 0,
            "m_DynamicOccludee": 1,
            "m_MotionVectors": 0,
            "m_Time": 5,
            "m_MinVertexDistance": 0.1,
            "m_Autodestruct": 0,
            "m_Emitting": 1,
            "m_Parameters": {
                "widthMultiplier": 1,
                "widthCurve": {"serializedVersion": 2, "m_Curve": [], "m_PreInfinity": 2, "m_PostInfinity": 2},
                "colorGradient": {"serializedVersion": 2, "key0": {"r": 1, "g": 1, "b": 1, "a": 1}, "key1": {"r": 1, "g": 1, "b": 1, "a": 1}},
            },
        })
    elif component_type == "LineRenderer":
        content.update({
            "m_CastShadows": 0,
            "m_ReceiveShadows": 0,
            "m_DynamicOccludee": 1,
            "m_MotionVectors": 0,
            "m_Positions": [],
            "m_Parameters": {
                "widthMultiplier": 1,
                "widthCurve": {"serializedVersion": 2, "m_Curve": [], "m_PreInfinity": 2, "m_PostInfinity": 2},
                "colorGradient": {"serializedVersion": 2, "key0": {"r": 1, "g": 1, "b": 1, "a": 1}, "key1": {"r": 1, "g": 1, "b": 1, "a": 1}},
            },
            "m_UseWorldSpace": 1,
            "m_Loop": 0,
        })
    elif component_type == "SkinnedMeshRenderer":
        content.update({
            "m_CastShadows": 1,
            "m_ReceiveShadows": 1,
            "m_DynamicOccludee": 1,
            "m_MotionVectors": 1,
            "m_LightProbeUsage": 1,
            "m_ReflectionProbeUsage": 1,
            "m_RenderingLayerMask": 1,
            "m_RendererPriority": 0,
            "m_Materials": [],
            "m_Mesh": {"fileID": 0},
            "m_Bones": [],
            "m_BlendShapeWeights": [],
            "m_RootBone": {"fileID": 0},
            "m_AABB": {"m_Center": {"x": 0, "y": 0, "z": 0}, "m_Extent": {"x": 0, "y": 0, "z": 0}},
            "m_UpdateWhenOffscreen": 0,
            "m_SkinnedMotionVectors": 1,
        })
    # Audio
    elif component_type == "AudioListener":
        # AudioListener has minimal properties
        pass  # Uses base content only
    # 3D Colliders
    elif component_type == "BoxCollider":
        content.update({
            "m_IsTrigger": 0,
            "m_Material": {"fileID": 0},
            "m_Center": {"x": 0, "y": 0, "z": 0},
            "m_Size": {"x": 1, "y": 1, "z": 1},
        })
    elif component_type == "SphereCollider":
        content.update({
            "m_IsTrigger": 0,
            "m_Material": {"fileID": 0},
            "m_Center": {"x": 0, "y": 0, "z": 0},
            "m_Radius": 0.5,
        })
    elif component_type == "CapsuleCollider":
        content.update({
            "m_IsTrigger": 0,
            "m_Material": {"fileID": 0},
            "m_Center": {"x": 0, "y": 0, "z": 0},
            "m_Radius": 0.5,
            "m_Height": 2,
            "m_Direction": 1,  # Y-axis
        })
    elif component_type == "MeshCollider":
        content.update({
            "m_IsTrigger": 0,
            "m_Material": {"fileID": 0},
            "m_Convex": 0,
            "m_CookingOptions": 30,
            "m_Mesh": {"fileID": 0},
        })
    # 2D Colliders (additional)
    elif component_type == "PolygonCollider2D":
        content.update({
            "m_Density": 1,
            "m_Material": {"fileID": 0},
            "m_IsTrigger": 0,
            "m_UsedByEffector": 0,
            "m_UsedByComposite": 0,
            "m_Offset": {"x": 0, "y": 0},
            "m_UseDelaunayMesh": 0,
            "m_Points": {"m_Paths": []},
        })
    elif component_type == "EdgeCollider2D":
        content.update({
            "m_Density": 1,
            "m_Material": {"fileID": 0},
            "m_IsTrigger": 0,
            "m_UsedByEffector": 0,
            "m_UsedByComposite": 0,
            "m_Offset": {"x": 0, "y": 0},
            "m_EdgeRadius": 0,
            "m_Points": [],
        })
    elif component_type == "CapsuleCollider2D":
        content.update({
            "m_Density": 1,
            "m_Material": {"fileID": 0},
            "m_IsTrigger": 0,
            "m_UsedByEffector": 0,
            "m_UsedByComposite": 0,
            "m_Offset": {"x": 0, "y": 0},
            "m_Size": {"x": 1, "y": 2},
            "m_Direction": 1,  # Vertical
        })
    elif component_type == "CompositeCollider2D":
        content.update({
            "m_Density": 1,
            "m_Material": {"fileID": 0},
            "m_IsTrigger": 0,
            "m_UsedByEffector": 0,
            "m_Offset": {"x": 0, "y": 0},
            "m_GeometryType": 0,  # Polygons
            "m_GenerationType": 0,  # Synchronous
            "m_VertexDistance": 0.0005,
            "m_OffsetDistance": 0.000025,
        })
    # Physics (3D)
    elif component_type == "Rigidbody":
        content.update({
            "m_Mass": 1,
            "m_Drag": 0,
            "m_AngularDrag": 0.05,
            "m_CenterOfMass": {"x": 0, "y": 0, "z": 0},
            "m_InertiaTensor": {"x": 1, "y": 1, "z": 1},
            "m_InertiaRotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            "m_UseGravity": 1,
            "m_IsKinematic": 0,
            "m_Interpolate": 0,
            "m_Constraints": 0,
            "m_CollisionDetection": 0,
        })
    elif component_type == "CharacterController":
        content.update({
            "m_Height": 2,
            "m_Radius": 0.5,
            "m_SlopeLimit": 45,
            "m_StepOffset": 0.3,
            "m_SkinWidth": 0.08,
            "m_MinMoveDistance": 0.001,
            "m_Center": {"x": 0, "y": 0, "z": 0},
        })
    # Animation
    elif component_type == "Animator":
        content.update({
            "m_Controller": {"fileID": 0},
            "m_Avatar": {"fileID": 0},
            "m_ApplyRootMotion": 0,
            "m_LinearVelocityBlending": 0,
            "m_WarningMessage": "",
            "m_HasTransformHierarchy": 1,
            "m_AllowConstantClipSamplingOptimization": 1,
            "m_KeepAnimatorStateOnDisable": 0,
            "m_UpdateMode": 0,  # Normal
            "m_CullingMode": 0,  # AlwaysAnimate
        })
    elif component_type == "Animation":
        content.update({
            "m_Animation": {"fileID": 0},
            "m_Animations": [],
            "m_WrapMode": 0,  # Default
            "m_PlayAutomatically": 1,
            "m_AnimatePhysics": 0,
            "m_CullingType": 0,
        })
    # Misc
    elif component_type == "MeshFilter":
        content.update({
            "m_Mesh": {"fileID": 0},
        })
    elif component_type == "TextMesh":
        content.update({
            "m_Text": "",
            "m_OffsetZ": 0,
            "m_CharacterSize": 1,
            "m_LineSpacing": 1,
            "m_Anchor": 4,  # MiddleCenter
            "m_Alignment": 0,  # Left
            "m_TabSize": 4,
            "m_FontSize": 0,
            "m_FontStyle": 0,  # Normal
            "m_RichText": 1,
            "m_Font": {"fileID": 0},
            "m_Color": {"r": 1, "g": 1, "b": 1, "a": 1},
        })
    elif component_type == "ParticleSystem":
        # ParticleSystem has very complex default structure, using minimal
        content.update({
            "lengthInSec": 5,
            "simulationSpeed": 1,
            "looping": 1,
            "prewarm": 0,
            "playOnAwake": 1,
            "useUnscaledTime": 0,
            "autoRandomSeed": 1,
            "useRigidbodyForVelocity": 1,
            "startDelay": {"serializedVersion": 2, "minMaxState": 0, "scalar": 0},
            "moveWithTransform": 0,
            "moveWithCustomTransform": {"fileID": 0},
            "scalingMode": 1,
            "randomSeed": 0,
        })
    elif component_type == "SpriteMask":
        content.update({
            "m_Sprite": {"fileID": 0},
            "m_AlphaCutoff": 0.5,
            "m_IsCustomRangeActive": 0,
            "m_FrontSortingLayerID": 0,
            "m_FrontSortingOrder": 0,
            "m_BackSortingLayerID": 0,
            "m_BackSortingOrder": 0,
            "m_SpriteSortPoint": 0,
        })

    # Override with custom properties
    if properties:
        content.update(properties)

    return UnityYAMLObject(
        class_id=class_id,
        file_id=file_id,
        data={component_type: content},
        stripped=False,
    )


@main.command(name="delete-object")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--id",
    "-i",
    "gameobject_path",
    type=str,
    required=True,
    help="GameObject path (e.g., 'Canvas/Panel/Button')",
)
@click.option(
    "--cascade",
    is_flag=True,
    help="Delete all children as well",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Delete without confirmation",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
def delete_object(
    file: Path,
    gameobject_path: str,
    cascade: bool,
    force: bool,
    output: Path | None,
) -> None:
    """Delete a GameObject from a Unity YAML file.

    Deletes the GameObject and all its components.
    Use --cascade to also delete all children recursively.

    Examples:

        # Delete a GameObject (keeps children)
        unityflow delete-object Scene.unity --id "Canvas/Panel/Button"

        # Delete a GameObject and all its children
        unityflow delete-object Scene.unity --id "Enemy" --cascade

        # Delete without confirmation
        unityflow delete-object Scene.unity --id "Player" --force

        # When multiple GameObjects have the same path, use index
        unityflow delete-object Scene.unity --id "Canvas/Panel/Button[1]"
    """
    from unityflow.parser import UnityYAMLDocument

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Resolve GameObject by path
    gameobject_id, error = _resolve_gameobject_by_path(doc, gameobject_path)
    if error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    obj = doc.get_by_file_id(gameobject_id)
    if obj is None or obj.class_id != 1:
        click.echo(f"Error: Failed to resolve GameObject at '{gameobject_path}'", err=True)
        sys.exit(1)

    # Collect all objects to delete
    objects_to_delete = _collect_objects_to_delete(doc, gameobject_id, cascade)

    if not force:
        click.echo(f"Will delete {len(objects_to_delete)} object(s):")
        for obj_id in objects_to_delete[:10]:
            del_obj = doc.get_by_file_id(obj_id)
            if del_obj:
                name = ""
                content = del_obj.get_content()
                if content and "m_Name" in content:
                    name = f" '{content['m_Name']}'"
                click.echo(f"  {del_obj.class_name}{name}")
        if len(objects_to_delete) > 10:
            click.echo(f"  ... and {len(objects_to_delete) - 10} more")

        if not click.confirm("Continue?"):
            click.echo("Aborted")
            return

    # Update parent Transform's children list
    go_content = obj.get_content()
    if go_content and "m_Component" in go_content:
        for comp_ref in go_content["m_Component"]:
            comp_id = comp_ref.get("component", {}).get("fileID", 0)
            comp = doc.get_by_file_id(comp_id)
            if comp and comp.class_id in (4, 224):  # Transform or RectTransform
                comp_content = comp.get_content()
                if comp_content and "m_Father" in comp_content:
                    parent_id = comp_content["m_Father"].get("fileID", 0)
                    if parent_id != 0:
                        parent_transform = doc.get_by_file_id(parent_id)
                        if parent_transform:
                            parent_content = parent_transform.get_content()
                            if parent_content and "m_Children" in parent_content:
                                parent_content["m_Children"] = [
                                    c for c in parent_content["m_Children"]
                                    if c.get("fileID") != comp_id
                                ]

    # Delete all collected objects
    deleted_count = 0
    for obj_id in objects_to_delete:
        if doc.remove_object(obj_id):
            deleted_count += 1

    doc.save(output_path)
    click.echo(f"Deleted {deleted_count} object(s)")

    if output:
        click.echo(f"Saved to: {output}")


@main.command(name="delete-component")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--from",
    "-f",
    "target_path",
    type=str,
    required=True,
    help="Target GameObject path (e.g., 'Canvas/Panel/Button')",
)
@click.option(
    "--type",
    "component_type",
    type=click.Choice(ALL_COMPONENT_TYPES),
    default=None,
    help="Component type to delete (built-in or package component)",
)
@click.option(
    "--script",
    "script_ref",
    type=str,
    default=None,
    help="Script name to delete (e.g., 'PlayerController')",
)
@click.option(
    "--force",
    is_flag=True,
    help="Delete without confirmation",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
def delete_component(
    file: Path,
    target_path: str,
    component_type: str | None,
    script_ref: str | None,
    force: bool,
    output: Path | None,
) -> None:
    """Delete a component from a Unity YAML file.

    Removes the component from the specified GameObject.
    Requires either --type for built-in/package components or --script for custom MonoBehaviour.

    Examples:

        # Delete a built-in component
        unityflow delete-component Scene.unity --from "Player" --type SpriteRenderer

        # Delete a package component
        unityflow delete-component Scene.unity --from "Canvas/Panel/Button" --type Image

        # When multiple GameObjects have the same path, use index
        unityflow delete-component Scene.unity --from "Canvas/Panel/Button[1]" --type Image

        # Delete a custom MonoBehaviour by script name
        unityflow delete-component Scene.unity --from "Player" --script PlayerController

        # Delete without confirmation
        unityflow delete-component Scene.unity --from "Player" --type SpriteRenderer --force
    """
    from unityflow.parser import UnityYAMLDocument

    if not component_type and not script_ref:
        click.echo("Error: Specify --type or --script", err=True)
        sys.exit(1)

    if component_type and script_ref:
        click.echo("Error: Cannot use both --type and --script", err=True)
        sys.exit(1)

    # Resolve script reference to GUID if specified
    script_guid = None
    if script_ref:
        script_guid, error = _resolve_script_to_guid(script_ref, file)
        if error:
            click.echo(f"Error: {error}", err=True)
            sys.exit(1)

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Resolve target GameObject by path
    target_id, error = _resolve_gameobject_by_path(doc, target_path)
    if error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    target_go = doc.get_by_file_id(target_id)
    if target_go is None or target_go.class_id != 1:
        click.echo(f"Error: Failed to resolve GameObject at '{target_path}'", err=True)
        sys.exit(1)

    # Find the component to delete
    go_content = target_go.get_content()
    if not go_content or "m_Component" not in go_content:
        click.echo(f"Error: GameObject has no components", err=True)
        sys.exit(1)

    component_to_delete = None
    component_id = None

    # Get class ID for built-in components
    builtin_class_ids = {
        "Transform": 4,
        "RectTransform": 224,
        "SpriteRenderer": 212,
        "Camera": 20,
        "Light": 108,
        "AudioSource": 82,
        "BoxCollider2D": 61,
        "CircleCollider2D": 58,
        "Rigidbody2D": 50,
    }

    for comp_entry in go_content["m_Component"]:
        comp_ref = comp_entry.get("component", {})
        comp_file_id = comp_ref.get("fileID", 0)
        if not comp_file_id:
            continue

        comp_obj = doc.get_by_file_id(comp_file_id)
        if comp_obj is None:
            continue

        if script_guid:
            # Looking for MonoBehaviour with specific script GUID
            if comp_obj.class_id == 114:  # MonoBehaviour
                comp_content = comp_obj.get_content()
                if comp_content:
                    script_ref_data = comp_content.get("m_Script", {})
                    if script_ref_data.get("guid") == script_guid:
                        component_to_delete = comp_obj
                        component_id = comp_file_id
                        break
        elif component_type in PACKAGE_COMPONENT_GUIDS:
            # Looking for package component (MonoBehaviour with known GUID)
            if comp_obj.class_id == 114:  # MonoBehaviour
                comp_content = comp_obj.get_content()
                if comp_content:
                    script_ref_data = comp_content.get("m_Script", {})
                    if script_ref_data.get("guid") == PACKAGE_COMPONENT_GUIDS[component_type]:
                        component_to_delete = comp_obj
                        component_id = comp_file_id
                        break
        else:
            # Looking for built-in component by class ID
            expected_class_id = builtin_class_ids.get(component_type)
            if expected_class_id and comp_obj.class_id == expected_class_id:
                component_to_delete = comp_obj
                component_id = comp_file_id
                break

    if component_to_delete is None:
        if script_ref:
            click.echo(f"Error: MonoBehaviour '{script_ref}' not found on '{target_path}'", err=True)
        else:
            click.echo(f"Error: Component '{component_type}' not found on '{target_path}'", err=True)
        sys.exit(1)

    # Prevent deleting Transform/RectTransform
    if component_to_delete.class_id in (4, 224):
        click.echo(f"Error: Cannot delete Transform or RectTransform", err=True)
        sys.exit(1)

    if not force:
        display_name = script_ref if script_ref else component_type
        click.echo(f"Will delete {display_name} from '{target_path}'")
        if not click.confirm("Continue?"):
            click.echo("Aborted")
            return

    # Update GameObject's component list
    go_content["m_Component"] = [
        c for c in go_content["m_Component"]
        if c.get("component", {}).get("fileID") != component_id
    ]

    # Remove the component object
    doc.remove_object(component_id)
    doc.save(output_path)

    display_name = script_ref if script_ref else component_type
    click.echo(f"Deleted {display_name} from '{target_path}'")

    if output:
        click.echo(f"Saved to: {output}")


def _collect_objects_to_delete(
    doc: "UnityYAMLDocument",
    gameobject_id: int,
    cascade: bool,
) -> list[int]:
    """Collect all objects to delete for a GameObject."""
    objects_to_delete: list[int] = []
    objects_to_delete.append(gameobject_id)

    go = doc.get_by_file_id(gameobject_id)
    if not go:
        return objects_to_delete

    content = go.get_content()
    if not content:
        return objects_to_delete

    # Collect components
    components = content.get("m_Component", [])
    transform_id = None
    for comp_ref in components:
        comp_id = comp_ref.get("component", {}).get("fileID", 0)
        if comp_id != 0:
            objects_to_delete.append(comp_id)
            # Check if this is a Transform
            comp = doc.get_by_file_id(comp_id)
            if comp and comp.class_id in (4, 224):
                transform_id = comp_id

    # If cascade, collect children recursively
    if cascade and transform_id:
        transform = doc.get_by_file_id(transform_id)
        if transform:
            transform_content = transform.get_content()
            if transform_content and "m_Children" in transform_content:
                for child_ref in transform_content["m_Children"]:
                    child_transform_id = child_ref.get("fileID", 0)
                    if child_transform_id != 0:
                        child_transform = doc.get_by_file_id(child_transform_id)
                        if child_transform:
                            child_content = child_transform.get_content()
                            if child_content and "m_GameObject" in child_content:
                                child_go_id = child_content["m_GameObject"].get("fileID", 0)
                                if child_go_id != 0:
                                    # Recursively collect
                                    child_objects = _collect_objects_to_delete(doc, child_go_id, cascade)
                                    objects_to_delete.extend(child_objects)

    return objects_to_delete


@main.command(name="clone-object")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--id",
    "-i",
    "source_path",
    type=str,
    required=True,
    help="GameObject path to clone (e.g., 'Canvas/Panel/Button')",
)
@click.option(
    "--name",
    "-n",
    "new_name",
    type=str,
    default=None,
    help="Name for the cloned GameObject (default: original name + ' (Clone)')",
)
@click.option(
    "--parent",
    "-p",
    "parent_path",
    type=str,
    default=None,
    help="Parent GameObject path for the clone (default: same as source)",
)
@click.option(
    "--position",
    type=str,
    default=None,
    help="Position offset as 'x,y,z' (default: same as source)",
)
@click.option(
    "--deep",
    is_flag=True,
    help="Clone children as well (deep clone)",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
def clone_object(
    file: Path,
    source_path: str,
    new_name: str | None,
    parent_path: str | None,
    position: str | None,
    deep: bool,
    output: Path | None,
) -> None:
    """Clone a GameObject within a Unity YAML file.

    Duplicates a GameObject and all its components with new fileIDs.

    Examples:

        # Simple clone (shallow)
        unityflow clone-object Scene.unity --id "Player"

        # Clone with new name
        unityflow clone-object Scene.unity --id "Player" --name "Player2"

        # Clone to different parent
        unityflow clone-object Scene.unity --id "Enemy" --parent "Enemies"

        # Clone with position offset
        unityflow clone-object Scene.unity --id "Player" --position "5,0,0"

        # Deep clone (include children)
        unityflow clone-object Scene.unity --id "Canvas/Panel" --deep

        # When multiple GameObjects have the same path, use index
        unityflow clone-object Scene.unity --id "Canvas/Panel/Button[1]"
    """
    from unityflow.parser import UnityYAMLDocument, UnityYAMLObject
    import copy

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Resolve source GameObject by path
    source_id, error = _resolve_gameobject_by_path(doc, source_path)
    if error:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    source_go = doc.get_by_file_id(source_id)
    if source_go is None or source_go.class_id != 1:
        click.echo(f"Error: Failed to resolve GameObject at '{source_path}'", err=True)
        sys.exit(1)

    # Resolve parent if specified
    parent_id = None
    if parent_path:
        parent_go_id, error = _resolve_gameobject_by_path(doc, parent_path)
        if error:
            click.echo(f"Error: {error}", err=True)
            sys.exit(1)
        # Find the Transform component of the parent GameObject
        parent_go = doc.get_by_file_id(parent_go_id)
        if parent_go:
            parent_content = parent_go.get_content()
            if parent_content and "m_Component" in parent_content:
                for comp_ref in parent_content["m_Component"]:
                    comp_id = comp_ref.get("component", {}).get("fileID", 0)
                    comp = doc.get_by_file_id(comp_id)
                    if comp and comp.class_id in (4, 224):  # Transform or RectTransform
                        parent_id = comp_id
                        break

    # Parse position offset
    pos_offset = None
    if position:
        try:
            x, y, z = map(float, position.split(","))
            pos_offset = {"x": x, "y": y, "z": z}
        except ValueError:
            click.echo(f"Error: Invalid position format: {position}", err=True)
            click.echo("Expected format: x,y,z (e.g., '5,0,0')", err=True)
            sys.exit(1)

    # Collect objects to clone
    if deep:
        objects_to_clone = _collect_objects_for_clone(doc, source_id)
    else:
        objects_to_clone = _collect_shallow_clone(doc, source_id)

    # Create ID mapping
    id_map: dict[int, int] = {}
    for old_id in objects_to_clone:
        id_map[old_id] = doc.generate_unique_file_id()

    # Clone objects
    cloned_objects: list[UnityYAMLObject] = []
    for old_id in objects_to_clone:
        old_obj = doc.get_by_file_id(old_id)
        if old_obj is None:
            continue

        new_id = id_map[old_id]
        new_data = _remap_file_ids(copy.deepcopy(old_obj.data), id_map)

        # Apply modifications for the main GameObject
        if old_id == source_id and new_name:
            root_key = old_obj.root_key
            if root_key and root_key in new_data:
                new_data[root_key]["m_Name"] = new_name
        elif old_id == source_id and new_name is None:
            # Default: add " (Clone)" suffix
            root_key = old_obj.root_key
            if root_key and root_key in new_data:
                original_name = new_data[root_key].get("m_Name", "Object")
                new_data[root_key]["m_Name"] = f"{original_name} (Clone)"

        cloned_obj = UnityYAMLObject(
            class_id=old_obj.class_id,
            file_id=new_id,
            data=new_data,
            stripped=old_obj.stripped,
        )
        cloned_objects.append(cloned_obj)

    # Apply position offset and parent change to the main Transform
    source_content = source_go.get_content()
    if source_content and "m_Component" in source_content:
        for comp_ref in source_content["m_Component"]:
            comp_id = comp_ref.get("component", {}).get("fileID", 0)
            comp = doc.get_by_file_id(comp_id)
            if comp and comp.class_id in (4, 224):  # Transform or RectTransform
                new_transform_id = id_map.get(comp_id)
                if new_transform_id:
                    for cloned_obj in cloned_objects:
                        if cloned_obj.file_id == new_transform_id:
                            content = cloned_obj.get_content()
                            if content:
                                # Apply parent change
                                if parent_id is not None:
                                    content["m_Father"] = {"fileID": parent_id}

                                # Apply position offset
                                if pos_offset and "m_LocalPosition" in content:
                                    current_pos = content["m_LocalPosition"]
                                    content["m_LocalPosition"] = {
                                        "x": current_pos.get("x", 0) + pos_offset["x"],
                                        "y": current_pos.get("y", 0) + pos_offset["y"],
                                        "z": current_pos.get("z", 0) + pos_offset["z"],
                                    }
                break

    # Add cloned objects to document
    for cloned_obj in cloned_objects:
        doc.add_object(cloned_obj)

    # Update parent's children list
    main_transform_id = None
    for comp_ref in source_content.get("m_Component", []):
        comp_id = comp_ref.get("component", {}).get("fileID", 0)
        comp = doc.get_by_file_id(comp_id)
        if comp and comp.class_id in (4, 224):
            main_transform_id = id_map.get(comp_id)
            break

    if main_transform_id:
        # Find the parent transform
        effective_parent_id = parent_id
        if effective_parent_id is None:
            # Use same parent as source
            for comp_ref in source_content.get("m_Component", []):
                comp_id = comp_ref.get("component", {}).get("fileID", 0)
                comp = doc.get_by_file_id(comp_id)
                if comp and comp.class_id in (4, 224):
                    comp_content = comp.get_content()
                    if comp_content:
                        effective_parent_id = comp_content.get("m_Father", {}).get("fileID", 0)
                    break

        if effective_parent_id and effective_parent_id != 0:
            parent_transform = doc.get_by_file_id(effective_parent_id)
            if parent_transform:
                parent_content = parent_transform.get_content()
                if parent_content and "m_Children" in parent_content:
                    parent_content["m_Children"].append({"fileID": main_transform_id})

    doc.save(output_path)

    click.echo(f"Cloned GameObject")
    click.echo(f"  Source: {source_path}")
    click.echo(f"  Total objects cloned: {len(cloned_objects)}")

    if output:
        click.echo(f"Saved to: {output}")


def _collect_shallow_clone(doc: "UnityYAMLDocument", gameobject_id: int) -> list[int]:
    """Collect objects for a shallow clone (GO + components only)."""
    objects: list[int] = [gameobject_id]

    go = doc.get_by_file_id(gameobject_id)
    if go:
        content = go.get_content()
        if content and "m_Component" in content:
            for comp_ref in content["m_Component"]:
                comp_id = comp_ref.get("component", {}).get("fileID", 0)
                if comp_id != 0:
                    objects.append(comp_id)

    return objects


def _collect_objects_for_clone(doc: "UnityYAMLDocument", gameobject_id: int) -> list[int]:
    """Collect all objects for a deep clone (GO + components + children)."""
    objects: list[int] = []
    objects.append(gameobject_id)

    go = doc.get_by_file_id(gameobject_id)
    if not go:
        return objects

    content = go.get_content()
    if not content:
        return objects

    # Collect components
    transform_id = None
    for comp_ref in content.get("m_Component", []):
        comp_id = comp_ref.get("component", {}).get("fileID", 0)
        if comp_id != 0:
            objects.append(comp_id)
            comp = doc.get_by_file_id(comp_id)
            if comp and comp.class_id in (4, 224):
                transform_id = comp_id

    # Recursively collect children
    if transform_id:
        transform = doc.get_by_file_id(transform_id)
        if transform:
            transform_content = transform.get_content()
            if transform_content and "m_Children" in transform_content:
                for child_ref in transform_content["m_Children"]:
                    child_transform_id = child_ref.get("fileID", 0)
                    if child_transform_id != 0:
                        child_transform = doc.get_by_file_id(child_transform_id)
                        if child_transform:
                            child_content = child_transform.get_content()
                            if child_content and "m_GameObject" in child_content:
                                child_go_id = child_content["m_GameObject"].get("fileID", 0)
                                if child_go_id != 0:
                                    child_objects = _collect_objects_for_clone(doc, child_go_id)
                                    objects.extend(child_objects)

    return objects


def _remap_file_ids(data: Any, id_map: dict[int, int]) -> Any:
    """Recursively remap fileIDs in a data structure."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == "fileID" and isinstance(value, int) and value in id_map:
                result[key] = id_map[value]
            else:
                result[key] = _remap_file_ids(value, id_map)
        return result
    elif isinstance(data, list):
        return [_remap_file_ids(item, id_map) for item in data]
    else:
        return data


@main.command(name="generate-meta")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-r", "--recursive",
    is_flag=True,
    help="Process directories recursively",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite existing .meta files",
)
@click.option(
    "--guid",
    type=str,
    default=None,
    help="Use specific GUID (32 hex chars) instead of random",
)
@click.option(
    "--seed",
    type=str,
    default=None,
    help="Use seed for deterministic GUID generation (e.g., file path)",
)
@click.option(
    "--type",
    "asset_type",
    type=click.Choice([
        "auto", "folder", "script", "texture", "audio", "video",
        "model", "shader", "material", "prefab", "scene", "text", "default"
    ]),
    default="auto",
    help="Force asset type (default: auto-detect)",
)
@click.option(
    "--sprite",
    is_flag=True,
    help="Generate texture meta as sprite (sets sprite mode)",
)
@click.option(
    "--ppu",
    "pixels_per_unit",
    type=int,
    default=100,
    help="Sprite pixels per unit (default: 100)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be created without writing files",
)
def generate_meta(
    paths: tuple[Path, ...],
    recursive: bool,
    overwrite: bool,
    guid: str | None,
    seed: str | None,
    asset_type: str,
    sprite: bool,
    pixels_per_unit: int,
    dry_run: bool,
) -> None:
    """Generate .meta files for Unity assets.

    Creates .meta files with appropriate importer settings based on file type.
    Supports various asset types: scripts, textures, audio, models, shaders, etc.

    Examples:

        # Generate meta for a single file
        unityflow generate-meta Assets/Scripts/Player.cs

        # Generate meta for multiple files
        unityflow generate-meta Assets/Textures/*.png

        # Generate meta for a folder recursively
        unityflow generate-meta Assets/NewFolder -r

        # Generate sprite meta with custom PPU
        unityflow generate-meta icon.png --sprite --ppu 32

        # Generate with deterministic GUID (reproducible builds)
        unityflow generate-meta Assets/Data/config.json --seed "config.json"

        # Dry run to preview
        unityflow generate-meta Assets/ -r --dry-run
    """
    from unityflow.meta_generator import (
        AssetType,
        MetaFileOptions,
        generate_meta_file,
        generate_meta_files_recursive,
        detect_asset_type,
        generate_meta_content,
    )

    if not paths:
        click.echo("Error: No paths provided", err=True)
        sys.exit(1)

    # Validate GUID if provided
    if guid:
        if len(guid) != 32 or not all(c in "0123456789abcdef" for c in guid.lower()):
            click.echo("Error: GUID must be 32 hexadecimal characters", err=True)
            sys.exit(1)
        guid = guid.lower()

    # Map string type to AssetType enum
    type_map = {
        "auto": None,
        "folder": AssetType.FOLDER,
        "script": AssetType.SCRIPT,
        "texture": AssetType.TEXTURE,
        "audio": AssetType.AUDIO,
        "video": AssetType.VIDEO,
        "model": AssetType.MODEL,
        "shader": AssetType.SHADER,
        "material": AssetType.MATERIAL,
        "prefab": AssetType.PREFAB,
        "scene": AssetType.SCENE,
        "text": AssetType.TEXT,
        "default": AssetType.DEFAULT,
    }
    forced_type = type_map.get(asset_type)

    # Build options
    options = MetaFileOptions(
        guid=guid,
        guid_seed=seed,
        texture_type="Sprite" if sprite else "Default",
        sprite_mode=1 if sprite else 0,
        sprite_pixels_per_unit=pixels_per_unit,
    )

    total_created = 0
    total_skipped = 0
    total_failed = 0

    for path in paths:
        # Resolve to absolute path for consistent handling
        abs_path = path.resolve()

        if recursive and abs_path.is_dir():
            if dry_run:
                click.echo(f"Would process directory: {path}")
                # Count files that would be processed
                for item in abs_path.rglob("*"):
                    if item.suffix == ".meta":
                        continue
                    if any(part.startswith(".") for part in item.parts):
                        continue
                    meta_path = Path(str(item) + ".meta")
                    if meta_path.exists() and not overwrite:
                        click.echo(f"  [skip] {item.relative_to(abs_path)} (meta exists)")
                        total_skipped += 1
                    else:
                        detected = detect_asset_type(item)
                        click.echo(f"  [create] {item.relative_to(abs_path)} ({detected.value})")
                        total_created += 1
            else:
                results = generate_meta_files_recursive(
                    abs_path,
                    overwrite=overwrite,
                    skip_existing=not overwrite,
                    options=options,
                )
                for item_path, success, message in results:
                    if success:
                        try:
                            rel_path = item_path.relative_to(abs_path)
                            display_path = str(rel_path) if str(rel_path) != "." else abs_path.name
                        except ValueError:
                            display_path = item_path.name
                        click.echo(f"Created: {display_path}.meta")
                        total_created += 1
                    else:
                        if "already exists" in message:
                            total_skipped += 1
                        else:
                            click.echo(f"Failed: {item_path}: {message}", err=True)
                            total_failed += 1
        else:
            # Single file or non-recursive directory
            meta_path = Path(str(path) + ".meta")

            if meta_path.exists() and not overwrite:
                click.echo(f"Skipped: {path} (meta already exists)")
                total_skipped += 1
                continue

            if dry_run:
                detected = forced_type or detect_asset_type(path)
                content = generate_meta_content(path, detected, options)
                click.echo(f"Would create: {meta_path}")
                click.echo(f"  Type: {detected.value}")
                # Extract GUID from content for display
                for line in content.split("\n"):
                    if line.startswith("guid:"):
                        click.echo(f"  GUID: {line.split(':')[1].strip()}")
                        break
                total_created += 1
            else:
                try:
                    generate_meta_file(path, forced_type, options, overwrite=overwrite)
                    click.echo(f"Created: {meta_path}")
                    total_created += 1
                except FileExistsError:
                    click.echo(f"Skipped: {path} (meta already exists)")
                    total_skipped += 1
                except Exception as e:
                    click.echo(f"Failed: {path}: {e}", err=True)
                    total_failed += 1

    # Summary
    click.echo("")
    if dry_run:
        click.echo("Dry run summary:")
    else:
        click.echo("Summary:")
    click.echo(f"  Created: {total_created}")
    if total_skipped > 0:
        click.echo(f"  Skipped: {total_skipped}")
    if total_failed > 0:
        click.echo(f"  Failed: {total_failed}")

    if total_failed > 0:
        sys.exit(1)


@main.command(name="modify-meta")
@click.argument("meta_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--sprite-mode",
    type=click.Choice(["none", "single", "multiple"]),
    default=None,
    help="Set sprite mode (texture only)",
)
@click.option(
    "--ppu",
    "pixels_per_unit",
    type=int,
    default=None,
    help="Set sprite pixels per unit (texture only)",
)
@click.option(
    "--filter",
    "filter_mode",
    type=click.Choice(["point", "bilinear", "trilinear"]),
    default=None,
    help="Set filter mode (texture only)",
)
@click.option(
    "--max-size",
    type=click.Choice(["32", "64", "128", "256", "512", "1024", "2048", "4096", "8192", "16384"]),
    default=None,
    help="Set max texture size (texture only)",
)
@click.option(
    "--execution-order",
    type=int,
    default=None,
    help="Set script execution order (script only)",
)
@click.option(
    "--bundle-name",
    type=str,
    default=None,
    help="Set asset bundle name",
)
@click.option(
    "--bundle-variant",
    type=str,
    default=None,
    help="Set asset bundle variant",
)
@click.option(
    "--info",
    "show_info",
    is_flag=True,
    help="Show current meta file information",
)
def modify_meta(
    meta_path: Path,
    sprite_mode: str | None,
    pixels_per_unit: int | None,
    filter_mode: str | None,
    max_size: str | None,
    execution_order: int | None,
    bundle_name: str | None,
    bundle_variant: str | None,
    show_info: bool,
) -> None:
    """Modify settings in an existing .meta file.

    Note: GUID cannot be modified to prevent breaking asset references.

    Examples:

        # Show current meta file info
        unityflow modify-meta icon.png.meta --info

        # Change texture to sprite mode
        unityflow modify-meta icon.png.meta --sprite-mode single

        # Set sprite with custom PPU and filter
        unityflow modify-meta icon.png.meta --sprite-mode single --ppu 32 --filter point

        # Set max texture size
        unityflow modify-meta icon.png.meta --max-size 512

        # Set script execution order
        unityflow modify-meta Player.cs.meta --execution-order -100

        # Set asset bundle
        unityflow modify-meta Player.prefab.meta --bundle-name "characters" --bundle-variant "hd"
    """
    from unityflow.meta_generator import (
        get_meta_info,
        set_texture_sprite_mode,
        set_texture_max_size,
        set_script_execution_order,
        set_asset_bundle,
    )

    # Handle path - support both asset path and meta path
    if not str(meta_path).endswith(".meta"):
        meta_path = Path(str(meta_path) + ".meta")

    if not meta_path.exists():
        click.echo(f"Error: Meta file not found: {meta_path}", err=True)
        sys.exit(1)

    # Show info mode
    if show_info:
        try:
            info = get_meta_info(meta_path)
            click.echo(f"Meta file: {meta_path}")
            click.echo(f"  GUID: {info['guid']}")
            click.echo(f"  Importer: {info['importer_type']}")

            if info.get("sprite_mode") is not None:
                sprite_modes = {0: "None", 1: "Single", 2: "Multiple"}
                click.echo(f"  Sprite Mode: {sprite_modes.get(info['sprite_mode'], info['sprite_mode'])}")

            if info.get("pixels_per_unit") is not None:
                click.echo(f"  Pixels Per Unit: {info['pixels_per_unit']}")

            if info.get("max_texture_size") is not None:
                click.echo(f"  Max Texture Size: {info['max_texture_size']}")

            if info.get("filter_mode") is not None:
                filter_modes = {0: "Point", 1: "Bilinear", 2: "Trilinear"}
                click.echo(f"  Filter Mode: {filter_modes.get(info['filter_mode'], info['filter_mode'])}")

            if info.get("texture_type") is not None:
                texture_types = {0: "Default", 1: "NormalMap", 8: "Sprite"}
                click.echo(f"  Texture Type: {texture_types.get(info['texture_type'], info['texture_type'])}")

            if info.get("execution_order") is not None:
                click.echo(f"  Execution Order: {info['execution_order']}")

            if info.get("asset_bundle_name"):
                click.echo(f"  Asset Bundle: {info['asset_bundle_name']}")
                if info.get("asset_bundle_variant"):
                    click.echo(f"  Bundle Variant: {info['asset_bundle_variant']}")

        except Exception as e:
            click.echo(f"Error reading meta file: {e}", err=True)
            sys.exit(1)
        return

    # Check if any modification was requested
    has_modifications = any([
        sprite_mode is not None,
        pixels_per_unit is not None,
        filter_mode is not None,
        max_size is not None,
        execution_order is not None,
        bundle_name is not None,
        bundle_variant is not None,
    ])

    if not has_modifications:
        click.echo("Error: No modifications specified. Use --info to view current settings.", err=True)
        click.echo("Available options: --sprite-mode, --ppu, --filter, --max-size, --execution-order, --bundle-name, --bundle-variant")
        sys.exit(1)

    modified = False

    try:
        # Apply texture modifications
        if sprite_mode is not None or pixels_per_unit is not None or filter_mode is not None:
            sprite_mode_map = {"none": 0, "single": 1, "multiple": 2}
            filter_mode_map = {"point": 0, "bilinear": 1, "trilinear": 2}

            sm = sprite_mode_map.get(sprite_mode) if sprite_mode else None
            fm = filter_mode_map.get(filter_mode) if filter_mode else None

            if sm is not None:
                set_texture_sprite_mode(meta_path, sprite_mode=sm, pixels_per_unit=pixels_per_unit, filter_mode=fm)
                click.echo(f"Set sprite mode: {sprite_mode}")
                if pixels_per_unit is not None:
                    click.echo(f"Set pixels per unit: {pixels_per_unit}")
                if filter_mode is not None:
                    click.echo(f"Set filter mode: {filter_mode}")
            elif pixels_per_unit is not None or fm is not None:
                # Need to get current sprite mode
                info = get_meta_info(meta_path)
                current_sm = info.get("sprite_mode", 1)
                set_texture_sprite_mode(meta_path, sprite_mode=current_sm, pixels_per_unit=pixels_per_unit, filter_mode=fm)
                if pixels_per_unit is not None:
                    click.echo(f"Set pixels per unit: {pixels_per_unit}")
                if filter_mode is not None:
                    click.echo(f"Set filter mode: {filter_mode}")
            modified = True

        if max_size is not None:
            set_texture_max_size(meta_path, int(max_size))
            click.echo(f"Set max texture size: {max_size}")
            modified = True

        if execution_order is not None:
            set_script_execution_order(meta_path, execution_order)
            click.echo(f"Set execution order: {execution_order}")
            modified = True

        if bundle_name is not None or bundle_variant is not None:
            # Get current values if only one is being set
            info = get_meta_info(meta_path)
            bn = bundle_name if bundle_name is not None else (info.get("asset_bundle_name") or "")
            bv = bundle_variant if bundle_variant is not None else (info.get("asset_bundle_variant") or "")
            set_asset_bundle(meta_path, bn, bv)
            if bundle_name is not None:
                click.echo(f"Set asset bundle name: {bundle_name or '(cleared)'}")
            if bundle_variant is not None:
                click.echo(f"Set asset bundle variant: {bundle_variant or '(cleared)'}")
            modified = True

        if modified:
            click.echo(f"\nModified: {meta_path}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


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
                    result["children"] = [
                        node_to_dict(child, current_depth + 1)
                        for child in node.children
                    ]
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
                    result["transform"]["anchoredPosition"] = transform_content.get("m_AnchoredPosition")
                    result["transform"]["sizeDelta"] = transform_content.get("m_SizeDelta")
                    result["transform"]["anchorMin"] = transform_content.get("m_AnchorMin")
                    result["transform"]["anchorMax"] = transform_content.get("m_AnchorMax")
                    result["transform"]["pivot"] = transform_content.get("m_Pivot")

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
            click.echo(f"Is Prefab Instance: Yes")
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

                pos = transform_content.get("m_LocalPosition", {})
                if isinstance(pos, dict):
                    click.echo(f"  localPosition: ({pos.get('x', 0)}, {pos.get('y', 0)}, {pos.get('z', 0)})")

                rot = transform_content.get("m_LocalRotation", {})
                if isinstance(rot, dict):
                    click.echo(f"  localRotation: ({rot.get('x', 0)}, {rot.get('y', 0)}, {rot.get('z', 0)}, {rot.get('w', 1)})")

                scale = transform_content.get("m_LocalScale", {})
                if isinstance(scale, dict):
                    click.echo(f"  localScale: ({scale.get('x', 1)}, {scale.get('y', 1)}, {scale.get('z', 1)})")

                # RectTransform specific
                if transform_obj.class_id == 224:
                    anchor_pos = transform_content.get("m_AnchoredPosition", {})
                    if isinstance(anchor_pos, dict):
                        click.echo(f"  anchoredPosition: ({anchor_pos.get('x', 0)}, {anchor_pos.get('y', 0)})")

                    size = transform_content.get("m_SizeDelta", {})
                    if isinstance(size, dict):
                        click.echo(f"  sizeDelta: ({size.get('x', 0)}, {size.get('y', 0)})")

                    anchor_min = transform_content.get("m_AnchorMin", {})
                    if isinstance(anchor_min, dict):
                        click.echo(f"  anchorMin: ({anchor_min.get('x', 0)}, {anchor_min.get('y', 0)})")

                    anchor_max = transform_content.get("m_AnchorMax", {})
                    if isinstance(anchor_max, dict):
                        click.echo(f"  anchorMax: ({anchor_max.get('x', 0)}, {anchor_max.get('y', 0)})")

                    pivot = transform_content.get("m_Pivot", {})
                    if isinstance(pivot, dict):
                        click.echo(f"  pivot: ({pivot.get('x', 0.5)}, {pivot.get('y', 0.5)})")

                click.echo()

        # Other components
        for comp in node.components:
            comp_type = comp.script_name or comp.class_name
            click.echo(f"[{comp_type}]")

            if comp.script_guid:
                click.echo(f"  script_guid: {comp.script_guid}")

            # Show key properties (excluding internal Unity fields)
            skip_keys = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
                         "m_PrefabAsset", "m_GameObject", "m_Enabled", "m_Script"}
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
