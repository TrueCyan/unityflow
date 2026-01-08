"""Tests for Unity asset reference tracker."""

import tempfile
import time
from pathlib import Path

from unityflow.asset_tracker import (
    BINARY_ASSET_EXTENSIONS,
    AssetDependency,
    AssetReference,
    CachedGUIDIndex,
    DependencyReport,
    GUIDIndex,
    LazyGUIDIndex,
    _classify_asset_type,
    _parse_meta_file,
    analyze_dependencies,
    build_guid_index,
    extract_guid_references,
    find_references_to_asset,
    find_unity_project_root,
    get_cached_guid_index,
    get_file_dependencies,
    get_lazy_guid_index,
    get_local_package_paths,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestAssetReference:
    """Tests for AssetReference class."""

    def test_create_reference(self):
        """Test creating an asset reference."""
        ref = AssetReference(
            file_id=11500000,
            guid="abc123def456",
            ref_type=3,
        )

        assert ref.file_id == 11500000
        assert ref.guid == "abc123def456"
        assert ref.ref_type == 3

    def test_reference_equality(self):
        """Test reference equality comparison."""
        ref1 = AssetReference(file_id=100, guid="abc123", ref_type=3)
        ref2 = AssetReference(file_id=100, guid="abc123", ref_type=2)
        ref3 = AssetReference(file_id=200, guid="abc123", ref_type=3)

        # Same fileID and guid are equal
        assert ref1 == ref2

        # Different fileID are not equal
        assert ref1 != ref3

    def test_reference_hash(self):
        """Test reference hashing for use in sets/dicts."""
        ref1 = AssetReference(file_id=100, guid="abc123", ref_type=3)
        ref2 = AssetReference(file_id=100, guid="abc123", ref_type=2)

        # Same hash for equal references
        assert hash(ref1) == hash(ref2)

        # Can be used in sets
        refs = {ref1, ref2}
        assert len(refs) == 1


class TestAssetDependency:
    """Tests for AssetDependency class."""

    def test_resolved_dependency(self):
        """Test a resolved dependency."""
        dep = AssetDependency(
            guid="abc123",
            path=Path("Assets/Textures/player.png"),
            asset_type="Texture",
        )

        assert dep.is_resolved
        assert dep.is_binary
        assert dep.guid == "abc123"

    def test_unresolved_dependency(self):
        """Test an unresolved dependency."""
        dep = AssetDependency(
            guid="xyz789",
            path=None,
        )

        assert not dep.is_resolved
        assert not dep.is_binary

    def test_non_binary_dependency(self):
        """Test a non-binary asset dependency."""
        dep = AssetDependency(
            guid="abc123",
            path=Path("Assets/Scripts/Player.cs"),
            asset_type="Script",
        )

        assert dep.is_resolved
        assert not dep.is_binary


class TestGUIDIndex:
    """Tests for GUIDIndex class."""

    def test_empty_index(self):
        """Test empty GUID index."""
        index = GUIDIndex()

        assert len(index) == 0
        assert index.get_path("abc123") is None

    def test_add_and_lookup(self):
        """Test adding entries and looking them up."""
        index = GUIDIndex()
        path = Path("Assets/Textures/player.png")

        index.guid_to_path["abc123"] = path
        index.path_to_guid[path] = "abc123"

        assert len(index) == 1
        assert index.get_path("abc123") == path
        assert index.get_guid(path) == "abc123"


class TestExtractGUIDReferences:
    """Tests for extract_guid_references function."""

    def test_extract_simple_reference(self):
        """Test extracting a simple GUID reference."""
        data = {"m_Script": {"fileID": 11500000, "guid": "abc123def456", "type": 3}}

        refs = list(extract_guid_references(data))

        assert len(refs) == 1
        assert refs[0].guid == "abc123def456"
        assert refs[0].file_id == 11500000
        assert refs[0].ref_type == 3

    def test_extract_nested_references(self):
        """Test extracting references from nested structures."""
        data = {
            "GameObject": {
                "m_Component": [
                    {"component": {"fileID": 100000, "guid": "guid1", "type": 2}},
                    {"component": {"fileID": 200000, "guid": "guid2", "type": 3}},
                ],
                "m_Material": {"fileID": 300000, "guid": "guid3", "type": 2},
            }
        }

        refs = list(extract_guid_references(data))
        guids = {ref.guid for ref in refs}

        assert len(refs) == 3
        assert guids == {"guid1", "guid2", "guid3"}

    def test_extract_from_modifications(self):
        """Test extracting references from m_Modifications."""
        data = {
            "PrefabInstance": {
                "m_Modification": {
                    "m_Modifications": [
                        {
                            "target": {"fileID": 400000, "guid": "abc123def456", "type": 3},
                            "propertyPath": "m_LocalPosition.x",
                            "value": 5,
                        }
                    ],
                    "m_SourcePrefab": {"fileID": 100100000, "guid": "xyz789", "type": 3},
                }
            }
        }

        refs = list(extract_guid_references(data))
        guids = {ref.guid for ref in refs}

        assert len(refs) == 2
        assert "abc123def456" in guids
        assert "xyz789" in guids

    def test_skip_internal_references(self):
        """Test that internal references (no guid) are skipped."""
        data = {
            "Transform": {
                "m_Father": {"fileID": 400000},  # Internal reference
                "m_Children": [
                    {"fileID": 400001},
                    {"fileID": 400002},
                ],
            }
        }

        refs = list(extract_guid_references(data))

        assert len(refs) == 0

    def test_empty_data(self):
        """Test with empty data."""
        refs = list(extract_guid_references({}))
        assert len(refs) == 0

        refs = list(extract_guid_references([]))
        assert len(refs) == 0


class TestGetFileDependencies:
    """Tests for get_file_dependencies function."""

    def test_get_dependencies_from_prefab(self):
        """Test getting dependencies from a prefab with modifications."""
        deps = get_file_dependencies(FIXTURES_DIR / "prefab_with_modifications.prefab")

        assert len(deps) > 0
        # The fixture references guid "abc123def45678901234567890123456"
        guids = {d.guid for d in deps}
        assert "abc123def45678901234567890123456" in guids

    def test_basic_prefab_no_external_deps(self):
        """Test basic prefab has no external dependencies."""
        deps = get_file_dependencies(FIXTURES_DIR / "basic_prefab.prefab")

        # Basic prefab may have no external references
        # (only internal fileID references)
        assert isinstance(deps, list)


class TestClassifyAssetType:
    """Tests for _classify_asset_type function."""

    def test_texture_types(self):
        """Test texture classification."""
        assert _classify_asset_type(Path("test.png")) == "Texture"
        assert _classify_asset_type(Path("test.jpg")) == "Texture"
        assert _classify_asset_type(Path("test.tga")) == "Texture"
        assert _classify_asset_type(Path("test.psd")) == "Texture"

    def test_model_types(self):
        """Test model classification."""
        assert _classify_asset_type(Path("test.fbx")) == "Model"
        assert _classify_asset_type(Path("test.obj")) == "Model"
        assert _classify_asset_type(Path("test.blend")) == "Model"

    def test_audio_types(self):
        """Test audio classification."""
        assert _classify_asset_type(Path("test.wav")) == "Audio"
        assert _classify_asset_type(Path("test.mp3")) == "Audio"
        assert _classify_asset_type(Path("test.ogg")) == "Audio"

    def test_script_types(self):
        """Test script classification."""
        assert _classify_asset_type(Path("test.cs")) == "Script"

    def test_shader_types(self):
        """Test shader classification."""
        assert _classify_asset_type(Path("test.shader")) == "Shader"
        assert _classify_asset_type(Path("test.cginc")) == "Shader"

    def test_font_types(self):
        """Test font classification."""
        assert _classify_asset_type(Path("test.ttf")) == "Font"
        assert _classify_asset_type(Path("test.otf")) == "Font"

    def test_unknown_type(self):
        """Test unknown type classification."""
        assert _classify_asset_type(Path("test.xyz")) == "Unknown"


class TestDependencyReport:
    """Tests for DependencyReport class."""

    def test_empty_report(self):
        """Test empty dependency report."""
        report = DependencyReport(
            source_files=[Path("test.prefab")],
            dependencies=[],
        )

        assert report.total_dependencies == 0
        assert report.resolved_count == 0
        assert report.unresolved_count == 0
        assert report.binary_count == 0

    def test_report_with_dependencies(self):
        """Test report with various dependencies."""
        deps = [
            AssetDependency(guid="g1", path=Path("tex.png"), asset_type="Texture"),
            AssetDependency(guid="g2", path=Path("script.cs"), asset_type="Script"),
            AssetDependency(guid="g3", path=None),  # Unresolved
        ]

        report = DependencyReport(
            source_files=[Path("test.prefab")],
            dependencies=deps,
        )

        assert report.total_dependencies == 3
        assert report.resolved_count == 2
        assert report.unresolved_count == 1
        assert report.binary_count == 1

    def test_get_by_type(self):
        """Test filtering by type."""
        deps = [
            AssetDependency(guid="g1", path=Path("tex1.png"), asset_type="Texture"),
            AssetDependency(guid="g2", path=Path("tex2.png"), asset_type="Texture"),
            AssetDependency(guid="g3", path=Path("script.cs"), asset_type="Script"),
        ]

        report = DependencyReport(
            source_files=[Path("test.prefab")],
            dependencies=deps,
        )

        textures = report.get_by_type("Texture")
        assert len(textures) == 2

        scripts = report.get_by_type("Script")
        assert len(scripts) == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        deps = [
            AssetDependency(guid="g1", path=Path("tex.png"), asset_type="Texture"),
        ]

        report = DependencyReport(
            source_files=[Path("test.prefab")],
            dependencies=deps,
        )

        data = report.to_dict()

        assert "source_files" in data
        assert "summary" in data
        assert "dependencies" in data
        assert data["summary"]["total"] == 1


class TestBuildGUIDIndex:
    """Tests for build_guid_index function."""

    def test_build_index_with_temp_project(self):
        """Test building index from a temporary Unity project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create minimal Unity project structure
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create a test asset and its .meta file
            (project_root / "Assets" / "test.txt").write_text("test content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            # Build index
            index = build_guid_index(project_root)

            assert len(index) == 1
            assert index.get_path("0123456789abcdef0123456789abcdef") is not None


class TestFindUnityProjectRoot:
    """Tests for find_unity_project_root function."""

    def test_find_project_root_from_assets(self):
        """Test finding project root from Assets folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Unity project structure
            (project_root / "Assets" / "Prefabs").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir()

            # Test from prefab path
            prefab_path = project_root / "Assets" / "Prefabs" / "test.prefab"

            found_root = find_unity_project_root(prefab_path.parent)

            assert found_root == project_root

    def test_not_in_unity_project(self):
        """Test when not in a Unity project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No Assets folder
            path = Path(tmpdir)

            found_root = find_unity_project_root(path)

            assert found_root is None


class TestAnalyzeDependencies:
    """Tests for analyze_dependencies function."""

    def test_analyze_single_file(self):
        """Test analyzing a single file."""
        report = analyze_dependencies([FIXTURES_DIR / "prefab_with_modifications.prefab"])

        assert len(report.source_files) == 1
        assert isinstance(report.dependencies, list)

    def test_analyze_multiple_files(self):
        """Test analyzing multiple files."""
        files = [
            FIXTURES_DIR / "basic_prefab.prefab",
            FIXTURES_DIR / "prefab_with_modifications.prefab",
        ]
        report = analyze_dependencies(files)

        assert len(report.source_files) == 2


class TestBinaryAssetExtensions:
    """Tests for BINARY_ASSET_EXTENSIONS constant."""

    def test_contains_common_formats(self):
        """Test that common binary formats are included."""
        # Textures
        assert ".png" in BINARY_ASSET_EXTENSIONS
        assert ".jpg" in BINARY_ASSET_EXTENSIONS
        assert ".tga" in BINARY_ASSET_EXTENSIONS

        # Models
        assert ".fbx" in BINARY_ASSET_EXTENSIONS
        assert ".obj" in BINARY_ASSET_EXTENSIONS

        # Audio
        assert ".wav" in BINARY_ASSET_EXTENSIONS
        assert ".mp3" in BINARY_ASSET_EXTENSIONS

        # Fonts
        assert ".ttf" in BINARY_ASSET_EXTENSIONS

    def test_does_not_contain_yaml_formats(self):
        """Test that Unity YAML formats are not in binary extensions."""
        assert ".prefab" not in BINARY_ASSET_EXTENSIONS
        assert ".unity" not in BINARY_ASSET_EXTENSIONS
        assert ".asset" not in BINARY_ASSET_EXTENSIONS


class TestFindReferencesToAsset:
    """Tests for find_references_to_asset function."""

    def test_find_refs_with_temp_setup(self):
        """Test finding references with temporary setup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project structure
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create asset with meta file (GUID must be 32 hex characters)
            test_guid = "0123456789abcdef0123456789abcdef"
            asset_path = project_root / "Assets" / "texture.png"
            asset_path.write_bytes(b"fake png")
            meta_path = project_root / "Assets" / "texture.png.meta"
            meta_path.write_text(f"fileFormatVersion: 2\nguid: {test_guid}\n")

            # Create a prefab that references this asset
            prefab_path = project_root / "Assets" / "test.prefab"
            prefab_content = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &100000
MonoBehaviour:
  m_Texture: {{fileID: 2800000, guid: {test_guid}, type: 3}}
"""
            prefab_path.write_text(prefab_content)

            # Build index
            guid_index = build_guid_index(project_root)

            # Find references
            results = find_references_to_asset(
                asset_path=asset_path,
                search_paths=[project_root / "Assets"],
                guid_index=guid_index,
            )

            assert len(results) == 1
            assert results[0][0] == prefab_path


class TestParseMetaFile:
    """Tests for _parse_meta_file function."""

    def test_parse_valid_meta_file(self):
        """Test parsing a valid .meta file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()

            meta_path = project_root / "Assets" / "test.txt.meta"
            meta_path.write_text("fileFormatVersion: 2\nguid: abcdef0123456789abcdef0123456789\n")

            result = _parse_meta_file(meta_path, project_root)

            assert result is not None
            guid, path, mtime = result
            assert guid == "abcdef0123456789abcdef0123456789"
            assert path == Path("Assets/test.txt")
            assert isinstance(mtime, float)

    def test_parse_invalid_meta_file(self):
        """Test parsing an invalid .meta file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()

            meta_path = project_root / "Assets" / "test.txt.meta"
            meta_path.write_text("invalid content without guid")

            result = _parse_meta_file(meta_path, project_root)

            assert result is None

    def test_parse_nonexistent_file(self):
        """Test parsing a nonexistent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            meta_path = project_root / "nonexistent.meta"

            result = _parse_meta_file(meta_path, project_root)

            assert result is None


class TestCachedGUIDIndex:
    """Tests for CachedGUIDIndex with SQLite caching."""

    def test_create_cache_index(self):
        """Test creating a cached GUID index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            cache = CachedGUIDIndex(project_root=project_root)

            assert cache.project_root == project_root
            assert cache.cache_db == project_root / ".unityflow" / "guid_cache.db"

    def test_build_and_cache_index(self):
        """Test building and caching a GUID index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test assets
            (project_root / "Assets" / "test1.txt").write_text("content1")
            (project_root / "Assets" / "test1.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )
            (project_root / "Assets" / "test2.txt").write_text("content2")
            (project_root / "Assets" / "test2.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: fedcba9876543210fedcba9876543210\n"
            )

            cache = CachedGUIDIndex(project_root=project_root)
            index = cache.get_index(include_packages=False)

            assert len(index) == 2
            assert index.get_path("0123456789abcdef0123456789abcdef") is not None
            assert index.get_path("fedcba9876543210fedcba9876543210") is not None

            # Verify cache database was created
            assert cache.cache_db.exists()

    def test_load_from_cache(self):
        """Test loading index from existing cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test asset
            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            # Build first cache
            cache1 = CachedGUIDIndex(project_root=project_root)
            index1 = cache1.get_index(include_packages=False)
            assert len(index1) == 1

            # Create new cache instance and load from DB
            cache2 = CachedGUIDIndex(project_root=project_root)
            index2 = cache2.get_index(include_packages=False)

            assert len(index2) == 1
            assert index2.get_path("0123456789abcdef0123456789abcdef") is not None

    def test_invalidate_cache(self):
        """Test invalidating the cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test asset
            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            cache = CachedGUIDIndex(project_root=project_root)
            cache.get_index(include_packages=False)

            assert cache.cache_db.exists()

            cache.invalidate()

            assert not cache.cache_db.exists()

    def test_incremental_update_new_file(self):
        """Test incremental update when a new file is added."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create initial asset
            (project_root / "Assets" / "test1.txt").write_text("content1")
            (project_root / "Assets" / "test1.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            # Build initial cache
            cache = CachedGUIDIndex(project_root=project_root)
            index1 = cache.get_index(include_packages=False)
            assert len(index1) == 1

            # Reset the cached index
            cache._index = None

            # Add new file
            (project_root / "Assets" / "test2.txt").write_text("content2")
            (project_root / "Assets" / "test2.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: fedcba9876543210fedcba9876543210\n"
            )

            # Get index again (should do incremental update)
            index2 = cache.get_index(include_packages=False)
            assert len(index2) == 2

    def test_incremental_update_deleted_file(self):
        """Test incremental update when a file is deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create initial assets
            (project_root / "Assets" / "test1.txt").write_text("content1")
            (project_root / "Assets" / "test1.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )
            (project_root / "Assets" / "test2.txt").write_text("content2")
            (project_root / "Assets" / "test2.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: fedcba9876543210fedcba9876543210\n"
            )

            # Build initial cache
            cache = CachedGUIDIndex(project_root=project_root)
            index1 = cache.get_index(include_packages=False)
            assert len(index1) == 2

            # Reset the cached index
            cache._index = None

            # Delete one file
            (project_root / "Assets" / "test2.txt").unlink()
            (project_root / "Assets" / "test2.txt.meta").unlink()

            # Get index again (should do incremental update)
            index2 = cache.get_index(include_packages=False)
            assert len(index2) == 1
            assert index2.get_path("0123456789abcdef0123456789abcdef") is not None
            assert index2.get_path("fedcba9876543210fedcba9876543210") is None

    def test_incremental_update_modified_file(self):
        """Test incremental update when a file is modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create initial asset
            meta_path = project_root / "Assets" / "test.txt.meta"
            (project_root / "Assets" / "test.txt").write_text("content")
            meta_path.write_text("fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n")

            # Build initial cache
            cache = CachedGUIDIndex(project_root=project_root)
            index1 = cache.get_index(include_packages=False)
            assert index1.get_path("0123456789abcdef0123456789abcdef") is not None

            # Reset the cached index
            cache._index = None

            # Modify the meta file with a new GUID (wait to ensure mtime changes)
            time.sleep(0.1)
            meta_path.write_text("fileFormatVersion: 2\nguid: aaaabbbbccccddddeeeeffffaaaabbbb\n")

            # Get index again (should do incremental update)
            index2 = cache.get_index(include_packages=False)
            assert index2.get_path("aaaabbbbccccddddeeeeffffaaaabbbb") is not None

    def test_progress_callback(self):
        """Test progress callback during index building."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test assets
            for i in range(5):
                (project_root / "Assets" / f"test{i}.txt").write_text(f"content{i}")
                (project_root / "Assets" / f"test{i}.txt.meta").write_text(f"fileFormatVersion: 2\nguid: {i:032x}\n")

            progress_calls = []

            def progress_callback(current, total):
                progress_calls.append((current, total))

            cache = CachedGUIDIndex(project_root=project_root)
            cache.get_index(include_packages=False, progress_callback=progress_callback)

            assert len(progress_calls) > 0
            # Last call should have current == total
            assert progress_calls[-1][0] == progress_calls[-1][1]


class TestGetCachedGUIDIndex:
    """Tests for get_cached_guid_index function."""

    def test_get_cached_index(self):
        """Test getting a cached GUID index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test asset
            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            index = get_cached_guid_index(project_root, include_packages=False)

            assert len(index) == 1
            assert index.get_path("0123456789abcdef0123456789abcdef") is not None

    def test_get_cached_index_with_max_workers(self):
        """Test getting index with custom max_workers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test assets
            for i in range(3):
                (project_root / "Assets" / f"test{i}.txt").write_text(f"content{i}")
                (project_root / "Assets" / f"test{i}.txt.meta").write_text(f"fileFormatVersion: 2\nguid: {i:032x}\n")

            index = get_cached_guid_index(
                project_root,
                include_packages=False,
                max_workers=2,
            )

            assert len(index) == 3


class TestLazyGUIDIndex:
    """Tests for LazyGUIDIndex class."""

    def test_create_lazy_index(self):
        """Test creating a lazy GUID index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test asset and cache
            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            # Build cache first
            get_cached_guid_index(project_root, include_packages=False)

            # Create lazy index
            lazy_index = LazyGUIDIndex(project_root=project_root)
            assert lazy_index.project_root == project_root

    def test_lazy_index_get_path(self):
        """Test getting path from lazy index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test asset
            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            # Get lazy index (builds cache if needed)
            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # Query path
            path = lazy_index.get_path("0123456789abcdef0123456789abcdef")
            assert path is not None
            assert path.name == "test.txt"

    def test_lazy_index_resolve_name(self):
        """Test resolving name from lazy index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test script
            (project_root / "Assets" / "PlayerController.cs").write_text("class Player {}")
            (project_root / "Assets" / "PlayerController.cs.meta").write_text(
                "fileFormatVersion: 2\nguid: abcdef0123456789abcdef0123456789\n"
            )

            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # Resolve name
            name = lazy_index.resolve_name("abcdef0123456789abcdef0123456789")
            assert name == "PlayerController"

    def test_lazy_index_get_guid(self):
        """Test getting GUID from path using lazy index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test asset
            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: fedcba9876543210fedcba9876543210\n"
            )

            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # Query GUID
            guid = lazy_index.get_guid(Path("Assets/test.txt"))
            assert guid == "fedcba9876543210fedcba9876543210"

    def test_lazy_index_caching(self):
        """Test that lazy index caches results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create test asset
            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # First access (from DB)
            path1 = lazy_index.get_path("0123456789abcdef0123456789abcdef")

            # Check it's in cache
            assert "0123456789abcdef0123456789abcdef" in lazy_index._cache

            # Second access (from cache)
            path2 = lazy_index.get_path("0123456789abcdef0123456789abcdef")

            assert path1 == path2

    def test_lazy_index_cache_eviction(self):
        """Test that lazy index evicts oldest entries when cache is full."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create multiple test assets
            for i in range(5):
                (project_root / "Assets" / f"test{i}.txt").write_text(f"content{i}")
                (project_root / "Assets" / f"test{i}.txt.meta").write_text(f"fileFormatVersion: 2\nguid: {i:032x}\n")

            # Get lazy index with small cache
            lazy_index = get_lazy_guid_index(project_root, include_packages=False, cache_size=2)

            # Access all 5 GUIDs
            for i in range(5):
                lazy_index.get_path(f"{i:032x}")

            # Only last 2 should be in cache
            assert len(lazy_index._cache) == 2

    def test_lazy_index_len(self):
        """Test lazy index __len__ method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            # Create multiple test assets
            for i in range(3):
                (project_root / "Assets" / f"test{i}.txt").write_text(f"content{i}")
                (project_root / "Assets" / f"test{i}.txt.meta").write_text(f"fileFormatVersion: 2\nguid: {i:032x}\n")

            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # len should return total DB entries, not just cached
            assert len(lazy_index) == 3

    def test_lazy_index_nonexistent_guid(self):
        """Test lazy index returns None for nonexistent GUID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # Query nonexistent GUID
            path = lazy_index.get_path("nonexistent12345678901234567890")
            assert path is None

    def test_lazy_index_clear_cache(self):
        """Test clearing the in-memory cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # Populate cache
            lazy_index.get_path("0123456789abcdef0123456789abcdef")
            assert len(lazy_index._cache) == 1

            # Clear cache
            lazy_index.clear_cache()
            assert len(lazy_index._cache) == 0

            # Should still be able to query (from DB)
            path = lazy_index.get_path("0123456789abcdef0123456789abcdef")
            assert path is not None

    def test_lazy_index_close(self):
        """Test closing the database connection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()

            (project_root / "Assets" / "test.txt").write_text("content")
            (project_root / "Assets" / "test.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n"
            )

            lazy_index = get_lazy_guid_index(project_root, include_packages=False)

            # Open connection
            lazy_index.get_path("0123456789abcdef0123456789abcdef")
            assert lazy_index._conn is not None

            # Close connection
            lazy_index.close()
            assert lazy_index._conn is None


class TestLocalPackageGUIDCaching:
    """Tests for local package GUID caching via file: paths in manifest.json."""

    def test_get_local_package_paths_utility(self):
        """Test the get_local_package_paths utility function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "UnityProject"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages").mkdir()

            # Create external package directory (simulating file:../../packages/mypackage)
            external_packages = Path(tmpdir) / "packages"
            external_packages.mkdir()
            package_dir = external_packages / "com.test.mypackage"
            package_dir.mkdir()

            # Create manifest.json with file: reference
            manifest = {"dependencies": {"com.test.mypackage": "file:../../packages/com.test.mypackage"}}
            (project_root / "Packages" / "manifest.json").write_text(__import__("json").dumps(manifest))

            # Test the utility function directly
            local_paths = get_local_package_paths(project_root)

            assert len(local_paths) == 1
            assert local_paths[0].resolve() == package_dir.resolve()

    def test_get_local_package_paths(self):
        """Test extracting local package paths from manifest.json via CachedGUIDIndex."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "UnityProject"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages").mkdir()

            # Create external package directory (simulating file:../../packages/mypackage)
            external_packages = Path(tmpdir) / "packages"
            external_packages.mkdir()
            package_dir = external_packages / "com.test.mypackage"
            package_dir.mkdir()

            # Create manifest.json with file: reference
            manifest = {"dependencies": {"com.test.mypackage": "file:../../packages/com.test.mypackage"}}
            (project_root / "Packages" / "manifest.json").write_text(__import__("json").dumps(manifest))

            cache = CachedGUIDIndex(project_root=project_root)
            local_paths = cache._get_local_package_paths()

            assert len(local_paths) == 1
            assert local_paths[0].resolve() == package_dir.resolve()

    def test_local_package_guid_indexing(self):
        """Test that GUIDs from local packages are indexed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "UnityProject"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages").mkdir()

            # Create asset in Assets folder
            (project_root / "Assets" / "main.txt").write_text("main content")
            (project_root / "Assets" / "main.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 11111111111111111111111111111111\n"
            )

            # Create external package directory
            external_packages = Path(tmpdir) / "packages"
            external_packages.mkdir()
            package_dir = external_packages / "com.test.mypackage"
            (package_dir / "Runtime").mkdir(parents=True)

            # Create asset in local package
            (package_dir / "Runtime" / "LocalScript.cs").write_text("class LocalScript {}")
            (package_dir / "Runtime" / "LocalScript.cs.meta").write_text(
                "fileFormatVersion: 2\nguid: 22222222222222222222222222222222\n"
            )

            # Create manifest.json with file: reference
            manifest = {"dependencies": {"com.test.mypackage": "file:../../packages/com.test.mypackage"}}
            (project_root / "Packages" / "manifest.json").write_text(__import__("json").dumps(manifest))

            # Build index with packages
            cache = CachedGUIDIndex(project_root=project_root)
            index = cache.get_index(include_packages=True)

            # Both Assets and local package GUIDs should be indexed
            assert index.get_path("11111111111111111111111111111111") is not None
            assert index.get_path("22222222222222222222222222222222") is not None

    def test_local_package_version_tracking(self):
        """Test that local package paths are tracked for cache invalidation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "UnityProject"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages").mkdir()

            # Create external package directory
            external_packages = Path(tmpdir) / "packages"
            external_packages.mkdir()
            package_dir = external_packages / "com.test.pkg"
            package_dir.mkdir()

            # Create manifest.json with file: reference
            manifest = {"dependencies": {"com.test.pkg": "file:../../packages/com.test.pkg"}}
            (project_root / "Packages" / "manifest.json").write_text(__import__("json").dumps(manifest))

            cache = CachedGUIDIndex(project_root=project_root)
            versions = cache._get_package_versions()

            # Local package should be tracked with its full file: path
            assert "local:com.test.pkg" in versions
            assert versions["local:com.test.pkg"] == "file:../../packages/com.test.pkg"

    def test_local_package_path_with_version_suffix(self):
        """Test local package path with @version suffix like file:../../pkg@1.7.0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "UnityProject"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages").mkdir()

            # Create external package with version in directory name
            external_packages = Path(tmpdir) / "NK.Packages"
            external_packages.mkdir()
            package_dir = external_packages / "com.domybest.mybox@1.7.0"
            (package_dir / "Runtime").mkdir(parents=True)

            # Create asset in local package
            (package_dir / "Runtime" / "MyScript.cs").write_text("class MyScript {}")
            (package_dir / "Runtime" / "MyScript.cs.meta").write_text(
                "fileFormatVersion: 2\nguid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1\n"
            )

            # Create manifest.json with file: reference (matching user's example)
            manifest = {"dependencies": {"com.domybest.mybox": "file:../../NK.Packages/com.domybest.mybox@1.7.0"}}
            (project_root / "Packages" / "manifest.json").write_text(__import__("json").dumps(manifest))

            # Build index with packages
            cache = CachedGUIDIndex(project_root=project_root)
            index = cache.get_index(include_packages=True)

            # Local package GUID should be indexed
            path = index.get_path("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1")
            assert path is not None

    def test_build_guid_index_with_local_packages(self):
        """Test that build_guid_index includes local packages when include_packages=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "UnityProject"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages").mkdir()

            # Create asset in Assets folder
            (project_root / "Assets" / "main.txt").write_text("main content")
            (project_root / "Assets" / "main.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 11111111111111111111111111111111\n"
            )

            # Create external package directory
            external_packages = Path(tmpdir) / "external"
            external_packages.mkdir()
            package_dir = external_packages / "com.test.external"
            (package_dir / "Runtime").mkdir(parents=True)

            # Create asset in local package
            (package_dir / "Runtime" / "ExtScript.cs").write_text("class ExtScript {}")
            (package_dir / "Runtime" / "ExtScript.cs.meta").write_text(
                "fileFormatVersion: 2\nguid: 33333333333333333333333333333333\n"
            )

            # Create manifest.json with file: reference
            manifest = {"dependencies": {"com.test.external": "file:../../external/com.test.external"}}
            (project_root / "Packages" / "manifest.json").write_text(__import__("json").dumps(manifest))

            # Test build_guid_index with include_packages=True
            index = build_guid_index(project_root, include_packages=True)

            # Both Assets and local package GUIDs should be indexed
            assert index.get_path("11111111111111111111111111111111") is not None
            assert index.get_path("33333333333333333333333333333333") is not None

    def test_build_guid_index_without_local_packages(self):
        """Test that build_guid_index excludes local packages when include_packages=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "UnityProject"
            project_root.mkdir()
            (project_root / "Assets").mkdir()
            (project_root / "ProjectSettings").mkdir()
            (project_root / "Packages").mkdir()

            # Create asset in Assets folder
            (project_root / "Assets" / "main.txt").write_text("main content")
            (project_root / "Assets" / "main.txt.meta").write_text(
                "fileFormatVersion: 2\nguid: 44444444444444444444444444444444\n"
            )

            # Create external package directory
            external_packages = Path(tmpdir) / "external"
            external_packages.mkdir()
            package_dir = external_packages / "com.test.external"
            package_dir.mkdir()

            # Create asset in local package
            (package_dir / "External.cs").write_text("class External {}")
            (package_dir / "External.cs.meta").write_text(
                "fileFormatVersion: 2\nguid: 55555555555555555555555555555555\n"
            )

            # Create manifest.json with file: reference
            manifest = {"dependencies": {"com.test.external": "file:../../external/com.test.external"}}
            (project_root / "Packages" / "manifest.json").write_text(__import__("json").dumps(manifest))

            # Test build_guid_index with include_packages=False (default)
            index = build_guid_index(project_root, include_packages=False)

            # Only Assets GUID should be indexed, not local package
            assert index.get_path("44444444444444444444444444444444") is not None
            assert index.get_path("55555555555555555555555555555555") is None
