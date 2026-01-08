"""Tests for C# script parser."""

from unityflow.script_parser import (
    SerializedField,
    parse_script,
    reorder_fields,
)


class TestParseScript:
    """Tests for parse_script function."""

    def test_parse_simple_monobehaviour(self):
        """Test parsing a simple MonoBehaviour with public fields."""
        script = """
using UnityEngine;

public class Player : MonoBehaviour
{
    public float speed;
    public int health;
    public string playerName;
}
"""
        info = parse_script(script)

        assert info is not None
        assert info.class_name == "Player"
        assert info.base_class == "MonoBehaviour"
        assert len(info.fields) == 3

        field_names = [f.name for f in info.fields]
        assert field_names == ["speed", "health", "playerName"]

        unity_names = [f.unity_name for f in info.fields]
        assert unity_names == ["m_Speed", "m_Health", "m_PlayerName"]

    def test_parse_serialize_field_attribute(self):
        """Test parsing private fields with [SerializeField]."""
        script = """
using UnityEngine;

public class Enemy : MonoBehaviour
{
    [SerializeField]
    private float attackDamage;

    [SerializeField]
    private int maxHealth;

    private int currentHealth;  // Not serialized
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 2

        field_names = [f.name for f in info.fields]
        assert field_names == ["attackDamage", "maxHealth"]
        assert "currentHealth" not in field_names

    def test_parse_mixed_fields(self):
        """Test parsing a class with mixed public and private fields."""
        script = """
using UnityEngine;

public class GameManager : MonoBehaviour
{
    public int level;

    [SerializeField]
    private float difficulty;

    public string gameName;

    [SerializeField]
    private bool isActive;

    private int internalCounter;  // Not serialized
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 4

        # Check order is preserved
        expected_order = ["level", "difficulty", "gameName", "isActive"]
        actual_order = [f.name for f in info.fields]
        assert actual_order == expected_order

    def test_skip_static_fields(self):
        """Test that static fields are skipped."""
        script = """
using UnityEngine;

public class Config : MonoBehaviour
{
    public static int instanceCount;
    public float normalField;
    private static string staticPrivate;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 1
        assert info.fields[0].name == "normalField"

    def test_skip_const_fields(self):
        """Test that const fields are skipped."""
        script = """
using UnityEngine;

public class Constants : MonoBehaviour
{
    public const int MAX_HEALTH = 100;
    public float speed;
    private const string NAME = "Player";
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 1
        assert info.fields[0].name == "speed"

    def test_skip_readonly_fields(self):
        """Test that readonly fields are skipped."""
        script = """
using UnityEngine;

public class ReadOnlyTest : MonoBehaviour
{
    public readonly int readonlyField = 5;
    public float mutableField;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 1
        assert info.fields[0].name == "mutableField"

    def test_skip_nonserialized_fields(self):
        """Test that [NonSerialized] fields are skipped."""
        script = """
using UnityEngine;
using System;

public class NonSerializedTest : MonoBehaviour
{
    [NonSerialized]
    public int notSerialized;

    public float serializedField;

    [System.NonSerialized]
    public string alsoNotSerialized;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 1
        assert info.fields[0].name == "serializedField"

    def test_parse_complex_types(self):
        """Test parsing fields with complex types."""
        script = """
using UnityEngine;
using System.Collections.Generic;

public class ComplexTypes : MonoBehaviour
{
    public List<int> numbers;
    public Dictionary<string, float> values;
    public int[] array;
    public Vector3 position;
    public GameObject? nullableObject;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 5

        types = [f.field_type for f in info.fields]
        assert "List<int>" in types
        assert "Dictionary<string, float>" in types
        assert "int[]" in types

    def test_parse_with_namespace(self):
        """Test parsing a class with namespace."""
        script = """
namespace Game.Characters
{
    using UnityEngine;

    public class Hero : MonoBehaviour
    {
        public float strength;
    }
}
"""
        info = parse_script(script)

        assert info is not None
        assert info.namespace == "Game.Characters"
        assert info.class_name == "Hero"

    def test_parse_with_comments(self):
        """Test that comments don't interfere with parsing."""
        script = """
using UnityEngine;

// This is a player class
public class Player : MonoBehaviour
{
    // Speed of the player
    public float speed;

    /* Health points
       Can be modified */
    public int health;

    // [SerializeField]
    // private int commentedOut;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 2
        assert "commentedOut" not in [f.name for f in info.fields]

    def test_parse_with_initializers(self):
        """Test parsing fields with initializers."""
        script = """
using UnityEngine;

public class Initialized : MonoBehaviour
{
    public float speed = 5.0f;
    public int count = 10;
    public string name = "Default";
    public bool enabled = true;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 4

    def test_parse_scriptable_object(self):
        """Test parsing a ScriptableObject."""
        script = """
using UnityEngine;

[CreateAssetMenu(fileName = "Data", menuName = "Game/Data")]
public class GameData : ScriptableObject
{
    public string gameName;
    public int maxPlayers;
}
"""
        info = parse_script(script)

        assert info is not None
        assert info.class_name == "GameData"
        assert info.base_class == "ScriptableObject"
        assert len(info.fields) == 2

    def test_get_field_order(self):
        """Test getting field order as Unity names."""
        script = """
using UnityEngine;

public class OrderTest : MonoBehaviour
{
    public float alpha;
    public int beta;
    public string gamma;
}
"""
        info = parse_script(script)

        assert info is not None
        order = info.get_field_order()
        assert order == ["m_Alpha", "m_Beta", "m_Gamma"]

