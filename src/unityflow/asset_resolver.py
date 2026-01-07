"""Asset Reference Resolver.

Provides utilities for resolving asset paths to Unity references with
automatic GUID and fileID detection.

Usage:
    # In values, use @ prefix to reference assets
    "@Assets/Scripts/Player.cs"           -> Script reference
    "@Assets/Sprites/icon.png"            -> Sprite reference (Single mode)
    "@Assets/Sprites/atlas.png:idle_0"    -> Sprite sub-sprite (Multiple mode)
    "@Assets/Audio/jump.wav"              -> AudioClip reference
    "@Assets/Prefabs/Enemy.prefab"        -> Prefab reference
    "@Assets/Materials/Custom.mat"        -> Material reference
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from unityflow.asset_tracker import META_GUID_PATTERN


class AssetType(Enum):
    """Unity asset types for type validation."""

    SPRITE = "Sprite"
    TEXTURE = "Texture2D"
    AUDIO_CLIP = "AudioClip"
    MATERIAL = "Material"
    PREFAB = "Prefab"
    SCRIPT = "Script"
    SCRIPTABLE_OBJECT = "ScriptableObject"
    ANIMATION_CLIP = "AnimationClip"
    ANIMATOR_CONTROLLER = "AnimatorController"
    FONT = "Font"
    SHADER = "Shader"
    TEXT_ASSET = "TextAsset"
    VIDEO_CLIP = "VideoClip"
    MODEL = "Model"
    UNKNOWN = "Unknown"


# Extension to asset type mapping
EXTENSION_TO_ASSET_TYPE: dict[str, AssetType] = {
    # Sprites/Textures (images are typically used as sprites in 2D)
    ".png": AssetType.SPRITE,
    ".jpg": AssetType.SPRITE,
    ".jpeg": AssetType.SPRITE,
    ".tga": AssetType.SPRITE,
    ".psd": AssetType.SPRITE,
    ".tiff": AssetType.SPRITE,
    ".gif": AssetType.SPRITE,
    ".bmp": AssetType.SPRITE,
    ".exr": AssetType.TEXTURE,  # HDR textures
    ".hdr": AssetType.TEXTURE,
    # Audio
    ".wav": AssetType.AUDIO_CLIP,
    ".mp3": AssetType.AUDIO_CLIP,
    ".ogg": AssetType.AUDIO_CLIP,
    ".aiff": AssetType.AUDIO_CLIP,
    ".aif": AssetType.AUDIO_CLIP,
    ".flac": AssetType.AUDIO_CLIP,
    # Materials
    ".mat": AssetType.MATERIAL,
    # Scripts
    ".cs": AssetType.SCRIPT,
    # Prefabs
    ".prefab": AssetType.PREFAB,
    # ScriptableObjects
    ".asset": AssetType.SCRIPTABLE_OBJECT,
    # Animations
    ".anim": AssetType.ANIMATION_CLIP,
    ".controller": AssetType.ANIMATOR_CONTROLLER,
    # Fonts
    ".ttf": AssetType.FONT,
    ".otf": AssetType.FONT,
    ".fon": AssetType.FONT,
    # Shaders
    ".shader": AssetType.SHADER,
    ".shadergraph": AssetType.SHADER,
    # Text/Data
    ".txt": AssetType.TEXT_ASSET,
    ".json": AssetType.TEXT_ASSET,
    ".xml": AssetType.TEXT_ASSET,
    ".bytes": AssetType.TEXT_ASSET,
    ".csv": AssetType.TEXT_ASSET,
    # Models
    ".fbx": AssetType.MODEL,
    ".obj": AssetType.MODEL,
    ".blend": AssetType.MODEL,
    # Video
    ".mp4": AssetType.VIDEO_CLIP,
    ".webm": AssetType.VIDEO_CLIP,
    ".mov": AssetType.VIDEO_CLIP,
}


# Field name patterns to expected asset types
# Patterns are checked in order, first match wins
FIELD_NAME_TO_EXPECTED_TYPES: list[tuple[re.Pattern, list[AssetType]]] = [
    # Sprite fields (including camelCase like playerSprite)
    (re.compile(r"(?i)(^|_)sprite($|s$|_)|[a-z]Sprite(s)?$"), [AssetType.SPRITE]),
    (re.compile(r"^m_Sprite$"), [AssetType.SPRITE]),
    # Audio fields
    (re.compile(r"(?i)(audio|sound|clip|music|sfx)"), [AssetType.AUDIO_CLIP]),
    (re.compile(r"^m_audioClip$", re.IGNORECASE), [AssetType.AUDIO_CLIP]),
    # Material fields
    (re.compile(r"(?i)(^|_)material($|s$|_)"), [AssetType.MATERIAL]),
    (re.compile(r"^m_Material"), [AssetType.MATERIAL]),
    (re.compile(r"^m_Materials"), [AssetType.MATERIAL]),
    # Prefab fields
    (re.compile(r"(?i)prefab"), [AssetType.PREFAB]),
    # Script fields
    (re.compile(r"^m_Script$"), [AssetType.SCRIPT]),
    # Animator fields
    (re.compile(r"(?i)(animator|controller)"), [AssetType.ANIMATOR_CONTROLLER]),
    (re.compile(r"^m_Controller$"), [AssetType.ANIMATOR_CONTROLLER]),
    # Animation fields
    (re.compile(r"(?i)(anim|animation)(?!.*controller)"), [AssetType.ANIMATION_CLIP]),
    # Font fields
    (re.compile(r"(?i)font"), [AssetType.FONT]),
    # Texture fields (general textures, not sprites)
    (re.compile(r"(?i)texture"), [AssetType.TEXTURE, AssetType.SPRITE]),
    (re.compile(r"^m_Texture"), [AssetType.TEXTURE, AssetType.SPRITE]),
    # Mesh/Model fields
    (re.compile(r"(?i)(mesh|model)"), [AssetType.MODEL]),
    # Video fields
    (re.compile(r"(?i)video"), [AssetType.VIDEO_CLIP]),
    # ScriptableObject fields (generic data references)
    (re.compile(r"(?i)(data|config|settings|so$)"), [AssetType.SCRIPTABLE_OBJECT]),
]


class AssetTypeMismatchError(ValueError):
    """Error raised when asset type doesn't match expected field type."""

    def __init__(
        self,
        field_name: str,
        asset_path: str,
        expected_types: list[AssetType],
        actual_type: AssetType,
    ):
        self.field_name = field_name
        self.asset_path = asset_path
        self.expected_types = expected_types
        self.actual_type = actual_type
        expected_str = ", ".join(t.value for t in expected_types)
        super().__init__(
            f"Type mismatch for field '{field_name}': "
            f"expected {expected_str}, but '{asset_path}' is {actual_type.value}"
        )


