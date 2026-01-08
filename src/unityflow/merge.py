"""Three-way merge for Unity YAML files.

Implements a diff3-style merge algorithm that works on normalized
Unity YAML content to reduce false conflicts from non-deterministic
serialization.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher

# Conflict markers
CONFLICT_START = "<<<<<<< ours"
CONFLICT_SEP = "======="
CONFLICT_END = ">>>>>>> theirs"


@dataclass
class MergeResult:
    """Result of a three-way merge operation."""

    content: str
    has_conflicts: bool
    conflict_count: int = 0


def three_way_merge(
    base: str,
    ours: str,
    theirs: str,
) -> tuple[str, bool]:
    """Perform a three-way merge of text content.

    This is a line-based diff3-style merge algorithm:
    1. Find changes from base->ours and base->theirs
    2. If changes don't overlap, merge them automatically
    3. If changes conflict, insert conflict markers

    Args:
        base: The common ancestor content
        ours: Our version (current branch)
        theirs: Their version (branch being merged)

    Returns:
        Tuple of (merged_content, has_conflicts)
    """
    # Fast paths
    if ours == theirs:
        # Both made same changes (or neither changed)
        return ours, False

    if ours == base:
        # We didn't change, take theirs
        return theirs, False

    if theirs == base:
        # They didn't change, keep ours
        return ours, False

    # Need to do actual merge
    base_lines = base.splitlines(keepends=True)
    ours_lines = ours.splitlines(keepends=True)
    theirs_lines = theirs.splitlines(keepends=True)

    result = merge_lines(base_lines, ours_lines, theirs_lines)

    return result.content, result.has_conflicts


def merge_lines(
    base: list[str],
    ours: list[str],
    theirs: list[str],
) -> MergeResult:
    """Merge three versions of a file at line level.

    Uses a simplified diff3 algorithm:
    1. Compute diff base->ours and base->theirs
    2. Walk through both diffs simultaneously
    3. Apply non-conflicting changes, mark conflicts
    """
    # Get changes from base to each version
    ours_changes = list(compute_changes(base, ours))
    theirs_changes = list(compute_changes(base, theirs))

    # Build merged result
    result_lines: list[str] = []
    conflict_count = 0

    # Current position in base
    base_pos = 0

    # Indexes into change lists
    ours_idx = 0
    theirs_idx = 0

    while base_pos < len(base) or ours_idx < len(ours_changes) or theirs_idx < len(theirs_changes):
        # Get next change from each side (if any applies at current position)
        ours_change = None
        theirs_change = None

        if ours_idx < len(ours_changes):
            c = ours_changes[ours_idx]
            if c.base_start <= base_pos:
                ours_change = c

        if theirs_idx < len(theirs_changes):
            c = theirs_changes[theirs_idx]
            if c.base_start <= base_pos:
                theirs_change = c

        # No more changes - copy rest of base
        if ours_change is None and theirs_change is None:
            if base_pos < len(base):
                result_lines.append(base[base_pos])
                base_pos += 1
            else:
                break
            continue

        # Only ours changed
        if ours_change is not None and theirs_change is None:
            result_lines.extend(ours_change.new_lines)
            base_pos = ours_change.base_end
            ours_idx += 1
            continue

        # Only theirs changed
        if theirs_change is not None and ours_change is None:
            result_lines.extend(theirs_change.new_lines)
            base_pos = theirs_change.base_end
            theirs_idx += 1
            continue

        # Both changed - check for conflict
        assert ours_change is not None and theirs_change is not None

        # If changes are identical, no conflict
        if ours_change.new_lines == theirs_change.new_lines:
            result_lines.extend(ours_change.new_lines)
            base_pos = max(ours_change.base_end, theirs_change.base_end)
            ours_idx += 1
            theirs_idx += 1
            continue

        # Check if changes overlap
        if changes_overlap(ours_change, theirs_change):
            # Conflict!
            conflict_count += 1
            result_lines.append(f"{CONFLICT_START}\n")
            result_lines.extend(ours_change.new_lines)
            result_lines.append(f"{CONFLICT_SEP}\n")
            result_lines.extend(theirs_change.new_lines)
            result_lines.append(f"{CONFLICT_END}\n")
            base_pos = max(ours_change.base_end, theirs_change.base_end)
            ours_idx += 1
            theirs_idx += 1
        else:
            # Non-overlapping changes - apply in order
            if ours_change.base_start <= theirs_change.base_start:
                result_lines.extend(ours_change.new_lines)
                base_pos = ours_change.base_end
                ours_idx += 1
            else:
                result_lines.extend(theirs_change.new_lines)
                base_pos = theirs_change.base_end
                theirs_idx += 1

    content = "".join(result_lines)

    # Ensure trailing newline (but not for empty content)
    if content and not content.endswith("\n"):
        content += "\n"

    return MergeResult(
        content=content,
        has_conflicts=conflict_count > 0,
        conflict_count=conflict_count,
    )


@dataclass
class Change:
    """Represents a change from base to a new version."""

    base_start: int  # Start index in base (inclusive)
    base_end: int  # End index in base (exclusive)
    new_lines: list[str]  # New lines replacing base[start:end]


def compute_changes(base: list[str], new: list[str]) -> Iterator[Change]:
    """Compute the changes needed to transform base into new.

    Yields Change objects representing contiguous modifications.
    """
    matcher = SequenceMatcher(None, base, new, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        elif tag == "replace":
            yield Change(
                base_start=i1,
                base_end=i2,
                new_lines=new[j1:j2],
            )
        elif tag == "delete":
            yield Change(
                base_start=i1,
                base_end=i2,
                new_lines=[],
            )
        elif tag == "insert":
            yield Change(
                base_start=i1,
                base_end=i1,  # Insert at position, doesn't consume base lines
                new_lines=new[j1:j2],
            )


def changes_overlap(a: Change, b: Change) -> bool:
    """Check if two changes overlap in their base regions."""
    # Changes overlap if their base ranges intersect
    return not (a.base_end <= b.base_start or b.base_end <= a.base_start)
