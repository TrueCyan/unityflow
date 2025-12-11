#!/usr/bin/env python3
"""예시: UI Panel 프리팹 생성

이 스크립트는 새로운 UI Panel 프리팹을 생성합니다:
- Canvas 컴포넌트를 가진 루트 GameObject
- Panel (Image + RectTransform)
- Title Text
- Close Button
"""

from pathlib import Path
from prefab_tool.parser import (
    UnityYAMLDocument,
    UnityYAMLObject,
    create_game_object,
    create_rect_transform,
    generate_file_id,
)
from prefab_tool.formats import create_rect_transform_file_values


def create_ui_panel(output_path: str) -> None:
    """UI Panel 프리팹 생성."""
    doc = UnityYAMLDocument()
    existing_ids: set[int] = set()

    def new_id() -> int:
        """고유 ID 생성."""
        id = generate_file_id(existing_ids)
        existing_ids.add(id)
        return id

    # ===================
    # 1. Panel (루트)
    # ===================
    panel_go_id = new_id()
    panel_rt_id = new_id()

    # Panel RectTransform (화면 중앙, 400x300)
    panel_vals = create_rect_transform_file_values(
        anchor_preset="center",
        pivot=(0.5, 0.5),
        pos_x=0, pos_y=0,
        width=400, height=300,
    )

    panel_go = create_game_object(
        name="Panel",
        file_id=panel_go_id,
        layer=5,  # UI layer
        is_active=True,
        components=[panel_rt_id],
    )

    panel_rt = create_rect_transform(
        game_object_id=panel_go_id,
        file_id=panel_rt_id,
        anchor_min=panel_vals.anchor_min,
        anchor_max=panel_vals.anchor_max,
        anchored_position=panel_vals.anchored_position,
        size_delta=panel_vals.size_delta,
        pivot=panel_vals.pivot,
        parent_id=0,  # 루트
    )

    # ===================
    # 2. Title (자식)
    # ===================
    title_go_id = new_id()
    title_rt_id = new_id()

    # Title RectTransform (상단 스트레치, 높이 50)
    title_vals = create_rect_transform_file_values(
        anchor_preset="stretch-top",
        pivot=(0.5, 1),
        left=10, right=10,
        height=50, pos_y=0,
    )

    title_go = create_game_object(
        name="Title",
        file_id=title_go_id,
        layer=5,
        components=[title_rt_id],
    )

    title_rt = create_rect_transform(
        game_object_id=title_go_id,
        file_id=title_rt_id,
        anchor_min=title_vals.anchor_min,
        anchor_max=title_vals.anchor_max,
        anchored_position=title_vals.anchored_position,
        size_delta=title_vals.size_delta,
        pivot=title_vals.pivot,
        parent_id=panel_rt_id,
    )

    # ===================
    # 3. CloseButton (자식)
    # ===================
    btn_go_id = new_id()
    btn_rt_id = new_id()

    # Button RectTransform (우상단, 30x30)
    btn_vals = create_rect_transform_file_values(
        anchor_preset="top-right",
        pivot=(1, 1),
        pos_x=-10, pos_y=-10,
        width=30, height=30,
    )

    btn_go = create_game_object(
        name="CloseButton",
        file_id=btn_go_id,
        layer=5,
        components=[btn_rt_id],
    )

    btn_rt = create_rect_transform(
        game_object_id=btn_go_id,
        file_id=btn_rt_id,
        anchor_min=btn_vals.anchor_min,
        anchor_max=btn_vals.anchor_max,
        anchored_position=btn_vals.anchored_position,
        size_delta=btn_vals.size_delta,
        pivot=btn_vals.pivot,
        parent_id=panel_rt_id,
    )

    # ===================
    # 4. Content Area (자식)
    # ===================
    content_go_id = new_id()
    content_rt_id = new_id()

    # Content RectTransform (전체 스트레치, 여백 포함)
    content_vals = create_rect_transform_file_values(
        anchor_preset="stretch-all",
        pivot=(0.5, 0.5),
        left=10, right=10, top=60, bottom=10,
    )

    content_go = create_game_object(
        name="Content",
        file_id=content_go_id,
        layer=5,
        components=[content_rt_id],
    )

    content_rt = create_rect_transform(
        game_object_id=content_go_id,
        file_id=content_rt_id,
        anchor_min=content_vals.anchor_min,
        anchor_max=content_vals.anchor_max,
        anchored_position=content_vals.anchored_position,
        size_delta=content_vals.size_delta,
        pivot=content_vals.pivot,
        parent_id=panel_rt_id,
    )

    # ===================
    # 부모-자식 관계 업데이트
    # ===================
    # Panel의 children 업데이트
    panel_rt.data["RectTransform"]["m_Children"] = [
        {"fileID": title_rt_id},
        {"fileID": btn_rt_id},
        {"fileID": content_rt_id},
    ]

    # ===================
    # 문서에 추가
    # ===================
    for obj in [panel_go, panel_rt, title_go, title_rt,
                btn_go, btn_rt, content_go, content_rt]:
        doc.add_object(obj)

    # 저장
    doc.save(output_path)
    print(f"Created: {output_path}")
    print(f"  - Panel (root): {panel_go_id}")
    print(f"  - Title: {title_go_id}")
    print(f"  - CloseButton: {btn_go_id}")
    print(f"  - Content: {content_go_id}")


if __name__ == "__main__":
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "UIPanel.prefab"
    create_ui_panel(output)
