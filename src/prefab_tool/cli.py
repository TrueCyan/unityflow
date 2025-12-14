"""Command-line interface for prefab-tool.

Provides commands for normalizing, diffing, and validating Unity YAML files.
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import click

from prefab_tool import __version__
from prefab_tool.diff import DiffFormat, PrefabDiff
from prefab_tool.git_utils import (
    UNITY_EXTENSIONS,
    get_changed_files,
    get_files_changed_since,
    get_repo_root,
    is_git_repository,
)
from prefab_tool.normalizer import UnityPrefabNormalizer
from prefab_tool.validator import PrefabValidator
from prefab_tool.asset_tracker import (
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
@click.version_option(version=__version__, prog_name="prefab-tool")
def main() -> None:
    """Unity Prefab Deterministic Serializer.

    A tool for canonical serialization of Unity YAML files to eliminate
    non-deterministic changes and reduce VCS noise.
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
    "--no-sort-documents",
    is_flag=True,
    help="Don't sort documents by fileID",
)
@click.option(
    "--no-sort-modifications",
    is_flag=True,
    help="Don't sort m_Modifications arrays",
)
@click.option(
    "--no-normalize-floats",
    is_flag=True,
    help="Don't normalize floating-point values",
)
@click.option(
    "--hex-floats",
    is_flag=True,
    help="Use IEEE 754 hex format for floats (lossless)",
)
@click.option(
    "--no-normalize-quaternions",
    is_flag=True,
    help="Don't normalize quaternions",
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
    "--no-reorder-fields",
    is_flag=True,
    help="Disable reordering MonoBehaviour fields according to C# script declaration order",
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
    no_sort_documents: bool,
    no_sort_modifications: bool,
    no_normalize_floats: bool,
    hex_floats: bool,
    no_normalize_quaternions: bool,
    precision: int,
    output_format: str,
    progress: bool,
    parallel_jobs: int,
    in_place: bool,
    no_reorder_fields: bool,
    project_root: Path | None,
) -> None:
    """Normalize Unity YAML files for deterministic serialization.

    INPUT_FILES are paths to prefab, scene, or asset files.

    Examples:

        # Normalize in place
        prefab-tool normalize Player.prefab

        # Normalize multiple files
        prefab-tool normalize *.prefab

        # Normalize to a new file
        prefab-tool normalize Player.prefab -o Player.normalized.prefab

        # Output to stdout
        prefab-tool normalize Player.prefab --stdout

    Incremental normalization (requires git):

        # Normalize changed files only
        prefab-tool normalize --changed-only

        # Normalize staged files only
        prefab-tool normalize --changed-only --staged-only

        # Normalize files changed since a commit
        prefab-tool normalize --since HEAD~5

        # Normalize files changed since a branch
        prefab-tool normalize --since main

        # Filter by pattern
        prefab-tool normalize --changed-only --pattern "Assets/Prefabs/**/*.prefab"

        # Dry run to see what would be normalized
        prefab-tool normalize --changed-only --dry-run

    Script-based field ordering (enabled by default):

        # Disable field reordering
        prefab-tool normalize Player.prefab --no-reorder-fields

        # With explicit project root for script resolution
        prefab-tool normalize Player.prefab --project-root /path/to/unity/project
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
        "sort_documents": not no_sort_documents,
        "sort_modifications": not no_sort_modifications,
        "normalize_floats": not no_normalize_floats,
        "use_hex_floats": hex_floats,
        "normalize_quaternions": not no_normalize_quaternions,
        "float_precision": precision,
        "reorder_script_fields": not no_reorder_fields,
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
        prefab-tool diff old.prefab new.prefab

        # Show raw diff without normalization
        prefab-tool diff old.prefab new.prefab --no-normalize

        # Exit with status code (for scripts)
        prefab-tool diff old.prefab new.prefab --exit-code
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
        prefab-tool validate Player.prefab

        # Validate multiple files
        prefab-tool validate *.prefab

        # Strict validation (warnings are errors)
        prefab-tool validate Player.prefab --strict
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
    help="Find GameObjects with MonoBehaviour by script GUID",
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
        prefab-tool query Player.prefab --path "gameObjects/*/name"

        # Get all component types as JSON
        prefab-tool query Player.prefab --path "components/*/type" --format json

        # Show summary (no path)
        prefab-tool query Player.prefab

        # Find GameObjects by name (supports wildcards)
        prefab-tool query Scene.unity --find-name "Player*"
        prefab-tool query Scene.unity --find-name "*Enemy*"

        # Find GameObjects with specific component
        prefab-tool query Scene.unity --find-component "Light2D"
        prefab-tool query Scene.unity --find-component "SpriteRenderer"

        # Find GameObjects with MonoBehaviour by script GUID
        prefab-tool query Scene.unity --find-script "abc123def456..."
    """
    from prefab_tool.parser import UnityYAMLDocument, CLASS_IDS
    from prefab_tool.query import query_path as do_query
    from prefab_tool.formats import get_summary
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
                click.echo(f"  {r['name']} (fileID: {r['fileID']})")
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
                click.echo(f"  {r['name']} (fileID: {r['fileID']})")
                click.echo(f"    Component fileID: {r['componentFileID']}")
        return

    # Handle find-script query
    if find_script is not None:
        results = _find_by_script(doc, find_script)
        if not results:
            click.echo(f"No GameObjects found with script GUID: {find_script}")
            return

        if output_format == "json":
            click.echo(json.dumps(results, indent=2))
        else:
            click.echo(f"Found {len(results)} GameObject(s) with script '{find_script[:16]}...':")
            for r in results:
                click.echo(f"  {r['name']} (fileID: {r['fileID']})")
                click.echo(f"    MonoBehaviour fileID: {r['componentFileID']}")
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
    from prefab_tool.parser import CLASS_IDS

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

        # Export to JSON
        prefab-tool export Player.prefab -o player.json

        # Export to stdout
        prefab-tool export Player.prefab

        # Compact output without raw fields
        prefab-tool export Player.prefab --no-raw --indent 0
    """
    from prefab_tool.formats import export_file_to_json

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
        prefab-tool import player.json -o Player.prefab

        # Round-trip workflow
        prefab-tool export Player.prefab -o player.json
        # ... edit player.json ...
        prefab-tool import player.json -o Player.prefab
    """
    from prefab_tool.formats import import_file_from_json

    try:
        doc = import_file_from_json(file, output_path=output)
        click.echo(f"Imported: {file} -> {output}")
        click.echo(f"  Objects: {len(doc.objects)}")
    except Exception as e:
        click.echo(f"Error: Failed to import {file}: {e}", err=True)
        sys.exit(1)


