"""Unity Prefab Diff Utilities.

Provides meaningful diff output by normalizing files before comparison,
eliminating noise from Unity's non-deterministic serialization.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from unityflow.normalizer import UnityPrefabNormalizer


class DiffFormat(Enum):
    """Output format for diff."""

    UNIFIED = "unified"
    CONTEXT = "context"
    SIDE_BY_SIDE = "side-by-side"
    SUMMARY = "summary"


@dataclass
class DiffResult:
    """Result of a diff operation."""

    old_path: str
    new_path: str
    old_content: str
    new_content: str
    has_changes: bool
    diff_lines: list[str]

    def __str__(self) -> str:
        return "\n".join(self.diff_lines)

    @property
    def additions(self) -> int:
        """Count of added lines."""
        return sum(1 for line in self.diff_lines if line.startswith("+") and not line.startswith("+++"))

    @property
    def deletions(self) -> int:
        """Count of deleted lines."""
        return sum(1 for line in self.diff_lines if line.startswith("-") and not line.startswith("---"))


class PrefabDiff:
    """Diff utility for Unity prefab files."""

    def __init__(
        self,
        normalize: bool = True,
        context_lines: int = 3,
        format: DiffFormat = DiffFormat.UNIFIED,
    ):
        """Initialize the diff utility.

        Args:
            normalize: Whether to normalize files before diffing
            context_lines: Number of context lines to show
            format: Output format
        """
        self.normalize = normalize
        self.context_lines = context_lines
        self.format = format
        self._normalizer = UnityPrefabNormalizer() if normalize else None

    def diff_files(
        self,
        old_path: str | Path,
        new_path: str | Path,
    ) -> DiffResult:
        """Diff two Unity YAML files.

        Args:
            old_path: Path to the old/original file
            new_path: Path to the new/modified file

        Returns:
            DiffResult containing the diff output
        """
        old_path = Path(old_path)
        new_path = Path(new_path)

        # Read and optionally normalize
        if self.normalize and self._normalizer:
            old_content = self._normalizer.normalize_file(old_path)
            new_content = self._normalizer.normalize_file(new_path)
        else:
            old_content = old_path.read_text(encoding="utf-8")
            new_content = new_path.read_text(encoding="utf-8")

        return self.diff_content(
            old_content,
            new_content,
            old_label=str(old_path),
            new_label=str(new_path),
        )

    def diff_content(
        self,
        old_content: str,
        new_content: str,
        old_label: str = "old",
        new_label: str = "new",
    ) -> DiffResult:
        """Diff two content strings.

        Args:
            old_content: The old/original content
            new_content: The new/modified content
            old_label: Label for the old content
            new_label: Label for the new content

        Returns:
            DiffResult containing the diff output
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        has_changes = old_content != new_content

        if self.format == DiffFormat.UNIFIED:
            diff_lines = list(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=old_label,
                    tofile=new_label,
                    n=self.context_lines,
                )
            )
        elif self.format == DiffFormat.CONTEXT:
            diff_lines = list(
                difflib.context_diff(
                    old_lines,
                    new_lines,
                    fromfile=old_label,
                    tofile=new_label,
                    n=self.context_lines,
                )
            )
        elif self.format == DiffFormat.SUMMARY:
            diff_lines = self._generate_summary(old_lines, new_lines, old_label, new_label)
        else:
            diff_lines = list(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=old_label,
                    tofile=new_label,
                    n=self.context_lines,
                )
            )

        # Strip trailing newlines from diff lines for cleaner output
        diff_lines = [line.rstrip("\n") for line in diff_lines]

        return DiffResult(
            old_path=old_label,
            new_path=new_label,
            old_content=old_content,
            new_content=new_content,
            has_changes=has_changes,
            diff_lines=diff_lines,
        )

    def _generate_summary(
        self,
        old_lines: list[str],
        new_lines: list[str],
        old_label: str,
        new_label: str,
    ) -> list[str]:
        """Generate a summary of changes."""
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = matcher.get_opcodes()

        summary = [f"Comparing {old_label} -> {new_label}", ""]

        additions = 0
        deletions = 0
        changes = 0

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "insert":
                additions += j2 - j1
            elif tag == "delete":
                deletions += i2 - i1
            elif tag == "replace":
                changes += max(i2 - i1, j2 - j1)

        summary.append(f"  Lines added: {additions}")
        summary.append(f"  Lines deleted: {deletions}")
        summary.append(f"  Lines changed: {changes}")

        if additions == 0 and deletions == 0 and changes == 0:
            summary.append("")
            summary.append("No changes detected.")
        else:
            summary.append("")
            summary.append("Changed sections:")
            for tag, i1, i2, j1, j2 in opcodes:
                if tag != "equal":
                    summary.append(f"  - {tag}: lines {i1+1}-{i2} -> {j1+1}-{j2}")

        return summary


def diff_prefabs(
    old_path: str | Path,
    new_path: str | Path,
    normalize: bool = True,
    format: DiffFormat = DiffFormat.UNIFIED,
    context_lines: int = 3,
) -> DiffResult:
    """Convenience function to diff two prefab files.

    Args:
        old_path: Path to the old file
        new_path: Path to the new file
        normalize: Whether to normalize before diffing
        format: Output format
        context_lines: Number of context lines

    Returns:
        DiffResult containing the diff
    """
    differ = PrefabDiff(normalize=normalize, format=format, context_lines=context_lines)
    return differ.diff_files(old_path, new_path)
