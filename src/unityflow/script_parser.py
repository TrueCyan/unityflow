"""C# Script Parser for Unity SerializeField extraction.

Parses C# MonoBehaviour scripts to extract serialized field names
and their declaration order. Used for proper field ordering in
prefab/scene file manipulation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from unityflow.asset_tracker import GUIDIndex, build_guid_index


@dataclass
class SerializedField:
    """Represents a serialized field in a Unity MonoBehaviour."""

    name: str
    unity_name: str  # m_FieldName format
    field_type: str
    is_public: bool = False
    has_serialize_field: bool = False
    line_number: int = 0
    former_names: list[str] = field(default_factory=list)  # FormerlySerializedAs names
    default_value: any = None  # Parsed default value for Unity serialization

    @classmethod
    def from_field_name(
        cls,
        name: str,
        field_type: str = "",
        former_names: list[str] | None = None,
        default_value: any = None,
        **kwargs,
    ) -> SerializedField:
        """Create a SerializedField with auto-generated Unity name."""
        # Unity uses m_FieldName format for serialized fields
        unity_name = f"m_{name[0].upper()}{name[1:]}" if name else ""
        return cls(
            name=name,
            unity_name=unity_name,
            field_type=field_type,
            former_names=former_names or [],
            default_value=default_value,
            **kwargs,
        )


@dataclass
class ScriptInfo:
    """Information extracted from a C# script."""

    class_name: str
    namespace: str | None = None
    base_class: str | None = None
    fields: list[SerializedField] = field(default_factory=list)
    path: Path | None = None
    guid: str | None = None

    def get_field_order(self) -> list[str]:
        """Get the list of Unity field names in declaration order."""
        return [f.unity_name for f in self.fields]

    def get_field_index(self, unity_name: str) -> int:
        """Get the index of a field by its Unity name.

        Returns -1 if not found.
        """
        for i, f in enumerate(self.fields):
            if f.unity_name == unity_name:
                return i
        return -1

    def get_valid_field_names(self) -> set[str]:
        """Get all valid field names (current names only)."""
        return {f.unity_name for f in self.fields}

    def get_rename_mapping(self) -> dict[str, str]:
        """Get mapping of old field names to new field names.

        Returns:
            Dict mapping old Unity name -> new Unity name
        """
        mapping = {}
        for f in self.fields:
            for former in f.former_names:
                mapping[former] = f.unity_name
        return mapping

    def is_obsolete_field(self, unity_name: str) -> bool:
        """Check if a field name is obsolete (not in current script).

        Note: FormerlySerializedAs names are considered obsolete.
        """
        valid_names = self.get_valid_field_names()
        return unity_name not in valid_names

    def get_missing_fields(self, existing_names: set[str]) -> list[SerializedField]:
        """Get fields that exist in script but not in the existing set.

        Args:
            existing_names: Set of field names already present

        Returns:
            List of SerializedField objects that are missing
        """
        missing = []
        for f in self.fields:
            if f.unity_name not in existing_names:
                missing.append(f)
        return missing


# Regex patterns for C# parsing
# Note: These are simplified patterns that work for common cases

# Match class declaration
CLASS_PATTERN = re.compile(
    r"(?:public\s+)?(?:partial\s+)?class\s+(\w+)" r"(?:\s*:\s*(\w+(?:\s*,\s*\w+)*))?" r"\s*\{", re.MULTILINE
)

# Match namespace declaration
NAMESPACE_PATTERN = re.compile(r"namespace\s+([\w.]+)\s*\{", re.MULTILINE)

# Match field declarations with attributes
# Captures: attributes, access_modifier, static/const/readonly, type, name, default_value
# Note: Access modifier is required to avoid matching method parameters
FIELD_PATTERN = re.compile(
    r"(?P<attrs>(?:\[\s*[\w.()=,\s\"\']+\s*\]\s*)*)"  # Attributes
    r"(?P<access>public|private|protected|internal)\s+"  # Access modifier (required)
    r"(?P<modifiers>(?:(?:static|const|readonly|volatile|new)\s+)*)"  # Other modifiers
    r"(?P<type>[\w.<>,\[\]\s?]+?)\s+"  # Type (including generics, arrays, nullable)
    r"(?P<name>\w+)\s*"  # Field name
    r"(?:=\s*(?P<default>[^;]+))?\s*;",  # Optional initializer and semicolon
    re.MULTILINE,
)

