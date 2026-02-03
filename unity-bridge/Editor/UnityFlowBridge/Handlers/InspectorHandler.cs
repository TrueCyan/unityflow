using System.Net;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace UnityFlow.Bridge.Handlers
{
    public static class InspectorHandler
    {
        public static void Register(UnityFlowHttpServer server)
        {
            server.RegisterRoute("/api/inspector", HandleInspector);
        }

        private static string HandleInspector(HttpListenerRequest request, RequestContext ctx)
        {
            GameObject target = null;

            string idStr = request.QueryString["id"];
            string path = request.QueryString["path"];

            if (!string.IsNullOrEmpty(idStr) && int.TryParse(idStr, out int instanceId))
            {
                target = EditorUtility.InstanceIDToObject(instanceId) as GameObject;
            }
            else if (!string.IsNullOrEmpty(path))
            {
                target = GameObject.Find(path);
            }

            if (target == null)
            {
                ctx.StatusCode = 404;
                return "{\"error\":\"object not found\"}";
            }

            var sb = new StringBuilder();
            sb.Append("{\"name\":\"");
            sb.Append(EscapeJson(target.name));
            sb.Append("\",\"instanceId\":");
            sb.Append(target.GetInstanceID());
            sb.Append(",\"active\":");
            sb.Append(target.activeSelf ? "true" : "false");
            sb.Append(",\"tag\":\"");
            sb.Append(EscapeJson(target.tag));
            sb.Append("\",\"layer\":");
            sb.Append(target.layer);

            SerializeTransform(target.transform, sb);

            var components = target.GetComponents<Component>();
            sb.Append(",\"components\":[");

            for (int i = 0; i < components.Length; i++)
            {
                if (components[i] == null) continue;
                if (i > 0) sb.Append(",");
                SerializeComponent(components[i], sb);
            }

            sb.Append("]}");
            return sb.ToString();
        }

        private static void SerializeTransform(Transform t, StringBuilder sb)
        {
            sb.Append(",\"transform\":{");
            sb.Append("\"position\":{\"x\":");
            sb.Append(t.localPosition.x);
            sb.Append(",\"y\":");
            sb.Append(t.localPosition.y);
            sb.Append(",\"z\":");
            sb.Append(t.localPosition.z);
            sb.Append("},\"rotation\":{\"x\":");
            sb.Append(t.localEulerAngles.x);
            sb.Append(",\"y\":");
            sb.Append(t.localEulerAngles.y);
            sb.Append(",\"z\":");
            sb.Append(t.localEulerAngles.z);
            sb.Append("},\"scale\":{\"x\":");
            sb.Append(t.localScale.x);
            sb.Append(",\"y\":");
            sb.Append(t.localScale.y);
            sb.Append(",\"z\":");
            sb.Append(t.localScale.z);
            sb.Append("}}");
        }

        private static void SerializeComponent(Component comp, StringBuilder sb)
        {
            sb.Append("{\"type\":\"");
            sb.Append(comp.GetType().Name);
            sb.Append("\",\"fullType\":\"");
            sb.Append(EscapeJson(comp.GetType().FullName));
            sb.Append("\",\"enabled\":");

            if (comp is Behaviour behaviour)
                sb.Append(behaviour.enabled ? "true" : "false");
            else if (comp is Renderer renderer)
                sb.Append(renderer.enabled ? "true" : "false");
            else if (comp is Collider collider)
                sb.Append(collider.enabled ? "true" : "false");
            else
                sb.Append("true");

            sb.Append(",\"properties\":{");

            var so = new SerializedObject(comp);
            var prop = so.GetIterator();
            bool first = true;

            if (prop.NextVisible(true))
            {
                do
                {
                    if (prop.name == "m_Script") continue;
                    if (!first) sb.Append(",");
                    first = false;

                    sb.Append("\"");
                    sb.Append(EscapeJson(prop.name));
                    sb.Append("\":");
                    SerializeProperty(prop, sb);
                } while (prop.NextVisible(false));
            }

            sb.Append("}}");
        }

        private static void SerializeProperty(SerializedProperty prop, StringBuilder sb)
        {
            switch (prop.propertyType)
            {
                case SerializedPropertyType.Integer:
                    sb.Append(prop.intValue);
                    break;
                case SerializedPropertyType.Boolean:
                    sb.Append(prop.boolValue ? "true" : "false");
                    break;
                case SerializedPropertyType.Float:
                    sb.Append(prop.floatValue);
                    break;
                case SerializedPropertyType.String:
                    sb.Append("\"");
                    sb.Append(EscapeJson(prop.stringValue));
                    sb.Append("\"");
                    break;
                case SerializedPropertyType.Enum:
                    sb.Append("\"");
                    if (prop.enumValueIndex >= 0 && prop.enumValueIndex < prop.enumDisplayNames.Length)
                        sb.Append(EscapeJson(prop.enumDisplayNames[prop.enumValueIndex]));
                    else
                        sb.Append(prop.enumValueIndex);
                    sb.Append("\"");
                    break;
                case SerializedPropertyType.ObjectReference:
                    if (prop.objectReferenceValue != null)
                    {
                        sb.Append("{\"name\":\"");
                        sb.Append(EscapeJson(prop.objectReferenceValue.name));
                        sb.Append("\",\"type\":\"");
                        sb.Append(prop.objectReferenceValue.GetType().Name);
                        sb.Append("\",\"instanceId\":");
                        sb.Append(prop.objectReferenceValue.GetInstanceID());
                        sb.Append("}");
                    }
                    else
                    {
                        sb.Append("null");
                    }
                    break;
                case SerializedPropertyType.Vector2:
                    var v2 = prop.vector2Value;
                    sb.Append("{\"x\":");
                    sb.Append(v2.x);
                    sb.Append(",\"y\":");
                    sb.Append(v2.y);
                    sb.Append("}");
                    break;
                case SerializedPropertyType.Vector3:
                    var v3 = prop.vector3Value;
                    sb.Append("{\"x\":");
                    sb.Append(v3.x);
                    sb.Append(",\"y\":");
                    sb.Append(v3.y);
                    sb.Append(",\"z\":");
                    sb.Append(v3.z);
                    sb.Append("}");
                    break;
                case SerializedPropertyType.Vector4:
                    var v4 = prop.vector4Value;
                    sb.Append("{\"x\":");
                    sb.Append(v4.x);
                    sb.Append(",\"y\":");
                    sb.Append(v4.y);
                    sb.Append(",\"z\":");
                    sb.Append(v4.z);
                    sb.Append(",\"w\":");
                    sb.Append(v4.w);
                    sb.Append("}");
                    break;
                case SerializedPropertyType.Color:
                    var color = prop.colorValue;
                    sb.Append("{\"r\":");
                    sb.Append(color.r);
                    sb.Append(",\"g\":");
                    sb.Append(color.g);
                    sb.Append(",\"b\":");
                    sb.Append(color.b);
                    sb.Append(",\"a\":");
                    sb.Append(color.a);
                    sb.Append("}");
                    break;
                case SerializedPropertyType.Rect:
                    var rect = prop.rectValue;
                    sb.Append("{\"x\":");
                    sb.Append(rect.x);
                    sb.Append(",\"y\":");
                    sb.Append(rect.y);
                    sb.Append(",\"width\":");
                    sb.Append(rect.width);
                    sb.Append(",\"height\":");
                    sb.Append(rect.height);
                    sb.Append("}");
                    break;
                case SerializedPropertyType.Bounds:
                    var bounds = prop.boundsValue;
                    sb.Append("{\"center\":{\"x\":");
                    sb.Append(bounds.center.x);
                    sb.Append(",\"y\":");
                    sb.Append(bounds.center.y);
                    sb.Append(",\"z\":");
                    sb.Append(bounds.center.z);
                    sb.Append("},\"size\":{\"x\":");
                    sb.Append(bounds.size.x);
                    sb.Append(",\"y\":");
                    sb.Append(bounds.size.y);
                    sb.Append(",\"z\":");
                    sb.Append(bounds.size.z);
                    sb.Append("}}");
                    break;
                case SerializedPropertyType.LayerMask:
                    sb.Append(prop.intValue);
                    break;
                case SerializedPropertyType.AnimationCurve:
                    sb.Append("\"<AnimationCurve>\"");
                    break;
                default:
                    sb.Append("\"<");
                    sb.Append(prop.propertyType.ToString());
                    sb.Append(">\"");
                    break;
            }
        }

        private static string EscapeJson(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
        }
    }
}