def get_asset_type_from_extension(extension: str) -> AssetType:
    """Get the asset type from a file extension.

    Args:
        extension: File extension (with or without leading dot)

    Returns:
        AssetType for the extension
    """
    ext = extension.lower()
    if not ext.startswith("."):
        ext = "." + ext
    return EXTENSION_TO_ASSET_TYPE.get(ext, AssetType.UNKNOWN)


def get_expected_types_for_field(field_name: str) -> list[AssetType] | None:
    """Get expected asset types for a field name.

    Args:
        field_name: The field name (e.g., 'm_Sprite', 'audioClip', 'enemyPrefab')

    Returns:
        List of acceptable AssetTypes, or None if no expectation
    """
    for pattern, types in FIELD_NAME_TO_EXPECTED_TYPES:
        if pattern.search(field_name):
            return types
    return None


def validate_asset_type_for_field(
    field_name: str,
    asset_path: str,
    asset_type: AssetType,
) -> None:
    """Validate that an asset type is compatible with a field.

    Args:
        field_name: The field name being set
        asset_path: The asset path (for error messages)
        asset_type: The actual asset type

    Raises:
        AssetTypeMismatchError: If the type doesn't match expectations
    """
    expected_types = get_expected_types_for_field(field_name)

    if expected_types is None:
        # No expectation for this field, allow anything
        return

    if asset_type in expected_types:
        return

    # Special case: SPRITE can be used where TEXTURE is expected
    if asset_type == AssetType.SPRITE and AssetType.TEXTURE in expected_types:
        return

    # Special case: TEXTURE can be used where SPRITE is expected
    if asset_type == AssetType.TEXTURE and AssetType.SPRITE in expected_types:
        return

    raise AssetTypeMismatchError(
        field_name=field_name,
        asset_path=asset_path,
        expected_types=expected_types,
        actual_type=asset_type,
    )


