---
name: unity-animation-workflow
description: 애니메이션 클립(.anim)과 애니메이터 컨트롤러(.controller) 파일을 편집합니다. 키프레임 추가/수정/삭제, 애니메이션 커브 조작, 애니메이터 스테이트/파라미터/트랜지션 설정 등의 작업을 수행합니다. 키워드: 애니메이션, 키프레임, 커브, 애니메이터, 스테이트, 트랜지션, 파라미터, .anim, .controller
---

## ⚠️ Required: unityflow CLI

All `unityflow` commands in this skill use the CLI installed in a virtual environment.

**How to run** (if not in PATH):
```bash
~/.unityflow-venv/bin/unityflow <command>
```

The SessionStart hook installs it automatically, so `unityflow` usually works directly.

---

# Unity Animation Workflow

This skill enables programmatic editing of Unity animation files (.anim, .controller)
using the `unityflow` CLI.

## Core Principle

**NEVER directly edit .anim or .controller files as text.**

Always use `unityflow anim` and `unityflow ctrl` commands. Direct YAML editing will
corrupt animation data, break curve bindings, and cause Unity import failures.

## Animation Clip Commands

### Creating Animations

```bash
unityflow anim create NewClip.anim --name "NewClip" --duration 2.0 --loop
```

### Querying Animation Structure

| Command | Purpose |
|---------|---------|
| `unityflow anim info <file>` | Get clip metadata (duration, loop, sample rate) |
| `unityflow anim curves <file>` | List all animation curves with keyframe counts |
| `unityflow anim keyframes <file> --index <idx>` | View keyframes for curve by index |
| `unityflow anim keyframes <file> --path <path> --attr <attr>` | View keyframes by path/attribute |
| `unityflow anim events <file>` | List animation events |
| `unityflow anim settings <file>` | View clip settings |

### Modifying Animations

| Command | Purpose |
|---------|---------|
| `unityflow anim set-key <file> --index <curve> --key <idx> --value <val>` | Modify keyframe value |
| `unityflow anim add-key <file> --index <curve> --time <t> --value <val>` | Add new keyframe |
| `unityflow anim del-key <file> --index <curve> --key <idx>` | Delete keyframe |
| `unityflow anim add-curve <file> --path <path> --type <type>` | Add new curve |
| `unityflow anim del-curve <file> --index <idx>` | Delete curve |
| `unityflow anim set-settings <file> --loop --duration 2.0` | Modify clip settings |
| `unityflow anim add-event <file> --time <t> --function <name>` | Add animation event |
| `unityflow anim del-event <file> --index <idx>` | Delete animation event |

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
| `unityflow ctrl info <file>` | Get controller overview |
| `unityflow ctrl layers <file>` | List animator layers |
| `unityflow ctrl states <file> --layer <name>` | List states in a layer |
| `unityflow ctrl transitions <file> --state <name>` | List transitions from a state |
| `unityflow ctrl transitions <file> --any-state --layer <name>` | List Any State transitions |
| `unityflow ctrl params <file>` | List parameters |
| `unityflow ctrl get-state <file> --state <name>` | Get detailed state info (JSON) |

### Modifying Controllers

| Command | Purpose |
|---------|---------|
| `unityflow ctrl set-state <file> --state <name> --speed 1.5` | Modify state properties |
| `unityflow ctrl set-state <file> --state <name> --motion "@Assets/Anim/New.anim"` | Change state motion |
| `unityflow ctrl add-param <file> --name "Fire" --type trigger` | Add parameter |
| `unityflow ctrl set-param <file> --name "Speed" --default 1.5` | Modify parameter default |
| `unityflow ctrl del-param <file> --name "OldParam"` | Delete parameter |

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
unityflow anim info Idle.anim

# List all curves
unityflow anim curves Idle.anim

# View specific curve keyframes
unityflow anim keyframes Idle.anim --index 0
```

### Adjust Animation Timing

```bash
# Check current keyframes
unityflow anim keyframes Idle.anim --path "Root/character" --attr position

# Modify specific keyframe time and value
unityflow anim set-key Idle.anim \
    --path "Root/character" --attr position \
    --key 0 --value '{"x": 0, "y": 2.0, "z": 0}'
```

### Add State Transition (conceptual - full transition API pending)

```bash
# Add trigger parameter if not exists
unityflow ctrl params Player.controller
unityflow ctrl add-param Player.controller --name "Attack" --type trigger
```

### Change Animation Speed

```bash
unityflow ctrl set-state Player.controller --state "Run" --speed 1.5
```

### Extract Keyframes to JSON

```bash
# Export keyframes for later use
unityflow anim keyframes Source.anim --index 0 --format json > keys.json
```

## Best Practices

1. **Always query first** - Use `info`, `curves`, `states` to understand structure before modifying
2. **Backup important files** - Animation data is complex and easy to corrupt
3. **Use relative paths** - Prefer `--path "Child/Grandchild"` over full hierarchy paths when possible
4. **Check curve indices** - Use `unityflow anim curves` to find correct curve indices before modifying

## Output Formats

All query commands support `--format json` for structured output:

```bash
unityflow anim info Clip.anim --format json
unityflow anim curves Clip.anim --format json
unityflow ctrl states Player.controller --format json
```

## Limitations

- Cannot visually preview animations (use Unity Editor for playback)
- BlendTree editing has limited support
- Complex PPtrCurve (sprite swap) editing may require manual verification
- Adding new states/transitions to controllers requires careful fileID management
