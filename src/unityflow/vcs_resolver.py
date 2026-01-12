"""VCS-agnostic merge conflict resolver for Unity YAML files.

Supports both Git and Perforce for intelligent merge conflict resolution:
1. Analyzing commit/changelist descriptions for modification context
2. Using semantic 3-way merge for Unity YAML files
3. Auto-resolving non-overlapping changes
4. Presenting conflicts with context for user decision
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from unityflow.git_utils import UNITY_EXTENSIONS
from unityflow.parser import UnityYAMLDocument
from unityflow.semantic_merge import (
    PropertyConflict,
    SemanticMergeResult,
    apply_resolution,
    semantic_three_way_merge,
)

if TYPE_CHECKING:
    from unityflow.semantic_merge import ObjectConflict


class VCSType(Enum):
    """Type of version control system."""

    GIT = "git"
    PERFORCE = "perforce"
    UNKNOWN = "unknown"


class ResolutionStrategy(Enum):
    """Strategy for resolving a conflict."""

    AUTO = "auto"
    """Automatically resolved by semantic merge."""

    OURS = "ours"
    """Keep our version."""

    THEIRS = "theirs"
    """Accept their version."""

    MANUAL = "manual"
    """Requires manual resolution."""

    SKIP = "skip"
    """Skip this file, leave unresolved."""


@dataclass
class ChangeInfo:
    """VCS-agnostic change information (commit or changelist)."""

    identifier: str
    """Commit hash or changelist number."""

    author: str
    """Author/user of the change."""

    date: str
    """Date of the change."""

    description: str
    """Full description/message."""

    vcs_type: VCSType
    """Type of VCS."""

    def get_summary(self) -> str:
        """Get the first line of the description as summary."""
        lines = self.description.strip().split("\n")
        return lines[0] if lines else ""


@dataclass
class MergeFiles:
    """Three files needed for 3-way merge."""

    base: Path
    """Base version (common ancestor)."""

    ours: Path
    """Our version (local changes)."""

    theirs: Path
    """Their version (incoming changes)."""

    result: Path
    """Target file for merge result."""


@dataclass
class ConflictFile:
    """A file with merge conflicts."""

    local_path: Path
    """Local file path."""

    ours_ref: str
    """Our reference (commit, revision, etc.)."""

    theirs_ref: str
    """Their reference."""

    base_ref: str
    """Base reference (common ancestor)."""

    vcs_type: VCSType
    """Type of VCS."""


@dataclass
class ModificationContext:
    """Context about what was modified and why."""

    file_path: Path
    """Path to the modified file."""

    ours_change: ChangeInfo | None
    """Our change information."""

    theirs_change: ChangeInfo | None
    """Their change information."""

    ours_objects: list[str] = field(default_factory=list)
    """List of object names/paths mentioned in our change."""

    theirs_objects: list[str] = field(default_factory=list)
    """List of object names/paths mentioned in their change."""

    ours_intent: str = ""
    """Inferred intent from our change description."""

    theirs_intent: str = ""
    """Inferred intent from their change description."""


@dataclass
class ConflictInfo:
    """Extended conflict information with context."""

    conflict: PropertyConflict | ObjectConflict
    """The underlying conflict from semantic merge."""

    game_object_path: str
    """Full path to the affected GameObject."""

    component_type: str
    """Type of component affected."""

    property_display: str
    """Human-readable property description."""

    ours_context: str
    """Context about our change."""

    theirs_context: str
    """Context about their change."""

    suggested_resolution: ResolutionStrategy
    """AI-suggested resolution based on context."""

    suggestion_reason: str
    """Reason for the suggested resolution."""


@dataclass
class ResolveResult:
    """Result of resolving a single file."""

    file_path: Path
    """Path to the file."""

    success: bool
    """Whether resolution was successful."""

    strategy: ResolutionStrategy
    """Strategy used for resolution."""

    auto_merged_count: int
    """Number of changes auto-merged."""

    conflict_count: int
    """Number of conflicts (resolved + unresolved)."""

    conflicts_resolved: int
    """Number of conflicts resolved."""

    message: str
    """Human-readable status message."""


# ============================================================================
# VCS Adapter Interface
# ============================================================================


class VCSAdapter(ABC):
    """Abstract base class for VCS-specific operations."""

    @abstractmethod
    def get_vcs_type(self) -> VCSType:
        """Get the VCS type."""
        ...

    @abstractmethod
    def is_available(self, cwd: Path | None = None) -> bool:
        """Check if this VCS is available in the given directory."""
        ...

    @abstractmethod
    def get_conflicts(self, cwd: Path | None = None) -> list[ConflictFile]:
        """Get list of files with merge conflicts."""
        ...

    @abstractmethod
    def get_merge_files(self, conflict: ConflictFile, cwd: Path | None = None) -> MergeFiles | None:
        """Get base, ours, theirs files for merge."""
        ...

    @abstractmethod
    def get_change_info(self, ref: str, cwd: Path | None = None) -> ChangeInfo | None:
        """Get change information for a reference."""
        ...

    @abstractmethod
    def mark_resolved(self, file_path: Path, cwd: Path | None = None) -> bool:
        """Mark a file as resolved."""
        ...


# ============================================================================
# Git Adapter
# ============================================================================


class GitAdapter(VCSAdapter):
    """Git-specific VCS operations."""

    def get_vcs_type(self) -> VCSType:
        return VCSType.GIT

    def is_available(self, cwd: Path | None = None) -> bool:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_conflicts(self, cwd: Path | None = None) -> list[ConflictFile]:
        """Get files with unmerged status from git."""
        try:
            # Get unmerged files
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return []

            conflicts = []
            repo_root = self._get_repo_root(cwd)
            if not repo_root:
                return []

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                file_path = repo_root / line
                suffix = file_path.suffix.lower()
                if suffix not in UNITY_EXTENSIONS:
                    continue

                conflicts.append(
                    ConflictFile(
                        local_path=file_path,
                        ours_ref="HEAD",
                        theirs_ref="MERGE_HEAD",
                        base_ref="$(git merge-base HEAD MERGE_HEAD)",
                        vcs_type=VCSType.GIT,
                    )
                )

            return conflicts
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    def get_merge_files(self, conflict: ConflictFile, cwd: Path | None = None) -> MergeFiles | None:
        """Get base, ours, theirs from git."""
        try:
            repo_root = self._get_repo_root(cwd)
            if not repo_root:
                return None

            rel_path = conflict.local_path.relative_to(repo_root)
            temp_dir = Path(tempfile.mkdtemp(prefix="unityflow_git_"))

            # Get base (stage 1)
            base_path = temp_dir / "base"
            base_content = self._get_staged_content(rel_path, 1, cwd)
            if base_content:
                base_path.write_bytes(base_content)
            else:
                # Try merge-base
                base_content = self._get_ref_content(rel_path, "$(git merge-base HEAD MERGE_HEAD)", cwd)
                if base_content:
                    base_path.write_bytes(base_content)
                else:
                    return None

            # Get ours (stage 2 or HEAD)
            ours_path = temp_dir / "ours"
            ours_content = self._get_staged_content(rel_path, 2, cwd)
            if not ours_content:
                ours_content = self._get_ref_content(rel_path, "HEAD", cwd)
            if ours_content:
                ours_path.write_bytes(ours_content)
            else:
                return None

            # Get theirs (stage 3 or MERGE_HEAD)
            theirs_path = temp_dir / "theirs"
            theirs_content = self._get_staged_content(rel_path, 3, cwd)
            if not theirs_content:
                theirs_content = self._get_ref_content(rel_path, "MERGE_HEAD", cwd)
            if theirs_content:
                theirs_path.write_bytes(theirs_content)
            else:
                return None

            return MergeFiles(
                base=base_path,
                ours=ours_path,
                theirs=theirs_path,
                result=conflict.local_path,
            )

        except Exception:
            return None

    def get_change_info(self, ref: str, cwd: Path | None = None) -> ChangeInfo | None:
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H%n%an%n%ai%n%B", ref],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return None

            lines = result.stdout.strip().split("\n")
            if len(lines) < 4:
                return None

            return ChangeInfo(
                identifier=lines[0],
                author=lines[1],
                date=lines[2],
                description="\n".join(lines[3:]),
                vcs_type=VCSType.GIT,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def mark_resolved(self, file_path: Path, cwd: Path | None = None) -> bool:
        try:
            result = subprocess.run(
                ["git", "add", str(file_path)],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_repo_root(self, cwd: Path | None = None) -> Path | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return Path(result.stdout.strip())
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _get_staged_content(self, rel_path: Path, stage: int, cwd: Path | None = None) -> bytes | None:
        """Get file content from git index at specific stage."""
        try:
            result = subprocess.run(
                ["git", "show", f":{stage}:{rel_path}"],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _get_ref_content(self, rel_path: Path, ref: str, cwd: Path | None = None) -> bytes | None:
        """Get file content at a specific ref."""
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{rel_path}"],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None


# ============================================================================
# Perforce Adapter
# ============================================================================


class PerforceAdapter(VCSAdapter):
    """Perforce-specific VCS operations."""

    def get_vcs_type(self) -> VCSType:
        return VCSType.PERFORCE

    def is_available(self, cwd: Path | None = None) -> bool:
        try:
            result = subprocess.run(
                ["p4", "info"],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and "Client root:" in result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_conflicts(self, cwd: Path | None = None) -> list[ConflictFile]:
        """Get files needing resolve from p4."""
        try:
            result = subprocess.run(
                ["p4", "resolve", "-n"],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True,
                timeout=60,
            )

            conflicts = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                conflict = self._parse_resolve_line(line, cwd)
                if conflict and conflict.local_path.suffix.lower() in UNITY_EXTENSIONS:
                    conflicts.append(conflict)

            return conflicts
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    def get_merge_files(self, conflict: ConflictFile, cwd: Path | None = None) -> MergeFiles | None:
        """Get base, ours, theirs from Perforce."""
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="unityflow_p4_"))

            # Get ours (current file)
            ours_path = temp_dir / "ours"
            ours_content = conflict.local_path.read_bytes()
            ours_path.write_bytes(ours_content)

            # Get theirs
            theirs_path = temp_dir / "theirs"
            theirs_content = self._get_revision_content(conflict.theirs_ref, cwd)
            if not theirs_content:
                return None
            theirs_path.write_bytes(theirs_content)

            # Get base
            base_path = temp_dir / "base"
            base_content = self._get_revision_content(conflict.base_ref, cwd)
            if not base_content:
                base_content = theirs_content  # Fallback
            base_path.write_bytes(base_content)

            return MergeFiles(
                base=base_path,
                ours=ours_path,
                theirs=theirs_path,
                result=conflict.local_path,
            )
        except Exception:
            return None

    def get_change_info(self, ref: str, cwd: Path | None = None) -> ChangeInfo | None:
        try:
            result = subprocess.run(
                ["p4", "describe", "-s", ref],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return None

            return self._parse_describe_output(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def mark_resolved(self, file_path: Path, cwd: Path | None = None) -> bool:
        try:
            result = subprocess.run(
                ["p4", "resolve", "-ae", str(file_path)],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                timeout=60,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _parse_resolve_line(self, line: str, cwd: Path | None = None) -> ConflictFile | None:
        """Parse a line from p4 resolve -n output."""
        match = re.match(r"(.+) - (\w+) from (.+)#(\d+),?#?(\d+)?", line)
        if not match:
            return None

        local_path = Path(match.group(1).strip())
        from_file = match.group(3)
        end_rev = match.group(5) if match.group(5) else match.group(4)

        return ConflictFile(
            local_path=local_path,
            ours_ref="local",
            theirs_ref=f"{from_file}#{end_rev}",
            base_ref=f"{from_file}#head",
            vcs_type=VCSType.PERFORCE,
        )

    def _get_revision_content(self, ref: str, cwd: Path | None = None) -> bytes | None:
        try:
            result = subprocess.run(
                ["p4", "print", "-q", ref],
                cwd=cwd or Path.cwd(),
                capture_output=True,
                timeout=60,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _parse_describe_output(self, output: str) -> ChangeInfo | None:
        lines = output.strip().split("\n")
        if not lines:
            return None

        match = re.match(r"Change (\d+) by (\S+)@(\S+) on (\S+ \S+)", lines[0])
        if not match:
            return None

        description_lines = []
        for line in lines[1:]:
            if line.startswith("\t"):
                description_lines.append(line[1:])
            elif line.startswith("Affected files"):
                break

        return ChangeInfo(
            identifier=match.group(1),
            author=match.group(2),
            date=match.group(4),
            description="\n".join(description_lines),
            vcs_type=VCSType.PERFORCE,
        )


# ============================================================================
# VCS Detection and Factory
# ============================================================================


def detect_vcs(cwd: Path | None = None) -> VCSAdapter | None:
    """Detect which VCS is being used and return appropriate adapter.

    Args:
        cwd: Working directory

    Returns:
        VCSAdapter for the detected VCS, or None if not in a VCS
    """
    # Try Git first (more common)
    git_adapter = GitAdapter()
    if git_adapter.is_available(cwd):
        return git_adapter

    # Try Perforce
    p4_adapter = PerforceAdapter()
    if p4_adapter.is_available(cwd):
        return p4_adapter

    return None


# ============================================================================
# Resolution Logic (VCS-agnostic)
# ============================================================================


def extract_object_names(description: str) -> list[str]:
    """Extract potential GameObject/component names from a description."""
    names = []

    # Path-like patterns
    path_pattern = r"\b([A-Z][a-zA-Z0-9]*(?:/[A-Z][a-zA-Z0-9]*)+)\b"
    paths = re.findall(path_pattern, description)
    names.extend(paths)

    # Quoted strings
    quoted_pattern = r'"([^"]+)"|\'([^\']+)\''
    quoted = re.findall(quoted_pattern, description)
    for q1, q2 in quoted:
        if q1:
            names.append(q1)
        if q2:
            names.append(q2)

    # Component types
    component_types = [
        "Transform",
        "RectTransform",
        "SpriteRenderer",
        "Image",
        "Button",
        "Text",
        "Canvas",
        "Animator",
        "Collider",
        "Rigidbody",
        "AudioSource",
        "ParticleSystem",
        "Light",
        "Camera",
    ]
    for comp in component_types:
        if comp.lower() in description.lower():
            names.append(comp)

    return list(set(names))


def infer_intent(description: str) -> str:
    """Infer the intent/purpose from a change description."""
    desc_lower = description.lower()

    intent_patterns = [
        (r"\b(fix|bug|issue|crash|error)\b", "bug fix"),
        (r"\b(add|new|create|implement)\b", "new feature"),
        (r"\b(update|modify|change|adjust)\b", "modification"),
        (r"\b(remove|delete|clean)\b", "removal"),
        (r"\b(refactor|reorganize|restructure)\b", "refactoring"),
        (r"\b(position|move|layout|align)\b", "layout change"),
        (r"\b(color|style|visual|appearance)\b", "visual change"),
        (r"\b(size|scale|dimension)\b", "size change"),
        (r"\b(animation|anim)\b", "animation change"),
        (r"\b(collider|physics|trigger)\b", "physics change"),
    ]

    for pattern, intent in intent_patterns:
        if re.search(pattern, desc_lower):
            return intent

    first_line = description.strip().split("\n")[0]
    return first_line[:50] + "..." if len(first_line) > 50 else first_line


def analyze_context(
    conflict: ConflictFile,
    adapter: VCSAdapter,
    cwd: Path | None = None,
) -> ModificationContext:
    """Analyze the modification context from VCS history."""
    context = ModificationContext(file_path=conflict.local_path)

    # Get our change info
    if conflict.ours_ref and conflict.ours_ref not in ("local", "HEAD"):
        context.ours_change = adapter.get_change_info(conflict.ours_ref, cwd)
    elif adapter.get_vcs_type() == VCSType.GIT:
        context.ours_change = adapter.get_change_info("HEAD", cwd)

    # Get their change info
    if conflict.theirs_ref:
        if adapter.get_vcs_type() == VCSType.GIT:
            context.theirs_change = adapter.get_change_info("MERGE_HEAD", cwd)
        else:
            # For Perforce, extract changelist from theirs_ref
            match = re.search(r"#(\d+)", conflict.theirs_ref)
            if match:
                # Would need to get changelist from filelog - simplified here
                pass

    # Extract objects and intent
    if context.ours_change:
        context.ours_objects = extract_object_names(context.ours_change.description)
        context.ours_intent = infer_intent(context.ours_change.description)

    if context.theirs_change:
        context.theirs_objects = extract_object_names(context.theirs_change.description)
        context.theirs_intent = infer_intent(context.theirs_change.description)

    return context


def resolve_unity_file(
    merge_files: MergeFiles,
    context: ModificationContext | None = None,
) -> tuple[SemanticMergeResult, list[ConflictInfo]]:
    """Resolve a Unity YAML file using semantic merge."""
    base_doc = UnityYAMLDocument.load(merge_files.base)
    ours_doc = UnityYAMLDocument.load(merge_files.ours)
    theirs_doc = UnityYAMLDocument.load(merge_files.theirs)

    merge_result = semantic_three_way_merge(base_doc, ours_doc, theirs_doc)

    conflict_infos = []
    for conflict in merge_result.property_conflicts:
        info = _build_conflict_info(conflict, context, merge_result.merged_document)
        conflict_infos.append(info)

    return merge_result, conflict_infos


def _format_value(value) -> str:
    """Format a value for display."""
    if isinstance(value, dict):
        if "x" in value and "y" in value:
            if "z" in value:
                if "w" in value:
                    return f"({value['x']}, {value['y']}, {value['z']}, {value['w']})"
                return f"({value['x']}, {value['y']}, {value['z']})"
            return f"({value['x']}, {value['y']})"
        if "r" in value and "g" in value:
            return f"rgba({value.get('r', 0)}, {value.get('g', 0)}, {value.get('b', 0)}, {value.get('a', 1)})"
        if "fileID" in value:
            return f"ref({value['fileID']})"
        return str(value)
    if isinstance(value, (list, tuple)):
        return f"[{len(value)} items]"
    if isinstance(value, str) and len(value) > 30:
        return f'"{value[:27]}..."'
    return str(value)


def _build_conflict_info(
    conflict: PropertyConflict,
    context: ModificationContext | None,
    merged_doc: UnityYAMLDocument,
) -> ConflictInfo:
    """Build extended conflict information with context."""
    go_path = conflict.game_object_name or f"Object[{conflict.file_id}]"
    component_type = conflict.class_name

    property_display = f"{conflict.property_path}"
    if conflict.ours_value is not None and conflict.theirs_value is not None:
        property_display += f": {_format_value(conflict.ours_value)} vs {_format_value(conflict.theirs_value)}"

    ours_context = ""
    theirs_context = ""
    if context:
        if context.ours_change:
            ours_context = f"{context.ours_change.identifier[:8]}: {context.ours_intent}"
        if context.theirs_change:
            theirs_context = f"{context.theirs_change.identifier[:8]}: {context.theirs_intent}"

    suggested, reason = _suggest_resolution(conflict, context)

    return ConflictInfo(
        conflict=conflict,
        game_object_path=go_path,
        component_type=component_type,
        property_display=property_display,
        ours_context=ours_context,
        theirs_context=theirs_context,
        suggested_resolution=suggested,
        suggestion_reason=reason,
    )


def _suggest_resolution(
    conflict: PropertyConflict,
    context: ModificationContext | None,
) -> tuple[ResolutionStrategy, str]:
    """Suggest a resolution based on conflict and context analysis."""
    if context:
        ours_score = _calculate_relevance_score(conflict, context, is_ours=True)
        theirs_score = _calculate_relevance_score(conflict, context, is_ours=False)

        if ours_score > theirs_score + 2:
            return ResolutionStrategy.OURS, f"Our change is more relevant (score: {ours_score} vs {theirs_score})"
        if theirs_score > ours_score + 2:
            return ResolutionStrategy.THEIRS, f"Their change is more relevant (score: {theirs_score} vs {ours_score})"

    prop_path = conflict.property_path.lower()

    if any(p in prop_path for p in ["position", "rotation", "scale", "localposition", "localrotation", "localscale"]):
        return ResolutionStrategy.MANUAL, "Transform changes require manual review"

    if "sortingorder" in prop_path or "sortinglayer" in prop_path:
        if conflict.ours_value is not None and conflict.theirs_value is not None:
            if isinstance(conflict.ours_value, (int, float)) and isinstance(conflict.theirs_value, (int, float)):
                if conflict.ours_value >= conflict.theirs_value:
                    return ResolutionStrategy.OURS, "Taking higher sorting order"
                return ResolutionStrategy.THEIRS, "Taking higher sorting order"

    if "enabled" in prop_path or "isactive" in prop_path:
        if conflict.ours_value == 1 or conflict.ours_value is True:
            return ResolutionStrategy.OURS, "Keeping object/component enabled"
        if conflict.theirs_value == 1 or conflict.theirs_value is True:
            return ResolutionStrategy.THEIRS, "Keeping object/component enabled"

    return ResolutionStrategy.MANUAL, "Overlapping changes require human decision"


def _calculate_relevance_score(
    conflict: PropertyConflict,
    context: ModificationContext,
    is_ours: bool,
) -> int:
    """Calculate how relevant a change is based on VCS context."""
    score = 0

    change = context.ours_change if is_ours else context.theirs_change
    objects = context.ours_objects if is_ours else context.theirs_objects
    intent = context.ours_intent if is_ours else context.theirs_intent

    if not change:
        return score

    if conflict.game_object_name:
        for obj_name in objects:
            if conflict.game_object_name.lower() in obj_name.lower():
                score += 3
            if obj_name.lower() in conflict.game_object_name.lower():
                score += 2

    for obj_name in objects:
        if conflict.class_name.lower() in obj_name.lower():
            score += 2

    prop_name = conflict.property_path.split(".")[-1].lower()
    if prop_name in change.description.lower():
        score += 3

    if "bug fix" in intent.lower():
        score += 2
    if "new feature" in intent.lower():
        score += 1
    if "layout" in intent.lower() and any(p in conflict.property_path.lower() for p in ["position", "size", "anchor"]):
        score += 2

    return score


def auto_resolve_where_possible(
    merge_result: SemanticMergeResult,
    conflict_infos: list[ConflictInfo],
) -> tuple[int, list[ConflictInfo]]:
    """Auto-resolve conflicts where we have high confidence."""
    resolved_count = 0
    remaining = []

    for info in conflict_infos:
        if info.suggested_resolution == ResolutionStrategy.OURS:
            if isinstance(info.conflict, PropertyConflict):
                apply_resolution(merge_result.merged_document, info.conflict, "ours")
                resolved_count += 1
        elif info.suggested_resolution == ResolutionStrategy.THEIRS:
            if isinstance(info.conflict, PropertyConflict):
                apply_resolution(merge_result.merged_document, info.conflict, "theirs")
                resolved_count += 1
        else:
            remaining.append(info)

    return resolved_count, remaining


def format_conflict_for_user(info: ConflictInfo, index: int) -> str:
    """Format a conflict for display to the user."""
    lines = [
        f"[Conflict {index}] {info.game_object_path} / {info.component_type}",
        f"  Property: {info.property_display}",
    ]

    if isinstance(info.conflict, PropertyConflict):
        lines.extend(
            [
                f"  Base:   {_format_value(info.conflict.base_value)}",
                f"  Ours:   {_format_value(info.conflict.ours_value)}",
                f"  Theirs: {_format_value(info.conflict.theirs_value)}",
            ]
        )

    if info.ours_context:
        lines.append(f"  Our change: {info.ours_context}")
    if info.theirs_context:
        lines.append(f"  Their change: {info.theirs_context}")

    if info.suggested_resolution != ResolutionStrategy.MANUAL:
        lines.append(f"  Suggestion: {info.suggested_resolution.value} - {info.suggestion_reason}")

    return "\n".join(lines)


# ============================================================================
# Main Resolution Function
# ============================================================================


def resolve_conflicts(
    cwd: Path | None = None,
    auto_resolve: bool = True,
    user_input_fn: Callable[[str, list[str]], str] | None = None,
) -> list[ResolveResult]:
    """Resolve all Unity merge conflicts in the current directory.

    Args:
        cwd: Working directory
        auto_resolve: Whether to auto-resolve when possible
        user_input_fn: Callback for user input (prompt, choices) -> choice

    Returns:
        List of ResolveResult for each file
    """
    adapter = detect_vcs(cwd)
    if adapter is None:
        return []

    conflicts = adapter.get_conflicts(cwd)
    results = []

    for conflict in conflicts:
        result = resolve_single_file(conflict, adapter, cwd, auto_resolve, user_input_fn)
        results.append(result)

        if result.success:
            adapter.mark_resolved(result.file_path, cwd)

    return results


def resolve_single_file(
    conflict: ConflictFile,
    adapter: VCSAdapter,
    cwd: Path | None = None,
    auto_resolve: bool = True,
    user_input_fn: Callable[[str, list[str]], str] | None = None,
) -> ResolveResult:
    """Resolve a single file's conflicts."""
    file_path = conflict.local_path

    merge_files = adapter.get_merge_files(conflict, cwd)
    if merge_files is None:
        return ResolveResult(
            file_path=file_path,
            success=False,
            strategy=ResolutionStrategy.SKIP,
            auto_merged_count=0,
            conflict_count=0,
            conflicts_resolved=0,
            message="Failed to get merge files from VCS",
        )

    try:
        context = analyze_context(conflict, adapter, cwd)
        merge_result, conflict_infos = resolve_unity_file(merge_files, context)

        auto_merged_count = len(merge_result.auto_merged)
        total_conflicts = len(conflict_infos)

        if not merge_result.has_conflicts:
            merge_result.merged_document.save(file_path)
            return ResolveResult(
                file_path=file_path,
                success=True,
                strategy=ResolutionStrategy.AUTO,
                auto_merged_count=auto_merged_count,
                conflict_count=0,
                conflicts_resolved=0,
                message=f"Auto-merged successfully ({auto_merged_count} changes)",
            )

        if auto_resolve:
            resolved_count, remaining = auto_resolve_where_possible(merge_result, conflict_infos)
            if not remaining:
                merge_result.merged_document.save(file_path)
                return ResolveResult(
                    file_path=file_path,
                    success=True,
                    strategy=ResolutionStrategy.AUTO,
                    auto_merged_count=auto_merged_count,
                    conflict_count=total_conflicts,
                    conflicts_resolved=resolved_count,
                    message=f"Auto-resolved all {resolved_count} conflicts",
                )
        else:
            remaining = conflict_infos
            resolved_count = 0

        if user_input_fn is None:
            merge_result.merged_document.save(file_path)
            return ResolveResult(
                file_path=file_path,
                success=False,
                strategy=ResolutionStrategy.MANUAL,
                auto_merged_count=auto_merged_count,
                conflict_count=total_conflicts,
                conflicts_resolved=resolved_count,
                message=f"{len(remaining)} conflicts require manual resolution",
            )

        # Interactive resolution
        for i, info in enumerate(remaining):
            prompt = format_conflict_for_user(info, i + 1)
            prompt += "\n\nResolve with: (o)urs, (t)heirs, (b)ase, (s)kip"

            choice = user_input_fn(prompt, ["o", "t", "b", "s"])

            if choice == "o":
                if isinstance(info.conflict, PropertyConflict):
                    apply_resolution(merge_result.merged_document, info.conflict, "ours")
                    resolved_count += 1
            elif choice == "t":
                if isinstance(info.conflict, PropertyConflict):
                    apply_resolution(merge_result.merged_document, info.conflict, "theirs")
                    resolved_count += 1
            elif choice == "b":
                if isinstance(info.conflict, PropertyConflict):
                    apply_resolution(merge_result.merged_document, info.conflict, "base")
                    resolved_count += 1

        merge_result.merged_document.save(file_path)

        return ResolveResult(
            file_path=file_path,
            success=resolved_count == total_conflicts,
            strategy=ResolutionStrategy.MANUAL,
            auto_merged_count=auto_merged_count,
            conflict_count=total_conflicts,
            conflicts_resolved=resolved_count,
            message=f"Resolved {resolved_count}/{total_conflicts} conflicts",
        )

    except Exception as e:
        return ResolveResult(
            file_path=file_path,
            success=False,
            strategy=ResolutionStrategy.SKIP,
            auto_merged_count=0,
            conflict_count=0,
            conflicts_resolved=0,
            message=f"Error: {e!s}",
        )
