"""Unity .meta file generator.

Generate .meta files for Unity assets without opening Unity Editor.
Supports various asset types with appropriate importer settings.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AssetType(Enum):
    """Unity asset types with their corresponding importers."""

    FOLDER = "folder"
    SCRIPT = "script"  # .cs, .js
    TEXTURE = "texture"  # .png, .jpg, .jpeg, .tga, .psd, .tiff, .bmp, .gif, .exr, .hdr
    AUDIO = "audio"  # .wav, .mp3, .ogg, .aiff, .flac
    VIDEO = "video"  # .mp4, .mov, .avi, .webm
    MODEL = "model"  # .fbx, .obj, .dae, .3ds, .blend
    SHADER = "shader"  # .shader, .cginc, .hlsl, .compute
    MATERIAL = "material"  # .mat (Unity YAML)
    PREFAB = "prefab"  # .prefab (Unity YAML)
    SCENE = "scene"  # .unity (Unity YAML)
    SCRIPTABLE_OBJECT = "scriptable_object"  # .asset (Unity YAML)
    ANIMATION = "animation"  # .anim, .controller, .overrideController
    FONT = "font"  # .ttf, .otf
    TEXT = "text"  # .txt, .json, .xml, .csv, .bytes
    PLUGIN = "plugin"  # .dll, .so, .dylib
    DEFAULT = "default"  # fallback


# File extension to asset type mapping
EXTENSION_TO_TYPE: dict[str, AssetType] = {
    # Scripts
    ".cs": AssetType.SCRIPT,
    ".js": AssetType.SCRIPT,
    # Textures
    ".png": AssetType.TEXTURE,
    ".jpg": AssetType.TEXTURE,
    ".jpeg": AssetType.TEXTURE,
    ".tga": AssetType.TEXTURE,
    ".psd": AssetType.TEXTURE,
    ".tiff": AssetType.TEXTURE,
    ".tif": AssetType.TEXTURE,
    ".bmp": AssetType.TEXTURE,
    ".gif": AssetType.TEXTURE,
    ".exr": AssetType.TEXTURE,
    ".hdr": AssetType.TEXTURE,
    # Audio
    ".wav": AssetType.AUDIO,
    ".mp3": AssetType.AUDIO,
    ".ogg": AssetType.AUDIO,
    ".aiff": AssetType.AUDIO,
    ".aif": AssetType.AUDIO,
    ".flac": AssetType.AUDIO,
    ".m4a": AssetType.AUDIO,
    # Video
    ".mp4": AssetType.VIDEO,
    ".mov": AssetType.VIDEO,
    ".avi": AssetType.VIDEO,
    ".webm": AssetType.VIDEO,
    # 3D Models
    ".fbx": AssetType.MODEL,
    ".obj": AssetType.MODEL,
    ".dae": AssetType.MODEL,
    ".3ds": AssetType.MODEL,
    ".blend": AssetType.MODEL,
    ".max": AssetType.MODEL,
    ".ma": AssetType.MODEL,
    ".mb": AssetType.MODEL,
    # Shaders
    ".shader": AssetType.SHADER,
    ".cginc": AssetType.SHADER,
    ".hlsl": AssetType.SHADER,
    ".glsl": AssetType.SHADER,
    ".compute": AssetType.SHADER,
    # Unity YAML assets
    ".mat": AssetType.MATERIAL,
    ".prefab": AssetType.PREFAB,
    ".unity": AssetType.SCENE,
    ".asset": AssetType.SCRIPTABLE_OBJECT,
    # Animation
    ".anim": AssetType.ANIMATION,
    ".controller": AssetType.ANIMATION,
    ".overrideController": AssetType.ANIMATION,
    ".playable": AssetType.ANIMATION,
    ".mask": AssetType.ANIMATION,
    # Fonts
    ".ttf": AssetType.FONT,
    ".otf": AssetType.FONT,
    ".fon": AssetType.FONT,
    # Text/Data
    ".txt": AssetType.TEXT,
    ".json": AssetType.TEXT,
    ".xml": AssetType.TEXT,
    ".csv": AssetType.TEXT,
    ".bytes": AssetType.TEXT,
    ".html": AssetType.TEXT,
    ".htm": AssetType.TEXT,
    ".yaml": AssetType.TEXT,
    ".yml": AssetType.TEXT,
    # Plugins
    ".dll": AssetType.PLUGIN,
    ".so": AssetType.PLUGIN,
    ".dylib": AssetType.PLUGIN,
}


def generate_guid(seed: str | None = None) -> str:
    """Generate a Unity-compatible GUID (32 hex characters).

    Args:
        seed: Optional seed string for deterministic GUID generation.
              If provided, the same seed always produces the same GUID.
              If None, generates a random GUID.

    Returns:
        32-character lowercase hex string (Unity GUID format)
    """
    if seed is not None:
        # Deterministic GUID based on seed (useful for reproducible builds)
        hash_bytes = hashlib.md5(seed.encode("utf-8")).digest()
        return hash_bytes.hex()
    else:
        # Random GUID
        return uuid.uuid4().hex


def detect_asset_type(path: Path) -> AssetType:
    """Detect the asset type from file path.

    Args:
        path: Path to the asset file

    Returns:
        Detected AssetType
    """
    if path.is_dir():
        return AssetType.FOLDER

    ext = path.suffix.lower()
    return EXTENSION_TO_TYPE.get(ext, AssetType.DEFAULT)


@dataclass
class MetaFileOptions:
    """Options for meta file generation."""

    # Common options
    guid: str | None = None  # Auto-generated if None
    labels: list[str] = field(default_factory=list)
    asset_bundle_name: str = ""
    asset_bundle_variant: str = ""

    # Texture options
    texture_type: str = "Default"  # Default, NormalMap, Sprite, Cursor, Cookie, Lightmap, etc.
    sprite_mode: int = 1  # 0=None, 1=Single, 2=Multiple
    sprite_pixels_per_unit: int = 100
    sprite_pivot: tuple[float, float] = (0.5, 0.5)
    filter_mode: int = 1  # 0=Point, 1=Bilinear, 2=Trilinear
    max_texture_size: int = 2048
    texture_compression: str = "Compressed"

    # Audio options
    load_type: int = 0  # 0=DecompressOnLoad, 1=CompressedInMemory, 2=Streaming
    force_mono: bool = False

    # Model options
    import_materials: bool = True
    import_animation: bool = True
    mesh_compression: int = 0  # 0=Off, 1=Low, 2=Medium, 3=High

    # Script options
    execution_order: int = 0
    icon: str = ""

    # Use seed for deterministic GUID generation
    guid_seed: str | None = None


def _generate_folder_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a folder."""
    return f"""fileFormatVersion: 2
guid: {guid}
folderAsset: yes
DefaultImporter:
  externalObjects: {{}}
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_script_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a C# script."""
    icon_line = f"  icon: {options.icon}" if options.icon else "  icon: {instanceID: 0}"
    return f"""fileFormatVersion: 2
guid: {guid}
MonoImporter:
  externalObjects: {{}}
  serializedVersion: 2
  defaultReferences: []
  executionOrder: {options.execution_order}
{icon_line}
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_texture_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a texture."""
    # Determine texture import settings based on texture type
    sprite_mode = options.sprite_mode if options.texture_type == "Sprite" else 0

    return f"""fileFormatVersion: 2
guid: {guid}
TextureImporter:
  internalIDToNameTable: []
  externalObjects: {{}}
  serializedVersion: 12
  mipmaps:
    mipMapMode: 0
    enableMipMap: 1
    sRGBTexture: 1
    linearTexture: 0
    fadeOut: 0
    borderMipMap: 0
    mipMapsPreserveCoverage: 0
    alphaTestReferenceValue: 0.5
    mipMapFadeDistanceStart: 1
    mipMapFadeDistanceEnd: 3
  bumpmap:
    convertToNormalMap: 0
    externalNormalMap: 0
    heightScale: 0.25
    normalMapFilter: 0
    flipGreenChannel: 0
  isReadable: 0
  streamingMipmaps: 0
  streamingMipmapsPriority: 0
  vTOnly: 0
  ignoreMipmapLimit: 0
  grayScaleToAlpha: 0
  generateCubemap: 6
  cubemapConvolution: 0
  seamlessCubemap: 0
  textureFormat: 1
  maxTextureSize: {options.max_texture_size}
  textureSettings:
    serializedVersion: 2
    filterMode: {options.filter_mode}
    aniso: 1
    mipBias: 0
    wrapU: 0
    wrapV: 0
    wrapW: 0
  nPOTScale: 1
  lightmap: 0
  compressionQuality: 50
  spriteMode: {sprite_mode}
  spriteExtrude: 1
  spriteMeshType: 1
  alignment: 0
  spritePivot: {{x: {options.sprite_pivot[0]}, y: {options.sprite_pivot[1]}}}
  spritePixelsToUnits: {options.sprite_pixels_per_unit}
  spriteBorder: {{x: 0, y: 0, z: 0, w: 0}}
  spriteGenerateFallbackPhysicsShape: 1
  alphaUsage: 1
  alphaIsTransparency: 0
  spriteTessellationDetail: -1
  textureType: {_get_texture_type_id(options.texture_type)}
  textureShape: 1
  singleChannelComponent: 0
  flipbookRows: 1
  flipbookColumns: 1
  maxTextureSizeSet: 0
  compressionQualitySet: 0
  textureFormatSet: 0
  ignorePngGamma: 0
  applyGammaDecoding: 0
  swizzle: 50462976
  cookieLightType: 0
  platformSettings:
  - serializedVersion: 3
    buildTarget: DefaultTexturePlatform
    maxTextureSize: {options.max_texture_size}
    resizeAlgorithm: 0
    textureFormat: -1
    textureCompression: 1
    compressionQuality: 50
    crunchedCompression: 0
    allowsAlphaSplitting: 0
    overridden: 0
    ignorePlatformSupport: 0
    androidETC2FallbackOverride: 0
    forceMaximumCompressionQuality_BC6H_BC7: 0
  spriteSheet:
    serializedVersion: 2
    sprites: []
    outline: []
    physicsShape: []
    bones: []
    spriteID:
    internalID: 0
    vertices: []
    indices:
    edges: []
    weights: []
    secondaryTextures: []
    nameFileIdTable: {{}}
  mipmapLimitGroupName:
  pSDRemoveMatte: 0
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _get_texture_type_id(texture_type: str) -> int:
    """Convert texture type name to Unity's internal ID."""
    type_map = {
        "Default": 0,
        "NormalMap": 1,
        "GUI": 2,  # Legacy
        "Sprite": 8,
        "Cursor": 7,
        "Cookie": 4,
        "Lightmap": 6,
        "DirectionalLightmap": 11,
        "Shadowmask": 12,
        "SingleChannel": 10,
    }
    return type_map.get(texture_type, 0)