# Match SerializeField attribute
SERIALIZE_FIELD_ATTR = re.compile(r"\[\s*SerializeField\s*\]", re.IGNORECASE)

# Match NonSerialized attribute
NON_SERIALIZED_ATTR = re.compile(r"\[\s*(?:System\.)?NonSerialized\s*\]", re.IGNORECASE)

# Match HideInInspector attribute (still serialized, just hidden)
HIDE_IN_INSPECTOR_ATTR = re.compile(r"\[\s*HideInInspector\s*\]", re.IGNORECASE)

# Match FormerlySerializedAs attribute - captures the old field name
# Example: [FormerlySerializedAs("oldName")] or [UnityEngine.Serialization.FormerlySerializedAs("oldName")]
FORMERLY_SERIALIZED_AS_ATTR = re.compile(
    r"\[\s*(?:UnityEngine\.Serialization\.)?FormerlySerializedAs\s*\(\s*\"(\w+)\"\s*\)\s*\]", re.IGNORECASE
)


def _parse_default_value(value_str: str | None, field_type: str) -> any:
    """Parse a C# default value string into a Unity-compatible Python value.

    Args:
        value_str: The default value string from C# code (e.g., "100", "5.5f", '"hello"')
        field_type: The C# type name

    Returns:
        Python value suitable for Unity YAML serialization, or None if cannot parse
    """
    if value_str is None:
        # Return type-appropriate default for common types
        return _get_type_default(field_type)

    value_str = value_str.strip()

    # Handle null/default
    if value_str in ("null", "default"):
        return _get_type_default(field_type)

    # Handle boolean
    if value_str == "true":
        return 1  # Unity uses 1 for true
    if value_str == "false":
        return 0  # Unity uses 0 for false

    # Handle string literals
    if value_str.startswith('"') and value_str.endswith('"'):
        return value_str[1:-1]  # Remove quotes

    # Handle character literals
    if value_str.startswith("'") and value_str.endswith("'"):
        return value_str[1:-1]

    # Handle float/double (remove suffix)
    if value_str.endswith("f") or value_str.endswith("F"):
        try:
            return float(value_str[:-1])
        except ValueError:
            pass
    if value_str.endswith("d") or value_str.endswith("D"):
        try:
            return float(value_str[:-1])
        except ValueError:
            pass

    # Handle integer (remove suffix)
    int_suffixes = ["u", "U", "l", "L", "ul", "UL", "lu", "LU"]
    for suffix in int_suffixes:
        if value_str.endswith(suffix):
            value_str = value_str[: -len(suffix)]
            break

    # Try integer
    try:
        return int(value_str)
    except ValueError:
        pass

    # Try float
    try:
        return float(value_str)
    except ValueError:
        pass

    # Handle Vector2/Vector3/Vector4 constructors
    # new Vector3(1, 2, 3) or Vector3.zero etc.
    vector_match = re.match(r"new\s+(Vector[234]|Quaternion|Color)\s*\(\s*([^)]*)\s*\)", value_str, re.IGNORECASE)
    if vector_match:
        vec_type = vector_match.group(1).lower()
        args_str = vector_match.group(2)
        return _parse_vector_args(vec_type, args_str)

    # Handle static members like Vector3.zero, Color.white
    static_match = re.match(r"(Vector[234]|Quaternion|Color)\.(\w+)", value_str, re.IGNORECASE)
    if static_match:
        type_name = static_match.group(1).lower()
        member = static_match.group(2).lower()
        return _get_static_member_value(type_name, member)

    # Cannot parse - return type default
    return _get_type_default(field_type)


