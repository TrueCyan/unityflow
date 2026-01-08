"""Tests for asset_resolver module."""

from pathlib import Path

import pytest

from unityflow.asset_resolver import (
    ASSET_TYPE_FILE_IDS,
    AssetType,
    AssetTypeMismatchError,
    get_asset_type_from_extension,
    get_expected_types_for_field,
    get_guid_from_meta,
    get_sprite_file_id,
    is_asset_reference,
    parse_asset_reference,
    resolve_asset_reference,
    resolve_value,
    validate_asset_type_for_field,
)


class TestIsAssetReference:
    """Tests for is_asset_reference function."""

    def test_valid_asset_reference(self):
        assert is_asset_reference("@Assets/Scripts/Player.cs") is True
        assert is_asset_reference("@Assets/Sprites/icon.png") is True
        assert is_asset_reference("@Assets/Audio/jump.wav") is True

    def test_invalid_asset_reference(self):
        assert is_asset_reference("Assets/Scripts/Player.cs") is False
        assert is_asset_reference("hello") is False
        assert is_asset_reference("") is False
        assert is_asset_reference(123) is False
        assert is_asset_reference(None) is False


class TestParseAssetReference:
    """Tests for parse_asset_reference function."""

    def test_simple_path(self):
        path, sub = parse_asset_reference("@Assets/Scripts/Player.cs")
        assert path == "Assets/Scripts/Player.cs"
        assert sub is None

    def test_path_with_sub_asset(self):
        path, sub = parse_asset_reference("@Assets/Sprites/atlas.png:idle_0")
        assert path == "Assets/Sprites/atlas.png"
        assert sub == "idle_0"

    def test_path_without_prefix(self):
        path, sub = parse_asset_reference("Assets/Scripts/Player.cs")
        assert path == "Assets/Scripts/Player.cs"
        assert sub is None

    def test_sub_sprite_with_special_chars(self):
        path, sub = parse_asset_reference("@Assets/Sprites/atlas.png:player_idle_frame_0")
        assert path == "Assets/Sprites/atlas.png"
        assert sub == "player_idle_frame_0"


class TestResolveValue:
    """Tests for resolve_value function."""

    def test_non_asset_string(self):
        result = resolve_value("hello")
        assert result == "hello"

    def test_number(self):
        result = resolve_value(42)
        assert result == 42

    def test_dict_without_asset_refs(self):
        value = {"x": 1, "y": 2, "z": 3}
        result = resolve_value(value)
        assert result == {"x": 1, "y": 2, "z": 3}

    def test_list_without_asset_refs(self):
        value = [1, 2, 3]
        result = resolve_value(value)
        assert result == [1, 2, 3]

    def test_nested_dict_without_asset_refs(self):
        value = {"pos": {"x": 0, "y": 5}, "name": "Player"}
        result = resolve_value(value)
        assert result == {"pos": {"x": 0, "y": 5}, "name": "Player"}

    def test_unresolvable_asset_reference_raises(self):
        with pytest.raises(ValueError, match="Could not resolve asset reference"):
            resolve_value("@Assets/NonExistent/File.cs")


class TestAssetTypeFileIds:
    """Tests for ASSET_TYPE_FILE_IDS mapping."""

    def test_script_file_id(self):
        assert ASSET_TYPE_FILE_IDS[".cs"] == 11500000

    def test_audio_file_ids(self):
        assert ASSET_TYPE_FILE_IDS[".wav"] == 8300000
        assert ASSET_TYPE_FILE_IDS[".mp3"] == 8300000
        assert ASSET_TYPE_FILE_IDS[".ogg"] == 8300000

    def test_material_file_id(self):
        assert ASSET_TYPE_FILE_IDS[".mat"] == 2100000

    def test_sprite_file_id(self):
        assert ASSET_TYPE_FILE_IDS[".png"] == 21300000

    def test_scriptable_object_file_id(self):
        assert ASSET_TYPE_FILE_IDS[".asset"] == 11400000