def _generate_audio_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for an audio file."""
    return f"""fileFormatVersion: 2
guid: {guid}
AudioImporter:
  externalObjects: {{}}
  serializedVersion: 7
  defaultSettings:
    serializedVersion: 2
    loadType: {options.load_type}
    sampleRateSetting: 0
    sampleRateOverride: 44100
    compressionFormat: 1
    quality: 1
    conversionMode: 0
    preloadAudioData: 1
  platformSettingOverrides: {{}}
  forceToMono: {1 if options.force_mono else 0}
  normalize: 1
  loadInBackground: 0
  ambisonic: 0
  3D: 1
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_video_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a video file."""
    return f"""fileFormatVersion: 2
guid: {guid}
VideoClipImporter:
  externalObjects: {{}}
  serializedVersion: 2
  frameRange: 0
  startFrame: -1
  endFrame: -1
  colorSpace: 0
  deinterlace: 0
  encodeAlpha: 0
  flipVertical: 0
  flipHorizontal: 0
  importAudio: 1
  targetSettings: {{}}
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_model_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a 3D model."""
    return f"""fileFormatVersion: 2
guid: {guid}
ModelImporter:
  serializedVersion: 22200
  internalIDToNameTable: []
  externalObjects: {{}}
  materials:
    materialImportMode: {1 if options.import_materials else 0}
    materialName: 0
    materialSearch: 1
    materialLocation: 1
  animations:
    legacyGenerateAnimations: 4
    bakeSimulation: 0
    resampleCurves: 1
    optimizeGameObjects: 0
    removeConstantScaleCurves: 0
    motionNodeName:
    rigImportErrors:
    rigImportWarnings:
    animationImportErrors:
    animationImportWarnings:
    animationRetargetingWarnings:
    animationDoRetargetingWarnings: 0
    importAnimatedCustomProperties: 0
    importConstraints: 0
    animationCompression: {options.mesh_compression}
    animationRotationError: 0.5
    animationPositionError: 0.5
    animationScaleError: 0.5
    animationWrapMode: 0
    extraExposedTransformPaths: []
    extraUserProperties: []
    clipAnimations: []
    isReadable: 0
  meshes:
    lODScreenPercentages: []
    globalScale: 1
    meshCompression: {options.mesh_compression}
    addColliders: 0
    useSRGBMaterialColor: 1
    sortHierarchyByName: 1
    importPhysicalCameras: 1
    importVisibility: 1
    importBlendShapes: 1
    importCameras: 1
    importLights: 1
    nodeNameCollisionStrategy: 1
    fileIdsGeneration: 2
    swapUVChannels: 0
    generateSecondaryUV: 0
    useFileUnits: 1
    keepQuads: 0
    weldVertices: 1
    bakeAxisConversion: 0
    preserveHierarchy: 0
    skinWeightsMode: 0
    maxBonesPerVertex: 4
    minBoneWeight: 0.001
    optimizeMeshPolygons: 1
    optimizeMeshVertices: 1
    meshOptimizationFlags: -1
    indexFormat: 0
    secondaryUVAngleDistortion: 8
    secondaryUVAreaDistortion: 15.000001
    secondaryUVHardAngle: 88
    secondaryUVMarginMethod: 1
    secondaryUVMinLightmapResolution: 40
    secondaryUVMinObjectScale: 1
    secondaryUVPackMargin: 4
    useFileScale: 1
    strictVertexDataChecks: 0
  tangentSpace:
    normalSmoothAngle: 60
    normalImportMode: 0
    tangentImportMode: 3
    normalCalculationMode: 4
    legacyComputeAllNormalsFromSmoothingGroupsWhenMeshHasBlendShapes: 0
    blendShapeNormalImportMode: 1
  referencedClips: []
  importAnimation: {1 if options.import_animation else 0}
  humanDescription:
    serializedVersion: 3
    human: []
    skeleton: []
    armTwist: 0.5
    foreArmTwist: 0.5
    upperLegTwist: 0.5
    legTwist: 0.5
    armStretch: 0.05
    legStretch: 0.05
    feetSpacing: 0
    globalScale: 1
    rootMotionBoneName:
    hasTranslationDoF: 0
    hasExtraRoot: 0
    skeletonHasParents: 1
  lastHumanDescriptionAvatarSource: {{instanceID: 0}}
  autoGenerateAvatarMappingIfUnspecified: 1
  animationType: 2
  humanoidOversampling: 1
  avatarSetup: 0
  addHumanoidExtraRootOnlyWhenUsingAvatar: 1
  importBlendShapeDeformPercent: 1
  remapMaterialsIfMaterialImportModeIsNone: 0
  additionalBone: 0
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_shader_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a shader."""
    return f"""fileFormatVersion: 2