@main.command(name="set")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--path",
    "-p",
    "set_path",
    required=True,
    help="Path to the value to set (e.g., 'components/12345/localPosition')",
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
    "--sprite",
    "-s",
    "sprite_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Sprite path - auto-detects fileID from .meta file (e.g., 'Assets/Sprites/icon.png')",
)
@click.option(
    "--sub-sprite",
    "sub_sprite",
    default=None,
    help="For Multiple mode sprites, the specific sub-sprite name",
)
@click.option(
    "--material",
    "-m",
    "material_path",
    default=None,
    help="Material path or name to set along with sprite (e.g., 'Sprite-Lit-Default')",
)
@click.option(
    "--use-urp-default",
    "use_urp_default",
    is_flag=True,
    help="Use URP default material (Sprite-Lit-Default) along with sprite",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
@click.option(
    "--create",
    "-c",
    is_flag=True,
    help="Create the path if it doesn't exist (upsert behavior)",
)
def set_value_cmd(
    file: Path,
    set_path: str,
    value: str | None,
    batch_values_json: str | None,
    sprite_path: Path | None,
    sub_sprite: str | None,
    material_path: str | None,
    use_urp_default: bool,
    output: Path | None,
    create: bool,
) -> None:
    """Set a value at a specific path in a Unity YAML file.

    This enables surgical editing of prefab data.

    Value Modes (mutually exclusive):
        --value: Set a single value (JSON or string)
        --batch: Set multiple key-value pairs at once
        --sprite: Set a sprite reference with auto fileID detection

    Examples:

        # Set position
        prefab-tool set Player.prefab \\
            --path "components/12345/localPosition" \\
            --value '{"x": 0, "y": 5, "z": 0}'

        # Set a simple value
        prefab-tool set Player.prefab \\
            --path "gameObjects/12345/name" \\
            --value '"NewName"'

        # Save to a new file
        prefab-tool set Player.prefab \\
            --path "components/12345/localScale" \\
            --value '{"x": 2, "y": 2, "z": 2}' \\
            -o Player_modified.prefab

        # Create a new field if it doesn't exist
        prefab-tool set Scene.unity \\
            --path "components/495733805/portalAPrefab" \\
            --value '{"fileID": 123, "guid": "abc", "type": 3}' \\
            --create

        # Set multiple fields at once (batch mode)
        prefab-tool set Scene.unity \\
            --path "components/495733805" \\
            --batch '{
                "portalAPrefab": {"fileID": 123, "guid": "abc", "type": 3},
                "portalBPrefab": {"fileID": 456, "guid": "def", "type": 3}
            }' \\
            --create

        # Set sprite with auto fileID detection (Single mode)
        prefab-tool set Player.prefab \\
            --path "components/12345/m_Sprite" \\
            --sprite "Assets/Sprites/player.png"

        # Set sprite with sub-sprite (Multiple mode / atlas)
        prefab-tool set Player.prefab \\
            --path "components/12345/m_Sprite" \\
            --sprite "Assets/Sprites/atlas.png" \\
            --sub-sprite "player_idle_0"

        # Set sprite with URP material
        prefab-tool set Player.prefab \\
            --path "components/12345/m_Sprite" \\
            --sprite "Assets/Sprites/player.png" \\
            --use-urp-default

        # Set sprite with custom material
        prefab-tool set Player.prefab \\
            --path "components/12345/m_Sprite" \\
            --sprite "Assets/Sprites/player.png" \\
            --material "Assets/Materials/Custom.mat"

    Note:
        New fields are appended at the end. Unity will reorder fields
        according to the C# script declaration order when saved in editor.

        For --sprite mode, the fileID is automatically detected from the
        sprite's .meta file based on import mode (Single vs Multiple).
    """
    from prefab_tool.parser import UnityYAMLDocument
    from prefab_tool.query import set_value, merge_values
    from prefab_tool.sprite import (
        get_sprite_reference,
        get_sprite_info,
        get_material_reference,
    )
    import json

    # Count how many value modes are specified
    value_modes = sum([
        value is not None,
        batch_values_json is not None,
        sprite_path is not None,
    ])

    # Validate options
    if value_modes == 0:
        click.echo("Error: One of --value, --batch, or --sprite is required", err=True)
        sys.exit(1)
    if value_modes > 1:
        click.echo("Error: Cannot use multiple value modes (--value, --batch, --sprite)", err=True)
        sys.exit(1)

    # Validate sprite-related options
    if sub_sprite and not sprite_path:
        click.echo("Error: --sub-sprite requires --sprite", err=True)
        sys.exit(1)
    if material_path and not sprite_path:
        click.echo("Error: --material requires --sprite", err=True)
        sys.exit(1)
    if use_urp_default and not sprite_path:
        click.echo("Error: --use-urp-default requires --sprite", err=True)
        sys.exit(1)
    if material_path and use_urp_default:
        click.echo("Error: Cannot use both --material and --use-urp-default", err=True)
        sys.exit(1)

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    if sprite_path is not None:
        # Sprite mode - auto-detect fileID from meta file
        sprite_ref = get_sprite_reference(sprite_path, sub_sprite)
        if not sprite_ref:
            sprite_info = get_sprite_info(sprite_path)
            if sprite_info and sprite_info.is_multiple and sub_sprite:
                click.echo(f"Error: Sub-sprite '{sub_sprite}' not found in sprite", err=True)
                click.echo(f"Available sub-sprites: {', '.join(sprite_info.get_sprite_names())}", err=True)
            elif not Path(str(sprite_path) + ".meta").exists():
                click.echo(f"Error: Meta file not found for sprite: {sprite_path}", err=True)
            else:
                click.echo(f"Error: Could not get sprite reference for: {sprite_path}", err=True)
            sys.exit(1)

        # Set sprite reference
        if set_value(doc, set_path, sprite_ref.to_dict(), create=create):
            # Get sprite info for display
            sprite_info = get_sprite_info(sprite_path)
            mode_str = "Single" if sprite_info and sprite_info.is_single else "Multiple"

            # Handle material if specified
            material_set = False
            if use_urp_default or material_path:
                material_ref = None
                if use_urp_default:
                    material_ref = get_material_reference("Sprite-Lit-Default")
                elif material_path:
                    project_root = find_unity_project_root(file)
                    material_ref = get_material_reference(material_path, project_root)
                    if not material_ref:
                        click.echo(f"Error: Could not find material: {material_path}", err=True)
                        sys.exit(1)

                if material_ref:
                    # Derive material path from sprite path
                    # e.g., components/12345/m_Sprite -> components/12345/m_Materials/0
                    path_parts = set_path.rsplit("/", 1)
                    if len(path_parts) == 2:
                        material_set_path = f"{path_parts[0]}/m_Materials/0"
                        if set_value(doc, material_set_path, material_ref.to_dict(), create=create):
                            material_set = True

            doc.save(output_path)
            click.echo(f"Set sprite at {set_path}:")
            click.echo(f"  Sprite: {sprite_path} ({mode_str} mode)")
            click.echo(f"  fileID: {sprite_ref.file_id}")
            click.echo(f"  guid: {sprite_ref.guid}")
            if material_set:
                click.echo(f"  Material: {'Sprite-Lit-Default (URP)' if use_urp_default else material_path}")
        else:
            click.echo(f"Error: Path not found: {set_path}", err=True)
            sys.exit(1)

    elif batch_values_json is not None:
        # Batch mode
        try:
            parsed_values = json.loads(batch_values_json)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --batch: {e}", err=True)
            sys.exit(1)

        if not isinstance(parsed_values, dict):
            click.echo("Error: --batch value must be a JSON object", err=True)
            sys.exit(1)

        updated, created = merge_values(doc, set_path, parsed_values, create=create)

        if updated == 0 and created == 0:
            click.echo(f"Error: Path not found or no fields set: {set_path}", err=True)
            sys.exit(1)

        doc.save(output_path)
        click.echo(f"Set {updated + created} fields at {set_path}")
        click.echo(f"  Updated: {updated}, Created: {created}")

    else:
        # Single value mode
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value

        if set_value(doc, set_path, parsed_value, create=create):
            doc.save(output_path)
            if create:
                click.echo(f"Set (upsert) {set_path} = {value}")
            else:
                click.echo(f"Set {set_path} = {value}")
        else:
            click.echo(f"Error: Path not found: {set_path}", err=True)
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
            textconv = prefab-tool git-textconv

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
        git config difftool.prefab-unity.cmd 'prefab-tool difftool "$LOCAL" "$REMOTE"'

    Or use 'prefab-tool setup --with-difftool' for automatic configuration.

    Git Fork setup:

        1. Open Git Fork → Settings → Integration
        2. Set External Diff Tool to: Custom
        3. Path: prefab-tool
        4. Arguments: difftool "$LOCAL" "$REMOTE"

    Examples:

        # Compare with auto-detected tool
        prefab-tool difftool old.prefab new.prefab

        # Use VS Code
        prefab-tool difftool old.prefab new.prefab --tool vscode

        # Open HTML diff in browser
        prefab-tool difftool old.prefab new.prefab --tool html

        # Compare without normalization
        prefab-tool difftool old.prefab new.prefab --no-normalize
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
        prefab-tool install-hooks --pre-commit

        # Install native git hook
        prefab-tool install-hooks --git-hooks

        # Overwrite existing hooks
        prefab-tool install-hooks --git-hooks --force
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
            if "prefab-tool" in content:
                click.echo("prefab-tool hook already configured in .pre-commit-config.yaml")
                return
            click.echo("Found existing .pre-commit-config.yaml")
            click.echo("Add prefab-tool manually or use --force to overwrite")
            sys.exit(1)

        config_content = """\
# See https://pre-commit.com for more information
repos:
  # Unity Prefab Normalizer
  - repo: https://github.com/TrueCyan/prefab-tool
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
# prefab-tool pre-commit hook
# Automatically normalize Unity YAML files before commit

set -e

# Get list of staged Unity files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.(prefab|unity|asset)$' || true)

if [ -n "$STAGED_FILES" ]; then
    echo "Normalizing Unity files..."

    # Normalize each staged file
    for file in $STAGED_FILES; do
        if [ -f "$file" ]; then
            prefab-tool normalize "$file" --in-place
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
            driver = prefab-tool merge %O %A %B -o %A --path %P

    Setup in .gitattributes:

        *.prefab merge=unity
        *.unity merge=unity
        *.asset merge=unity
    """
    from prefab_tool.merge import three_way_merge

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
        prefab-tool stats Boss.unity

        # Show stats for multiple files
        prefab-tool stats *.prefab

        # Output as JSON
        prefab-tool stats Boss.unity --format json
    """
    from prefab_tool.parser import UnityYAMLDocument, CLASS_IDS
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
        prefab-tool deps Player.prefab

        # Show only binary assets (textures, meshes, audio)
        prefab-tool deps Player.prefab --binary-only

        # Show only unresolved (missing) dependencies
        prefab-tool deps Player.prefab --unresolved-only

        # Filter by type
        prefab-tool deps Player.prefab --type Texture

        # Output as JSON
        prefab-tool deps Player.prefab --format json

        # Analyze multiple files
        prefab-tool deps *.prefab
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
        prefab-tool find-refs Textures/player.png

        # Search in specific directories
        prefab-tool find-refs Textures/player.png --search-path Assets/Prefabs

        # Output as JSON
        prefab-tool find-refs Textures/player.png --format json

        # Show progress
        prefab-tool find-refs Textures/player.png --progress
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
        prefab-tool scan-scripts Player.prefab

        # Scan a directory recursively
        prefab-tool scan-scripts Assets/Prefabs -r

        # Show property keys (to understand component structure)
        prefab-tool scan-scripts Scene.unity --show-properties

        # Group by GUID to see all usages
        prefab-tool scan-scripts Assets/ -r --group-by-guid

        # Output as JSON for further processing
        prefab-tool scan-scripts *.prefab --format json
    """
    from prefab_tool.parser import UnityYAMLDocument
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
        prefab-tool scan-meta "Library/PackageCache/com.unity.render-pipelines.universal@*" -r --scripts-only

        # Find Light-related scripts
        prefab-tool scan-meta "Library/PackageCache/com.unity.render-pipelines.universal@*" -r --filter Light

        # Scan TextMeshPro package
        prefab-tool scan-meta "Library/PackageCache/com.unity.textmeshpro@*" -r --scripts-only

        # Scan local Assets folder
        prefab-tool scan-meta Assets/Scripts -r

        # Output as JSON
        prefab-tool scan-meta "Library/PackageCache/com.unity.cinemachine@*" -r --scripts-only --format json
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
        prefab-tool parse-script Assets/Scripts/Player.cs

        # Output as JSON
        prefab-tool parse-script Assets/Scripts/Player.cs --format json
    """
    from prefab_tool.script_parser import parse_script_file
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
        prefab-tool setup

        # Global setup (applies to all repos)
        prefab-tool setup --global

        # Setup with pre-commit hooks
        prefab-tool setup --with-hooks

        # Setup with pre-commit framework
        prefab-tool setup --with-pre-commit

        # Setup with difftool for Git Fork
        prefab-tool setup --with-difftool

        # Setup difftool with specific backend
        prefab-tool setup --with-difftool --difftool-backend vscode
    """
    import subprocess

    click.echo("=== prefab-tool Git Integration Setup ===")
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
    subprocess.run([*git_config_cmd, "diff.unity.textconv", "prefab-tool git-textconv"], check=True)
    subprocess.run([*git_config_cmd, "diff.unity.cachetextconv", "true"], check=True)

    # Configure merge driver
    click.echo("  Configuring merge driver...")
    subprocess.run([*git_config_cmd, "merge.unity.name", "Unity YAML Merge (prefab-tool)"], check=True)
    subprocess.run([*git_config_cmd, "merge.unity.driver", "prefab-tool merge %O %A %B -o %A --path %P"], check=True)
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
            [*git_config_cmd, "difftool.prefab-unity.cmd", f'prefab-tool difftool{backend_arg} "$LOCAL" "$REMOTE"'],
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
# Unity YAML files - use prefab-tool for diff and merge
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
# prefab-tool pre-commit hook
# Automatically normalize Unity YAML files before commit

set -e

# Get list of staged Unity files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.(prefab|unity|asset)$' || true)

if [ -n "$STAGED_FILES" ]; then
    echo "Normalizing Unity files..."

    for file in $STAGED_FILES; do
        if [ -f "$file" ]; then
            prefab-tool normalize "$file" --in-place
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
  - repo: https://github.com/TrueCyan/prefab-tool
    rev: v0.1.0
    hooks:
      - id: prefab-normalize
      # - id: prefab-validate  # Optional: add validation
"""

        if config_path.exists() and not force:
            existing = config_path.read_text()
            if "prefab-tool" in existing:
                click.echo("  pre-commit already configured for prefab-tool")
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
    click.echo("Git is now configured to use prefab-tool for Unity files.")
    click.echo()
    click.echo("Test with:")
    click.echo("  git diff HEAD~1 -- '*.prefab'")
    click.echo()


@main.command(name="sprite-link", deprecated=True)
@click.argument("prefab", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--component",
    "-c",
    "component_id",
    type=int,
    required=True,
    help="fileID of the SpriteRenderer component to modify",
)
@click.option(
    "--sprite",
    "-s",
    "sprite_path",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to the sprite image file (e.g., Assets/Sprites/icon.png)",
)
@click.option(
    "--sub-sprite",
    type=str,
    help="For Multiple mode sprites, the specific sub-sprite name",
)
@click.option(
    "--material",
    "-m",
    "material_path",
    type=str,
    help="Material path or name (e.g., 'Sprite-Lit-Default' or 'Assets/Materials/Custom.mat')",
)
@click.option(
    "--use-urp-default",
    is_flag=True,
    help="Use URP default material (Sprite-Lit-Default)",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file (default: modify in place)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
def sprite_link(
    prefab: Path,
    component_id: int,
    sprite_path: Path,
    sub_sprite: str | None,
    material_path: str | None,
    use_urp_default: bool,
    output: Path | None,
    dry_run: bool,
) -> None:
    """[DEPRECATED] Link a sprite to a SpriteRenderer component.

    This command is deprecated. Use 'prefab-tool set --sprite' instead:

        prefab-tool set Player.prefab \\
            --path "components/1234567890/m_Sprite" \\
            --sprite "Assets/Sprites/player.png"

    The 'set --sprite' command provides the same functionality with a more
    consistent interface that matches other value-setting operations.
    """
    import warnings
    warnings.warn(
        "sprite-link is deprecated. Use 'prefab-tool set --sprite' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    click.echo(
        "Warning: 'sprite-link' is deprecated. Use 'set --sprite' instead:",
        err=True,
    )
    click.echo(
        f"  prefab-tool set {prefab} --path \"components/{component_id}/m_Sprite\" "
        f"--sprite \"{sprite_path}\"",
        err=True,
    )
    click.echo(err=True)

    from prefab_tool.parser import UnityYAMLDocument
    from prefab_tool.sprite import (
        get_sprite_reference,
        get_sprite_info,
        get_material_reference,
        link_sprite_to_renderer,
    )

    # Get sprite reference
    sprite_ref = get_sprite_reference(sprite_path, sub_sprite)
    if not sprite_ref:
        sprite_info = get_sprite_info(sprite_path)
        if sprite_info and sprite_info.is_multiple and sub_sprite:
            click.echo(f"Error: Sub-sprite '{sub_sprite}' not found in sprite", err=True)
            click.echo(f"Available sub-sprites: {', '.join(sprite_info.get_sprite_names())}", err=True)
        elif not Path(str(sprite_path) + ".meta").exists():
            click.echo(f"Error: Meta file not found for sprite: {sprite_path}", err=True)
        else:
            click.echo(f"Error: Could not get sprite reference for: {sprite_path}", err=True)
        sys.exit(1)

    # Get material reference if specified
    material_ref = None
    if use_urp_default:
        material_ref = get_material_reference("Sprite-Lit-Default")
    elif material_path:
        project_root = find_unity_project_root(prefab)
        material_ref = get_material_reference(material_path, project_root)
        if not material_ref:
            click.echo(f"Error: Could not find material: {material_path}", err=True)
            sys.exit(1)

    # Show sprite info
    sprite_info = get_sprite_info(sprite_path)
    mode_str = "Single" if sprite_info and sprite_info.is_single else "Multiple"

    if dry_run:
        click.echo("Dry run - would perform the following:")
        click.echo(f"  Prefab: {prefab}")
        click.echo(f"  Component fileID: {component_id}")
        click.echo(f"  Sprite: {sprite_path}")
        click.echo(f"  Sprite mode: {mode_str}")
        click.echo(f"  Sprite reference: fileID={sprite_ref.file_id}, guid={sprite_ref.guid}")
        if material_ref:
            click.echo(f"  Material: fileID={material_ref.file_id}, guid={material_ref.guid or '(built-in)'}")
        return

    # Load prefab
    try:
        doc = UnityYAMLDocument.load(prefab)
    except Exception as e:
        click.echo(f"Error: Failed to load prefab: {e}", err=True)
        sys.exit(1)

    # Verify component exists
    obj = doc.get_by_file_id(component_id)
    if not obj:
        click.echo(f"Error: Component with fileID {component_id} not found in prefab", err=True)
        sys.exit(1)

    # Verify it's a SpriteRenderer (class_id 212)
    if obj.class_id != 212:
        click.echo(f"Warning: Component is {obj.class_name} (classID: {obj.class_id}), not SpriteRenderer", err=True)
        click.echo("Proceeding anyway...", err=True)

    # Link sprite
    if not link_sprite_to_renderer(doc, component_id, sprite_ref, material_ref):
        click.echo(f"Error: Failed to link sprite to component", err=True)
        sys.exit(1)

    # Save
    output_path = output or prefab
    doc.save(output_path)

    click.echo(f"Linked sprite to SpriteRenderer:")
    click.echo(f"  Sprite: {sprite_path} ({mode_str} mode)")
    click.echo(f"  fileID: {sprite_ref.file_id}")
    click.echo(f"  guid: {sprite_ref.guid}")
    if material_ref:
        click.echo(f"  Material: fileID={material_ref.file_id}")
    click.echo(f"  Saved to: {output_path}")


@main.command(name="sprite-link-batch")
@click.option(
    "--prefabs",
    type=str,
    help="Glob pattern for prefabs (e.g., 'Assets/Prefabs/*.prefab')",
)
@click.option(
    "--sprite",
    "-s",
    "sprite_path",
    type=click.Path(path_type=Path),
    help="Path to sprite image (for applying same sprite to all prefabs)",
)
@click.option(
    "--component-type",
    type=str,
    default="SpriteRenderer",
    help="Component type to modify (default: SpriteRenderer)",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="JSON configuration file for batch mapping",
)
@click.option(
    "--material",
    "-m",
    "default_material",
    type=str,
    help="Default material for all sprites (name or path)",
)
@click.option(
    "--use-urp-default",
    is_flag=True,
    help="Use URP default material for all sprites",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
@click.option(
    "--progress",
    is_flag=True,
    help="Show progress bar",
)
def sprite_link_batch(
    prefabs: str | None,
    sprite_path: Path | None,
    component_type: str,
    config_path: Path | None,
    default_material: str | None,
    use_urp_default: bool,
    dry_run: bool,
    progress: bool,
) -> None:
    """Batch link sprites to prefabs.

    Two modes of operation:

    1. Pattern mode: Apply same sprite to all prefabs matching a pattern
    2. Config mode: Use a JSON file to define prefab->sprite mappings

    Config File Format:
    {
        "mappings": [
            {
                "prefab": "Assets/Prefabs/Enemy.prefab",
                "sprite": "Assets/Sprites/enemy.png",
                "subSprite": "enemy_idle"  // optional
            }
        ],
        "defaultMaterial": "Sprite-Lit-Default"  // optional
    }

    Examples:

        # Apply same sprite to all prefabs
        prefab-tool sprite-link-batch \\
            --prefabs "Assets/Prefabs/*.prefab" \\
            --sprite "Assets/Sprites/default.png" \\
            --use-urp-default

        # Use config file
        prefab-tool sprite-link-batch --config sprite-mapping.json

        # Dry run
        prefab-tool sprite-link-batch --config sprite-mapping.json --dry-run
    """
    from prefab_tool.parser import UnityYAMLDocument
    from prefab_tool.sprite import (
        get_sprite_reference,
        get_material_reference,
        link_sprite_to_renderer,
    )
    import json
    import glob

    if not prefabs and not config_path:
        click.echo("Error: Either --prefabs or --config is required", err=True)
        sys.exit(1)

    if prefabs and not sprite_path and not config_path:
        click.echo("Error: --sprite is required when using --prefabs without --config", err=True)
        sys.exit(1)

    # Collect mappings
    mappings: list[dict[str, Any]] = []

    if config_path:
        # Load from config file
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            click.echo(f"Error: Failed to load config file: {e}", err=True)
            sys.exit(1)

        mappings = config.get("mappings", [])
        if "defaultMaterial" in config and not default_material:
            default_material = config["defaultMaterial"]

    if prefabs:
        # Expand glob pattern
        prefab_files = list(glob.glob(prefabs, recursive=True))
        if not prefab_files:
            click.echo(f"Error: No prefabs found matching pattern: {prefabs}", err=True)
            sys.exit(1)

        for pf in prefab_files:
            mappings.append({
                "prefab": pf,
                "sprite": str(sprite_path) if sprite_path else None,
            })

    if not mappings:
        click.echo("Error: No mappings to process", err=True)
        sys.exit(1)

    # Get default material reference
    material_ref = None
    if use_urp_default:
        material_ref = get_material_reference("Sprite-Lit-Default")
    elif default_material:
        material_ref = get_material_reference(default_material)

    # Process mappings
    success_count = 0
    error_count = 0

    if progress:
        mappings_iter = click.progressbar(
            mappings,
            label="Processing",
            show_eta=True,
            show_percent=True,
        )
    else:
        mappings_iter = mappings

    for mapping in mappings_iter:
        prefab_path = Path(mapping["prefab"])
        sprite_file = mapping.get("sprite")
        sub_sprite = mapping.get("subSprite")

        if not sprite_file:
            if not progress:
                click.echo(f"Skipping {prefab_path}: no sprite specified", err=True)
            error_count += 1
            continue

        # Get sprite reference
        sprite_ref = get_sprite_reference(sprite_file, sub_sprite)
        if not sprite_ref:
            if not progress:
                click.echo(f"Error: Could not get sprite reference for {sprite_file}", err=True)
            error_count += 1
            continue

        if dry_run:
            if not progress:
                click.echo(f"Would link: {prefab_path} <- {sprite_file}")
            success_count += 1
            continue

        # Load and modify prefab
        try:
            doc = UnityYAMLDocument.load(prefab_path)
        except Exception as e:
            if not progress:
                click.echo(f"Error loading {prefab_path}: {e}", err=True)
            error_count += 1
            continue

        # Find SpriteRenderer component
        sprite_renderers = doc.get_by_class_id(212)  # SpriteRenderer class ID
        if not sprite_renderers:
            if not progress:
                click.echo(f"Warning: No SpriteRenderer found in {prefab_path}", err=True)
            error_count += 1
            continue

        # Link to first SpriteRenderer
        renderer = sprite_renderers[0]
        if link_sprite_to_renderer(doc, renderer.file_id, sprite_ref, material_ref):
            doc.save(prefab_path)
            if not progress:
                click.echo(f"Linked: {prefab_path} <- {sprite_file}")
            success_count += 1
        else:
            if not progress:
                click.echo(f"Error: Failed to link sprite to {prefab_path}", err=True)
            error_count += 1

    click.echo()
    if dry_run:
        click.echo(f"Dry run complete: {success_count} would be processed, {error_count} skipped")
    else:
        click.echo(f"Batch complete: {success_count} processed, {error_count} errors")


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
        prefab-tool sprite-info Assets/Sprites/player.png

        # Output as JSON
        prefab-tool sprite-info Assets/Sprites/atlas.png --format json
    """
    from prefab_tool.sprite import get_sprite_info, SPRITE_SINGLE_MODE_FILE_ID
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
        click.echo(f"GUID: {info.guid}")
        click.echo(f"Mode: {'Single' if info.is_single else 'Multiple'} (spriteMode: {info.sprite_mode})")
        click.echo()

        if info.is_single:
            click.echo(f"Reference fileID: {SPRITE_SINGLE_MODE_FILE_ID}")
            click.echo()
            click.echo("Usage:")
            click.echo(f"  prefab-tool sprite-link <prefab> -c <component_id> -s \"{sprite}\"")
        else:
            click.echo(f"Sub-sprites ({len(info.sprites)}):")
            for s in info.sprites:
                click.echo(f"  {s['name']}: {s['internalID']}")

            if info.sprites:
                first_sprite = info.sprites[0]
                click.echo()
                click.echo("Usage (first sub-sprite):")
                click.echo(f"  prefab-tool sprite-link <prefab> -c <component_id> -s \"{sprite}\" --sub-sprite \"{first_sprite['name']}\"")


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
    "parent_id",
    type=int,
    default=0,
    help="Parent Transform fileID (0 for root)",
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
    parent_id: int,
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
        prefab-tool add-object Scene.unity --name "Player"

        # Add with parent
        prefab-tool add-object Scene.unity --name "Child" --parent 12345

        # Add with position
        prefab-tool add-object Scene.unity --name "Enemy" --position "10,0,5"

        # Add UI GameObject (RectTransform)
        prefab-tool add-object Scene.unity --name "Button" --ui --parent 67890

        # Add with layer and tag
        prefab-tool add-object Scene.unity --name "Enemy" --layer 8 --tag "Enemy"
    """
    from prefab_tool.parser import (
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
            parent_id=parent_id,
        )
    else:
        transform = create_transform(
            game_object_id=go_id,
            file_id=transform_id,
            position=pos,
            parent_id=parent_id,
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
    if parent_id != 0:
        parent_obj = doc.get_by_file_id(parent_id)
        if parent_obj:
            content = parent_obj.get_content()
            if content and "m_Children" in content:
                content["m_Children"].append({"fileID": transform_id})

    doc.save(output_path)
    click.echo(f"Added GameObject '{obj_name}'")
    click.echo(f"  GameObject fileID: {go_id}")
    click.echo(f"  {'RectTransform' if ui else 'Transform'} fileID: {transform_id}")

    if output:
        click.echo(f"Saved to: {output}")


@main.command(name="add-component")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--to",
    "-t",
    "target_id",
    type=int,
    required=True,
    help="Target GameObject fileID",
)
@click.option(
    "--type",
    "component_type",
    type=click.Choice([
        "SpriteRenderer", "Camera", "Light", "AudioSource",
        "BoxCollider2D", "CircleCollider2D", "Rigidbody2D",
    ]),
    default=None,
    help="Built-in component type to add",
)
@click.option(
    "--script",
    "script_guid",
    type=str,
    default=None,
    help="GUID of the MonoBehaviour script to add",
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
    target_id: int,
    component_type: str | None,
    script_guid: str | None,
    props: str | None,
    output: Path | None,
) -> None:
    """Add a component to an existing GameObject.

    Requires either --type for built-in components or --script for MonoBehaviour.

    Examples:

        # Add a built-in component
        prefab-tool add-component Scene.unity --to 12345 --type SpriteRenderer

        # Add a MonoBehaviour
        prefab-tool add-component Scene.unity --to 12345 --script "abc123def456..."

        # Add with properties
        prefab-tool add-component Scene.unity --to 12345 --script "abc123..." \\
            --props '{"speed": 5.0, "health": 100}'

        # Add Camera component
        prefab-tool add-component Scene.unity --to 12345 --type Camera
    """
    from prefab_tool.parser import (
        UnityYAMLDocument,
        create_mono_behaviour,
    )
    import json

    if not component_type and not script_guid:
        click.echo("Error: Specify --type or --script", err=True)
        sys.exit(1)

    if component_type and script_guid:
        click.echo("Error: Cannot use both --type and --script", err=True)
        sys.exit(1)

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Parse properties
    properties = None
    if props:
        try:
            properties = json.loads(props)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --props: {e}", err=True)
            sys.exit(1)

    # Find target GameObject
    target_go = doc.get_by_file_id(target_id)
    if target_go is None:
        click.echo(f"Error: GameObject with fileID {target_id} not found", err=True)
        sys.exit(1)

    if target_go.class_id != 1:
        click.echo(f"Error: fileID {target_id} is not a GameObject", err=True)
        click.echo(f"  Found: {target_go.class_name}", err=True)
        sys.exit(1)

    component_id = doc.generate_unique_file_id()

    if script_guid:
        # Create MonoBehaviour
        component = create_mono_behaviour(
            game_object_id=target_id,
            script_guid=script_guid,
            file_id=component_id,
            properties=properties,
        )
        click.echo(f"Added MonoBehaviour component")
    else:
        # Create built-in component
        component = _create_builtin_component(
            component_type=component_type,
            game_object_id=target_id,
            file_id=component_id,
            properties=properties,
        )
        click.echo(f"Added {component_type} component")

    # Add component to document
    doc.add_object(component)

    # Update GameObject's component list
    go_content = target_go.get_content()
    if go_content and "m_Component" in go_content:
        go_content["m_Component"].append({"component": {"fileID": component_id}})

    doc.save(output_path)
    click.echo(f"  Component fileID: {component_id}")
    click.echo(f"  Target GameObject: {target_id}")

    if output:
        click.echo(f"Saved to: {output}")


def _create_builtin_component(
    component_type: str,
    game_object_id: int,
    file_id: int,
    properties: dict | None = None,
) -> "UnityYAMLObject":
    """Create a built-in Unity component."""
    from prefab_tool.parser import UnityYAMLObject

    # Class ID mapping for built-in components
    class_ids = {
        "Transform": 4,
        "RectTransform": 224,
        "MonoBehaviour": 114,
        "SpriteRenderer": 212,
        "Camera": 20,
        "Light": 108,
        "AudioSource": 82,
        "BoxCollider2D": 61,
        "CircleCollider2D": 58,
        "Rigidbody2D": 50,
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
    "gameobject_id",
    type=int,
    required=True,
    help="FileID of the GameObject to delete",
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
    gameobject_id: int,
    cascade: bool,
    force: bool,
    output: Path | None,
) -> None:
    """Delete a GameObject from a Unity YAML file.

    Deletes the GameObject and all its components.
    Use --cascade to also delete all children recursively.

    Examples:

        # Delete a GameObject (keeps children)
        prefab-tool delete-object Scene.unity --id 12345

        # Delete a GameObject and all its children
        prefab-tool delete-object Scene.unity --id 12345 --cascade

        # Delete without confirmation
        prefab-tool delete-object Scene.unity --id 12345 --force
    """
    from prefab_tool.parser import UnityYAMLDocument

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Find GameObject
    obj = doc.get_by_file_id(gameobject_id)
    if obj is None:
        click.echo(f"Error: GameObject with fileID {gameobject_id} not found", err=True)
        sys.exit(1)

    if obj.class_id != 1:
        click.echo(f"Error: fileID {gameobject_id} is not a GameObject", err=True)
        click.echo(f"  Found: {obj.class_name}", err=True)
        click.echo("Use delete-component for components", err=True)
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
                click.echo(f"  {del_obj.class_name}{name} (fileID: {obj_id})")
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
    "--id",
    "-i",
    "component_id",
    type=int,
    required=True,
    help="FileID of the component to delete",
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
def delete_component(
    file: Path,
    component_id: int,
    force: bool,
    output: Path | None,
) -> None:
    """Delete a component from a Unity YAML file.

    Removes the component and updates the parent GameObject's component list.

    Examples:

        # Delete a component
        prefab-tool delete-component Scene.unity --id 67890

        # Delete without confirmation
        prefab-tool delete-component Scene.unity --id 67890 --force
    """
    from prefab_tool.parser import UnityYAMLDocument

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Find component
    obj = doc.get_by_file_id(component_id)
    if obj is None:
        click.echo(f"Error: Component with fileID {component_id} not found", err=True)
        sys.exit(1)

    if obj.class_id == 1:
        click.echo(f"Error: fileID {component_id} is a GameObject, not a component", err=True)
        click.echo("Use delete-object for GameObjects", err=True)
        sys.exit(1)

    # Find and update the parent GameObject
    content = obj.get_content()
    if content and "m_GameObject" in content:
        parent_go_id = content["m_GameObject"].get("fileID", 0)
        parent_go = doc.get_by_file_id(parent_go_id)
        if parent_go:
            go_content = parent_go.get_content()
            if go_content and "m_Component" in go_content:
                go_content["m_Component"] = [
                    c for c in go_content["m_Component"]
                    if c.get("component", {}).get("fileID") != component_id
                ]

    if not force:
        click.echo(f"Will delete {obj.class_name} (fileID: {component_id})")
        if not click.confirm("Continue?"):
            click.echo("Aborted")
            return

    doc.remove_object(component_id)
    doc.save(output_path)
    click.echo(f"Deleted component {obj.class_name} (fileID: {component_id})")

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
    "source_id",
    type=int,
    required=True,
    help="FileID of the GameObject to clone",
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
    "parent_id",
    type=int,
    default=None,
    help="Parent Transform fileID for the clone (default: same as source)",
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
    source_id: int,
    new_name: str | None,
    parent_id: int | None,
    position: str | None,
    deep: bool,
    output: Path | None,
) -> None:
    """Clone a GameObject within a Unity YAML file.

    Duplicates a GameObject and all its components with new fileIDs.

    Examples:

        # Simple clone (shallow)
        prefab-tool clone-object Scene.unity --id 12345

        # Clone with new name
        prefab-tool clone-object Scene.unity --id 12345 --name "Player2"

        # Clone to different parent
        prefab-tool clone-object Scene.unity --id 12345 --parent 67890

        # Clone with position offset
        prefab-tool clone-object Scene.unity --id 12345 --position "5,0,0"

        # Deep clone (include children)
        prefab-tool clone-object Scene.unity --id 12345 --deep
    """
    from prefab_tool.parser import UnityYAMLDocument, UnityYAMLObject
    import copy

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    output_path = output or file

    # Find source GameObject
    source_go = doc.get_by_file_id(source_id)
    if source_go is None:
        click.echo(f"Error: GameObject with fileID {source_id} not found", err=True)
        sys.exit(1)

    if source_go.class_id != 1:
        click.echo(f"Error: fileID {source_id} is not a GameObject", err=True)
        click.echo(f"  Found: {source_go.class_name}", err=True)
        sys.exit(1)

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

    new_go_id = id_map[source_id]
    click.echo(f"Cloned GameObject")
    click.echo(f"  Source fileID: {source_id}")
    click.echo(f"  New fileID: {new_go_id}")
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


if __name__ == "__main__":
    main()
