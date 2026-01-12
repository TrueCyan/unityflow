"""Perforce merge conflict resolver for Unity YAML files.

Provides intelligent merge conflict resolution by:
1. Analyzing changelist descriptions for modification context
2. Using semantic 3-way merge for Unity YAML files
3. Auto-resolving non-overlapping changes
4. Presenting conflicts with context for user decision
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from unityflow.git_utils import UNITY_EXTENSIONS
from unityflow.p4_utils import (
    ChangelistInfo,
    MergeFiles,
    ResolveRecord,
    get_changelist_for_file,
    get_file_log,
    get_files_to_resolve,
    get_merge_files,
)
from unityflow.parser import UnityYAMLDocument
from unityflow.semantic_merge import (
    PropertyConflict,
    SemanticMergeResult,
    apply_resolution,
    semantic_three_way_merge,
)

if TYPE_CHECKING:
    from unityflow.semantic_merge import ObjectConflict


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
class ModificationContext:
    """Context about what was modified and why."""

    file_path: Path
    """Path to the modified file."""

    ours_changelist: ChangelistInfo | None
    """Our changelist information."""

    theirs_changelist: ChangelistInfo | None
    """Their changelist information (from integration source)."""

    ours_objects: list[str] = field(default_factory=list)
    """List of object names/paths mentioned in our changelist."""

    theirs_objects: list[str] = field(default_factory=list)
    """List of object names/paths mentioned in their changelist."""

    ours_intent: str = ""
    """Inferred intent from our changelist description."""

    theirs_intent: str = ""
    """Inferred intent from their changelist description."""


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


@dataclass
class P4ResolveSession:
    """Session for resolving Perforce merge conflicts."""

    files_to_resolve: list[ResolveRecord] = field(default_factory=list)
    """Files that need resolution."""

    results: list[ResolveResult] = field(default_factory=list)
    """Results of resolution attempts."""

    current_file_index: int = 0
    """Index of current file being resolved."""

    cwd: Path | None = None
    """Working directory."""


def analyze_modification_context(
    resolve_record: ResolveRecord,
    cwd: Path | None = None,
) -> ModificationContext:
    """Analyze the modification context from changelists.

    Args:
        resolve_record: ResolveRecord for the file
        cwd: Working directory

    Returns:
        ModificationContext with inferred information
    """
    context = ModificationContext(file_path=resolve_record.local_path)

    # Get our changelist
    context.ours_changelist = get_changelist_for_file(resolve_record.local_path, cwd)

    # Get their changelist from file log
    file_log = get_file_log(resolve_record.from_file, max_revisions=5, cwd=cwd)
    if file_log:
        # Find the revision that matches our integration
        for rev in file_log:
            if rev.revision == resolve_record.end_rev:
                context.theirs_changelist = ChangelistInfo(
                    number=rev.change,
                    user=rev.user,
                    client=rev.client,
                    date=rev.date,
                    description=rev.description,
                    status="submitted",
                )
                break

    # Extract object names from descriptions
    if context.ours_changelist:
        context.ours_objects = _extract_object_names(context.ours_changelist.description)
        context.ours_intent = _infer_intent(context.ours_changelist.description)

    if context.theirs_changelist:
        context.theirs_objects = _extract_object_names(context.theirs_changelist.description)
        context.theirs_intent = _infer_intent(context.theirs_changelist.description)

    return context


def _extract_object_names(description: str) -> list[str]:
    """Extract potential GameObject/component names from a description.

    Looks for patterns like:
    - "Player" (capitalized words)
    - "Player/Body/Hand" (path-like patterns)
    - "Transform", "SpriteRenderer" (component names)
    """
    names = []

    # Look for path-like patterns: Word/Word/Word
    path_pattern = r"\b([A-Z][a-zA-Z0-9]*(?:/[A-Z][a-zA-Z0-9]*)+)\b"
    paths = re.findall(path_pattern, description)
    names.extend(paths)

    # Look for quoted strings
    quoted_pattern = r'"([^"]+)"|\'([^\']+)\''
    quoted = re.findall(quoted_pattern, description)
    for q1, q2 in quoted:
        if q1:
            names.append(q1)
        if q2:
            names.append(q2)

    # Look for common Unity component types
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


def _infer_intent(description: str) -> str:
    """Infer the intent/purpose from a changelist description.

    Returns a short summary of what the change was for.
    """
    desc_lower = description.lower()

    # Check for common patterns
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

    # Default: use first line as summary
    first_line = description.strip().split("\n")[0]
    return first_line[:50] + "..." if len(first_line) > 50 else first_line


def resolve_unity_file(
    merge_files: MergeFiles,
    context: ModificationContext | None = None,
) -> tuple[SemanticMergeResult, list[ConflictInfo]]:
    """Resolve a Unity YAML file using semantic merge.

    Args:
        merge_files: Base, ours, theirs, and result paths
        context: Optional modification context

    Returns:
        Tuple of (SemanticMergeResult, list of ConflictInfo with context)
    """
    # Load documents
    base_doc = UnityYAMLDocument.load(merge_files.base)
    ours_doc = UnityYAMLDocument.load(merge_files.yours)
    theirs_doc = UnityYAMLDocument.load(merge_files.theirs)

    # Perform semantic merge
    merge_result = semantic_three_way_merge(base_doc, ours_doc, theirs_doc)

    # Build conflict info with context
    conflict_infos = []
    for conflict in merge_result.property_conflicts:
        info = _build_conflict_info(conflict, context, merge_result.merged_document)
        conflict_infos.append(info)

    return merge_result, conflict_infos


def _build_conflict_info(
    conflict: PropertyConflict,
    context: ModificationContext | None,
    merged_doc: UnityYAMLDocument,
) -> ConflictInfo:
    """Build extended conflict information with context."""
    # Get GameObject path
    go_path = conflict.game_object_name or f"Object[{conflict.file_id}]"

    # Get component type
    component_type = conflict.class_name

    # Build property display
    property_display = f"{conflict.property_path}"
    if conflict.ours_value is not None and conflict.theirs_value is not None:
        property_display += f": {_format_value(conflict.ours_value)} vs {_format_value(conflict.theirs_value)}"

    # Build context strings
    ours_context = ""
    theirs_context = ""
    if context:
        if context.ours_changelist:
            ours_context = f"CL#{context.ours_changelist.number}: {context.ours_intent}"
        if context.theirs_changelist:
            theirs_context = f"CL#{context.theirs_changelist.number}: {context.theirs_intent}"

    # Determine suggested resolution
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


def _suggest_resolution(
    conflict: PropertyConflict,
    context: ModificationContext | None,
) -> tuple[ResolutionStrategy, str]:
    """Suggest a resolution based on conflict and context analysis.

    Returns:
        Tuple of (suggested strategy, reason for suggestion)
    """
    # Check if one side is clearly more important based on context
    if context:
        ours_score = _calculate_relevance_score(conflict, context, is_ours=True)
        theirs_score = _calculate_relevance_score(conflict, context, is_ours=False)

        if ours_score > theirs_score + 2:
            return ResolutionStrategy.OURS, f"Our change is more relevant (score: {ours_score} vs {theirs_score})"
        if theirs_score > ours_score + 2:
            return ResolutionStrategy.THEIRS, f"Their change is more relevant (score: {theirs_score} vs {ours_score})"

    # Check for specific property types that have common resolution patterns
    prop_path = conflict.property_path.lower()

    # Transform properties - usually keep the newer one
    if any(p in prop_path for p in ["position", "rotation", "scale", "localposition", "localrotation", "localscale"]):
        return ResolutionStrategy.MANUAL, "Transform changes require manual review"

    # Sorting index - can often take the higher value
    if "sortingorder" in prop_path or "sortinglayer" in prop_path:
        if conflict.ours_value is not None and conflict.theirs_value is not None:
            if isinstance(conflict.ours_value, (int, float)) and isinstance(conflict.theirs_value, (int, float)):
                if conflict.ours_value >= conflict.theirs_value:
                    return ResolutionStrategy.OURS, "Taking higher sorting order"
                return ResolutionStrategy.THEIRS, "Taking higher sorting order"

    # Enabled/Active flags - usually keep enabled
    if "enabled" in prop_path or "isactive" in prop_path:
        if conflict.ours_value == 1 or conflict.ours_value is True:
            return ResolutionStrategy.OURS, "Keeping object/component enabled"
        if conflict.theirs_value == 1 or conflict.theirs_value is True:
            return ResolutionStrategy.THEIRS, "Keeping object/component enabled"

    # Default: manual resolution required
    return ResolutionStrategy.MANUAL, "Overlapping changes require human decision"


def _calculate_relevance_score(
    conflict: PropertyConflict,
    context: ModificationContext,
    is_ours: bool,
) -> int:
    """Calculate how relevant a change is based on changelist context.

    Higher score means more relevant/intentional change.
    """
    score = 0

    changelist = context.ours_changelist if is_ours else context.theirs_changelist
    objects = context.ours_objects if is_ours else context.theirs_objects
    intent = context.ours_intent if is_ours else context.theirs_intent

    if not changelist:
        return score

    # Check if the affected object is mentioned in the changelist
    if conflict.game_object_name:
        for obj_name in objects:
            if conflict.game_object_name.lower() in obj_name.lower():
                score += 3
            if obj_name.lower() in conflict.game_object_name.lower():
                score += 2

    # Check if the component type is mentioned
    for obj_name in objects:
        if conflict.class_name.lower() in obj_name.lower():
            score += 2

    # Check if the property is mentioned
    prop_name = conflict.property_path.split(".")[-1].lower()
    if prop_name in changelist.description.lower():
        score += 3

    # Check intent relevance
    if "bug fix" in intent.lower():
        score += 2  # Bug fixes are usually important
    if "new feature" in intent.lower():
        score += 1
    if "layout" in intent.lower() and any(p in conflict.property_path.lower() for p in ["position", "size", "anchor"]):
        score += 2

    return score


def auto_resolve_where_possible(
    merge_result: SemanticMergeResult,
    conflict_infos: list[ConflictInfo],
) -> tuple[int, list[ConflictInfo]]:
    """Auto-resolve conflicts where we have high confidence.

    Args:
        merge_result: The semantic merge result
        conflict_infos: List of conflict info with suggestions

    Returns:
        Tuple of (number resolved, remaining conflicts)
    """
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
    """Format a conflict for display to the user.

    Args:
        info: ConflictInfo to display
        index: 1-based index for display

    Returns:
        Formatted string for terminal display
    """
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


def get_unity_files_to_resolve(cwd: Path | None = None) -> list[ResolveRecord]:
    """Get Unity YAML files that need resolution.

    Args:
        cwd: Working directory

    Returns:
        List of ResolveRecord for Unity files only
    """
    all_files = get_files_to_resolve(cwd)
    unity_files = []

    for record in all_files:
        suffix = record.local_path.suffix.lower()
        if suffix in UNITY_EXTENSIONS:
            unity_files.append(record)

    return unity_files


def create_resolve_session(cwd: Path | None = None) -> P4ResolveSession:
    """Create a new resolve session.

    Args:
        cwd: Working directory

    Returns:
        P4ResolveSession ready for interactive resolution
    """
    session = P4ResolveSession(cwd=cwd)
    session.files_to_resolve = get_unity_files_to_resolve(cwd)
    return session


def resolve_file_in_session(
    session: P4ResolveSession,
    resolve_record: ResolveRecord,
    user_input_fn: Callable[[str, list[str]], str] | None = None,
    auto_resolve: bool = True,
) -> ResolveResult:
    """Resolve a single file in the session.

    Args:
        session: The resolve session
        resolve_record: The file to resolve
        user_input_fn: Optional callback for user input (prompt, choices) -> choice
        auto_resolve: Whether to auto-resolve when possible

    Returns:
        ResolveResult for this file
    """
    file_path = resolve_record.local_path

    # Get merge files
    merge_files = get_merge_files(resolve_record, session.cwd)
    if merge_files is None:
        return ResolveResult(
            file_path=file_path,
            success=False,
            strategy=ResolutionStrategy.SKIP,
            auto_merged_count=0,
            conflict_count=0,
            conflicts_resolved=0,
            message="Failed to get merge files from Perforce",
        )

    try:
        # Analyze context
        context = analyze_modification_context(resolve_record, session.cwd)

        # Perform semantic merge
        merge_result, conflict_infos = resolve_unity_file(merge_files, context)

        auto_merged_count = len(merge_result.auto_merged)
        total_conflicts = len(conflict_infos)

        if not merge_result.has_conflicts:
            # All resolved automatically
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

        # Try auto-resolution for high-confidence conflicts
        if auto_resolve:
            resolved_count, remaining = auto_resolve_where_possible(merge_result, conflict_infos)
            if not remaining:
                # All conflicts auto-resolved
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

        # Need user input for remaining conflicts
        if user_input_fn is None:
            # No user input available, save with remaining conflicts
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
            # 's' = skip, leave as-is

        # Save the result
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