guid: {guid}
ShaderImporter:
  externalObjects: {{}}
  defaultTextures: []
  nonModifiableTextures: []
  preprocessorOverride: 0
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_font_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a font file."""
    return f"""fileFormatVersion: 2
guid: {guid}
TrueTypeFontImporter:
  externalObjects: {{}}
  serializedVersion: 4
  fontSize: 16
  forceTextureCase: -2
  characterSpacing: 0
  characterPadding: 1
  includeFontData: 1
  fontName:
  fallbackFontReferences: []
  fontNames: []
  customCharacters:
  fontRenderingMode: 0
  ascentCalculationMode: 1
  useLegacyBoundsCalculation: 0
  shouldRoundAdvanceValue: 1
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_text_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a text file."""
    return f"""fileFormatVersion: 2
guid: {guid}
TextScriptImporter:
  externalObjects: {{}}
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_plugin_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for a native plugin."""
    return f"""fileFormatVersion: 2
guid: {guid}
PluginImporter:
  externalObjects: {{}}
  serializedVersion: 2
  iconMap: {{}}
  executionOrder: {{}}
  defineConstraints: []
  isPreloaded: 0
  isOverridable: 0
  isExplicitlyReferenced: 0
  validateReferences: 1
  platformData:
  - first:
      Any:
    second:
      enabled: 1
      settings: {{}}
  - first:
      Editor: Editor
    second:
      enabled: 1
      settings:
        DefaultValueInitialized: true
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_default_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for default/Unity YAML assets."""
    return f"""fileFormatVersion: 2
