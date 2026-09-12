"""렌더를 걸기 전에 점검하는 툴.

렌더는 비싸다. 한 프레임에 몇 분이 걸리는데, 카메라가 안 걸렸거나 라이트가
없어서 새까만 그림이 나오면 그 시간을 통째로 버린다. 걸기 전에 안다.

`start_render` 는 기본적으로 이 점검을 먼저 돌리고, errors 가 있으면 렌더를
시작하지 않는다.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from ._common import lop_stage, require_node
from ._usdrender import render_checks


@tool()
def validate_render(path: str, settings_prim: str | None = None) -> dict[str, Any]:
    """렌더를 걸어도 되는 상태인지 스테이지를 훑어 점검한다.

    보는 것: RenderSettings 가 있는가, 카메라가 걸렸고 실제로 카메라인가,
    해상도가 말이 되는가, 라이트가 있는가, 렌더할 지오메트리가 있는가,
    머티리얼이 걸렸는가, 출력 경로에 쓸 수 있는가, RenderProduct 와
    RenderVar(AOV)가 있는가.

    `errors` 가 비어 있지 않으면 렌더해 봐야 소용이 없다. `warnings` 는 그림이
    나오기는 하지만 의도와 다를 수 있다는 뜻이다 (라이트 없음, 머티리얼 없음).

    Args:
        path: LOP 노드 경로, 또는 usdrender_rop / karma ROP 경로.
            ROP 를 주면 그것이 가리키는 LOP 을 따라간다.
        settings_prim: 점검할 RenderSettings 프림. 생략하면 스테이지 기본값.
    """
    node = _resolve_lop(path)
    stage = lop_stage(node)
    result = render_checks(stage, settings_prim)
    result["node"] = node.path()
    result["comment"] = node.comment()
    return result


def _resolve_lop(path: str) -> hou.LopNode:
    """LOP 이면 그대로, ROP 이면 그 ROP 이 렌더하는 LOP 을 찾아 준다.

    사용자는 보통 렌더 버튼이 달린 ROP 을 손에 들고 있다. 거기서 LOP 을
    직접 찾아 오라고 하면 왕복이 는다.
    """
    node = require_node(path)
    if isinstance(node, hou.LopNode):
        return node

    # usdrender_rop / karma LOP ROP 은 loppath 로 대상을 가리킨다.
    for parm_name in ("loppath", "lopoutput"):
        parm = node.parm(parm_name)
        if parm is None:
            continue
        target = parm.evalAsString().strip()
        if not target:
            continue
        candidate = hou.node(target)
        if isinstance(candidate, hou.LopNode):
            return candidate

    # /out 의 karma ROP 처럼 LOP 을 직접 가리키지 않으면 표시 노드를 쓴다.
    stage_net = hou.node("/stage")
    if stage_net is not None:
        display = stage_net.displayNode()
        if isinstance(display, hou.LopNode):
            return display

    raise ValueError(
        f"{path} 에서 렌더할 LOP 을 찾지 못했습니다 "
        f"(type={node.type().name()}). /stage 아래의 LOP 경로를 직접 주세요."
    )