def _parse_vector_args(vec_type: str, args_str: str) -> dict | None:
    """Parse vector constructor arguments."""
    if not args_str.strip():
        return _get_type_default(vec_type)

    # Split by comma and parse each value
    parts = [p.strip() for p in args_str.split(",")]

    try:
        values = []
        for p in parts:
            # Remove float suffix
            if p.endswith("f") or p.endswith("F"):
                p = p[:-1]
            values.append(float(p))
    except ValueError:
        return _get_type_default(vec_type)

    if vec_type == "vector2" and len(values) >= 2:
        return {"x": values[0], "y": values[1]}
    elif vec_type == "vector3" and len(values) >= 3:
        return {"x": values[0], "y": values[1], "z": values[2]}
    elif vec_type == "vector4" and len(values) >= 4:
        return {"x": values[0], "y": values[1], "z": values[2], "w": values[3]}
    elif vec_type == "quaternion" and len(values) >= 4:
        return {"x": values[0], "y": values[1], "z": values[2], "w": values[3]}
    elif vec_type == "color" and len(values) >= 3:
        r, g, b = values[0], values[1], values[2]
        a = values[3] if len(values) >= 4 else 1.0
        return {"r": r, "g": g, "b": b, "a": a}

    return _get_type_default(vec_type)


def _get_static_member_value(type_name: str, member: str) -> dict | None:
    """Get value for static members like Vector3.zero, Color.white."""
    static_values = {
        "vector2": {
            "zero": {"x": 0, "y": 0},
            "one": {"x": 1, "y": 1},
            "up": {"x": 0, "y": 1},
            "down": {"x": 0, "y": -1},
            "left": {"x": -1, "y": 0},
            "right": {"x": 1, "y": 0},
        },
        "vector3": {
            "zero": {"x": 0, "y": 0, "z": 0},
            "one": {"x": 1, "y": 1, "z": 1},
            "up": {"x": 0, "y": 1, "z": 0},
            "down": {"x": 0, "y": -1, "z": 0},
            "left": {"x": -1, "y": 0, "z": 0},
            "right": {"x": 1, "y": 0, "z": 0},
            "forward": {"x": 0, "y": 0, "z": 1},
            "back": {"x": 0, "y": 0, "z": -1},
        },
        "vector4": {
            "zero": {"x": 0, "y": 0, "z": 0, "w": 0},
            "one": {"x": 1, "y": 1, "z": 1, "w": 1},
        },
        "quaternion": {
            "identity": {"x": 0, "y": 0, "z": 0, "w": 1},
        },
        "color": {
            "white": {"r": 1, "g": 1, "b": 1, "a": 1},
            "black": {"r": 0, "g": 0, "b": 0, "a": 1},
            "red": {"r": 1, "g": 0, "b": 0, "a": 1},
            "green": {"r": 0, "g": 1, "b": 0, "a": 1},
            "blue": {"r": 0, "g": 0, "b": 1, "a": 1},
            "yellow": {"r": 1, "g": 0.92156863, "b": 0.015686275, "a": 1},
            "cyan": {"r": 0, "g": 1, "b": 1, "a": 1},
            "magenta": {"r": 1, "g": 0, "b": 1, "a": 1},
            "gray": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1},
            "grey": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1},
            "clear": {"r": 0, "g": 0, "b": 0, "a": 0},
        },
    }

    type_values = static_values.get(type_name, {})
    return type_values.get(member, _get_type_default(type_name))


def _get_type_default(field_type: str) -> any:
    """Get the default value for a Unity field type."""
    if field_type is None:
        return None

    type_lower = field_type.lower().strip()

    # Remove nullable marker
    if type_lower.endswith("?"):
        type_lower = type_lower[:-1]

    # Primitives
    if type_lower in ("int", "int32", "uint", "uint32", "short", "ushort", "long", "ulong", "byte", "sbyte"):
        return 0
    if type_lower in ("float", "single", "double"):
        return 0.0
    if type_lower in ("bool", "boolean"):
        return 0  # Unity uses 0 for false
    if type_lower in ("string",):
        return ""
    if type_lower in ("char",):
        return ""

    # Unity types
    if type_lower == "vector2":
        return {"x": 0, "y": 0}
    if type_lower == "vector3":
        return {"x": 0, "y": 0, "z": 0}
    if type_lower == "vector4":
        return {"x": 0, "y": 0, "z": 0, "w": 0}
    if type_lower == "quaternion":
        return {"x": 0, "y": 0, "z": 0, "w": 1}
    if type_lower == "color":
        return {"r": 0, "g": 0, "b": 0, "a": 1}
    if type_lower == "color32":
        return {"r": 0, "g": 0, "b": 0, "a": 255}
    if type_lower == "rect":
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    if type_lower == "bounds":
        return {"m_Center": {"x": 0, "y": 0, "z": 0}, "m_Extent": {"x": 0, "y": 0, "z": 0}}

    # Reference types - use Unity's null reference format
    # For GameObject, Component, etc. references, use fileID: 0
    if _is_reference_type(type_lower):
        return {"fileID": 0}

    # Arrays/Lists - empty array
    if type_lower.endswith("[]") or type_lower.startswith("list<"):
        return []

    # Unknown type - return None (will be skipped)
    return None


