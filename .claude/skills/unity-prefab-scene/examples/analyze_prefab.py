#!/usr/bin/env python3
"""예시: 프리팹/씬 분석

이 스크립트는 프리팹이나 씬 파일을 분석하여 상세 정보를 출력합니다:
- 계층 구조
- 컴포넌트 목록
- 스크립트 참조
- 외부 에셋 참조
"""

import json
from pathlib import Path
from prefab_tool.parser import UnityYAMLDocument, CLASS_IDS
from prefab_tool.formats import export_to_json, get_summary


def analyze_prefab(file_path: str, output_format: str = "text") -> None:
    """프리팹/씬 파일 분석."""
    doc = UnityYAMLDocument.load(file_path)

    if output_format == "json":
        # JSON 형식으로 전체 정보 출력
        prefab_json = export_to_json(doc, include_raw=False)
        print(prefab_json.to_json(indent=2))
        return

    # 텍스트 형식 출력
    print(f"=== {file_path} ===\n")

    # 1. 요약
    summary = get_summary(doc)["summary"]
    print("[ Summary ]")
    print(f"  GameObjects: {summary['totalGameObjects']}")
    print(f"  Components: {summary['totalComponents']}")
    print()

    # 2. 타입별 개수
    print("[ Type Counts ]")
    for type_name, count in sorted(summary["typeCounts"].items(), key=lambda x: -x[1]):
        print(f"  {type_name}: {count}")
    print()

    # 3. 계층 구조
    print("[ Hierarchy ]")
    for path in summary["hierarchy"]:
        print(f"  {path}")
    print()

    # 4. 스크립트 참조 (MonoBehaviour)
    print("[ Scripts (MonoBehaviour) ]")
    scripts = []
    for obj in doc.objects:
        if obj.class_id == 114:  # MonoBehaviour
            content = obj.get_content()
            if content:
                script_ref = content.get("m_Script", {})
                guid = script_ref.get("guid", "")
                if guid:
                    go_ref = content.get("m_GameObject", {})
                    go_id = go_ref.get("fileID", 0) if isinstance(go_ref, dict) else 0
                    go_name = _get_go_name(doc, go_id)
                    scripts.append({
                        "guid": guid,
                        "gameObject": go_name,
                        "fileId": obj.file_id,
                    })

    if scripts:
        for s in scripts:
            print(f"  [{s['guid'][:8]}...] on {s['gameObject']} (fileID: {s['fileId']})")
    else:
        print("  (none)")
    print()

    # 5. 외부 참조 (GUID가 있는 참조)
    print("[ External References ]")
    external_refs = set()
    for obj in doc.objects:
        _find_external_refs(obj.data, external_refs)

    if external_refs:
        for guid in sorted(external_refs):
            print(f"  {guid}")
    else:
        print("  (none)")
    print()

    # 6. 프리팹 인스턴스
    print("[ Prefab Instances ]")
    instances = []
    for obj in doc.objects:
        if obj.class_id == 1001:  # PrefabInstance
            content = obj.get_content()
            if content:
                source = content.get("m_SourcePrefab", {})
                guid = source.get("guid", "")
                if guid:
                    instances.append({
                        "guid": guid,
                        "fileId": obj.file_id,
                    })

    if instances:
        for inst in instances:
            print(f"  [{inst['guid'][:8]}...] (fileID: {inst['fileId']})")
    else:
        print("  (none)")


def _get_go_name(doc: UnityYAMLDocument, file_id: int) -> str:
    """GameObject의 이름 찾기."""
    obj = doc.get_by_file_id(file_id)
    if obj and obj.class_id == 1:
        content = obj.get_content()
        if content:
            return content.get("m_Name", "<unnamed>")
    return f"<{file_id}>"


def _find_external_refs(data: any, refs: set[str]) -> None:
    """재귀적으로 외부 참조 찾기."""
    if isinstance(data, dict):
        if "guid" in data and data.get("guid"):
            refs.add(data["guid"])
        for value in data.values():
            _find_external_refs(value, refs)
    elif isinstance(data, list):
        for item in data:
            _find_external_refs(item, refs)


def compare_prefabs(file1: str, file2: str) -> None:
    """두 프리팹 비교."""
    doc1 = UnityYAMLDocument.load(file1)
    doc2 = UnityYAMLDocument.load(file2)

    sum1 = get_summary(doc1)["summary"]
    sum2 = get_summary(doc2)["summary"]

    print(f"=== Comparison ===\n")
    print(f"{'':20} | {Path(file1).name:20} | {Path(file2).name:20}")
    print("-" * 65)

    print(f"{'GameObjects':20} | {sum1['totalGameObjects']:20} | {sum2['totalGameObjects']:20}")
    print(f"{'Components':20} | {sum1['totalComponents']:20} | {sum2['totalComponents']:20}")

    # 타입 비교
    all_types = set(sum1["typeCounts"].keys()) | set(sum2["typeCounts"].keys())
    print()
    print("[ Type Comparison ]")
    for type_name in sorted(all_types):
        c1 = sum1["typeCounts"].get(type_name, 0)
        c2 = sum2["typeCounts"].get(type_name, 0)
        diff = c2 - c1
        diff_str = f"+{diff}" if diff > 0 else str(diff) if diff < 0 else ""
        print(f"  {type_name:20} | {c1:20} | {c2:20} {diff_str}")


def find_by_name(file_path: str, name_pattern: str) -> None:
    """이름으로 GameObject 검색."""
    doc = UnityYAMLDocument.load(file_path)

    print(f"Searching for '{name_pattern}' in {file_path}\n")

    found = []
    for obj in doc.get_game_objects():
        content = obj.get_content()
        if content:
            go_name = content.get("m_Name", "")
            if name_pattern.lower() in go_name.lower():
                found.append({
                    "fileId": obj.file_id,
                    "name": go_name,
                    "active": content.get("m_IsActive", 1) == 1,
                    "layer": content.get("m_Layer", 0),
                    "tag": content.get("m_TagString", "Untagged"),
                })

    if found:
        for item in found:
            status = "active" if item["active"] else "inactive"
            print(f"  [{item['fileId']}] {item['name']}")
            print(f"       Layer: {item['layer']}, Tag: {item['tag']}, Status: {status}")
    else:
        print("  No matches found")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python analyze_prefab.py <file.prefab>           # Analyze prefab")
        print("  python analyze_prefab.py <file.prefab> --json    # Output as JSON")
        print("  python analyze_prefab.py compare <f1> <f2>       # Compare two prefabs")
        print("  python analyze_prefab.py find <file> <pattern>   # Find by name")
        sys.exit(1)

    if sys.argv[1] == "compare":
        compare_prefabs(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "find":
        find_by_name(sys.argv[2], sys.argv[3])
    else:
        file_path = sys.argv[1]
        output_format = "json" if "--json" in sys.argv else "text"
        analyze_prefab(file_path, output_format)
