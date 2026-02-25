---
name: unity-animation-workflow
description: Edits animation clips (.anim) and animator controller (.controller) files. Handles keyframe add/modify/delete, animation curve manipulation, animator state/parameter/transition settings, etc. Keywords: animation, keyframe, curve, animator, state, transition, parameter, .anim, .controller
---

# Unity Animation Workflow

Edit Unity animation files (.anim, .controller) using `unityflow` CLI.

## Core Principle

**NEVER directly edit .anim or .controller files as text.**

Always use `uvx unityflow anim` and `uvx unityflow ctrl` commands. Direct YAML editing will
corrupt animation data, break curve bindings, and cause Unity import failures.

## Animation Clip Commands

### Creating Animations

```bash
uvx unityflow anim create NewClip.anim --name "NewClip" --duration 2.0 --loop
```

### Querying Animation Structure

| Command | Purpose |
|---------|---------|
| `uvx unityflow anim info <file>` | Get clip metadata (duration, loop, sample rate) |
| `uvx unityflow anim curves <file>` | List all animation curves with keyframe counts |
| `uvx unityflow anim keyframes <file> --index <idx>` | View keyframes for curve by index |
| `uvx unityflow anim keyframes <file> --path <path> --attr <attr>` | View keyframes by path/attribute |
| `uvx unityflow anim events <file>` | List animation events |
| `uvx unityflow anim settings <file>` | View clip settings |

### Modifying Animations

| Command | Purpose |
|---------|---------|
| `uvx unityflow anim set-key <file> --index <curve> --key <idx> --value <val>` | Modify keyframe value |
| `uvx unityflow anim add-key <file> --index <curve> --time <t> --value <val>` | Add new keyframe |
| `uvx unityflow anim del-key <file> --index <curve> --key <idx>` | Delete keyframe |
| `uvx unityflow anim add-curve <file> --path <path> --type <type>` | Add new curve |
| `uvx unityflow anim del-curve <file> --index <idx>` | Delete curve |
| `uvx unityflow anim set-settings <file> --loop --duration 2.0` | Modify clip settings |
| `uvx unityflow anim add-event <file> --time <t> --function <name>` | Add animation event |
| `uvx unityflow anim del-event <file> --index <idx>` | Delete animation event |

### Curve Types

- `position` - Transform.localPosition (Vector3)
- `euler` - Transform.localEulerAngles (Vector3)
- `scale` - Transform.localScale (Vector3)
- `float` - Single float properties (m_Color.a, m_IsActive, etc.)
- `pptr` - Object references (m_Sprite, m_Material)

## Animator Controller Commands

### Querying Controller Structure

| Command | Purpose |
|---------|---------|
| `uvx unityflow ctrl info <file>` | Get controller overview |
| `uvx unityflow ctrl layers <file>` | List animator layers |
| `uvx unityflow ctrl states <file> --layer <name>` | List states in a layer |
| `uvx unityflow ctrl transitions <file> --state <name>` | List transitions from a state |
| `uvx unityflow ctrl transitions <file> --any-state --layer <name>` | List Any State transitions |
| `uvx unityflow ctrl params <file>` | List parameters |
| `uvx unityflow ctrl get-state <file> --state <name>` | Get detailed state info (JSON) |

### Modifying Controllers

| Command | Purpose |
|---------|---------|
| `uvx unityflow ctrl set-state <file> --state <name> --speed 1.5` | Modify state properties |
| `uvx unityflow ctrl set-state <file> --state <name> --motion "@Assets/Anim/New.anim"` | Change state motion |
| `uvx unityflow ctrl add-param <file> --name "Fire" --type trigger` | Add parameter |
| `uvx unityflow ctrl set-param <file> --name "Speed" --default 1.5` | Modify parameter default |
| `uvx unityflow ctrl del-param <file> --name "OldParam"` | Delete parameter |

### Parameter Types

- `float` - Floating point value
- `int` - Integer value
- `bool` - Boolean value
- `trigger` - One-shot trigger

### Condition Syntax

When using condition strings:
```
<param> (If)           # Bool/Trigger is true
<param> (IfNot)        # Bool is false
<param> > <value>      # Float greater than
<param> < <value>      # Float less than
<param> == <value>     # Int equals
<param> != <value>     # Int not equals
```

## Asset References

Use `@path` syntax for all asset references:

```bash
# Animation clip
--motion "@Assets/Animations/Idle.anim"

# Sprite (sub-asset)
--sprite "@Assets/Sprites/atlas.png:idle_0"
```

## Value Input

```bash
# Vector3 (JSON object)
--value '{"x": 0, "y": 1.5, "z": 0}'

# Single float
--value 0.8

# Tangent modes: smooth, linear, constant, flat
--tangent smooth
```

## Common Workflows

### View Animation Structure

```bash
# Get overview
uvx unityflow anim info Idle.anim

# List all curves
uvx unityflow anim curves Idle.anim

# View specific curve keyframes
uvx unityflow anim keyframes Idle.anim --index 0
```

### Adjust Animation Timing

```bash
# Check current keyframes
uvx unityflow anim keyframes Idle.anim --path "Root/character" --attr position

# Modify specific keyframe time and value
uvx unityflow anim set-key Idle.anim \
    --path "Root/character" --attr position \
    --key 0 --value '{"x": 0, "y": 2.0, "z": 0}'
```

### Add State Transition (conceptual - full transition API pending)

```bash
# Add trigger parameter if not exists
uvx unityflow ctrl params Player.controller
uvx unityflow ctrl add-param Player.controller --name "Attack" --type trigger
```

### Change Animation Speed

```bash
uvx unityflow ctrl set-state Player.controller --state "Run" --speed 1.5
```

### Extract Keyframes to JSON

```bash
# Export keyframes for later use
uvx unityflow anim keyframes Source.anim --index 0 --format json > keys.json
```

## Best Practices

1. **Always query first** - Use `info`, `curves`, `states` to understand structure before modifying
2. **Backup important files** - Animation data is complex and easy to corrupt
3. **Use relative paths** - Prefer `--path "Child/Grandchild"` over full hierarchy paths when possible
4. **Check curve indices** - Use `uvx unityflow anim curves` to find correct curve indices before modifying

## Output Formats

All query commands support `--format json` for structured output:

```bash
uvx unityflow anim info Clip.anim --format json
uvx unityflow anim curves Clip.anim --format json
uvx unityflow ctrl states Player.controller --format json
```

## Limitations

- Cannot visually preview animations (use Unity Editor for playback)
- BlendTree editing has limited support
- Complex PPtrCurve (sprite swap) editing may require manual verification
- Adding new states/transitions to controllers has limited support

---

## Summary

- Use `uvx unityflow anim` for .anim files, `uvx unityflow ctrl` for .controller files
- Query structure first (`info`, `curves`, `states`), then modify
- References: `@` prefix for asset paths
