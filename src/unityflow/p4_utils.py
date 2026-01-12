"""Perforce utilities for merge conflict resolution.

Provides functions to interact with Perforce (p4) for:
- File history and changelist information
- Merge conflict detection and file content retrieval
- Understanding modification context from changelist descriptions
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChangelistInfo:
    """Information about a Perforce changelist."""

    number: int
    """Changelist number."""

    user: str
    """User who created the changelist."""

    client: str
    """Client workspace name."""

    date: str
    """Date of the changelist."""

    description: str
    """Full description of the changelist."""

    status: str
    """Status of the changelist (pending, submitted, etc.)."""

    def get_summary(self) -> str:
        """Get the first line of the description as summary."""
        lines = self.description.strip().split("\n")
        return lines[0] if lines else ""


@dataclass
class FileRevision:
    """Information about a file revision."""

    depot_path: str
    """Depot path of the file."""

    revision: int
    """Revision number."""

    change: int
    """Changelist number that created this revision."""

    action: str
    """Action (add, edit, delete, integrate, branch, etc.)."""

    file_type: str
    """Perforce file type."""

    date: str
    """Date of the revision."""

    user: str
    """User who made the change."""

    client: str
    """Client workspace."""

    description: str
    """Changelist description."""


@dataclass
class ResolveRecord:
    """Information about a file needing resolve."""

    local_path: Path
    """Local file path."""

    depot_path: str
    """Depot path of the file."""

    from_file: str
    """Source file of the integration."""

    start_rev: int
    """Starting revision of integration range."""

    end_rev: int
    """Ending revision of integration range."""

    how: str
    """Resolution type (content, branch, delete, etc.)."""

    base_rev: int | None = None
    """Base revision for 3-way merge."""

    resolve_type: str = "content"
    """Type of resolve needed."""


@dataclass
class MergeFiles:
    """Three files needed for 3-way merge."""

    base: Path
    """Base version (common ancestor)."""

    yours: Path
    """Your version (local changes)."""

    theirs: Path
    """Their version (incoming changes)."""

    result: Path
    """Target file for merge result."""


def is_perforce_workspace(path: Path | None = None) -> bool:
    """Check if the given path is inside a Perforce workspace.

    Args:
        path: Path to check (default: current directory)

    Returns:
        True if inside a Perforce workspace
    """
    try:
        result = subprocess.run(
            ["p4", "info"],
            cwd=path or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and "Client root:" in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_client_root(cwd: Path | None = None) -> Path | None:
    """Get the Perforce client root directory.

    Args:
        cwd: Working directory (default: current directory)

    Returns:
        Path to client root, or None if not in a workspace
    """
    try:
        result = subprocess.run(
            ["p4", "info"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.split("\n"):
            if line.startswith("Client root:"):
                root_path = line.split(":", 1)[1].strip()
                return Path(root_path)
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_depot_path(local_path: Path, cwd: Path | None = None) -> str | None:
    """Convert a local path to depot path.

    Args:
        local_path: Local file path
        cwd: Working directory

    Returns:
        Depot path string, or None if file is not mapped
    """
    try:
        result = subprocess.run(
            ["p4", "where", str(local_path)],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        # p4 where returns: depotPath clientPath localPath
        # We want the depot path (first column)
        line = result.stdout.strip()
        if line and not line.startswith("-"):
            parts = line.split()
            if parts:
                return parts[0]
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_changelist_info(changelist: int | str, cwd: Path | None = None) -> ChangelistInfo | None:
    """Get information about a changelist.

    Args:
        changelist: Changelist number or 'default'
        cwd: Working directory

    Returns:
        ChangelistInfo object, or None if not found
    """
    try:
        result = subprocess.run(
            ["p4", "describe", "-s", str(changelist)],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        return _parse_describe_output(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_pending_changelists(cwd: Path | None = None) -> list[ChangelistInfo]:
    """Get all pending changelists for the current client.

    Args:
        cwd: Working directory

    Returns:
        List of ChangelistInfo objects
    """
    try:
        result = subprocess.run(
            ["p4", "changes", "-s", "pending", "-c", ""],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Get client name first
        info_result = subprocess.run(
            ["p4", "info"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )

        client_name = None
        for line in info_result.stdout.split("\n"):
            if line.startswith("Client name:"):
                client_name = line.split(":", 1)[1].strip()
                break

        if not client_name:
            return []

        # Now get changes for this client
        result = subprocess.run(
            ["p4", "changes", "-s", "pending", "-c", client_name],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        changelists = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: Change 12345 on 2024/01/15 by user@client *pending* 'description...'
            match = re.match(r"Change (\d+) on (\S+) by (\S+)@(\S+) \*pending\* '(.+)'", line)
            if match:
                cl_num = int(match.group(1))
                # Get full description
                cl_info = get_changelist_info(cl_num, cwd)
                if cl_info:
                    changelists.append(cl_info)

        return changelists
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []


def get_file_log(
    file_path: Path | str,
    max_revisions: int = 10,
    cwd: Path | None = None,
) -> list[FileRevision]:
    """Get revision history for a file.

    Args:
        file_path: Local or depot path
        max_revisions: Maximum number of revisions to retrieve
        cwd: Working directory

    Returns:
        List of FileRevision objects (newest first)
    """
    try:
        result = subprocess.run(
            ["p4", "filelog", "-l", "-m", str(max_revisions), str(file_path)],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        return _parse_filelog_output(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []


def get_files_to_resolve(cwd: Path | None = None) -> list[ResolveRecord]:
    """Get list of files that need to be resolved.

    Args:
        cwd: Working directory

    Returns:
        List of ResolveRecord objects
    """
    try:
        result = subprocess.run(
            ["p4", "resolve", "-n"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=60,
        )

        # p4 resolve -n returns list of files needing resolve
        records = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            record = _parse_resolve_line(line, cwd)
            if record:
                records.append(record)

        return records
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []


def get_file_content_at_revision(
    file_path: Path | str,
    revision: int | str,
    cwd: Path | None = None,
) -> bytes | None:
    """Get file content at a specific revision.

    Args:
        file_path: Local or depot path
        revision: Revision number or 'head', 'have'
        cwd: Working directory

    Returns:
        File content as bytes, or None if failed
    """
    try:
        # Build the revision spec
        if isinstance(revision, int):
            rev_spec = f"#{revision}"
        else:
            rev_spec = f"#{revision}"

        result = subprocess.run(
            ["p4", "print", "-q", f"{file_path}{rev_spec}"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            timeout=60,
        )

        if result.returncode != 0:
            return None

        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_merge_files(resolve_record: ResolveRecord, cwd: Path | None = None) -> MergeFiles | None:
    """Get the three files needed for 3-way merge.

    Uses p4 resolve -o to get base, yours, and theirs files.

    Args:
        resolve_record: ResolveRecord from get_files_to_resolve
        cwd: Working directory

    Returns:
        MergeFiles with paths to temp files, or None if failed
    """
    try:
        # Create temp directory for merge files
        temp_dir = Path(tempfile.mkdtemp(prefix="unityflow_p4_"))

        # Get 'yours' (local file before resolve)
        yours_path = temp_dir / "yours"
        yours_content = resolve_record.local_path.read_bytes()
        yours_path.write_bytes(yours_content)

        # Get 'theirs' (source file revision)
        theirs_path = temp_dir / "theirs"
        theirs_content = get_file_content_at_revision(
            resolve_record.from_file,
            resolve_record.end_rev,
            cwd,
        )
        if theirs_content is None:
            return None
        theirs_path.write_bytes(theirs_content)

        # Get 'base' (common ancestor)
        # The base is typically the revision before the integration started
        base_path = temp_dir / "base"
        if resolve_record.base_rev:
            base_content = get_file_content_at_revision(
                resolve_record.depot_path,
                resolve_record.base_rev,
                cwd,
            )
        else:
            # Try to get have revision as base
            base_content = get_file_content_at_revision(
                resolve_record.depot_path,
                "have",
                cwd,
            )
        if base_content is None:
            # Use theirs as base if we can't find a better one
            base_content = theirs_content
        base_path.write_bytes(base_content)

        return MergeFiles(
            base=base_path,
            yours=yours_path,
            theirs=theirs_path,
            result=resolve_record.local_path,
        )
    except Exception:
        return None


def accept_resolve(
    file_path: Path,
    resolution: str = "am",
    cwd: Path | None = None,
) -> bool:
    """Accept a resolution for a file.

    Args:
        file_path: Local file path
        resolution: Resolution type:
            - 'am': accept merge (auto-merge)
            - 'ay': accept yours
            - 'at': accept theirs
            - 'ae': accept edit (use current file content)
        cwd: Working directory

    Returns:
        True if successful
    """
    try:
        result = subprocess.run(
            ["p4", "resolve", f"-{resolution}", str(file_path)],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_changelist_for_file(file_path: Path, cwd: Path | None = None) -> ChangelistInfo | None:
    """Get the changelist that a file is opened in.

    Args:
        file_path: Local file path
        cwd: Working directory

    Returns:
        ChangelistInfo if file is opened, None otherwise
    """
    try:
        result = subprocess.run(
            ["p4", "opened", str(file_path)],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        # Parse: //depot/path#rev - action (change CL) (type)
        line = result.stdout.strip()
        match = re.search(r"change (\d+|default)", line, re.IGNORECASE)
        if match:
            cl = match.group(1)
            if cl.lower() == "default":
                return ChangelistInfo(
                    number=0,
                    user="",
                    client="",
                    date="",
                    description="Default changelist",
                    status="pending",
                )
            return get_changelist_info(int(cl), cwd)
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_integration_history(file_path: Path | str, cwd: Path | None = None) -> list[dict]:
    """Get integration history for a file.

    Shows where the file was copied/merged from and to.

    Args:
        file_path: Local or depot path
        cwd: Working directory

    Returns:
        List of integration records
    """
    try:
        result = subprocess.run(
            ["p4", "integrated", str(file_path)],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        records = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Parse integration record
            # Format: depotFile#startRev,#endRev - how fromFile#startRev,#endRev
            record = _parse_integration_line(line)
            if record:
                records.append(record)

        return records
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []


# ============================================================================
# Parsing helpers
# ============================================================================


def _parse_describe_output(output: str) -> ChangelistInfo | None:
    """Parse p4 describe -s output."""
    lines = output.strip().split("\n")
    if not lines:
        return None

    # First line: Change 12345 by user@client on 2024/01/15 12:34:56 *pending*
    first_line = lines[0]
    match = re.match(r"Change (\d+) by (\S+)@(\S+) on (\S+ \S+)(?:\s+\*(\w+)\*)?", first_line)
    if not match:
        return None

    cl_number = int(match.group(1))
    user = match.group(2)
    client = match.group(3)
    date = match.group(4)
    status = match.group(5) or "submitted"

    # Description follows, indented with a tab
    description_lines = []
    in_description = False
    for line in lines[1:]:
        if line.startswith("\t"):
            description_lines.append(line[1:])  # Remove leading tab
            in_description = True
        elif in_description and line.strip() == "":
            continue
        elif line.startswith("Affected files"):
            break  # Stop at file list

    return ChangelistInfo(
        number=cl_number,
        user=user,
        client=client,
        date=date,
        description="\n".join(description_lines),
        status=status,
    )


def _parse_filelog_output(output: str) -> list[FileRevision]:
    """Parse p4 filelog -l output."""
    revisions = []
    lines = output.strip().split("\n")

    current_depot_path = ""
    current_rev: dict = {}

    for line in lines:
        if line.startswith("//"):
            # Depot path header
            current_depot_path = line.strip()
        elif line.startswith("... #"):
            # Revision line: ... #rev change 12345 action on date by user@client (type)
            if current_rev:
                revisions.append(_make_file_revision(current_depot_path, current_rev))
                current_rev = {}

            match = re.match(
                r"\.\.\. #(\d+) change (\d+) (\w+) on (\S+) by (\S+)@(\S+) \((.+)\)",
                line,
            )
            if match:
                current_rev = {
                    "revision": int(match.group(1)),
                    "change": int(match.group(2)),
                    "action": match.group(3),
                    "date": match.group(4),
                    "user": match.group(5),
                    "client": match.group(6),
                    "file_type": match.group(7),
                    "description": "",
                }
        elif line.startswith("\t") and current_rev:
            # Description line
            current_rev["description"] += line[1:] + "\n"

    if current_rev:
        revisions.append(_make_file_revision(current_depot_path, current_rev))

    return revisions


def _make_file_revision(depot_path: str, data: dict) -> FileRevision:
    """Create FileRevision from parsed data."""
    return FileRevision(
        depot_path=depot_path,
        revision=data.get("revision", 0),
        change=data.get("change", 0),
        action=data.get("action", ""),
        file_type=data.get("file_type", ""),
        date=data.get("date", ""),
        user=data.get("user", ""),
        client=data.get("client", ""),
        description=data.get("description", "").strip(),
    )


def _parse_resolve_line(line: str, cwd: Path | None = None) -> ResolveRecord | None:
    """Parse a line from p4 resolve -n output."""
    # Format varies but typically:
    # localPath - merging/integrating from fromPath#rev,#rev
    # or: localPath - merging from fromPath#rev using base fromPath#baseRev

    match = re.match(r"(.+) - (\w+) from (.+)#(\d+),?#?(\d+)?", line)
    if not match:
        return None

    local_path = Path(match.group(1).strip())
    how = match.group(2)
    from_file = match.group(3)
    start_rev = int(match.group(4))
    end_rev = int(match.group(5)) if match.group(5) else start_rev

    depot_path = get_depot_path(local_path, cwd) or ""

    return ResolveRecord(
        local_path=local_path,
        depot_path=depot_path,
        from_file=from_file,
        start_rev=start_rev,
        end_rev=end_rev,
        how=how,
    )


def _parse_integration_line(line: str) -> dict | None:
    """Parse a line from p4 integrated output."""
    # Format: depotFile#startRev,#endRev - how fromFile#startRev,#endRev
    match = re.match(r"(.+)#(\d+),?#?(\d+)? - (\w+) (.+)#(\d+),?#?(\d+)?", line)
    if not match:
        return None

    return {
        "to_file": match.group(1),
        "to_start_rev": int(match.group(2)),
        "to_end_rev": int(match.group(3)) if match.group(3) else int(match.group(2)),
        "how": match.group(4),
        "from_file": match.group(5),
        "from_start_rev": int(match.group(6)),
        "from_end_rev": int(match.group(7)) if match.group(7) else int(match.group(6)),
    }
