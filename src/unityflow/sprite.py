"""Sprite Reference Utilities.

Provides utilities for working with Unity sprite references:
- Automatic fileID detection based on sprite mode
- Meta file parsing for sprite import settings
- Material reference helpers
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from unityflow.asset_tracker import META_GUID_PATTERN

# Well-known material GUIDs
KNOWN_MATERIALS = {
    # URP (Universal Render Pipeline)
    "Sprite-Lit-Default": "a97c105638bdf8b4a8650670310a4cd3",
    # Built-in render pipeline
    "Sprites-Default": "10754",  # This is a built-in material (fileID only)
}

# Built-in material fileIDs (no GUID needed)
BUILTIN_MATERIAL_FILE_IDS = {
    "Sprites-Default": 10754,
}

# Default sprite fileID for Single mode
SPRITE_SINGLE_MODE_FILE_ID = 21300000


@dataclass
class SpriteInfo:
    """Information about a sprite extracted from its meta file."""

    guid: str
    sprite_mode: int  # 1 = Single, 2 = Multiple
    sprites: list[dict[str, Any]] = field(default_factory=list)
    internal_id_table: dict[str, int] = field(default_factory=dict)

    @property
    def is_single(self) -> bool:
        """Check if sprite is in Single mode."""
        return self.sprite_mode == 1

    @property
    def is_multiple(self) -> bool:
        """Check if sprite is in Multiple mode."""
        return self.sprite_mode == 2

    def get_file_id(self, sub_sprite_name: str | None = None) -> int | None:
        """Get the fileID for referencing this sprite.

        Args:
            sub_sprite_name: For Multiple mode, the name of the specific sub-sprite.
                           If None, returns the first sprite's ID for Multiple mode.

        Returns:
            The fileID to use in the sprite reference, or None if not found.
        """
        if self.is_single:
            return SPRITE_SINGLE_MODE_FILE_ID

        if self.is_multiple:
            if sub_sprite_name:
                # Look up by name in internal ID table
                return self.internal_id_table.get(sub_sprite_name)
            elif self.sprites:
                # Return first sprite's internalID
                return self.sprites[0].get("internalID")
            elif self.internal_id_table:
                # Fallback to first entry in internal ID table
                return next(iter(self.internal_id_table.values()), None)

        return None

    def get_sprite_names(self) -> list[str]:
        """Get list of all sprite names (for Multiple mode)."""
        if self.is_single:
            return []
        return list(self.internal_id_table.keys())


@dataclass
class SpriteReference:
    """A complete sprite reference for use in prefabs."""

    file_id: int
    guid: str
    type: int = 3  # Unity reference type (3 = asset)

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity reference dictionary format."""
        return {
            "fileID": self.file_id,
            "guid": self.guid,
            "type": self.type,
        }


@dataclass
class MaterialReference:
    """A material reference for use in prefabs."""

    file_id: int
    guid: str | None = None
    type: int = 2  # Unity reference type (2 for most assets)

    def to_dict(self) -> dict[str, Any]:
        """Convert to Unity reference dictionary format."""
        ref: dict[str, Any] = {"fileID": self.file_id}
        if self.guid:
            ref["guid"] = self.guid
            ref["type"] = self.type
        return ref


def parse_sprite_meta(meta_path: Path) -> SpriteInfo | None:
    """Parse a sprite meta file to extract sprite information.

    Args:
        meta_path: Path to the .meta file

    Returns:
        SpriteInfo object or None if parsing failed
    """
    try:
        content = meta_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Extract GUID
    guid_match = META_GUID_PATTERN.search(content)
    if not guid_match:
        return None
    guid = guid_match.group(1)

    # Extract spriteMode
    sprite_mode_match = re.search(r"^\s*spriteMode:\s*(\d+)", content, re.MULTILINE)
    sprite_mode = int(sprite_mode_match.group(1)) if sprite_mode_match else 1

    sprites: list[dict[str, Any]] = []
    internal_id_table: dict[str, int] = {}

    if sprite_mode == 2:  # Multiple mode
        # Parse internalIDToNameTable for sprite name -> ID mapping
        # Format:
        # internalIDToNameTable:
        # - first:
        #     213: <internal_id>
        #   second: sprite_name
        internal_table_match = re.search(
            r"internalIDToNameTable:\s*((?:\s*-\s+first:.*?second:.*?)+)",
            content,
            re.DOTALL,
        )
        if internal_table_match:
            table_content = internal_table_match.group(1)
            # Parse each entry
            entry_pattern = re.compile(
                r"-\s+first:\s*\n\s+213:\s*(-?\d+)\s*\n\s+second:\s*(\S+)",
                re.MULTILINE,
            )
            for match in entry_pattern.finditer(table_content):
                internal_id = int(match.group(1))
                sprite_name = match.group(2).strip()
                internal_id_table[sprite_name] = internal_id
                sprites.append({"name": sprite_name, "internalID": internal_id})

        # Also try to parse spriteSheet.sprites section
        # Format:
        # spriteSheet:
        #   sprites:
        #   - name: sprite_0
        #     internalID: 123456789
        sprite_sheet_match = re.search(
            r"spriteSheet:\s*\n\s+.*?sprites:\s*((?:\s+-\s+.*?\n)+)",
            content,
            re.DOTALL,
        )
        if sprite_sheet_match and not sprites:
            sprites_content = sprite_sheet_match.group(1)
            # Parse each sprite entry
            sprite_entry_pattern = re.compile(
                r"-\s+.*?name:\s*(\S+).*?internalID:\s*(-?\d+)",
                re.DOTALL,
            )
            for match in sprite_entry_pattern.finditer(sprites_content):
                sprite_name = match.group(1).strip()
                internal_id = int(match.group(2))
                if sprite_name not in internal_id_table:
                    internal_id_table[sprite_name] = internal_id
                    sprites.append({"name": sprite_name, "internalID": internal_id})

    return SpriteInfo(
        guid=guid,
        sprite_mode=sprite_mode,
        sprites=sprites,
        internal_id_table=internal_id_table,
    )