    def test_get_field_index(self):
        """Test getting field index by Unity name."""
        script = """
using UnityEngine;

public class IndexTest : MonoBehaviour
{
    public float first;
    public int second;
    public string third;
}
"""
        info = parse_script(script)

        assert info is not None
        assert info.get_field_index("m_First") == 0
        assert info.get_field_index("m_Second") == 1
        assert info.get_field_index("m_Third") == 2
        assert info.get_field_index("m_NotExists") == -1


class TestReorderFields:
    """Tests for reorder_fields function."""

    def test_reorder_basic(self):
        """Test basic field reordering."""
        fields = {
            "m_Gamma": 3,
            "m_Alpha": 1,
            "m_Beta": 2,
        }
        order = ["m_Alpha", "m_Beta", "m_Gamma"]

        result = reorder_fields(fields, order, unity_fields_first=False)

        assert list(result.keys()) == ["m_Alpha", "m_Beta", "m_Gamma"]
        assert result["m_Alpha"] == 1
        assert result["m_Beta"] == 2
        assert result["m_Gamma"] == 3

    def test_reorder_with_unity_fields(self):
        """Test that Unity standard fields come first."""
        fields = {
            "customField": "value",
            "m_Script": {"fileID": 11500000},
            "m_GameObject": {"fileID": 12345},
            "m_Enabled": 1,
        }
        order = ["customField"]

        result = reorder_fields(fields, order, unity_fields_first=True)

        keys = list(result.keys())
        # Unity fields should come before custom fields
        assert keys.index("m_GameObject") < keys.index("customField")
        assert keys.index("m_Enabled") < keys.index("customField")
        assert keys.index("m_Script") < keys.index("customField")

    def test_reorder_with_extra_fields(self):
        """Test reordering when fields has extra keys not in order."""
        fields = {
            "m_Gamma": 3,
            "m_Alpha": 1,
            "m_Extra": "extra",
            "m_Beta": 2,
        }
        order = ["m_Alpha", "m_Beta", "m_Gamma"]

        result = reorder_fields(fields, order, unity_fields_first=False)

        keys = list(result.keys())
        # m_Extra should be at the end
        assert keys[-1] == "m_Extra"
        # Ordered fields should be in order
        assert keys[:3] == ["m_Alpha", "m_Beta", "m_Gamma"]

    def test_reorder_preserves_values(self):
        """Test that reordering preserves all values."""
        fields = {
            "m_Position": {"x": 1, "y": 2, "z": 3},
            "m_Scale": {"x": 1, "y": 1, "z": 1},
            "m_Name": "Object",
        }
        order = ["m_Name", "m_Position", "m_Scale"]

        result = reorder_fields(fields, order, unity_fields_first=False)

        assert result["m_Position"] == {"x": 1, "y": 2, "z": 3}
        assert result["m_Scale"] == {"x": 1, "y": 1, "z": 1}
        assert result["m_Name"] == "Object"


class TestSerializedField:
    """Tests for SerializedField dataclass."""

    def test_from_field_name(self):
        """Test creating SerializedField from field name."""
        field = SerializedField.from_field_name("playerSpeed", "float")

        assert field.name == "playerSpeed"
        assert field.unity_name == "m_PlayerSpeed"
        assert field.field_type == "float"

    def test_from_field_name_single_char(self):
        """Test creating SerializedField from single character name."""
        field = SerializedField.from_field_name("x", "int")

        assert field.name == "x"
        assert field.unity_name == "m_X"

    def test_from_field_name_with_options(self):
        """Test creating SerializedField with additional options."""
        field = SerializedField.from_field_name(
            "health",
            "int",
            is_public=True,
            has_serialize_field=False,
            line_number=42,
        )

        assert field.name == "health"
        assert field.is_public is True
        assert field.has_serialize_field is False
        assert field.line_number == 42


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parse_empty_class(self):
        """Test parsing a class with no fields."""
        script = """
using UnityEngine;

public class Empty : MonoBehaviour
{
}
"""
        info = parse_script(script)

        assert info is not None
        assert info.class_name == "Empty"
        assert len(info.fields) == 0

    def test_parse_no_class(self):
        """Test parsing content with no class definition."""
        script = """
using UnityEngine;
using System;
"""
        info = parse_script(script)

        assert info is None

    def test_parse_interface(self):
        """Test that interfaces are not parsed as classes."""
        script = """
using UnityEngine;

public interface IPlayer
{
    float Speed { get; }
}
"""
        info = parse_script(script)

        # Should not find a class
        assert info is None

    def test_parse_partial_class(self):
        """Test parsing a partial class."""
        script = """
using UnityEngine;

public partial class Player : MonoBehaviour
{
    public float speed;
}
"""
        info = parse_script(script)

        assert info is not None
        assert info.class_name == "Player"
        assert len(info.fields) == 1

    def test_parse_generic_class(self):
        """Test parsing fields in a generic-like context."""
        script = """
using UnityEngine;
using System.Collections.Generic;

public class Container : MonoBehaviour
{
    public List<GameObject> items;
    public Dictionary<string, int> scores;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 2

    def test_parse_multiline_attribute(self):
        """Test parsing with multi-line attributes."""
        script = """
using UnityEngine;

public class Attributed : MonoBehaviour
{
    [SerializeField]
    [Header("Settings")]
    [Range(0, 100)]
    private float value;

    [Tooltip("Player name")]
    public string playerName;
}
"""
        info = parse_script(script)

        assert info is not None
        assert len(info.fields) == 2
        assert info.fields[0].name == "value"
        assert info.fields[0].has_serialize_field is True
        assert info.fields[1].name == "playerName"
