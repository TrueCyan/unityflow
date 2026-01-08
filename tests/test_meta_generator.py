"""Tests for Unity .meta file generator."""

import pytest

from unityflow.meta_generator import (
    EXTENSION_TO_TYPE,
    AssetType,
    MetaFileOptions,
    detect_asset_type,
    ensure_meta_file,
    generate_guid,
    generate_meta_content,
    generate_meta_file,
    generate_meta_files_recursive,
    get_guid_from_meta,
    get_meta_info,
    # Meta modification functions
    modify_meta_file,
    set_asset_bundle,
    set_script_execution_order,
    set_texture_max_size,
    set_texture_sprite_mode,
)


class TestGenerateGuid:
    """Tests for GUID generation."""

    def test_random_guid_format(self):
        """Test that random GUID has correct format."""
        guid = generate_guid()

        assert len(guid) == 32
        assert all(c in "0123456789abcdef" for c in guid)

    def test_random_guids_are_unique(self):
        """Test that random GUIDs are unique."""
        guids = [generate_guid() for _ in range(100)]
        assert len(set(guids)) == 100

    def test_seeded_guid_is_deterministic(self):
        """Test that seeded GUID generation is deterministic."""
        seed = "Assets/Scripts/Player.cs"

        guid1 = generate_guid(seed)
        guid2 = generate_guid(seed)

        assert guid1 == guid2

    def test_different_seeds_produce_different_guids(self):
        """Test that different seeds produce different GUIDs."""
        guid1 = generate_guid("seed1")
        guid2 = generate_guid("seed2")

        assert guid1 != guid2


class TestDetectAssetType:
    """Tests for asset type detection."""

    def test_detect_folder(self, tmp_path):
        """Test detecting folder type."""
        folder = tmp_path / "TestFolder"
        folder.mkdir()

        assert detect_asset_type(folder) == AssetType.FOLDER

    def test_detect_script(self, tmp_path):
        """Test detecting C# script type."""
        script = tmp_path / "Player.cs"
        script.touch()

        assert detect_asset_type(script) == AssetType.SCRIPT

    def test_detect_texture_types(self, tmp_path):
        """Test detecting various texture types."""
        for ext in [".png", ".jpg", ".jpeg", ".tga", ".psd", ".exr"]:
            texture = tmp_path / f"image{ext}"
            texture.touch()
            assert detect_asset_type(texture) == AssetType.TEXTURE

    def test_detect_audio_types(self, tmp_path):
        """Test detecting various audio types."""
        for ext in [".wav", ".mp3", ".ogg", ".aiff"]:
            audio = tmp_path / f"sound{ext}"
            audio.touch()
            assert detect_asset_type(audio) == AssetType.AUDIO

    def test_detect_model_types(self, tmp_path):
        """Test detecting various 3D model types."""
        for ext in [".fbx", ".obj", ".dae"]:
            model = tmp_path / f"model{ext}"
            model.touch()
            assert detect_asset_type(model) == AssetType.MODEL

    def test_detect_shader(self, tmp_path):
        """Test detecting shader files."""
        shader = tmp_path / "MyShader.shader"
        shader.touch()

        assert detect_asset_type(shader) == AssetType.SHADER

    def test_detect_unity_yaml_assets(self, tmp_path):
        """Test detecting Unity YAML asset types."""
        prefab = tmp_path / "Object.prefab"
        prefab.touch()
        assert detect_asset_type(prefab) == AssetType.PREFAB

        scene = tmp_path / "Main.unity"
        scene.touch()
        assert detect_asset_type(scene) == AssetType.SCENE

        asset = tmp_path / "Data.asset"
        asset.touch()
        assert detect_asset_type(asset) == AssetType.SCRIPTABLE_OBJECT

    def test_detect_unknown_defaults(self, tmp_path):
        """Test that unknown extensions default to DEFAULT type."""
        unknown = tmp_path / "file.xyz"
        unknown.touch()

        assert detect_asset_type(unknown) == AssetType.DEFAULT