# Standard fileIDs for different asset types
ASSET_TYPE_FILE_IDS: dict[str, int] = {
    # Scripts
    ".cs": 11500000,
    # Textures/Sprites
    ".png": 21300000,  # Sprite (Single mode default)
    ".jpg": 21300000,
    ".jpeg": 21300000,
    ".tga": 21300000,
    ".psd": 21300000,
    ".tiff": 21300000,
    ".gif": 21300000,
    ".bmp": 21300000,
    ".exr": 21300000,
    ".hdr": 21300000,
    # Audio
    ".wav": 8300000,
    ".mp3": 8300000,
    ".ogg": 8300000,
    ".aiff": 8300000,
    ".aif": 8300000,
    ".flac": 8300000,
    # Materials
    ".mat": 2100000,
    # Animations
    ".anim": 7400000,
    ".controller": 9100000,
    # Fonts
    ".ttf": 12800000,
    ".otf": 12800000,
    ".fon": 12800000,
    # Shaders
    ".shader": 4800000,
    ".shadergraph": 11400000,
    # ScriptableObjects
    ".asset": 11400000,
    # Text/Data
    ".txt": 4900000,
    ".json": 4900000,
    ".xml": 4900000,
    ".bytes": 4900000,
    ".csv": 4900000,
    # Models (main mesh)
    ".fbx": 10000,  # Mesh fileID varies, but ~100000 for main mesh
    ".obj": 10000,
    ".blend": 10000,
    # Video
    ".mp4": 32900000,
    ".webm": 32900000,
    ".mov": 32900000,
    # Prefabs - need special handling
    ".prefab": None,  # Requires parsing the prefab
}

# Reference type values
REF_TYPE_ASSET = 3  # External asset
REF_TYPE_BUILTIN = 2  # Built-in or internal


