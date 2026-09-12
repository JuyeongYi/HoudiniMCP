"""렌더 설정을 읽는 툴들.

노드 파라미터가 아니라 **스테이지에 찍힌 UsdRender 프림**을 읽는다. Karma 는
USD 렌더 델리게이트라, 실제로 렌더에 쓰이는 것은 `karmarendersettings` 의
파라미터가 아니라 그것이 만들어 낸 RenderSettings 프림이다. 파라미터 이름은
버전이 올라가면 바뀌지만 USD 스키마는 안 바뀐다.

설정을 **바꾸는** 툴은 여기 없다. 노드 파라미터를 거는 일은 base 의
`set_parms` 가 이미 한다. 무엇을 걸어야 하는지는 `render_settings` 가
보여주는 프림 이름으로 알 수 있다.
"""

from __future__ import annotations

import subprocess
from typing import Any

from houdini_mcp import tool

from ._common import clip, houdini_bin, lop_stage, require_lop
from ._usdrender import (
    describe_settings,
    find_settings_prims,
    resolve_settings,
    stage_frame_range,
)

_RENDERERS_CACHE: dict[str, Any] | None = None
"""델리게이트 목록은 한 세션 안에서 바뀌지 않는다. husk 기동이 2초쯤 걸린다."""


@tool()
def render_settings(path: str, settings_prim: str | None = None) -> dict[str, Any]:
    """LOP 노드가 만든 스테이지의 렌더 설정을 UsdRender 스키마로 읽는다.

    해상도·카메라·출력 경로·AOV 목록이 전부 한 번에 나온다. 노드 파라미터가
    아니라 실제로 렌더에 쓰일 값이므로, 파라미터를 걸었는데 반영이 안 될 때
    여기서 확인하면 된다.

    델리게이트 전용 설정(`karma:global:samplesperpixel` 등)은 스키마 밖이라
    `renderer_settings` 에 "실제로 값이 찍힌 것"만 담아 돌려준다.

    Args:
        path: LOP 노드 경로. 예: /stage/karma_settings
        settings_prim: 읽을 RenderSettings 프림 경로. 생략하면 스테이지 기본값.
    """
    node = require_lop(path)
    stage = lop_stage(node)
    settings = resolve_settings(stage, settings_prim)
    return {
        "node": node.path(),
        "comment": node.comment(),
        "settings_prims": find_settings_prims(stage),
        "frame_range": stage_frame_range(stage),
        **describe_settings(stage, settings),
    }


@tool()
def list_renderers() -> dict[str, Any]:
    """이 설치본에서 실제로 쓸 수 있는 Hydra 렌더 델리게이트.

    `husk --list-renderers` 를 그대로 물어본다. 이름을 추측하지 않는다 -
    `start_render` 의 `renderer` 인자에 넣을 수 있는 값이 여기 나온 것 전부다.
    지원되지 않는다고 표시된 델리게이트는 husk 로 최종 렌더를 낼 수 없다
    (뷰포트 전용이다).
    """
    global _RENDERERS_CACHE
    if _RENDERERS_CACHE is not None:
        return _RENDERERS_CACHE

    husk = houdini_bin("husk")
    try:
        proc = subprocess.run(
            [str(husk), "--list-renderers"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "husk --list-renderers 가 120초 안에 끝나지 않았습니다. "
            "라이선스 서버가 응답하는지 확인하세요."
        ) from exc

    renderers = []
    # husk 는 목록을 stderr 로 낸다(실측 확인). 둘 다 훑는다.
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        body = stripped[2:]
        unsupported = body.endswith("- unsupported")
        if unsupported:
            body = body[: -len("- unsupported")].strip()
        name, _, label = body.partition(" (")
        renderers.append({
            "name": name.strip(),
            "label": label.rstrip(")").strip() or None,
            "supported": not unsupported,
        })

    if not renderers:
        raise RuntimeError(
            f"델리게이트 목록을 읽지 못했습니다. husk 출력: "
            f"{clip(proc.stdout + proc.stderr)}"
        )

    _RENDERERS_CACHE = {
        "husk": str(husk),
        "count": len(renderers),
        "renderers": renderers,
        "supported": [r["name"] for r in renderers if r["supported"]],
    }
    return _RENDERERS_CACHE