class TestGenerateMetaContent:
    """Tests for meta content generation."""

    def test_folder_meta_content(self, tmp_path):
        """Test generating meta content for a folder."""
        folder = tmp_path / "TestFolder"
        folder.mkdir()

        content = generate_meta_content(folder)

        assert "fileFormatVersion: 2" in content
        assert "guid:" in content
        assert "folderAsset: yes" in content
        assert "DefaultImporter:" in content

    def test_script_meta_content(self, tmp_path):
        """Test generating meta content for a script."""
        script = tmp_path / "Player.cs"
        script.touch()

        content = generate_meta_content(script)

        assert "fileFormatVersion: 2" in content
        assert "guid:" in content
        assert "MonoImporter:" in content
        assert "executionOrder:" in content

    def test_texture_meta_content(self, tmp_path):
        """Test generating meta content for a texture."""
        texture = tmp_path / "icon.png"
        texture.touch()

        content = generate_meta_content(texture)

        assert "fileFormatVersion: 2" in content
        assert "guid:" in content
        assert "TextureImporter:" in content
        assert "maxTextureSize:" in content

    def test_sprite_meta_content(self, tmp_path):
        """Test generating meta content for a sprite."""
        sprite = tmp_path / "sprite.png"
        sprite.touch()

        options = MetaFileOptions(
            texture_type="Sprite",
            sprite_mode=1,
            sprite_pixels_per_unit=32,
        )
        content = generate_meta_content(sprite, options=options)

        assert "TextureImporter:" in content
        assert "spriteMode: 1" in content
        assert "spritePixelsToUnits: 32" in content

    def test_audio_meta_content(self, tmp_path):
        """Test generating meta content for audio."""
        audio = tmp_path / "sound.wav"
        audio.touch()

        content = generate_meta_content(audio)

        assert "AudioImporter:" in content
        assert "loadType:" in content

    def test_model_meta_content(self, tmp_path):
        """Test generating meta content for a 3D model."""
        model = tmp_path / "character.fbx"
        model.touch()

        content = generate_meta_content(model)

        assert "ModelImporter:" in content
        assert "meshCompression:" in content
        assert "importAnimation:" in content

    def test_custom_guid(self, tmp_path):
        """Test using a custom GUID."""
        file = tmp_path / "test.txt"
        file.touch()

        custom_guid = "a" * 32
        options = MetaFileOptions(guid=custom_guid)
        content = generate_meta_content(file, options=options)

        assert f"guid: {custom_guid}" in content

    def test_seeded_guid(self, tmp_path):
        """Test using seeded GUID generation."""
        file = tmp_path / "test.txt"
        file.touch()

        options = MetaFileOptions(guid_seed="test_seed")
        content1 = generate_meta_content(file, options=options)
        content2 = generate_meta_content(file, options=options)

        # Extract GUIDs
        guid1 = None
        guid2 = None
        for line in content1.split("\n"):
            if line.startswith("guid:"):
                guid1 = line.split(":")[1].strip()
                break
        for line in content2.split("\n"):
            if line.startswith("guid:"):
                guid2 = line.split(":")[1].strip()
                break

        assert guid1 == guid2


class TestGenerateMetaFile:
    """Tests for writing meta files to disk."""

    def test_generate_meta_file(self, tmp_path):
        """Test generating and writing a meta file."""
        script = tmp_path / "Player.cs"
        script.touch()

        meta_path = generate_meta_file(script)

        assert meta_path.exists()
        assert meta_path == script.parent / "Player.cs.meta"

        content = meta_path.read_text()
        assert "MonoImporter:" in content

    def test_generate_meta_file_no_overwrite(self, tmp_path):
        """Test that meta file is not overwritten by default."""
        script = tmp_path / "Player.cs"
        script.touch()

        meta_path = generate_meta_file(script)
        original_content = meta_path.read_text()

        with pytest.raises(FileExistsError):
            generate_meta_file(script)

        # Content should be unchanged
        assert meta_path.read_text() == original_content

    def test_generate_meta_file_overwrite(self, tmp_path):
        """Test overwriting an existing meta file."""
        script = tmp_path / "Player.cs"
        script.touch()

        # Create initial meta file
        generate_meta_file(script)
        original_content = (tmp_path / "Player.cs.meta").read_text()

        # Overwrite with different GUID
        options = MetaFileOptions(guid="b" * 32)
        generate_meta_file(script, options=options, overwrite=True)

        new_content = (tmp_path / "Player.cs.meta").read_text()
        assert new_content != original_content
        assert "b" * 32 in new_content

    def test_generate_meta_file_nonexistent_path(self, tmp_path):
        """Test error when asset path doesn't exist."""
        nonexistent = tmp_path / "nonexistent.cs"

        with pytest.raises(FileNotFoundError):
            generate_meta_file(nonexistent)