def get_sprite_reference(
    sprite_path: Path | str,
    sub_sprite_name: str | None = None,
) -> SpriteReference | None:
    """Get a sprite reference with automatic fileID detection.

    Automatically determines the correct fileID based on the sprite's
    import mode (Single vs Multiple) by reading the .meta file.

    Args:
        sprite_path: Path to the sprite image file (e.g., "Assets/Sprites/player.png")
        sub_sprite_name: For Multiple mode sprites, the name of the specific sub-sprite.
                        If None and sprite is Multiple mode, uses the first sprite.

    Returns:
        SpriteReference with correct fileID, or None if sprite not found/invalid

    Example:
        >>> ref = get_sprite_reference("Assets/Sprites/icon.png")
        >>> print(ref.to_dict())
        {'fileID': 21300000, 'guid': 'abc123...', 'type': 3}

        >>> ref = get_sprite_reference("Assets/Sprites/atlas.png", "sprite_0")
        >>> print(ref.to_dict())
        {'fileID': 1234567890, 'guid': 'def456...', 'type': 3}
    """
    sprite_path = Path(sprite_path)
    meta_path = Path(str(sprite_path) + ".meta")

    if not meta_path.is_file():
        return None

    sprite_info = parse_sprite_meta(meta_path)
    if not sprite_info:
        return None

    file_id = sprite_info.get_file_id(sub_sprite_name)
    if file_id is None:
        return None

    return SpriteReference(
        file_id=file_id,
        guid=sprite_info.guid,
        type=3,
    )


def get_material_reference(
    material_name_or_path: str | Path,
    project_root: Path | None = None,
) -> MaterialReference | None:
    """Get a material reference for use in SpriteRenderer.

    Supports:
    - Well-known material names (e.g., "Sprite-Lit-Default")
    - Custom material paths (e.g., "Assets/Materials/Custom.mat")

    Args:
        material_name_or_path: Either a well-known material name or path to .mat file
        project_root: Unity project root (for resolving relative paths)

    Returns:
        MaterialReference or None if not found

    Example:
        >>> ref = get_material_reference("Sprite-Lit-Default")
        >>> print(ref.to_dict())
        {'fileID': 2100000, 'guid': 'a97c105638bdf8b4a8650670310a4cd3', 'type': 2}

        >>> ref = get_material_reference("Sprites-Default")  # Built-in
        >>> print(ref.to_dict())
        {'fileID': 10754}
    """
    material_str = str(material_name_or_path)

    # Check for well-known materials
    if material_str in KNOWN_MATERIALS:
        guid = KNOWN_MATERIALS[material_str]

        # Check if it's a built-in material (no GUID, just fileID)
        if material_str in BUILTIN_MATERIAL_FILE_IDS:
            return MaterialReference(
                file_id=BUILTIN_MATERIAL_FILE_IDS[material_str],
                guid=None,
            )

        # External material with GUID
        return MaterialReference(
            file_id=2100000,  # Standard material fileID
            guid=guid,
            type=2,
        )

    # Try as a path
    material_path = Path(material_str)
    if project_root and not material_path.is_absolute():
        material_path = project_root / material_path

    meta_path = Path(str(material_path) + ".meta")
    if not meta_path.is_file():
        return None

    # Extract GUID from meta file
    try:
        content = meta_path.read_text(encoding="utf-8")
        guid_match = META_GUID_PATTERN.search(content)
        if guid_match:
            return MaterialReference(
                file_id=2100000,
                guid=guid_match.group(1),
                type=2,
            )
    except OSError:
        pass

    return None


def link_sprite_to_renderer(
    doc: Any,  # UnityYAMLDocument
    component_file_id: int,
    sprite_ref: SpriteReference,
    material_ref: MaterialReference | None = None,
) -> bool:
    """Link a sprite to a SpriteRenderer component in a document.

    Args:
        doc: UnityYAMLDocument containing the SpriteRenderer
        component_file_id: fileID of the SpriteRenderer component
        sprite_ref: Sprite reference to set
        material_ref: Optional material reference to set

    Returns:
        True if successful, False if component not found
    """
    obj = doc.get_by_file_id(component_file_id)
    if not obj:
        return False

    content = obj.get_content()
    if not content:
        return False

    # Set sprite reference
    content["m_Sprite"] = sprite_ref.to_dict()

    # Set material if provided
    if material_ref:
        materials = content.get("m_Materials", [])
        if materials:
            materials[0] = material_ref.to_dict()
        else:
            content["m_Materials"] = [material_ref.to_dict()]

    return True


def get_sprite_info(sprite_path: Path | str) -> SpriteInfo | None:
    """Get detailed information about a sprite from its meta file.

    Args:
        sprite_path: Path to the sprite image file

    Returns:
        SpriteInfo with sprite mode and sub-sprite details
    """
    sprite_path = Path(sprite_path)
    meta_path = Path(str(sprite_path) + ".meta")

    if not meta_path.is_file():
        return None

    return parse_sprite_meta(meta_path)