class TestGetGuidFromMeta:
    """Tests for get_guid_from_meta function."""

    def test_nonexistent_file(self, tmp_path):
        meta_path = tmp_path / "nonexistent.meta"
        assert get_guid_from_meta(meta_path) is None

    def test_valid_meta_file(self, tmp_path):
        meta_path = tmp_path / "test.cs.meta"
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n"
            "MonoImporter:\n"
            "  serializedVersion: 2\n"
        )
        guid = get_guid_from_meta(meta_path)
        assert guid == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"

    def test_meta_without_guid(self, tmp_path):
        meta_path = tmp_path / "test.cs.meta"
        meta_path.write_text("fileFormatVersion: 2\n")
        assert get_guid_from_meta(meta_path) is None


class TestGetSpriteFileId:
    """Tests for get_sprite_file_id function."""

    def test_single_mode_sprite(self, tmp_path):
        meta_path = tmp_path / "icon.png.meta"
        meta_path.write_text(
            "fileFormatVersion: 2\n" "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n" "TextureImporter:\n" "  spriteMode: 1\n"
        )
        file_id = get_sprite_file_id(meta_path)
        assert file_id == 21300000

    def test_multiple_mode_sprite_first(self, tmp_path):
        meta_path = tmp_path / "atlas.png.meta"
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n"
            "TextureImporter:\n"
            "  spriteMode: 2\n"
            "  internalIDToNameTable:\n"
            "  - first:\n"
            "      213: 1234567890\n"
            "    second: idle_0\n"
            "  - first:\n"
            "      213: 9876543210\n"
            "    second: idle_1\n"
        )
        file_id = get_sprite_file_id(meta_path)
        assert file_id == 1234567890

    def test_multiple_mode_sprite_by_name(self, tmp_path):
        meta_path = tmp_path / "atlas.png.meta"
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n"
            "TextureImporter:\n"
            "  spriteMode: 2\n"
            "  internalIDToNameTable:\n"
            "  - first:\n"
            "      213: 1234567890\n"
            "    second: idle_0\n"
            "  - first:\n"
            "      213: 9876543210\n"
            "    second: idle_1\n"
        )
        file_id = get_sprite_file_id(meta_path, "idle_1")
        assert file_id == 9876543210

    def test_multiple_mode_sprite_name_not_found(self, tmp_path):
        meta_path = tmp_path / "atlas.png.meta"
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n"
            "TextureImporter:\n"
            "  spriteMode: 2\n"
            "  internalIDToNameTable:\n"
            "  - first:\n"
            "      213: 1234567890\n"
            "    second: idle_0\n"
        )
        file_id = get_sprite_file_id(meta_path, "nonexistent")
        assert file_id is None

    def test_nonexistent_file(self, tmp_path):
        meta_path = tmp_path / "nonexistent.png.meta"
        assert get_sprite_file_id(meta_path) is None


