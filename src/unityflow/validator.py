"""Unity Prefab Validator.

Validates Unity YAML files for structural correctness and common issues.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from unityflow.parser import CLASS_IDS, UnityYAMLDocument, UnityYAMLObject

# Valid GUID pattern: 32 hexadecimal characters
GUID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def is_valid_guid(guid: Any) -> bool:
    """Check if a value is a valid Unity GUID.

    Unity GUIDs are 32 hexadecimal characters.
    """
    if guid is None:
        return True  # No guid is valid (internal reference)
    if not isinstance(guid, str):
        return False  # GUID must be a string
    return bool(GUID_PATTERN.match(guid))


class Severity(Enum):
    """Validation issue severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation issue."""

    severity: Severity
    message: str
    file_id: int | None = None
    property_path: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}]"]
        if self.file_id is not None:
            parts.append(f"(fileID: {self.file_id})")
        parts.append(self.message)
        if self.property_path:
            parts.append(f"at {self.property_path}")
        if self.suggestion:
            parts.append(f"- {self.suggestion}")
        return " ".join(parts)


@dataclass
class ValidationResult:
    """Result of validating a Unity file."""

    path: str
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get all error-level issues."""
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get all warning-level issues."""
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> list[ValidationIssue]:
        """Get all info-level issues."""
        return [i for i in self.issues if i.severity == Severity.INFO]

    def __str__(self) -> str:
        lines = [f"Validation result for {self.path}:"]
        lines.append(f"  Status: {'VALID' if self.is_valid else 'INVALID'}")
        lines.append(f"  Errors: {len(self.errors)}, Warnings: {len(self.warnings)}, Info: {len(self.infos)}")

        if self.issues:
            lines.append("")
            for issue in self.issues:
                lines.append(f"  {issue}")

        return "\n".join(lines)


class PrefabValidator:
    """Validates Unity prefab files."""

    def __init__(
        self,
        check_references: bool = True,
        check_structure: bool = True,
        check_duplicates: bool = True,
        strict: bool = False,
    ):
        """Initialize the validator.

        Args:
            check_references: Validate internal fileID references
            check_structure: Validate document structure
            check_duplicates: Check for duplicate fileIDs
            strict: Treat warnings as errors
        """
        self.check_references = check_references
        self.check_structure = check_structure
        self.check_duplicates = check_duplicates
        self.strict = strict

    def validate_file(self, path: str | Path) -> ValidationResult:
        """Validate a Unity YAML file.

        Args:
            path: Path to the file to validate

        Returns:
            ValidationResult with any issues found
        """
        path = Path(path)
        issues: list[ValidationIssue] = []

        # Check file exists and is readable
        if not path.exists():
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"File not found: {path}",
                )
            )
            return ValidationResult(path=str(path), is_valid=False, issues=issues)

        # Try to parse the file
        try:
            doc = UnityYAMLDocument.load(path)
        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Failed to parse file: {e}",
                )
            )
            return ValidationResult(path=str(path), is_valid=False, issues=issues)

        # Run validation checks
        issues.extend(self._validate_document(doc))

        # Determine validity
        is_valid = not any(i.severity == Severity.ERROR for i in issues)
        if self.strict:
            is_valid = is_valid and not any(i.severity == Severity.WARNING for i in issues)

        return ValidationResult(path=str(path), is_valid=is_valid, issues=issues)

    def validate_content(self, content: str, label: str = "<content>") -> ValidationResult:
        """Validate Unity YAML content from a string.

        Args:
            content: The YAML content to validate
            label: Label for the content in error messages

        Returns:
            ValidationResult with any issues found
        """
        issues: list[ValidationIssue] = []

        try:
            doc = UnityYAMLDocument.parse(content)
        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Failed to parse content: {e}",
                )
            )
            return ValidationResult(path=label, is_valid=False, issues=issues)

        issues.extend(self._validate_document(doc))

        is_valid = not any(i.severity == Severity.ERROR for i in issues)
        if self.strict:
            is_valid = is_valid and not any(i.severity == Severity.WARNING for i in issues)

        return ValidationResult(path=label, is_valid=is_valid, issues=issues)

    def _validate_document(self, doc: UnityYAMLDocument) -> list[ValidationIssue]:
        """Validate a parsed document."""
        issues: list[ValidationIssue] = []

        if not doc.objects:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    message="Document contains no objects",
                )
            )
            return issues

        # Check for duplicate fileIDs
        if self.check_duplicates:
            issues.extend(self._check_duplicate_file_ids(doc))

        # Build fileID index for reference checking
        file_id_index = {obj.file_id for obj in doc.objects}

        # Validate each object
        for obj in doc.objects:
            if self.check_structure:
                issues.extend(self._validate_object_structure(obj))

            if self.check_references:
                issues.extend(self._validate_object_references(obj, file_id_index))

        # Validate SceneRoots for scene files
        if self.check_structure:
            issues.extend(self._validate_scene_roots(doc))

        return issues

    def _check_duplicate_file_ids(self, doc: UnityYAMLDocument) -> list[ValidationIssue]:
        """Check for duplicate fileIDs."""
        issues: list[ValidationIssue] = []
        seen: dict[int, int] = {}

        for i, obj in enumerate(doc.objects):
            if obj.file_id in seen:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        file_id=obj.file_id,
                        message=f"Duplicate fileID found (first at index {seen[obj.file_id]}, duplicate at index {i})",
                        suggestion="Each object must have a unique fileID",
                    )
                )
            else:
                seen[obj.file_id] = i

        return issues

    def _validate_object_structure(self, obj: UnityYAMLObject) -> list[ValidationIssue]:
        """Validate the structure of a single object."""
        issues: list[ValidationIssue] = []

        # Check for valid class ID
        if obj.class_id <= 0:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    file_id=obj.file_id,
                    message=f"Invalid class ID: {obj.class_id}",
                )
            )

        # Check for empty data
        if not obj.data:
            if not obj.stripped:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        file_id=obj.file_id,
                        message="Object has no data",
                    )
                )

        # Check root key matches expected class
        root_key = obj.root_key
        if root_key:
            expected = CLASS_IDS.get(obj.class_id)
            if expected and root_key != expected:
                msg = f"Root key '{root_key}' doesn't match expected '{expected}' for class {obj.class_id}"
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        file_id=obj.file_id,
                        message=msg,
                    )
                )

        # Validate classId matches root_key (detect mismatched classIds)
        issues.extend(self._validate_class_id_root_key_match(obj))

        # Class-specific validation
        content = obj.get_content()
        if content:
            if obj.class_id == 1:  # GameObject
                issues.extend(self._validate_game_object(obj, content))
            elif obj.class_id == 4:  # Transform
                issues.extend(self._validate_transform(obj, content))
            elif obj.class_id == 1001:  # PrefabInstance
                issues.extend(self._validate_prefab_instance(obj, content))

        return issues

    def _validate_game_object(self, obj: UnityYAMLObject, content: dict[str, Any]) -> list[ValidationIssue]:
        """Validate a GameObject object."""
        issues: list[ValidationIssue] = []

        # Check required fields
        if "m_Name" not in content:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    file_id=obj.file_id,
                    message="GameObject missing m_Name",
                    property_path="GameObject.m_Name",
                )
            )

        if "m_Component" not in content:
            issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    file_id=obj.file_id,
                    message="GameObject has no components",
                    property_path="GameObject.m_Component",
                )
            )

        return issues

    def _validate_transform(self, obj: UnityYAMLObject, content: dict[str, Any]) -> list[ValidationIssue]:
        """Validate a Transform object."""
        issues: list[ValidationIssue] = []

        # Check for required transform properties
        for prop in ["m_LocalPosition", "m_LocalRotation", "m_LocalScale"]:
            if prop not in content:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        file_id=obj.file_id,
                        message=f"Transform missing {prop}",
                        property_path=f"Transform.{prop}",
                    )
                )

        # Validate quaternion if present
        rotation = content.get("m_LocalRotation")
        if rotation and isinstance(rotation, dict):
            issues.extend(self._validate_quaternion(obj, rotation, "m_LocalRotation"))

        return issues

    def _validate_quaternion(
        self,
        obj: UnityYAMLObject,
        q: dict[str, Any],
        property_name: str,
    ) -> list[ValidationIssue]:
        """Validate a quaternion value."""
        issues: list[ValidationIssue] = []

        required = {"x", "y", "z", "w"}
        missing = required - set(q.keys())
        if missing:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    file_id=obj.file_id,
                    message=f"Quaternion missing components: {missing}",
                    property_path=property_name,
                )
            )
            return issues

        # Check for valid values
        try:
            x = float(q["x"])
            y = float(q["y"])
            z = float(q["z"])
            w = float(q["w"])

            # Check unit length (with tolerance)
            length = (x * x + y * y + z * z + w * w) ** 0.5
            if abs(length - 1.0) > 0.01:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        file_id=obj.file_id,
                        message=f"Quaternion is not normalized (length={length:.4f})",
                        property_path=property_name,
                        suggestion="Consider normalizing to unit length",
                    )
                )
        except (TypeError, ValueError) as e:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    file_id=obj.file_id,
                    message=f"Invalid quaternion values: {e}",
                    property_path=property_name,
                )
            )

        return issues

    def _validate_class_id_root_key_match(self, obj: UnityYAMLObject) -> list[ValidationIssue]:
        """Validate that classId matches the root key in the data.

        This detects cases where LLM generated incorrect classIds,
        such as using SceneRoots classId (1660057539) for Light2D.
        """
        issues: list[ValidationIssue] = []
        root_key = obj.root_key

        if not root_key:
            return issues

        # Special case: SceneRoots classId (1660057539) must have SceneRoots root key
        if obj.class_id == 1660057539 and root_key != "SceneRoots":
            msg = f"ClassID 1660057539 (SceneRoots) used for '{root_key}' - Unity will fail to cast"
            suggestion = f"'{root_key}' needs a different classId. Check Unity docs."
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    file_id=obj.file_id,
                    message=msg,
                    property_path=root_key,
                    suggestion=suggestion,
                )
            )

        # Known classId -> root_key mismatches that cause Unity errors
        known_class_ids = {
            1: "GameObject",
            4: "Transform",
            20: "Camera",
            23: "MeshRenderer",
            33: "MeshFilter",
            54: "Rigidbody",
            65: "BoxCollider",
            81: "AudioListener",
            82: "AudioSource",
            114: "MonoBehaviour",
            124: "Behaviour",
            212: "SpriteRenderer",
            222: "CanvasRenderer",
            223: "Canvas",
            224: "RectTransform",
            225: "CanvasGroup",
            1001: "PrefabInstance",
            1660057539: "SceneRoots",
        }

        expected_root_key = known_class_ids.get(obj.class_id)
        if expected_root_key and root_key != expected_root_key:
            # Only error for well-known types where mismatch is definitely wrong
            if obj.class_id in (1, 4, 224, 1001, 1660057539):  # Critical types
                msg = f"ClassID {obj.class_id} expects '{expected_root_key}' but found '{root_key}'"
                suggestion = f"Change classId to match '{root_key}' or root key to '{expected_root_key}'"
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        file_id=obj.file_id,
                        message=msg,
                        property_path=root_key,
                        suggestion=suggestion,
                    )
                )

        return issues

    def _validate_prefab_instance(self, obj: UnityYAMLObject, content: dict[str, Any]) -> list[ValidationIssue]:
        """Validate a PrefabInstance object."""
        issues: list[ValidationIssue] = []

        # Check for m_SourcePrefab
        source = content.get("m_SourcePrefab")
        if not source:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    file_id=obj.file_id,
                    message="PrefabInstance missing m_SourcePrefab",
                    property_path="PrefabInstance.m_SourcePrefab",
                )
            )
        elif isinstance(source, dict):
            if not source.get("guid"):
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        file_id=obj.file_id,
                        message="m_SourcePrefab has no GUID",
                        property_path="PrefabInstance.m_SourcePrefab.guid",
                        suggestion="Prefab reference may be broken",
                    )
                )

        return issues

    def _validate_object_references(
        self,
        obj: UnityYAMLObject,
        file_id_index: set[int],
    ) -> list[ValidationIssue]:
        """Validate fileID references within an object."""
        issues: list[ValidationIssue] = []

        def check_reference(value: Any, path: str) -> None:
            if isinstance(value, dict):
                # Check if this is a file reference
                if "fileID" in value:
                    file_id = value.get("fileID")
                    guid = value.get("guid")
                    ref_type = value.get("type")

                    # Check GUID format if present
                    if guid is not None and not is_valid_guid(guid):
                        issues.append(
                            ValidationIssue(
                                severity=Severity.ERROR,
                                file_id=obj.file_id,
                                message=f"Invalid GUID format: {guid!r} (expected 32 hex chars or None)",
                                property_path=path,
                                suggestion="GUID must be a 32 character hexadecimal string",
                            )
                        )

                    # Check reference validity based on type
                    if file_id and file_id != 0:
                        is_internal_ref = not guid or ref_type == 0

                        if is_internal_ref:
                            # Internal reference - must exist in current file
                            if file_id not in file_id_index:
                                # Unity builtin assets use special fileIDs (typically < 100000)
                                # with type: 0 or type: 3, but should have a valid guid
                                if ref_type == 0 and not guid:
                                    msg = f"Broken ref: fileID {file_id} with type:0 not in file"
                                    sug = "Builtin assets need guid. Ensure target exists."
                                    issues.append(
                                        ValidationIssue(
                                            severity=Severity.ERROR,
                                            file_id=obj.file_id,
                                            message=msg,
                                            property_path=path,
                                            suggestion=sug,
                                        )
                                    )
                                else:
                                    msg = f"Internal ref to non-existent fileID: {file_id}"
                                    sug = "Reference may be broken or external"
                                    issues.append(
                                        ValidationIssue(
                                            severity=Severity.WARNING,
                                            file_id=obj.file_id,
                                            message=msg,
                                            property_path=path,
                                            suggestion=sug,
                                        )
                                    )

                # Recurse into dict values
                for key, val in value.items():
                    check_reference(val, f"{path}.{key}")

            elif isinstance(value, list):
                for i, item in enumerate(value):
                    check_reference(item, f"{path}[{i}]")

        if obj.data:
            check_reference(obj.data, obj.root_key or "root")

        return issues

    def _validate_scene_roots(
        self,
        doc: UnityYAMLDocument,
    ) -> list[ValidationIssue]:
        """Validate SceneRoots object for scene files."""
        issues: list[ValidationIssue] = []

        # Find SceneRoots object (class_id 1660057539)
        scene_roots_obj = None
        for obj in doc.objects:
            if obj.class_id == 1660057539:
                content = obj.get_content()
                if content and "m_Roots" in content:
                    scene_roots_obj = obj
                    break

        if scene_roots_obj is None:
            return issues  # Not a scene file or no SceneRoots

        # Find all root transforms (transforms with no parent)
        root_transform_ids: set[int] = set()
        for obj in doc.objects:
            if obj.class_id == 4:  # Transform
                content = obj.get_content()
                if content:
                    father = content.get("m_Father", {})
                    father_id = father.get("fileID", 0) if isinstance(father, dict) else 0
                    if father_id == 0:
                        root_transform_ids.add(obj.file_id)
            elif obj.class_id == 224:  # RectTransform
                content = obj.get_content()
                if content:
                    father = content.get("m_Father", {})
                    father_id = father.get("fileID", 0) if isinstance(father, dict) else 0
                    if father_id == 0:
                        root_transform_ids.add(obj.file_id)

        # Check SceneRoots m_Roots
        content = scene_roots_obj.get_content()
        roots_list = content.get("m_Roots", [])
        scene_root_ids: set[int] = set()
        for root in roots_list:
            if isinstance(root, dict):
                file_id = root.get("fileID", 0)
                if file_id:
                    scene_root_ids.add(file_id)

        # Check for missing roots
        missing_roots = root_transform_ids - scene_root_ids
        if missing_roots:
            count = len(missing_roots)
            msg = f"SceneRoots missing {count} root transform(s): {sorted(missing_roots)}"
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    file_id=scene_roots_obj.file_id,
                    message=msg,
                    property_path="SceneRoots.m_Roots",
                    suggestion="Use fix_scene_roots() to automatically fix this issue",
                )
            )

        # Check for invalid roots (pointing to non-existent transforms)
        invalid_roots = scene_root_ids - root_transform_ids
        for invalid_id in invalid_roots:
            if invalid_id != 0:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        file_id=scene_roots_obj.file_id,
                        message=f"SceneRoots references non-root transform: {invalid_id}",
                        property_path="SceneRoots.m_Roots",
                    )
                )

        return issues


def validate_prefab(
    path: str | Path,
    strict: bool = False,
) -> ValidationResult:
    """Convenience function to validate a prefab file.

    Args:
        path: Path to the prefab file
        strict: Treat warnings as errors

    Returns:
        ValidationResult
    """
    validator = PrefabValidator(strict=strict)
    return validator.validate_file(path)


def fix_invalid_guids(doc: UnityYAMLDocument) -> int:
    """Fix invalid GUID values in a document.

    Removes invalid GUID fields (like guid: 0.0) from references.
    For builtin Unity resources (fileID < 100000), guid is not required.

    Args:
        doc: The UnityYAMLDocument to fix

    Returns:
        Number of invalid GUIDs fixed
    """
    fixed_count = 0

    def fix_value(value: Any) -> Any:
        nonlocal fixed_count
        if isinstance(value, dict):
            # Check if this is a file reference with invalid guid
            if "fileID" in value and "guid" in value:
                guid = value.get("guid")
                if not is_valid_guid(guid):
                    # Remove invalid guid
                    del value["guid"]
                    fixed_count += 1
            # Recurse into dict values
            for key in list(value.keys()):
                value[key] = fix_value(value[key])
            return value
        elif isinstance(value, list):
            return [fix_value(item) for item in value]
        else:
            return value

    for obj in doc.objects:
        if obj.data:
            obj.data = fix_value(obj.data)

    return fixed_count


def fix_scene_roots(doc: UnityYAMLDocument) -> bool:
    """Fix SceneRoots object to include all root transforms.

    Finds all Transform/RectTransform objects with no parent and updates
    the SceneRoots.m_Roots list to include them all.

    Args:
        doc: The UnityYAMLDocument to fix

    Returns:
        True if SceneRoots was fixed, False if no fix was needed
    """
    # Find SceneRoots object (class_id 1660057539)
    scene_roots_obj = None
    for obj in doc.objects:
        if obj.class_id == 1660057539:
            content = obj.get_content()
            if content and "m_Roots" in content:
                scene_roots_obj = obj
                break

    if scene_roots_obj is None:
        return False  # Not a scene file or no SceneRoots

    # Find all root transforms (transforms with no parent)
    root_transform_ids: list[int] = []
    for obj in doc.objects:
        if obj.class_id in (4, 224):  # Transform or RectTransform
            content = obj.get_content()
            if content:
                father = content.get("m_Father", {})
                father_id = father.get("fileID", 0) if isinstance(father, dict) else 0
                if father_id == 0:
                    root_transform_ids.append(obj.file_id)

    # Sort for consistent output
    root_transform_ids.sort()

    # Get current roots
    content = scene_roots_obj.get_content()
    current_roots = content.get("m_Roots", [])
    current_root_ids: set[int] = set()
    for root in current_roots:
        if isinstance(root, dict):
            file_id = root.get("fileID", 0)
            if file_id:
                current_root_ids.add(file_id)

    # Check if fix is needed
    if set(root_transform_ids) == current_root_ids:
        return False  # No fix needed

    # Update m_Roots
    content["m_Roots"] = [{"fileID": fid} for fid in root_transform_ids]

    return True


def fix_document(doc: UnityYAMLDocument) -> dict[str, int]:
    """Apply all automatic fixes to a document.

    Args:
        doc: The UnityYAMLDocument to fix

    Returns:
        Dictionary with counts of each type of fix applied
    """
    results = {
        "invalid_guids_fixed": fix_invalid_guids(doc),
        "scene_roots_fixed": 1 if fix_scene_roots(doc) else 0,
    }
    return results
