// Unity API stubs for CI compilation verification
// These provide minimal type definitions to verify C# syntax without Unity installation

namespace UnityEngine
{
    public class Object
    {
        public string name;
        public int GetInstanceID() => 0;
        public static void DestroyImmediate(Object o) {}
        public static T Instantiate<T>(T original) where T : Object => original;
        public static Object Instantiate(Object original) => original;
    }
    public class Component : Object { public GameObject gameObject; }
    public class Behaviour : Component { public bool enabled; }
    public class MonoBehaviour : Behaviour { }
    public class GameObject : Object
    {
        public GameObject() {}
        public GameObject(string name) {}
        public Transform transform;
        public T GetComponent<T>() where T : class => default;
        public T[] GetComponents<T>() where T : class => new T[0];
        public T[] GetComponentsInChildren<T>() where T : class => new T[0];
        public T AddComponent<T>() where T : Component => default;
        public static GameObject Find(string name) => null;
        public bool activeSelf => true;
        public string tag;
        public int layer;
    }
    public class Transform : Component
    {
        public Vector3 localPosition;
        public Vector3 localEulerAngles;
        public Vector3 localScale;
        public Vector3 position;
        public Quaternion rotation;
        public int childCount;
        public Transform GetChild(int i) => null;
        public Transform parent;
        public void LookAt(Vector3 target) {}
    }
    public struct Vector2 { public float x, y; }
    public struct Vector3
    {
        public float x, y, z;
        public static Vector3 zero;
        public static Vector3 one;
        public Vector3 normalized => this;
        public static Vector3 operator +(Vector3 a, Vector3 b) => a;
        public static Vector3 operator *(Vector3 a, float b) => a;
        public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; }
    }
    public struct Vector4 { public float x, y, z, w; }
    public struct Color
    {
        public float r, g, b, a;
        public Color(float r, float g, float b, float a) { this.r = r; this.g = g; this.b = b; this.a = a; }
        public static Color red => new Color(1, 0, 0, 1);
        public static Color green => new Color(0, 1, 0, 1);
        public static Color blue => new Color(0, 0, 1, 1);
        public static Color white => new Color(1, 1, 1, 1);
        public static Color black => new Color(0, 0, 0, 1);
        public static Color yellow => new Color(1, 1, 0, 1);
    }
    public struct Rect { public float x, y, width, height; public Rect(float x, float y, float w, float h) { this.x = x; this.y = y; this.width = w; this.height = h; } }
    public struct Bounds
    {
        public Vector3 center;
        public Vector3 extents;
        public Vector3 size;
        public Bounds(Vector3 center, Vector3 size) { this.center = center; this.size = size; this.extents = size; }
        public void Encapsulate(Bounds b) {}
    }
    public struct Quaternion { public static Quaternion identity; public static Quaternion Euler(float x, float y, float z) => identity; public Vector3 eulerAngles; }
    public class Camera : Behaviour
    {
        public static Camera main;
        public RenderTexture targetTexture;
        public Transform transform;
        public void Render() {}
        public CameraClearFlags clearFlags;
        public Color backgroundColor;
        public float nearClipPlane;
        public float farClipPlane;
        public UnityEngine.SceneManagement.Scene scene;
    }
    public enum CameraClearFlags { Skybox, SolidColor, Depth, Nothing }
    public class Texture : Object { public int width; public int height; }
    public class Texture2D : Texture
    {
        public Texture2D(int w, int h) {}
        public Texture2D(int w, int h, TextureFormat f, bool m) {}
        public void ReadPixels(Rect r, int x, int y) {}
        public void Apply() {}
        public byte[] EncodeToPNG() => new byte[0];
        public bool LoadImage(byte[] data) => true;
        public TextureFormat format;
    }
    public enum TextureFormat { RGB24, ARGB32 }
    public class RenderTexture : Texture
    {
        public static RenderTexture active;
        public static RenderTexture GetTemporary(int w, int h, int d, RenderTextureFormat f) => null;
        public static void ReleaseTemporary(RenderTexture rt) {}
    }
    public enum RenderTextureFormat { ARGB32 }
    public class Debug { public static void Log(object msg) {} public static void LogError(object msg) {} public static void LogWarning(object msg) {} }
    public class Application
    {
        public static string unityVersion;
        public static string productName;
        public static event System.Action<string, string, LogType> logMessageReceived;
    }
    public enum LogType { Log, Warning, Error, Exception, Assert }
    public class Renderer : Behaviour { public Bounds bounds; }
    public class Collider : Behaviour { }
    public class Light : Behaviour { public LightType type; public float intensity; }
    public enum LightType { Directional, Point, Spot }
    public class Animator : Behaviour
    {
        public RuntimeAnimatorController runtimeAnimatorController;
        public int parameterCount;
        public AnimatorControllerParameter GetParameter(int i) => null;
        public AnimatorStateInfo GetCurrentAnimatorStateInfo(int layer) => default;
        public bool IsInTransition(int layer) => false;
        public int layerCount;
        public string GetLayerName(int i) => "";
        public float GetLayerWeight(int i) => 0;
        public bool GetBool(string name) => false;
        public int GetInteger(string name) => 0;
        public float GetFloat(string name) => 0;
    }
    public class RuntimeAnimatorController : Object { public AnimationClip[] animationClips => new AnimationClip[0]; }
    public class AnimatorControllerParameter { public string name; public AnimatorControllerParameterType type; }
    public enum AnimatorControllerParameterType { Bool, Int, Float, Trigger }
    public struct AnimatorStateInfo { public int shortNameHash; public float normalizedTime; public float length; public float speed; public bool loop; }
    public class Animation : Behaviour { public System.Collections.IEnumerator GetEnumerator() => null; }
    public class AnimationState { public string name; public AnimationClip clip; }
    public class AnimationClip : Object { public string name; public float length; public float frameRate; }
    public class Mathf
    {
        public static int Clamp(int v, int min, int max) => v;
        public static float Max(float a, float b) => a;
        public static float Max(float a, float b, float c) => a;
    }
    public class Graphics { public static void CopyTexture(Texture src, Texture dst) {} }
    public class GUILayoutOption {}
    public class GUIContent { public static GUIContent none; }
    public class GUIStyleState { public Color textColor; }
    public class GUIStyle
    {
        public GUIStyle() {}
        public GUIStyle(GUIStyle other) {}
        public GUIStyleState normal;
    }
    public class JsonUtility
    {
        public static string ToJson(object obj) => "";
        public static T FromJson<T>(string json) => default;
    }
    public class GUIUtility { public static int hotControl; }
    public class GUI
    {
        public static Color color;
        public static void Label(Rect r, string t, GUIStyle s) {}
        public static void Box(Rect r, GUIContent c) {}
        public static Vector2 BeginScrollView(Rect r, Vector2 p, Rect v) => p;
        public static void EndScrollView() {}
        public static void DrawTexture(Rect r, Texture t, ScaleMode m) {}
    }
    public enum ScaleMode { ScaleToFit, ScaleAndCrop, StretchToFill }
    public class GUILayout
    {
        public static void Label(string t, params GUILayoutOption[] o) {}
        public static bool Button(string t, params GUILayoutOption[] o) => false;
        public static void FlexibleSpace() {}
        public static GUILayoutOption Width(float w) => null;
    }
}