class TestResolveAssetReferenceIntegration:
    """Integration tests for asset reference resolution."""

    def test_resolve_script_reference(self, tmp_path):
        # Create script and meta file
        script_path = tmp_path / "Assets" / "Scripts" / "Player.cs"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("public class Player : MonoBehaviour {}")

        meta_path = Path(str(script_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: abcdef1234567890abcdef1234567890\n"
            "MonoImporter:\n"
            "  serializedVersion: 2\n"
        )

        result = resolve_value("@Assets/Scripts/Player.cs", tmp_path)
        assert result == {
            "fileID": 11500000,
            "guid": "abcdef1234567890abcdef1234567890",
            "type": 3,
        }

    def test_resolve_sprite_reference(self, tmp_path):
        # Create sprite and meta file
        sprite_path = tmp_path / "Assets" / "Sprites" / "icon.png"
        sprite_path.parent.mkdir(parents=True)
        sprite_path.write_bytes(b"PNG")

        meta_path = Path(str(sprite_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n" "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n" "TextureImporter:\n" "  spriteMode: 1\n"
        )

        result = resolve_value("@Assets/Sprites/icon.png", tmp_path)
        assert result == {
            "fileID": 21300000,
            "guid": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "type": 3,
        }

    def test_resolve_audio_reference(self, tmp_path):
        # Create audio and meta file
        audio_path = tmp_path / "Assets" / "Audio" / "jump.wav"
        audio_path.parent.mkdir(parents=True)
        audio_path.write_bytes(b"RIFF")

        meta_path = Path(str(audio_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5\n"
            "AudioImporter:\n"
            "  serializedVersion: 6\n"
        )

        result = resolve_value("@Assets/Audio/jump.wav", tmp_path)
        assert result == {
            "fileID": 8300000,
            "guid": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
            "type": 3,
        }

    def test_resolve_batch_with_mixed_values(self, tmp_path):
        # Create script and meta file
        script_path = tmp_path / "Assets" / "Scripts" / "Enemy.cs"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("public class Enemy : MonoBehaviour {}")

        meta_path = Path(str(script_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6\n"
            "MonoImporter:\n"
            "  serializedVersion: 2\n"
        )

        batch = {
            "enemyScript": "@Assets/Scripts/Enemy.cs",
            "spawnRate": 2.5,
            "maxEnemies": 10,
        }

        result = resolve_value(batch, tmp_path)
        assert result == {
            "enemyScript": {
                "fileID": 11500000,
                "guid": "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
                "type": 3,
            },
            "spawnRate": 2.5,
            "maxEnemies": 10,
        }

    def test_resolve_sub_sprite_reference(self, tmp_path):
        # Create atlas sprite and meta file
        sprite_path = tmp_path / "Assets" / "Sprites" / "atlas.png"
        sprite_path.parent.mkdir(parents=True)
        sprite_path.write_bytes(b"PNG")

        meta_path = Path(str(sprite_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1\n"
            "TextureImporter:\n"
            "  spriteMode: 2\n"
            "  internalIDToNameTable:\n"
            "  - first:\n"
            "      213: 1111111111\n"
            "    second: walk_0\n"
            "  - first:\n"
            "      213: 2222222222\n"
            "    second: walk_1\n"
        )

        result = resolve_value("@Assets/Sprites/atlas.png:walk_1", tmp_path)
        assert result == {
            "fileID": 2222222222,
            "guid": "d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1",
            "type": 3,
        }


class TestAssetTypeFromExtension:
    """Tests for get_asset_type_from_extension function."""

    def test_sprite_extensions(self):
        assert get_asset_type_from_extension(".png") == AssetType.SPRITE
        assert get_asset_type_from_extension(".jpg") == AssetType.SPRITE
        assert get_asset_type_from_extension("png") == AssetType.SPRITE

    def test_audio_extensions(self):
        assert get_asset_type_from_extension(".wav") == AssetType.AUDIO_CLIP
        assert get_asset_type_from_extension(".mp3") == AssetType.AUDIO_CLIP

    def test_prefab_extension(self):
        assert get_asset_type_from_extension(".prefab") == AssetType.PREFAB

    def test_script_extension(self):
        assert get_asset_type_from_extension(".cs") == AssetType.SCRIPT

    def test_unknown_extension(self):
        assert get_asset_type_from_extension(".xyz") == AssetType.UNKNOWN


class TestExpectedTypesForField:
    """Tests for get_expected_types_for_field function."""

    def test_sprite_fields(self):
        assert AssetType.SPRITE in get_expected_types_for_field("m_Sprite")
        assert AssetType.SPRITE in get_expected_types_for_field("playerSprite")
        assert AssetType.SPRITE in get_expected_types_for_field("icon_sprite")

    def test_audio_fields(self):
        assert AssetType.AUDIO_CLIP in get_expected_types_for_field("audioClip")
        assert AssetType.AUDIO_CLIP in get_expected_types_for_field("jumpSound")
        assert AssetType.AUDIO_CLIP in get_expected_types_for_field("bgMusic")

    def test_prefab_fields(self):
        assert AssetType.PREFAB in get_expected_types_for_field("enemyPrefab")
        assert AssetType.PREFAB in get_expected_types_for_field("playerPrefab")

    def test_material_fields(self):
        assert AssetType.MATERIAL in get_expected_types_for_field("m_Material")
        assert AssetType.MATERIAL in get_expected_types_for_field("m_Materials")

    def test_script_fields(self):
        assert AssetType.SCRIPT in get_expected_types_for_field("m_Script")

    def test_unknown_fields(self):
        assert get_expected_types_for_field("someRandomField") is None
        assert get_expected_types_for_field("health") is None


class TestValidateAssetTypeForField:
    """Tests for validate_asset_type_for_field function."""

    def test_valid_sprite_for_sprite_field(self):
        # Should not raise
        validate_asset_type_for_field("m_Sprite", "Assets/icon.png", AssetType.SPRITE)

    def test_valid_audio_for_audio_field(self):
        # Should not raise
        validate_asset_type_for_field("audioClip", "Assets/sound.wav", AssetType.AUDIO_CLIP)

    def test_invalid_audio_for_sprite_field(self):
        with pytest.raises(AssetTypeMismatchError) as exc_info:
            validate_asset_type_for_field("m_Sprite", "Assets/sound.wav", AssetType.AUDIO_CLIP)
        assert "m_Sprite" in str(exc_info.value)
        assert "Sprite" in str(exc_info.value)
        assert "AudioClip" in str(exc_info.value)

    def test_invalid_sprite_for_audio_field(self):
        with pytest.raises(AssetTypeMismatchError) as exc_info:
            validate_asset_type_for_field("audioClip", "Assets/icon.png", AssetType.SPRITE)
        assert "audioClip" in str(exc_info.value)
        assert "AudioClip" in str(exc_info.value)
        assert "Sprite" in str(exc_info.value)

    def test_unknown_field_allows_anything(self):
        # Unknown fields should allow any type
        validate_asset_type_for_field("customField", "Assets/icon.png", AssetType.SPRITE)
        validate_asset_type_for_field("customField", "Assets/sound.wav", AssetType.AUDIO_CLIP)

    def test_texture_and_sprite_interchangeable(self):
        # Sprite should be allowed where Texture is expected
        validate_asset_type_for_field("m_Texture", "Assets/icon.png", AssetType.SPRITE)


class TestResolveValueWithTypeValidation:
    """Tests for resolve_value with type validation."""

    def test_valid_type_match(self, tmp_path):
        # Create sprite and meta file
        sprite_path = tmp_path / "Assets" / "Sprites" / "icon.png"
        sprite_path.parent.mkdir(parents=True)
        sprite_path.write_bytes(b"PNG")

        meta_path = Path(str(sprite_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n" "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n" "TextureImporter:\n" "  spriteMode: 1\n"
        )

        # Should succeed - sprite for m_Sprite field
        result = resolve_value("@Assets/Sprites/icon.png", tmp_path, field_name="m_Sprite")
        assert result["fileID"] == 21300000

    def test_type_mismatch_raises_error(self, tmp_path):
        # Create audio and meta file
        audio_path = tmp_path / "Assets" / "Audio" / "jump.wav"
        audio_path.parent.mkdir(parents=True)
        audio_path.write_bytes(b"RIFF")

        meta_path = Path(str(audio_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5\n"
            "AudioImporter:\n"
            "  serializedVersion: 6\n"
        )

        # Should fail - audio for m_Sprite field
        with pytest.raises(AssetTypeMismatchError) as exc_info:
            resolve_value("@Assets/Audio/jump.wav", tmp_path, field_name="m_Sprite")
        assert "m_Sprite" in str(exc_info.value)
        assert "Sprite" in str(exc_info.value)
        assert "AudioClip" in str(exc_info.value)

    def test_batch_mode_validates_each_field(self, tmp_path):
        # Create sprite and meta file
        sprite_path = tmp_path / "Assets" / "Sprites" / "icon.png"
        sprite_path.parent.mkdir(parents=True)
        sprite_path.write_bytes(b"PNG")

        meta_path = Path(str(sprite_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n" "guid: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n" "TextureImporter:\n" "  spriteMode: 1\n"
        )

        # Should fail - sprite for audioClip field in batch mode
        batch = {
            "audioClip": "@Assets/Sprites/icon.png",  # Wrong type!
        }
        with pytest.raises(AssetTypeMismatchError) as exc_info:
            resolve_value(batch, tmp_path)
        assert "audioClip" in str(exc_info.value)

    def test_unknown_field_allows_any_type(self, tmp_path):
        # Create audio and meta file
        audio_path = tmp_path / "Assets" / "Audio" / "jump.wav"
        audio_path.parent.mkdir(parents=True)
        audio_path.write_bytes(b"RIFF")

        meta_path = Path(str(audio_path) + ".meta")
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5\n"
            "AudioImporter:\n"
            "  serializedVersion: 6\n"
        )

        # Should succeed - unknown field allows any type
        result = resolve_value("@Assets/Audio/jump.wav", tmp_path, field_name="customRef")
        assert result["fileID"] == 8300000


class TestAutoGenerateMeta:
    """Tests for auto-generating .meta files when resolving asset references."""

    def test_auto_generate_meta_for_script(self, tmp_path):
        """Test that .meta file is auto-generated for a script without one."""
        # Create script file WITHOUT meta
        script_path = tmp_path / "Assets" / "Scripts" / "Player.cs"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("public class Player : MonoBehaviour {}")

        # Verify no meta exists
        meta_path = Path(str(script_path) + ".meta")
        assert not meta_path.exists()

        # Resolve should auto-generate meta
        result = resolve_asset_reference("@Assets/Scripts/Player.cs", tmp_path)

        # Meta should now exist
        assert meta_path.exists()
        assert result is not None
        assert result.file_id == 11500000  # Script fileID
        assert len(result.guid) == 32  # Valid GUID

    def test_auto_generate_meta_for_texture(self, tmp_path):
        """Test that .meta file is auto-generated for a texture without one."""
        # Create texture file WITHOUT meta
        texture_path = tmp_path / "Assets" / "Textures" / "icon.png"
        texture_path.parent.mkdir(parents=True)
        texture_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG header

        # Resolve should auto-generate meta
        result = resolve_asset_reference("@Assets/Textures/icon.png", tmp_path)

        # Meta should now exist
        meta_path = Path(str(texture_path) + ".meta")
        assert meta_path.exists()
        assert result is not None
        assert len(result.guid) == 32

    def test_auto_generate_disabled(self, tmp_path):
        """Test that auto-generate can be disabled."""
        # Create script file WITHOUT meta
        script_path = tmp_path / "Assets" / "Scripts" / "Player.cs"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("public class Player : MonoBehaviour {}")

        # Resolve with auto_generate_meta=False should return None
        result = resolve_asset_reference(
            "@Assets/Scripts/Player.cs",
            tmp_path,
            auto_generate_meta=False,
        )

        # Should fail - no meta generated
        assert result is None
        meta_path = Path(str(script_path) + ".meta")
        assert not meta_path.exists()

    def test_no_auto_generate_for_missing_file(self, tmp_path):
        """Test that no meta is generated if the asset file doesn't exist."""
        # Don't create the script file
        result = resolve_asset_reference("@Assets/Scripts/NonExistent.cs", tmp_path)

        # Should fail - file doesn't exist
        assert result is None

    def test_resolve_value_auto_generates_meta(self, tmp_path):
        """Test that resolve_value also auto-generates meta files."""
        # Create script file WITHOUT meta
        script_path = tmp_path / "Assets" / "Scripts" / "Enemy.cs"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("public class Enemy : MonoBehaviour {}")

        # resolve_value should work and auto-generate meta
        result = resolve_value("@Assets/Scripts/Enemy.cs", tmp_path)

        # Should succeed
        assert isinstance(result, dict)
        assert result["fileID"] == 11500000
        assert "guid" in result

        # Meta should exist
        meta_path = Path(str(script_path) + ".meta")
        assert meta_path.exists()