def _is_reference_type(type_name: str) -> bool:
    """Check if a type is a Unity reference type."""
    reference_types = {
        "gameobject",
        "transform",
        "component",
        "monobehaviour",
        "rigidbody",
        "rigidbody2d",
        "collider",
        "collider2d",
        "renderer",
        "spriterenderer",
        "meshrenderer",
        "animator",
        "animation",
        "audioSource",
        "camera",
        "light",
        "sprite",
        "texture",
        "texture2d",
        "material",
        "mesh",
        "scriptableobject",
        "object",
    }
    return type_name.lower() in reference_types


def parse_script(content: str, path: Path | None = None) -> ScriptInfo | None:
    """Parse a C# script and extract serialized field information.

    Args:
        content: The C# script content
        path: Optional path to the script file

    Returns:
        ScriptInfo object with extracted information, or None if parsing fails
    """
    # Remove comments to avoid false matches
    content = _remove_comments(content)

    # Find namespace
    namespace_match = NAMESPACE_PATTERN.search(content)
    namespace = namespace_match.group(1) if namespace_match else None

    # Find class declaration
    class_match = CLASS_PATTERN.search(content)
    if not class_match:
        return None

    class_name = class_match.group(1)
    base_class = class_match.group(2).split(",")[0].strip() if class_match.group(2) else None

    # Check if it's a MonoBehaviour or ScriptableObject
    is_unity_class = _is_unity_serializable_class(base_class, content)

    info = ScriptInfo(
        class_name=class_name,
        namespace=namespace,
        base_class=base_class,
        path=path,
    )

    if not is_unity_class:
        # Not a Unity serializable class, but we can still try to extract fields
        # for [System.Serializable] classes used as nested types
        pass

    # Find class body
    class_start = class_match.end()
    class_body = _extract_class_body(content, class_start)

    if class_body is None:
        return info

    # Extract fields
    for match in FIELD_PATTERN.finditer(class_body):
        attrs = match.group("attrs") or ""
        access = match.group("access") or "private"
        modifiers = match.group("modifiers") or ""
        field_type = match.group("type").strip()
        field_name = match.group("name")
        default_str = match.group("default")  # May be None

        # Skip static, const, readonly fields
        if any(mod in modifiers.lower() for mod in ["static", "const", "readonly"]):
            continue

        # Skip non-serialized fields
        if NON_SERIALIZED_ATTR.search(attrs):
            continue

        # Determine if field is serialized
        is_public = access == "public"
        has_serialize_field = bool(SERIALIZE_FIELD_ATTR.search(attrs))

        # In Unity, fields are serialized if:
        # - Public (and not NonSerialized)
        # - Private/Protected with [SerializeField]
        if is_public or has_serialize_field:
            # Calculate line number
            line_num = content[: class_start + match.start()].count("\n") + 1

            # Extract FormerlySerializedAs names
            former_names = FORMERLY_SERIALIZED_AS_ATTR.findall(attrs)

            # Parse default value
            default_value = _parse_default_value(default_str, field_type)

            info.fields.append(
                SerializedField.from_field_name(
                    name=field_name,
                    field_type=field_type,
                    former_names=former_names,
                    default_value=default_value,
                    is_public=is_public,
                    has_serialize_field=has_serialize_field,
                    line_number=line_num,
                )
            )

    return info


def parse_script_file(path: Path) -> ScriptInfo | None:
    """Parse a C# script file.

    Args:
        path: Path to the .cs file

    Returns:
        ScriptInfo object or None if parsing fails
    """
    try:
        content = path.read_text(encoding="utf-8-sig")  # Handle BOM
        info = parse_script(content, path)
        return info
    except (OSError, UnicodeDecodeError):
        return None