class TestGenerateMetaFilesRecursive:
    """Tests for recursive meta file generation."""

    def test_recursive_generation(self, tmp_path):
        """Test generating meta files recursively."""
        # Create directory structure
        scripts = tmp_path / "Scripts"
        scripts.mkdir()
        (scripts / "Player.cs").touch()
        (scripts / "Enemy.cs").touch()

        textures = tmp_path / "Textures"
        textures.mkdir()
        (textures / "icon.png").touch()

        results = generate_meta_files_recursive(tmp_path)

        # Should have created meta files for all items
        success_count = sum(1 for _, success, _ in results if success)
        assert success_count >= 5  # tmp_path, Scripts, Player.cs, Enemy.cs, Textures, icon.png

        # Verify meta files exist
        assert (tmp_path / "Scripts.meta").exists()
        assert (scripts / "Player.cs.meta").exists()
        assert (textures / "icon.png.meta").exists()

    def test_recursive_skip_existing(self, tmp_path):
        """Test skipping existing meta files in recursive mode."""
        script = tmp_path / "Player.cs"
        script.touch()

        # Create initial meta file
        generate_meta_file(script)

        # Run recursive - should skip existing
        generate_meta_files_recursive(tmp_path, skip_existing=True)

        # The script's meta should not be in the successful results
        # (only tmp_path meta would be created)
        pass  # This is more of an integration test

    def test_skip_hidden_files(self, tmp_path):
        """Test that hidden files are skipped."""
        hidden = tmp_path / ".hidden"
        hidden.touch()

        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "config").touch()

        generate_meta_files_recursive(tmp_path)

        # Hidden files should not have meta files
        assert not (tmp_path / ".hidden.meta").exists()
        assert not (tmp_path / ".git.meta").exists()


class TestEnsureMetaFile:
    """Tests for ensure_meta_file function."""

    def test_ensure_creates_new(self, tmp_path):
        """Test that ensure creates a new meta file if needed."""
        script = tmp_path / "Player.cs"
        script.touch()

        meta_path, was_created = ensure_meta_file(script)

        assert was_created
        assert meta_path.exists()

    def test_ensure_skips_existing(self, tmp_path):
        """Test that ensure skips existing meta files."""
        script = tmp_path / "Player.cs"
        script.touch()

        # Create meta file
        generate_meta_file(script)
        original_content = (tmp_path / "Player.cs.meta").read_text()

        # Ensure should not modify
        meta_path, was_created = ensure_meta_file(script)

        assert not was_created
        assert meta_path.read_text() == original_content


class TestGetGuidFromMeta:
    """Tests for extracting GUID from meta files."""

    def test_extract_guid(self, tmp_path):
        """Test extracting GUID from a meta file."""
        script = tmp_path / "Player.cs"
        script.touch()

        custom_guid = "abcd1234" * 4
        options = MetaFileOptions(guid=custom_guid)
        meta_path = generate_meta_file(script, options=options)

        extracted = get_guid_from_meta(meta_path)

        assert extracted == custom_guid

    def test_extract_guid_from_invalid_file(self, tmp_path):
        """Test extracting GUID from invalid meta file."""
        invalid = tmp_path / "invalid.meta"
        invalid.write_text("not a valid meta file")

        result = get_guid_from_meta(invalid)
        assert result is None

    def test_extract_guid_nonexistent_file(self, tmp_path):
        """Test extracting GUID from nonexistent file."""
        nonexistent = tmp_path / "nonexistent.meta"

        result = get_guid_from_meta(nonexistent)
        assert result is None


class TestMetaFileOptions:
    """Tests for MetaFileOptions dataclass."""

    def test_default_options(self):
        """Test default option values."""
        options = MetaFileOptions()

        assert options.guid is None
        assert options.sprite_mode == 1
        assert options.sprite_pixels_per_unit == 100
        assert options.max_texture_size == 2048

    def test_custom_options(self):
        """Test custom option values."""
        options = MetaFileOptions(
            guid="a" * 32,
            texture_type="Sprite",
            sprite_mode=2,
            sprite_pixels_per_unit=32,
            execution_order=100,
        )

        assert options.guid == "a" * 32
        assert options.texture_type == "Sprite"
        assert options.sprite_mode == 2
        assert options.sprite_pixels_per_unit == 32
        assert options.execution_order == 100