guid: {guid}
DefaultImporter:
  externalObjects: {{}}
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


def _generate_native_format_meta(guid: str, options: MetaFileOptions) -> str:
    """Generate meta file content for native Unity formats (prefab, scene, etc.)."""
    return f"""fileFormatVersion: 2
guid: {guid}
NativeFormatImporter:
  externalObjects: {{}}
  mainObjectFileID: 100100000
  userData:
  assetBundleName: {options.asset_bundle_name}
  assetBundleVariant: {options.asset_bundle_variant}
"""


# Generator function mapping
META_GENERATORS: dict[AssetType, callable] = {
    AssetType.FOLDER: _generate_folder_meta,
    AssetType.SCRIPT: _generate_script_meta,
    AssetType.TEXTURE: _generate_texture_meta,
    AssetType.AUDIO: _generate_audio_meta,
    AssetType.VIDEO: _generate_video_meta,
    AssetType.MODEL: _generate_model_meta,
    AssetType.SHADER: _generate_shader_meta,
    AssetType.FONT: _generate_font_meta,
    AssetType.TEXT: _generate_text_meta,
    AssetType.PLUGIN: _generate_plugin_meta,
    AssetType.MATERIAL: _generate_default_meta,
    AssetType.PREFAB: _generate_default_meta,
    AssetType.SCENE: _generate_default_meta,
    AssetType.SCRIPTABLE_OBJECT: _generate_default_meta,
    AssetType.ANIMATION: _generate_native_format_meta,
    AssetType.DEFAULT: _generate_default_meta,
}