def get_script_field_order(
    script_guid: str,
    guid_index: GUIDIndex | None = None,
    project_root: Path | None = None,
) -> list[str] | None:
    """Get the field order for a script by its GUID.

    Args:
        script_guid: The GUID of the script asset
        guid_index: Optional pre-built GUID index
        project_root: Optional project root (for building index)

    Returns:
        List of Unity field names (m_FieldName format) in declaration order,
        or None if script cannot be found or parsed
    """
    if not script_guid:
        return None

    # Build index if not provided
    if guid_index is None:
        if project_root is None:
            return None
        guid_index = build_guid_index(project_root)

    # Find script path
    script_path = guid_index.get_path(script_guid)
    if script_path is None:
        return None

    # Resolve to absolute path
    if guid_index.project_root and not script_path.is_absolute():
        script_path = guid_index.project_root / script_path

    # Check if it's a C# script
    if script_path.suffix.lower() != ".cs":
        return None

    # Parse script
    info = parse_script_file(script_path)
    if info is None:
        return None

    return info.get_field_order()


def reorder_fields(
    fields: dict[str, any],
    field_order: list[str],
    unity_fields_first: bool = True,
) -> dict[str, any]:
    """Reorder dictionary fields according to the script field order.

    Args:
        fields: Dictionary of field name -> value
        field_order: List of field names in desired order
        unity_fields_first: If True, keep Unity standard fields first

    Returns:
        New dictionary with reordered fields
    """
    # Unity standard fields that should always come first
    unity_standard_fields = [
        "m_ObjectHideFlags",
        "m_CorrespondingSourceObject",
        "m_PrefabInstance",
        "m_PrefabAsset",
        "m_GameObject",
        "m_Enabled",
        "m_EditorHideFlags",
        "m_Script",
        "m_Name",
        "m_EditorClassIdentifier",
    ]

    result = {}

    # Add Unity standard fields first (if present)
    if unity_fields_first:
        for key in unity_standard_fields:
            if key in fields:
                result[key] = fields[key]

    # Add fields in script order
    for key in field_order:
        if key in fields and key not in result:
            result[key] = fields[key]

    # Add any remaining fields (not in order list)
    for key in fields:
        if key not in result:
            result[key] = fields[key]

    return result


def _remove_comments(content: str) -> str:
    """Remove C# comments from source code."""
    # Remove multi-line comments
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    # Remove single-line comments
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    return content


def _extract_class_body(content: str, start_pos: int) -> str | None:
    """Extract the body of a class from the opening brace.

    Args:
        content: Full source content
        start_pos: Position after the opening brace

    Returns:
        The class body content, or None if parsing fails
    """
    # We start just after the opening brace of the class
    # Need to find the matching closing brace
    depth = 1
    pos = start_pos

    while pos < len(content) and depth > 0:
        char = content[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        pos += 1

    if depth != 0:
        return None

    return content[start_pos : pos - 1]


def _is_unity_serializable_class(base_class: str | None, content: str) -> bool:
    """Check if a class is a Unity serializable class.

    Args:
        base_class: The base class name (if any)
        content: Full source content for checking using statements

    Returns:
        True if this appears to be a Unity MonoBehaviour, ScriptableObject, etc.
    """
    unity_base_classes = {
        "MonoBehaviour",
        "ScriptableObject",
        "StateMachineBehaviour",
        "NetworkBehaviour",  # Mirror/UNET
        "SerializedObject",
    }

    if base_class and base_class in unity_base_classes:
        return True

    # Check for inheritance chain (simplified)
    # Also check for [System.Serializable] attribute on the class
    if re.search(r"\[\s*(?:System\.)?Serializable\s*\]", content):
        return True

    return base_class is not None  # Assume any class with base could be Unity class


@dataclass
class ScriptFieldCache:
    """Cache for script field order lookups."""

    _cache: dict[str, list[str] | None] = field(default_factory=dict)
    guid_index: GUIDIndex | None = None
    project_root: Path | None = None

    def get_field_order(self, script_guid: str) -> list[str] | None:
        """Get field order for a script, using cache.

        Args:
            script_guid: The script GUID

        Returns:
            List of Unity field names in order, or None if not found
        """
        if script_guid in self._cache:
            return self._cache[script_guid]

        # Build index if needed
        if self.guid_index is None and self.project_root:
            self.guid_index = build_guid_index(self.project_root)

        result = get_script_field_order(
            script_guid,
            guid_index=self.guid_index,
            project_root=self.project_root,
        )

        self._cache[script_guid] = result
        return result

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
