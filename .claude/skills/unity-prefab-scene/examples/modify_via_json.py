#!/usr/bin/env python3
"""예시: JSON을 통한 프리팹 수정

이 스크립트는 JSON 변환을 통해 프리팹을 수정하는 방법을 보여줍니다:
1. 프리팹을 JSON으로 내보내기
2. JSON 데이터 수정
3. 다시 프리팹으로 변환
"""

import json
from pathlib import Path
from prefab_tool.parser import UnityYAMLDocument
from prefab_tool.formats import export_to_json, import_from_json, PrefabJSON


def modify_prefab_via_json(input_path: str, output_path: str) -> None:
    """JSON을 통해 프리팹 수정."""

    # 1. 프리팹 로드
    doc = UnityYAMLDocument.load(input_path)
    print(f"Loaded: {input_path}")
    print(f"  Objects: {len(doc.objects)}")

    # 2. JSON으로 변환
    prefab_json = export_to_json(doc, include_raw=True)

    # 3. JSON 데이터 수정 예시

    # 3-1. 모든 GameObject 이름에 접두사 추가
    for file_id, go_data in prefab_json.game_objects.items():
        original_name = go_data.get("name", "")
        go_data["name"] = f"Modified_{original_name}"
        print(f"  Renamed: {original_name} -> {go_data['name']}")

    # 3-2. 모든 Transform의 스케일을 2배로
    for file_id, comp_data in prefab_json.components.items():
        if comp_data.get("type") == "Transform":
            scale = comp_data.get("localScale", {"x": 1, "y": 1, "z": 1})
            comp_data["localScale"] = {
                "x": scale["x"] * 2,
                "y": scale["y"] * 2,
                "z": scale["z"] * 2,
            }
            print(f"  Scaled Transform {file_id}: x2")

    # 3-3. RectTransform UI 요소 크기 조정 (editorValues 사용)
    for file_id, comp_data in prefab_json.components.items():
        if comp_data.get("type") == "RectTransform":
            if "editorValues" in comp_data:
                editor = comp_data["editorValues"]
                # 고정 크기 모드인 경우 크기 1.5배
                if "width" in editor:
                    editor["width"] = editor["width"] * 1.5
                if "height" in editor:
                    editor["height"] = editor["height"] * 1.5
                print(f"  Resized RectTransform {file_id}: x1.5")

    # 4. 다시 프리팹으로 변환
    modified_doc = import_from_json(prefab_json)

    # 5. 저장
    modified_doc.save(output_path)
    print(f"\nSaved: {output_path}")


def batch_rename_gameobjects(
    input_path: str,
    output_path: str,
    search: str,
    replace: str,
) -> None:
    """GameObject 이름 일괄 변경."""
    doc = UnityYAMLDocument.load(input_path)
    prefab_json = export_to_json(doc, include_raw=True)

    count = 0
    for file_id, go_data in prefab_json.game_objects.items():
        name = go_data.get("name", "")
        if search in name:
            go_data["name"] = name.replace(search, replace)
            count += 1
            print(f"  {name} -> {go_data['name']}")

    if count > 0:
        modified_doc = import_from_json(prefab_json)
        modified_doc.save(output_path)
        print(f"\nRenamed {count} GameObjects")
    else:
        print(f"No GameObjects found with '{search}'")


def toggle_gameobjects(input_path: str, output_path: str, active: bool) -> None:
    """모든 GameObject 활성화/비활성화."""
    doc = UnityYAMLDocument.load(input_path)
    prefab_json = export_to_json(doc, include_raw=True)

    for file_id, go_data in prefab_json.game_objects.items():
        go_data["isActive"] = active

    modified_doc = import_from_json(prefab_json)
    modified_doc.save(output_path)

    state = "activated" if active else "deactivated"
    print(f"All {len(prefab_json.game_objects)} GameObjects {state}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python modify_via_json.py modify <input.prefab> [output.prefab]")
        print("  python modify_via_json.py rename <input.prefab> <search> <replace> [output.prefab]")
        print("  python modify_via_json.py toggle <input.prefab> <on|off> [output.prefab]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "modify":
        input_path = sys.argv[2]
        output_path = sys.argv[3] if len(sys.argv) > 3 else input_path
        modify_prefab_via_json(input_path, output_path)

    elif command == "rename":
        input_path = sys.argv[2]
        search = sys.argv[3]
        replace = sys.argv[4]
        output_path = sys.argv[5] if len(sys.argv) > 5 else input_path
        batch_rename_gameobjects(input_path, output_path, search, replace)

    elif command == "toggle":
        input_path = sys.argv[2]
        active = sys.argv[3].lower() in ("on", "true", "1", "yes")
        output_path = sys.argv[4] if len(sys.argv) > 4 else input_path
        toggle_gameobjects(input_path, output_path, active)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