def generate_meta_content(
    path: Path,
    asset_type: AssetType | None = None,
    options: MetaFileOptions | None = None,
) -> str:
    """Generate .meta file content for an asset.

    Args:
        path: Path to the asset (file or folder)
        asset_type: Asset type to use (auto-detected if None)
        options: Meta file generation options

    Returns:
        Meta file content as string
    """
    if options is None:
        options = MetaFileOptions()

    if asset_type is None:
        asset_type = detect_asset_type(path)

    # Generate or use provided GUID
    if options.guid:
        guid = options.guid
    elif options.guid_seed:
        guid = generate_guid(options.guid_seed)
    else:
        guid = generate_guid()

    generator = META_GENERATORS.get(asset_type, _generate_default_meta)
    return generator(guid, options)


def generate_meta_file(
    path: Path,
    asset_type: AssetType | None = None,
    options: MetaFileOptions | None = None,
    overwrite: bool = False,
) -> Path:
    """Generate a .meta file for an asset and write it to disk.

    Args:
        path: Path to the asset (file or folder)
        asset_type: Asset type to use (auto-detected if None)
        options: Meta file generation options
        overwrite: Whether to overwrite existing .meta file

    Returns:
        Path to the generated .meta file

    Raises:
        FileExistsError: If meta file exists and overwrite is False
        FileNotFoundError: If asset path doesn't exist
    """
    path = Path(path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Asset path does not exist: {path}")

    meta_path = Path(str(path) + ".meta")

    if meta_path.exists() and not overwrite:
        raise FileExistsError(f"Meta file already exists: {meta_path}")

    content = generate_meta_content(path, asset_type, options)
    meta_path.write_text(content, encoding="utf-8", newline="\n")

    return meta_path


def generate_meta_files_recursive(
    directory: Path,
    overwrite: bool = False,
    skip_existing: bool = True,
    options: MetaFileOptions | None = None,
    progress_callback: callable | None = None,
) -> list[tuple[Path, bool, str]]:
    """Generate .meta files for all assets in a directory recursively.

    Args:
        directory: Directory to process
        overwrite: Whether to overwrite existing .meta files
        skip_existing: Skip files that already have .meta files (ignored if overwrite=True)
        options: Base options for meta file generation
        progress_callback: Optional callback for progress (current, total)

    Returns:
        List of (path, success, message) tuples
    """
    directory = Path(directory).resolve()

    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    # Collect all files and folders that need .meta files
    items_to_process: list[Path] = []

    for item in directory.rglob("*"):
        # Skip .meta files themselves
        if item.suffix == ".meta":
            continue

        # Skip hidden files/folders
        if any(part.startswith(".") for part in item.parts):
            continue

        meta_path = Path(str(item) + ".meta")

        if meta_path.exists():
            if overwrite:
                items_to_process.append(item)
            elif not skip_existing:
                # Report as skipped
                pass
        else:
            items_to_process.append(item)

    # Also include the directory itself if it doesn't have a meta file
    dir_meta = Path(str(directory) + ".meta")
    if not dir_meta.exists() or overwrite:
        items_to_process.insert(0, directory)

    total = len(items_to_process)
    results: list[tuple[Path, bool, str]] = []

    for i, item in enumerate(items_to_process):
        if progress_callback:
            progress_callback(i + 1, total)

        try:
            generate_meta_file(item, options=options, overwrite=overwrite)
            results.append((item, True, ""))
        except Exception as e:
            results.append((item, False, str(e)))

    return results


def ensure_meta_file(
    path: Path,
    options: MetaFileOptions | None = None,
) -> tuple[Path, bool]:
    """Ensure an asset has a .meta file, creating one if needed.

    Args:
        path: Path to the asset
        options: Meta file generation options

    Returns:
        Tuple of (meta_path, was_created)
    """
    path = Path(path).resolve()
    meta_path = Path(str(path) + ".meta")

    if meta_path.exists():
        return meta_path, False

    generate_meta_file(path, options=options, overwrite=False)
    return meta_path, True


def get_guid_from_meta(meta_path: Path) -> str | None:
    """Extract GUID from an existing .meta file.

    Args:
        meta_path: Path to the .meta file

    Returns:
        GUID string or None if not found
    """
    import re

    pattern = re.compile(r"^guid:\s*([a-f0-9]{32})\s*$", re.MULTILINE)

    try:
        content = meta_path.read_text(encoding="utf-8")
        match = pattern.search(content)
        if match:
            return match.group(1)
    except OSError:
        pass

    return None


# ============================================================================
# Meta File Modification Functions
# ============================================================================


@dataclass
class MetaModification:
    """Represents a modification to be applied to a meta file."""

    field_path: str  # Dot-separated path like "TextureImporter.spriteMode"
    value: Any
    create_if_missing: bool = False


def parse_meta_file(meta_path: Path) -> dict[str, Any]:
    """Parse a .meta file into a dictionary structure.

    Args:
        meta_path: Path to the .meta file

    Returns:
        Dictionary representation of the meta file

    Raises:
        FileNotFoundError: If meta file doesn't exist
        ValueError: If meta file is invalid
    """

    if not meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {meta_path}")

    content = meta_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    result: dict[str, Any] = {}
    stack: list[tuple[dict, int]] = [(result, -1)]  # (current_dict, indent_level)

    for line in lines:
        if not line.strip() or line.startswith("%"):
            continue

        # Calculate indent level
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Parse key-value
        if ":" in stripped:
            colon_idx = stripped.index(":")
            key = stripped[:colon_idx].strip()
            value_part = stripped[colon_idx + 1 :].strip()

            # Pop stack until we find the right parent
            while len(stack) > 1 and stack[-1][1] >= indent:
                stack.pop()

            current_dict = stack[-1][0]

            if value_part == "" or value_part.startswith("#"):
                # This is a nested object
                new_dict: dict[str, Any] = {}
                current_dict[key] = new_dict
                stack.append((new_dict, indent))
            elif value_part == "[]":
                current_dict[key] = []
            elif value_part == "{}":
                current_dict[key] = {}
            else:
                # Parse the value
                current_dict[key] = _parse_yaml_value(value_part)

    return result


def _parse_yaml_value(value_str: str) -> Any:
    """Parse a YAML value string into Python type."""
    value_str = value_str.strip()

    # Handle inline dict like {x: 0, y: 0}
    if value_str.startswith("{") and value_str.endswith("}"):
        inner = value_str[1:-1].strip()
        if not inner:
            return {}
        result = {}
        # Simple parsing for Unity's inline format
        parts = inner.split(",")
        for part in parts:
            if ":" in part:
                k, v = part.split(":", 1)
                result[k.strip()] = _parse_yaml_value(v.strip())
        return result

    # Handle numbers
    if value_str.isdigit() or (value_str.startswith("-") and value_str[1:].isdigit()):
        return int(value_str)

    try:
        return float(value_str)
    except ValueError:
        pass

    # Handle booleans
    if value_str.lower() in ("true", "yes", "on"):
        return True
    if value_str.lower() in ("false", "no", "off"):
        return False

    # Handle quoted strings
    if (value_str.startswith('"') and value_str.endswith('"')) or (
        value_str.startswith("'") and value_str.endswith("'")
    ):
        return value_str[1:-1]

    return value_str


def _serialize_yaml_value(value: Any, indent: int = 0) -> str:
    """Serialize a Python value to YAML string."""
    if isinstance(value, bool):
        return "1" if value else "0"
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        # Format float without unnecessary trailing zeros
        if value == int(value):
            return str(int(value))
        return str(value)
    elif isinstance(value, dict):
        if not value:
            return "{}"
        # Inline dict format for simple values
        if all(isinstance(v, (int, float, str)) for v in value.values()):
            parts = [f"{k}: {_serialize_yaml_value(v)}" for k, v in value.items()]
            return "{" + ", ".join(parts) + "}"
        # Multi-line dict
        lines = []
        for k, v in value.items():
            lines.append(f"{' ' * indent}{k}: {_serialize_yaml_value(v, indent + 2)}")
        return "\n" + "\n".join(lines)
    elif isinstance(value, list):
        if not value:
            return "[]"
        lines = []
        for item in value:
            lines.append(f"{' ' * indent}- {_serialize_yaml_value(item, indent + 2)}")
        return "\n" + "\n".join(lines)
    elif value is None:
        return ""
    else:
        return str(value)


def modify_meta_file(
    meta_path: Path,
    modifications: dict[str, Any],
) -> Path:
    """Modify specific fields in an existing .meta file.

    Note: GUID modification is not allowed to prevent breaking asset references.
    Use generate-meta with --overwrite if you need to regenerate with a new GUID.

    Args:
        meta_path: Path to the .meta file
        modifications: Dictionary of field paths to new values
                      Keys are dot-separated paths like "TextureImporter.spriteMode"

    Returns:
        Path to the modified .meta file

    Raises:
        FileNotFoundError: If meta file doesn't exist
        ValueError: If attempting to modify GUID
    """
    meta_path = Path(meta_path)
    if not meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {meta_path}")

    # GUID modification is not allowed
    if "guid" in modifications:
        raise ValueError(
            "GUID modification is not allowed. "
            "Changing GUID will break all references to this asset. "
            "Use 'generate-meta --overwrite' if you need a new GUID."
        )

    content = meta_path.read_text(encoding="utf-8")

    # Apply modifications line by line for precise control
    lines = content.split("\n")
    modified_lines = _apply_modifications(lines, modifications)

    new_content = "\n".join(modified_lines)
    meta_path.write_text(new_content, encoding="utf-8", newline="\n")

    return meta_path


def _apply_modifications(lines: list[str], modifications: dict[str, Any]) -> list[str]:
    """Apply modifications to meta file lines."""

    result = lines.copy()

    for field_path, value in modifications.items():
        parts = field_path.split(".")
        result = _modify_field(result, parts, value)

    return result


def _modify_field(lines: list[str], path_parts: list[str], value: Any) -> list[str]:
    """Modify a specific field in the lines."""
    result = lines.copy()

    if len(path_parts) == 1:
        # Top-level field
        field_name = path_parts[0]
        for i, line in enumerate(result):
            stripped = line.lstrip()
            if stripped.startswith(f"{field_name}:"):
                indent = len(line) - len(stripped)
                result[i] = f"{' ' * indent}{field_name}: {_serialize_yaml_value(value)}"
                break
    else:
        # Nested field - find parent section first
        parent_path = path_parts[:-1]
        field_name = path_parts[-1]

        current_path: list[str] = []
        indent_stack: list[int] = [-1]

        for i, line in enumerate(result):
            if not line.strip():
                continue

            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # Pop stack for lower indents
            while indent_stack and indent <= indent_stack[-1]:
                indent_stack.pop()
                if current_path:
                    current_path.pop()

            if ":" in stripped:
                key = stripped.split(":")[0].strip()
                value_part = stripped.split(":", 1)[1].strip() if ":" in stripped else ""

                if value_part == "" or value_part.startswith("#"):
                    # Section header
                    current_path.append(key)
                    indent_stack.append(indent)

                    if current_path == parent_path:
                        pass  # Found parent section
                elif current_path == parent_path and key == field_name:
                    # Found the field to modify
                    result[i] = f"{' ' * indent}{field_name}: {_serialize_yaml_value(value)}"
                    return result

        # If we found the section but not the field, the field might need to be added
        # For now, just return as-is if not found

    return result


def set_texture_sprite_mode(
    meta_path: Path,
    sprite_mode: int = 1,
    pixels_per_unit: int | None = None,
    filter_mode: int | None = None,
) -> Path:
    """Set texture import settings for sprite mode.

    Args:
        meta_path: Path to the texture .meta file
        sprite_mode: 0=None, 1=Single, 2=Multiple
        pixels_per_unit: Pixels per unit (default: keep existing)
        filter_mode: 0=Point, 1=Bilinear, 2=Trilinear (default: keep existing)

    Returns:
        Path to the modified .meta file
    """
    meta_path = Path(meta_path)
    content = meta_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    modifications = []

    # Set textureType to Sprite (8) if enabling sprite mode
    if sprite_mode > 0:
        modifications.append(("textureType", 8))
    modifications.append(("spriteMode", sprite_mode))

    if pixels_per_unit is not None:
        modifications.append(("spritePixelsToUnits", pixels_per_unit))

    if filter_mode is not None:
        modifications.append(("filterMode", filter_mode))

    for field_name, value in modifications:
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(f"{field_name}:"):
                indent = len(line) - len(stripped)
                lines[i] = f"{' ' * indent}{field_name}: {value}"
                break

    new_content = "\n".join(lines)
    meta_path.write_text(new_content, encoding="utf-8", newline="\n")

    return meta_path


def set_script_execution_order(meta_path: Path, execution_order: int) -> Path:
    """Set script execution order in a MonoImporter .meta file.

    Args:
        meta_path: Path to the script .meta file
        execution_order: Execution order value (negative = earlier, positive = later)

    Returns:
        Path to the modified .meta file
    """
    meta_path = Path(meta_path)
    content = meta_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("executionOrder:"):
            indent = len(line) - len(stripped)
            lines[i] = f"{' ' * indent}executionOrder: {execution_order}"
            break

    new_content = "\n".join(lines)
    meta_path.write_text(new_content, encoding="utf-8", newline="\n")

    return meta_path


def set_asset_bundle(
    meta_path: Path,
    bundle_name: str = "",
    bundle_variant: str = "",
) -> Path:
    """Set asset bundle name and variant in a .meta file.

    Args:
        meta_path: Path to the .meta file
        bundle_name: Asset bundle name (empty string to clear)
        bundle_variant: Asset bundle variant (empty string to clear)

    Returns:
        Path to the modified .meta file
    """
    meta_path = Path(meta_path)
    content = meta_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("assetBundleName:"):
            indent = len(line) - len(stripped)
            lines[i] = f"{' ' * indent}assetBundleName: {bundle_name}"
        elif stripped.startswith("assetBundleVariant:"):
            indent = len(line) - len(stripped)
            lines[i] = f"{' ' * indent}assetBundleVariant: {bundle_variant}"

    new_content = "\n".join(lines)
    meta_path.write_text(new_content, encoding="utf-8", newline="\n")

    return meta_path


def set_texture_max_size(meta_path: Path, max_size: int) -> Path:
    """Set maximum texture size in a TextureImporter .meta file.

    Args:
        meta_path: Path to the texture .meta file
        max_size: Maximum texture size (32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384)

    Returns:
        Path to the modified .meta file
    """
    valid_sizes = {32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384}
    if max_size not in valid_sizes:
        raise ValueError(f"Invalid max size: {max_size}. Must be one of {sorted(valid_sizes)}")

    meta_path = Path(meta_path)
    content = meta_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("maxTextureSize:"):
            indent = len(line) - len(stripped)
            lines[i] = f"{' ' * indent}maxTextureSize: {max_size}"

    new_content = "\n".join(lines)
    meta_path.write_text(new_content, encoding="utf-8", newline="\n")

    return meta_path


def get_meta_info(meta_path: Path) -> dict[str, Any]:
    """Get summary information from a .meta file.

    Args:
        meta_path: Path to the .meta file

    Returns:
        Dictionary with meta file information
    """
    meta_path = Path(meta_path)
    if not meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {meta_path}")

    content = meta_path.read_text(encoding="utf-8")

    info: dict[str, Any] = {
        "path": str(meta_path),
        "guid": get_guid_from_meta(meta_path),
        "importer_type": None,
        "asset_bundle_name": None,
        "asset_bundle_variant": None,
    }

    # Detect importer type
    importer_types = [
        "DefaultImporter",
        "MonoImporter",
        "TextureImporter",
        "AudioImporter",
        "VideoClipImporter",
        "ModelImporter",
        "ShaderImporter",
        "PluginImporter",
        "TrueTypeFontImporter",
        "TextScriptImporter",
        "NativeFormatImporter",
    ]
    for importer in importer_types:
        if f"{importer}:" in content:
            info["importer_type"] = importer
            break

    # Extract specific fields
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("assetBundleName:"):
            value = stripped.split(":", 1)[1].strip()
            info["asset_bundle_name"] = value if value else None
        elif stripped.startswith("assetBundleVariant:"):
            value = stripped.split(":", 1)[1].strip()
            info["asset_bundle_variant"] = value if value else None
        elif stripped.startswith("spriteMode:"):
            info["sprite_mode"] = int(stripped.split(":")[1].strip())
        elif stripped.startswith("spritePixelsToUnits:"):
            info["pixels_per_unit"] = int(stripped.split(":")[1].strip())
        elif stripped.startswith("executionOrder:"):
            info["execution_order"] = int(stripped.split(":")[1].strip())
        elif stripped.startswith("maxTextureSize:") and "maxTextureSize" not in info:
            info["max_texture_size"] = int(stripped.split(":")[1].strip())
        elif stripped.startswith("textureType:"):
            info["texture_type"] = int(stripped.split(":")[1].strip())
        elif stripped.startswith("filterMode:"):
            info["filter_mode"] = int(stripped.split(":")[1].strip())

    return info
