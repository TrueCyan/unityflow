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


if __name__ == "__main__":
    main()
