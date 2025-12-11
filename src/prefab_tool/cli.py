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
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def query(
    file: Path,
    query_path_str: str | None,
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
    """
    from prefab_tool.parser import UnityYAMLDocument
    from prefab_tool.query import query_path as do_query
    from prefab_tool.formats import get_summary
    import json

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

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
    required=True,
    help="Value to set (JSON format for complex values)",
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
    value: str,
    output: Path | None,
) -> None:
    """Set a value at a specific path in a Unity YAML file.

    This enables surgical editing of prefab data.

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
    """
    from prefab_tool.parser import UnityYAMLDocument
    from prefab_tool.query import set_value
    import json

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    # Parse the value
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        # Try as raw string
        parsed_value = value

    # Set the value
    if set_value(doc, set_path, parsed_value):
        output_path = output or file
        doc.save(output_path)
        click.echo(f"Set {set_path} = {value}")
        if output:
            click.echo(f"Saved to: {output}")
    else:
        click.echo(f"Error: Path not found: {set_path}", err=True)
        sys.exit(1)


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


if __name__ == "__main__":
    main()