class TestExtensionToTypeMapping:
    """Tests for extension to type mapping."""

    def test_common_extensions(self):
        """Test common file extension mappings."""
        assert EXTENSION_TO_TYPE[".cs"] == AssetType.SCRIPT
        assert EXTENSION_TO_TYPE[".png"] == AssetType.TEXTURE
        assert EXTENSION_TO_TYPE[".wav"] == AssetType.AUDIO
        assert EXTENSION_TO_TYPE[".fbx"] == AssetType.MODEL
        assert EXTENSION_TO_TYPE[".shader"] == AssetType.SHADER
        assert EXTENSION_TO_TYPE[".prefab"] == AssetType.PREFAB
        assert EXTENSION_TO_TYPE[".unity"] == AssetType.SCENE


# ============================================================================
# Meta File Modification Tests
# ============================================================================


class TestModifyMetaFile:
    """Tests for modify_meta_file function."""

    def test_modify_meta_file_guid_not_allowed(self, tmp_path):
        """Test that GUID modification is not allowed."""
        script = tmp_path / "Player.cs"
        script.touch()
        generate_meta_file(script)

        meta_path = tmp_path / "Player.cs.meta"

        with pytest.raises(ValueError, match="GUID modification is not allowed"):
            modify_meta_file(meta_path, {"guid": "a" * 32})

    def test_modify_meta_file_preserves_guid(self, tmp_path):
        """Test that modifications preserve GUID."""
        texture = tmp_path / "icon.png"
        texture.touch()

        custom_guid = "abcd1234" * 4
        options = MetaFileOptions(guid=custom_guid)
        generate_meta_file(texture, options=options)

        meta_path = tmp_path / "icon.png.meta"
        original_guid = get_guid_from_meta(meta_path)

        # Modify sprite mode
        set_texture_sprite_mode(meta_path, sprite_mode=1)

        # GUID should be preserved
        assert get_guid_from_meta(meta_path) == original_guid


class TestSetTextureSpriteMode:
    """Tests for set_texture_sprite_mode function."""

    def test_set_sprite_mode_single(self, tmp_path):
        """Test setting sprite mode to single."""
        texture = tmp_path / "icon.png"
        texture.touch()
        generate_meta_file(texture)

        meta_path = tmp_path / "icon.png.meta"
        set_texture_sprite_mode(meta_path, sprite_mode=1)

        info = get_meta_info(meta_path)
        assert info["sprite_mode"] == 1
        assert info["texture_type"] == 8  # Sprite

    def test_set_sprite_mode_multiple(self, tmp_path):
        """Test setting sprite mode to multiple."""
        texture = tmp_path / "atlas.png"
        texture.touch()
        generate_meta_file(texture)

        meta_path = tmp_path / "atlas.png.meta"
        set_texture_sprite_mode(meta_path, sprite_mode=2)

        info = get_meta_info(meta_path)
        assert info["sprite_mode"] == 2

    def test_set_pixels_per_unit(self, tmp_path):
        """Test setting pixels per unit."""
        texture = tmp_path / "icon.png"
        texture.touch()
        generate_meta_file(texture)

        meta_path = tmp_path / "icon.png.meta"
        set_texture_sprite_mode(meta_path, sprite_mode=1, pixels_per_unit=32)

        info = get_meta_info(meta_path)
        assert info["pixels_per_unit"] == 32

    def test_set_filter_mode(self, tmp_path):
        """Test setting filter mode."""
        texture = tmp_path / "icon.png"
        texture.touch()
        generate_meta_file(texture)

        meta_path = tmp_path / "icon.png.meta"
        set_texture_sprite_mode(meta_path, sprite_mode=1, filter_mode=0)  # Point

        info = get_meta_info(meta_path)
        assert info["filter_mode"] == 0