@dataclass
class AssetResolveResult:
    """Result of resolving an asset path to a Unity reference."""

    file_id: int
    guid: str
    ref_type: int = REF_TYPE_ASSET
    asset_path: str | None = None
    sub_asset: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity reference dictionary format."""
        return {
            "fileID": self.file_id,
            "guid": self.guid,
            "type": self.ref_type,
        }


def is_asset_reference(value: str) -> bool:
    """Check if a value is an asset reference (starts with @)."""
    return isinstance(value, str) and value.startswith("@")


def parse_asset_reference(value: str) -> tuple[str, str | None]:
    """Parse an asset reference into path and optional sub-asset.

    Args:
        value: Asset reference string (e.g., "@Assets/Sprites/atlas.png:idle_0")

    Returns:
        Tuple of (asset_path, sub_asset_name or None)

    Examples:
        "@Assets/Scripts/Player.cs" -> ("Assets/Scripts/Player.cs", None)
        "@Assets/Sprites/atlas.png:idle_0" -> ("Assets/Sprites/atlas.png", "idle_0")
    """
    if not value.startswith("@"):
        return value, None

    path = value[1:]  # Remove @ prefix

    # Check for sub-asset separator (:)
    if ":" in path:
        # Find the last colon that's after the file extension
        # This handles Windows paths like C:\path\file.png
        parts = path.rsplit(":", 1)
        # Verify the first part looks like a file path (has extension)
        if "." in parts[0]:
            return parts[0], parts[1]

    return path, None


def get_guid_from_meta(meta_path: Path) -> str | None:
    """Extract GUID from a .meta file.

    Args:
        meta_path: Path to the .meta file

    Returns:
        GUID string or None if not found
    """
    try:
        content = meta_path.read_text(encoding="utf-8")
        match = META_GUID_PATTERN.search(content)
        if match:
            return match.group(1)
    except OSError:
        pass
    return None


def get_sprite_file_id(meta_path: Path, sub_sprite_name: str | None = None) -> int | None:
    """Get the fileID for a sprite reference.

    Args:
        meta_path: Path to the sprite's .meta file
        sub_sprite_name: For Multiple mode, the name of the sub-sprite

    Returns:
        fileID or None if not found
    """
    try:
        content = meta_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Check sprite mode
    sprite_mode_match = re.search(r"^\s*spriteMode:\s*(\d+)", content, re.MULTILINE)
    sprite_mode = int(sprite_mode_match.group(1)) if sprite_mode_match else 1

    if sprite_mode == 1:  # Single mode
        return 21300000

    if sprite_mode == 2:  # Multiple mode
        if sub_sprite_name:
            # Look up in internalIDToNameTable
            pattern = re.compile(
                r"-\s+first:\s*\n\s+213:\s*(-?\d+)\s*\n\s+second:\s*" + re.escape(sub_sprite_name),
                re.MULTILINE,
            )
            match = pattern.search(content)
            if match:
                return int(match.group(1))

            # Also try spriteSheet.sprites section
            sprite_pattern = re.compile(
                r"name:\s*" + re.escape(sub_sprite_name) + r".*?internalID:\s*(-?\d+)",
                re.DOTALL,
            )
            match = sprite_pattern.search(content)
            if match:
                return int(match.group(1))

            return None
        else:
            # Return first sprite's ID
            pattern = re.compile(
                r"-\s+first:\s*\n\s+213:\s*(-?\d+)",
                re.MULTILINE,
            )
            match = pattern.search(content)
            if match:
                return int(match.group(1))

    return 21300000  # Fallback


def get_prefab_root_file_id(prefab_path: Path) -> int | None:
    """Get the root GameObject's fileID from a prefab.

    Args:
        prefab_path: Path to the .prefab file

    Returns:
        fileID of the root GameObject, or None if not found
    """
    try:
        content = prefab_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Find all GameObject declarations and their transforms
    # Pattern: --- !u!1 &<fileID>
    game_objects: list[int] = []
    pattern = re.compile(r"^--- !u!1 &(\d+)", re.MULTILINE)
    for match in pattern.finditer(content):
        game_objects.append(int(match.group(1)))

    if not game_objects:
        return None

    # The root is typically the first GameObject, but let's verify
    # by checking which GameObject has no parent Transform
    # For simplicity, return the first one (most prefabs have root first)
    return game_objects[0]


def resolve_asset_reference(
    value: str,
    project_root: Path | None = None,
    auto_generate_meta: bool = True,
) -> AssetResolveResult | None:
    """Resolve an asset reference to a Unity reference.

    Args:
        value: Asset reference string (e.g., "@Assets/Scripts/Player.cs")
        project_root: Unity project root for resolving relative paths
        auto_generate_meta: If True, automatically generate .meta file if missing

    Returns:
        AssetResolveResult with fileID and guid, or None if resolution failed

    Examples:
        >>> result = resolve_asset_reference("@Assets/Scripts/Player.cs", project_root)
        >>> print(result.to_dict())
        {'fileID': 11500000, 'guid': 'abc123...', 'type': 3}
    """
    import logging

    logger = logging.getLogger(__name__)

    if not is_asset_reference(value):
        return None

    asset_path, sub_asset = parse_asset_reference(value)

    # Resolve to absolute path
    if project_root:
        full_path = project_root / asset_path
    else:
        full_path = Path(asset_path)

    meta_path = Path(str(full_path) + ".meta")

    # Check if meta file exists, auto-generate if needed
    if not meta_path.is_file():
        if auto_generate_meta and full_path.is_file():
            # Auto-generate .meta file
            from unityflow.meta_generator import generate_meta_file

            try:
                generate_meta_file(full_path)
                logger.info(f"Auto-generated .meta file for: {asset_path}")
            except Exception as e:
                logger.warning(f"Failed to auto-generate .meta for {asset_path}: {e}")
                return None
        else:
            return None

    # Get GUID from meta file
    guid = get_guid_from_meta(meta_path)
    if not guid:
        return None

    # Determine fileID based on asset type
    suffix = full_path.suffix.lower()
    file_id: int | None = None

    # Special handling for sprites (check mode and sub-sprite)
    if suffix in (".png", ".jpg", ".jpeg", ".tga", ".psd", ".tiff", ".gif", ".bmp", ".exr", ".hdr"):
        file_id = get_sprite_file_id(meta_path, sub_asset)

    # Special handling for prefabs
    elif suffix == ".prefab":
        file_id = get_prefab_root_file_id(full_path)

    # Use standard fileID for known types
    elif suffix in ASSET_TYPE_FILE_IDS:
        file_id = ASSET_TYPE_FILE_IDS[suffix]

    if file_id is None:
        return None

    return AssetResolveResult(
        file_id=file_id,
        guid=guid,
        ref_type=REF_TYPE_ASSET,
        asset_path=asset_path,
        sub_asset=sub_asset,
    )


def resolve_value(
    value: Any,
    project_root: Path | None = None,
    field_name: str | None = None,
) -> Any:
    """Resolve a value, converting asset references to Unity reference dicts.

    Recursively processes dicts and lists, converting any string values
    that start with @ to asset references.

    Args:
        value: Value to process
        project_root: Unity project root for resolving relative paths
        field_name: The field name being set (for type validation)

    Returns:
        Processed value with asset references resolved

    Raises:
        ValueError: If an asset reference cannot be resolved
        AssetTypeMismatchError: If the asset type doesn't match the field type
    """
    if isinstance(value, str):
        if is_asset_reference(value):
            result = resolve_asset_reference(value, project_root)
            if result is None:
                raise ValueError(f"Could not resolve asset reference: {value}")

            # Validate asset type if field name is provided
            if field_name and result.asset_path:
                suffix = Path(result.asset_path).suffix.lower()
                asset_type = get_asset_type_from_extension(suffix)
                validate_asset_type_for_field(field_name, result.asset_path, asset_type)

            return result.to_dict()
        return value

    elif isinstance(value, dict):
        # For dicts, use the key as the field name for validation
        return {k: resolve_value(v, project_root, field_name=k) for k, v in value.items()}

    elif isinstance(value, list):
        # For lists, use the parent field name
        return [resolve_value(item, project_root, field_name) for item in value]

    return value


def get_asset_info(
    asset_path: str,
    project_root: Path | None = None,
) -> dict[str, Any] | None:
    """Get detailed information about an asset.

    Args:
        asset_path: Path to the asset (without @ prefix)
        project_root: Unity project root

    Returns:
        Dictionary with asset info, or None if not found
    """
    if project_root:
        full_path = project_root / asset_path
    else:
        full_path = Path(asset_path)

    meta_path = Path(str(full_path) + ".meta")

    if not meta_path.is_file():
        return None

    guid = get_guid_from_meta(meta_path)
    if not guid:
        return None

    suffix = full_path.suffix.lower()
    info: dict[str, Any] = {
        "path": asset_path,
        "guid": guid,
        "type": suffix[1:] if suffix else "unknown",
    }

    # Add sprite-specific info
    if suffix in (".png", ".jpg", ".jpeg", ".tga", ".psd"):
        try:
            content = meta_path.read_text(encoding="utf-8")
            mode_match = re.search(r"^\s*spriteMode:\s*(\d+)", content, re.MULTILINE)
            if mode_match:
                mode = int(mode_match.group(1))
                info["spriteMode"] = "Single" if mode == 1 else "Multiple" if mode == 2 else "None"

                if mode == 2:
                    # Extract sub-sprite names
                    sub_sprites: list[str] = []
                    pattern = re.compile(
                        r"-\s+first:\s*\n\s+213:\s*(-?\d+)\s*\n\s+second:\s*(\S+)",
                        re.MULTILINE,
                    )
                    for match in pattern.finditer(content):
                        sub_sprites.append(match.group(2))
                    info["subSprites"] = sub_sprites
        except OSError:
            pass

    return info