namespace UnityEngine.SceneManagement
{
    public struct Scene
    {
        public string name;
        public string path;
        public bool IsValid() => true;
        public bool isLoaded => true;
        public bool isDirty => false;
        public GameObject[] GetRootGameObjects() => new GameObject[0];
    }
    public class SceneManager
    {
        public static Scene GetSceneByPath(string p) => default;
        public static void MoveGameObjectToScene(GameObject go, Scene s) {}
        public static int sceneCountInBuildSettings => 0;
    }
    public class SceneUtility
    {
        public static string GetScenePathByBuildIndex(int buildIndex) => "";
    }
}

namespace UnityEditor
{
    public class EditorWindow : UnityEngine.Object
    {
        public static T GetWindow<T>(string title) where T : EditorWindow => null;
        public UnityEngine.Rect position;
        public void Repaint() {}
        public void Show() {}
    }
    public class EditorApplication
    {
        public static bool isPlaying;
        public static bool isPaused;
        public static bool isCompiling;
        public static event System.Action delayCall;
        public static void Step() {}
    }
    public class EditorPrefs
    {
        public static int GetInt(string k, int d) => d;
        public static void SetInt(string k, int v) {}
        public static bool GetBool(string k, bool d) => d;
        public static void SetBool(string k, bool v) {}
    }
    public class EditorGUILayout
    {
        public static void BeginHorizontal(params UnityEngine.GUILayoutOption[] o) {}
        public static void EndHorizontal() {}
        public static void LabelField(string t, params UnityEngine.GUILayoutOption[] o) {}
        public static void LabelField(string t, UnityEngine.GUIStyle s, params UnityEngine.GUILayoutOption[] o) {}
        public static int IntField(int v, params UnityEngine.GUILayoutOption[] o) => v;
        public static bool ToggleLeft(string t, bool v, params UnityEngine.GUILayoutOption[] o) => v;
        public static void Space(float p) {}
        public static void HelpBox(string msg, MessageType t) {}
        public static UnityEngine.Rect GetControlRect(bool h, float height) => default;
    }
    public enum MessageType { Info, Warning, Error }
    public class EditorGUI { public static void BeginDisabledGroup(bool d) {} public static void EndDisabledGroup() {} }
    public class EditorGUIUtility { public static float singleLineHeight; }
    public class EditorStyles { public static UnityEngine.GUIStyle boldLabel; public static UnityEngine.GUIStyle miniLabel; }
    public class EditorUtility { public static UnityEngine.Object InstanceIDToObject(int id) => null; }
    public class Selection { public static UnityEngine.GameObject[] gameObjects; public static UnityEngine.GameObject activeGameObject; }
    public class SceneView : EditorWindow
    {
        public static SceneView lastActiveSceneView;
        public UnityEngine.Camera camera;
        public UnityEngine.Vector3 pivot;
        public UnityEngine.Quaternion rotation;
        public float size;
        public bool orthographic;
        public bool in2DMode;
        public void FrameSelected() {}
    }
    public class AssetDatabase
    {
        public static T LoadAssetAtPath<T>(string p) where T : class => null;
        public static string[] FindAssets(string filter) => new string[0];
        public static string GUIDToAssetPath(string guid) => "";
    }
    public class AssetPreview
    {
        public static UnityEngine.Texture2D GetAssetPreview(UnityEngine.Object o) => null;
        public static void SetPreviewTextureCacheSize(int s) {}
    }
    public class PrefabUtility { public static UnityEngine.Object InstantiatePrefab(UnityEngine.Object o, UnityEngine.SceneManagement.Scene s) => null; }
    public class SerializedObject : System.IDisposable
    {
        public SerializedObject(UnityEngine.Object o) {}
        public SerializedProperty GetIterator() => null;
        public void Dispose() {}
    }
    public class SerializedProperty
    {
        public string name;
        public SerializedPropertyType propertyType;
        public bool NextVisible(bool e) => false;
        public int intValue;
        public bool boolValue;
        public float floatValue;
        public string stringValue;
        public int enumValueIndex;
        public string[] enumDisplayNames;
        public UnityEngine.Object objectReferenceValue;
        public UnityEngine.Vector2 vector2Value;
        public UnityEngine.Vector3 vector3Value;
        public UnityEngine.Vector4 vector4Value;
        public UnityEngine.Color colorValue;
        public UnityEngine.Rect rectValue;
        public UnityEngine.Bounds boundsValue;
    }
    public enum SerializedPropertyType { Integer, Boolean, Float, String, Enum, ObjectReference, Vector2, Vector3, Vector4, Color, Rect, Bounds, LayerMask, AnimationCurve, Generic }
    [System.AttributeUsage(System.AttributeTargets.Class)] public class InitializeOnLoadAttribute : System.Attribute { }
    [System.AttributeUsage(System.AttributeTargets.Method)] public class MenuItemAttribute : System.Attribute { public MenuItemAttribute(string p) {} }
    public class AnimationMode
    {
        public static void StartAnimationMode() {}
        public static void StopAnimationMode() {}
        public static void BeginSampling() {}
        public static void EndSampling() {}
        public static void SampleAnimationClip(UnityEngine.GameObject go, UnityEngine.AnimationClip clip, float time) {}
    }
}

namespace UnityEditor.SceneManagement
{
    public enum OpenSceneMode { Single, Additive, AdditiveWithoutLoading }
    public class EditorSceneManager
    {
        public static UnityEngine.SceneManagement.Scene GetActiveScene() => default;
        public static UnityEngine.SceneManagement.Scene NewPreviewScene() => default;
        public static void ClosePreviewScene(UnityEngine.SceneManagement.Scene s) {}
        public static UnityEngine.SceneManagement.Scene OpenScene(string scenePath, OpenSceneMode mode = OpenSceneMode.Single) => default;
        public static bool SaveCurrentModifiedScenesIfUserWantsTo() => true;
    }
}