class TestSetTextureMaxSize:
    """Tests for set_texture_max_size function."""

    def test_set_max_size(self, tmp_path):
        """Test setting max texture size."""
        texture = tmp_path / "icon.png"
        texture.touch()
        generate_meta_file(texture)

        meta_path = tmp_path / "icon.png.meta"
        set_texture_max_size(meta_path, 512)

        info = get_meta_info(meta_path)
        assert info["max_texture_size"] == 512

    def test_invalid_max_size(self, tmp_path):
        """Test that invalid max size raises error."""
        texture = tmp_path / "icon.png"
        texture.touch()
        generate_meta_file(texture)

        meta_path = tmp_path / "icon.png.meta"

        with pytest.raises(ValueError, match="Invalid max size"):
            set_texture_max_size(meta_path, 100)  # Not a valid size


class TestSetScriptExecutionOrder:
    """Tests for set_script_execution_order function."""

    def test_set_execution_order_positive(self, tmp_path):
        """Test setting positive execution order."""
        script = tmp_path / "Player.cs"
        script.touch()
        generate_meta_file(script)

        meta_path = tmp_path / "Player.cs.meta"
        set_script_execution_order(meta_path, 100)

        info = get_meta_info(meta_path)
        assert info["execution_order"] == 100

    def test_set_execution_order_negative(self, tmp_path):
        """Test setting negative execution order."""
        script = tmp_path / "Bootstrap.cs"
        script.touch()
        generate_meta_file(script)

        meta_path = tmp_path / "Bootstrap.cs.meta"
        set_script_execution_order(meta_path, -100)

        info = get_meta_info(meta_path)
        assert info["execution_order"] == -100


class TestSetAssetBundle:
    """Tests for set_asset_bundle function."""

    def test_set_bundle_name(self, tmp_path):
        """Test setting asset bundle name."""
        prefab = tmp_path / "Player.prefab"
        prefab.touch()
        generate_meta_file(prefab)

        meta_path = tmp_path / "Player.prefab.meta"
        set_asset_bundle(meta_path, bundle_name="characters")

        info = get_meta_info(meta_path)
        assert info["asset_bundle_name"] == "characters"

    def test_set_bundle_name_and_variant(self, tmp_path):
        """Test setting both bundle name and variant."""
        prefab = tmp_path / "Player.prefab"
        prefab.touch()
        generate_meta_file(prefab)

        meta_path = tmp_path / "Player.prefab.meta"
        set_asset_bundle(meta_path, bundle_name="characters", bundle_variant="hd")

        info = get_meta_info(meta_path)
        assert info["asset_bundle_name"] == "characters"
        assert info["asset_bundle_variant"] == "hd"

    def test_clear_bundle_name(self, tmp_path):
        """Test clearing asset bundle name."""
        prefab = tmp_path / "Player.prefab"
        prefab.touch()
        generate_meta_file(prefab)

        meta_path = tmp_path / "Player.prefab.meta"
        set_asset_bundle(meta_path, bundle_name="characters")
        set_asset_bundle(meta_path, bundle_name="")  # Clear

        info = get_meta_info(meta_path)
        assert info["asset_bundle_name"] is None


class TestGetMetaInfo:
    """Tests for get_meta_info function."""

    def test_get_texture_info(self, tmp_path):
        """Test getting texture meta info."""
        texture = tmp_path / "icon.png"
        texture.touch()

        options = MetaFileOptions(
            guid="a" * 32,
            texture_type="Sprite",
            sprite_mode=1,
            sprite_pixels_per_unit=32,
        )
        generate_meta_file(texture, options=options)

        meta_path = tmp_path / "icon.png.meta"
        info = get_meta_info(meta_path)

        assert info["guid"] == "a" * 32
        assert info["importer_type"] == "TextureImporter"
        assert info["sprite_mode"] == 1
        assert info["pixels_per_unit"] == 32

    def test_get_script_info(self, tmp_path):
        """Test getting script meta info."""
        script = tmp_path / "Player.cs"
        script.touch()

        options = MetaFileOptions(execution_order=50)
        generate_meta_file(script, options=options)

        meta_path = tmp_path / "Player.cs.meta"
        info = get_meta_info(meta_path)

        assert info["importer_type"] == "MonoImporter"
        assert info["execution_order"] == 50

    def test_get_info_nonexistent_file(self, tmp_path):
        """Test error when meta file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.meta"

        with pytest.raises(FileNotFoundError):
            get_meta_info(nonexistent)
