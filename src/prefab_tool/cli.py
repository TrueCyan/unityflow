"""Command-line interface for prefab-tool.

Provides commands for normalizing, diffing, and validating Unity YAML files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from prefab_tool import __version__
from prefab_tool.diff import DiffFormat, PrefabDiff
from prefab_tool.normalizer import UnityPrefabNormalizer
from prefab_tool.validator import PrefabValidator


@click.group()
@click.version_option(version=__version__, prog_name="prefab-tool")
def main() -> None:
    """Unity Prefab Deterministic Serializer.

    A tool for canonical serialization of Unity YAML files to eliminate
    non-deterministic changes and reduce VCS noise.
    """
    pass


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (default: overwrite input or stdout with --stdout)",
)
@click.option(
    "--stdout",
    is_flag=True,
    help="Write to stdout instead of file",
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
def normalize(
    input_file: Path,
    output: Path | None,
    stdout: bool,
    no_sort_documents: bool,
    no_sort_modifications: bool,
    no_normalize_floats: bool,
    hex_floats: bool,
    no_normalize_quaternions: bool,
    precision: int,
    output_format: str,
) -> None:
    """Normalize a Unity YAML file for deterministic serialization.

    INPUT_FILE is the path to the prefab, scene, or asset file.

    Examples:

        # Normalize in place
        prefab-tool normalize Player.prefab

        # Normalize to a new file
        prefab-tool normalize Player.prefab -o Player.normalized.prefab

        # Output to stdout
        prefab-tool normalize Player.prefab --stdout
    """
    normalizer = UnityPrefabNormalizer(
        sort_documents=not no_sort_documents,
        sort_modifications=not no_sort_modifications,
        normalize_floats=not no_normalize_floats,
        use_hex_floats=hex_floats,
        normalize_quaternions=not no_normalize_quaternions,
        float_precision=precision,
    )

    try:
        content = normalizer.normalize_file(input_file)
    except Exception as e:
        click.echo(f"Error: Failed to normalize {input_file}: {e}", err=True)
        sys.exit(1)

    if output_format == "json":
        # TODO: Implement JSON export
        click.echo("Error: JSON format not yet implemented", err=True)
        sys.exit(1)

    if stdout:
        click.echo(content, nl=False)
    elif output:
        output.write_text(content, encoding="utf-8", newline="\n")
        click.echo(f"Normalized: {input_file} -> {output}")
    else:
        input_file.write_text(content, encoding="utf-8", newline="\n")
        click.echo(f"Normalized: {input_file}")


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
    "query_path",
    help="JSON path to query (e.g., 'gameObjects/*/name')",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "yaml"]),
    default="text",
    help="Output format (default: text)",
)
def query(
    file: Path,
    query_path: str | None,
    output_format: str,
) -> None:
    """Query data from a Unity YAML file.

    Examples:

        # List all GameObjects
        prefab-tool query Player.prefab --path "gameObjects/*/name"

        # Get component types
        prefab-tool query Player.prefab --path "components/*/type" --format json
    """
    from prefab_tool.parser import UnityYAMLDocument

    try:
        doc = UnityYAMLDocument.load(file)
    except Exception as e:
        click.echo(f"Error: Failed to load {file}: {e}", err=True)
        sys.exit(1)

    if not query_path:
        # Show summary
        click.echo(f"File: {file}")
        click.echo(f"Objects: {len(doc.objects)}")
        click.echo()
        click.echo("Objects by type:")

        type_counts: dict[str, int] = {}
        for obj in doc.objects:
            type_counts[obj.class_name] = type_counts.get(obj.class_name, 0) + 1

        for type_name, count in sorted(type_counts.items()):
            click.echo(f"  {type_name}: {count}")
        return

    # TODO: Implement path-based querying
    click.echo("Error: Path-based querying not yet fully implemented", err=True)
    click.echo("Showing document summary instead...")
    click.echo()

    for obj in doc.objects[:10]:  # Show first 10
        content = obj.get_content()
        name = content.get("m_Name", "<unnamed>") if content else "<no data>"
        click.echo(f"  [{obj.class_name}] fileID={obj.file_id} name={name}")

    if len(doc.objects) > 10:
        click.echo(f"  ... and {len(doc.objects) - 10} more objects")


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

    BASE is the common ancestor file.
    OURS is the current branch version.
    THEIRS is the version being merged.

    Examples:

        # Manual merge
        prefab-tool merge base.prefab ours.prefab theirs.prefab -o merged.prefab

        # Git merge driver usage (in .gitconfig):
        # [merge "unityyamlmerge"]
        #     driver = prefab-tool merge %O %A %B -o %A --path %P
    """
    # TODO: Implement proper semantic merge
    # For now, normalize and use line-based merge

    normalizer = UnityPrefabNormalizer()

    try:
        base_content = normalizer.normalize_file(base)
        ours_content = normalizer.normalize_file(ours)
        theirs_content = normalizer.normalize_file(theirs)
    except Exception as e:
        click.echo(f"Error: Failed to normalize files: {e}", err=True)
        sys.exit(1)

    # Simple line-based 3-way merge
    import difflib

    base_lines = base_content.splitlines(keepends=True)
    ours_lines = ours_content.splitlines(keepends=True)
    theirs_lines = theirs_content.splitlines(keepends=True)

    # Use SequenceMatcher for basic merge
    # This is a simplified merge - production would need semantic merge
    if ours_content == theirs_content:
        # No conflict - both sides made same changes
        result = ours_content
        has_conflict = False
    elif ours_content == base_content:
        # We didn't change, take theirs
        result = theirs_content
        has_conflict = False
    elif theirs_content == base_content:
        # They didn't change, keep ours
        result = ours_content
        has_conflict = False
    else:
        # Both sides changed - try diff3-style merge
        # For now, just report conflict
        click.echo(
            "Warning: Both branches modified the file. Manual resolution may be needed.",
            err=True,
        )
        # Take ours for now and exit with conflict status
        result = ours_content
        has_conflict = True

    output_path = output or ours
    output_path.write_text(result, encoding="utf-8", newline="\n")

    if has_conflict:
        click.echo(f"Conflict: {file_path or ours}", err=True)
        sys.exit(1)
    else:
        click.echo(f"Merged: {file_path or ours}")
        sys.exit(0)


if __name__ == "__main__":
    main()
