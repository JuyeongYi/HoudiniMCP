"""머티리얼과 셰이더 그래프를 만드는 툴.

노드를 만들고 잇는 것으로 끝내지 않는다. 셰이더 입력은 이름이 42개씩 되고
타입이 맞아야 하므로, 인덱스가 아니라 **이름으로 잇고 타입을 검사한다.**
연결이 걸린 입력에 파라미터를 걸면 값이 무시된다는 것도 알려 준다.

Houdini 22 의 머티리얼 계열은 넷이다 (실측으로 정리).

    materialx   mtlxstandard_surface + mtlxdisplacement. Karma 의 기본 경로이고
                MaterialX 문서로 내보낼 수 있다. 기본값으로 쓴다.
    karma       위에 kma_material_properties 를 더한 것. Karma 전용 속성을
                걸 수 있지만 MaterialX 로 내보낼 수 없다 (실측 확인).
    usdpreview  usdpreviewsurface. 상호운용·프리뷰용. 표현력이 가장 낮다.
    principled  principledshader::2.0. renderMask 가 "VMantra OGL" 이다 —
                Mantra 시절 경로다. 레거시 씬을 만질 때만 쓴다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from .common import (
    KIND_KARMA,
    build_material,
    KIND_MATERIALX,
    KIND_PRINCIPLED,
    KIND_USD_PREVIEW,
    connector_names,
    material_kind,
    node_summary,
    require_comment,
    require_vop,
    set_comment,
    terminal_shader,
    vop_container,
)

KINDS = (KIND_MATERIALX, KIND_KARMA, KIND_USD_PREVIEW, KIND_PRINCIPLED)

RENDERERS = {
    KIND_MATERIALX: "Karma (CPU/XPU), and any MaterialX-aware renderer",
    KIND_KARMA: "Karma (CPU/XPU) only",
    KIND_USD_PREVIEW: "USD Preview / Hydra Storm, and as a fallback everywhere",
    KIND_PRINCIPLED: "Mantra (legacy). Karma support is partial",
}


@tool()
@undoable("Create material")
def create_material(
    parent: str, name: str, comment: str, kind: str = "materialx"
) -> dict[str, Any]:
    """머티리얼을 만든다. 셰이더 노드와 출력 배선까지 갖춘 채로 나온다.

    빈 서브넷을 만들고 사용자가 배선하게 두지 않는다. Houdini 셸프가 쓰는
    조립 로직(voptoolutils)을 그대로 써서, surface 와 displacement 출력이 이미
    연결된 상태로 만든다.

    kind 를 정하기 어려우면 "materialx" 를 쓴다. Houdini 22 의 기본 렌더러인
    Karma 의 표준 경로이고, MaterialX 문서로 저장해 다른 DCC 에서 읽을 수 있다.

    name 은 무엇을 위한 머티리얼인지 드러나게 짓는다. material1 같은 기본 이름은
    나중에 그래프를 읽을 수 없게 만든다. 좋은 예: wall_stone, banner_cloth.
    이름과 코멘트는 씬 파일에 저장되므로 영어로 쓴다.

    Args:
        parent: 머티리얼을 담을 네트워크. 예: /mat, /stage/materiallibrary1
        name: 머티리얼 이름. 역할이 드러나게. 예: wall_stone
        comment: 이 머티리얼이 무엇을 위한 것인지. 필수. 영어로.
            예: "Weathered sandstone for the castle wall"
        kind: materialx / karma / usdpreview / principled 중 하나.
    """
    comment = require_comment(comment, "이 머티리얼")
    if kind not in KINDS:
        raise ValueError(
            f"kind 가 {kind!r} 입니다. 다음 중 하나여야 합니다: {', '.join(KINDS)}. "
            f"모르겠으면 'materialx' 를 쓰세요."
        )

    container = vop_container(parent)
    material = build_material(container, name, kind)
    set_comment(material, comment)
    material.moveToGoodPosition()

    shaders = [
        node_summary(child)
        for child in material.children()
        if child.type().name() not in ("subinput", "suboutput", "subnetconnector")
    ]
    return {
        "path": material.path(),
        "name": material.name(),
        "kind": material_kind(material),
        "comment": material.comment(),
        "type": material.type().name(),
        "outputs": list(material.outputNames()),
        "shaders": shaders,
        "surface_shader": (
            terminal_shader(material).path()
            if terminal_shader(material) is not None
            else None
        ),
        "renderers": RENDERERS[kind],
        "materialx_exportable": kind in (KIND_MATERIALX,),
        "next": (
            "assign_texture 로 텍스처를 붙이고, validate_material 로 검증한 뒤, "
            "assign_material 로 지오메트리에 겁니다."
        ),
    }


def _resolve_input(node: hou.VopNode, name: str) -> int:
    """입력 이름을 인덱스로. 없으면 무엇이 있는지 알려 준다."""
    names = list(node.inputNames())
    if name in names:
        return names.index(name)
    lowered = name.lower()
    close = [candidate for candidate in names if lowered in candidate.lower()]
    hint = f" 비슷한 것: {', '.join(close[:8])}" if close else ""
    raise ValueError(
        f"{node.path()} 에 {name!r} 이라는 입력이 없습니다.{hint} "
        f"shader_graph 나 material_info 로 입력 목록을 먼저 보세요."
    )


def _resolve_output(node: hou.VopNode, name: str) -> int:
    names = list(node.outputNames())
    if name in names:
        return names.index(name)
    raise ValueError(
        f"{node.path()} 에 {name!r} 이라는 출력이 없습니다. "
        f"쓸 수 있는 출력: {', '.join(names) or '(없음)'}"
    )


@tool()
@undoable("Connect shader")
def connect_shader(
    source: str, target: str, to_input: str, from_output: str = "out"
) -> dict[str, Any]:
    """셰이더 노드의 출력을 다른 셰이더의 입력에 **이름으로** 잇는다.

    셰이더 노드는 입력이 수십 개라 인덱스로는 잘못 꽂기 쉽다. 이름으로 걸고,
    거는 즉시 양쪽 타입을 확인해 돌려준다. 타입이 다르면 그대로 두지 않고
    무엇을 끼워야 하는지 알려 준다.

    Args:
        source: 값을 내보내는 노드. 예: /mat/wall_stone/base_color_tex
        target: 값을 받는 노드. 예: /mat/wall_stone/mtlxstandard_surface
        to_input: target 의 입력 이름. 예: base_color, specular_roughness
        from_output: source 의 출력 이름. MaterialX 노드는 대개 "out" 이다.
    """
    source_node = require_vop(source)
    target_node = require_vop(target)

    output_index = _resolve_output(source_node, from_output)
    input_index = _resolve_input(target_node, to_input)

    source_types = list(source_node.outputDataTypes())
    target_types = list(target_node.inputDataTypes())
    from_type = source_types[output_index] if output_index < len(source_types) else ""
    to_type = target_types[input_index] if input_index < len(target_types) else ""

    target_node.setNamedInput(to_input, source_node, from_output)

    mismatch = bool(from_type and to_type and from_type != to_type)
    result: dict[str, Any] = {
        "source": source_node.path(),
        "from_output": from_output,
        "from_type": from_type,
        "target": target_node.path(),
        "to_input": to_input,
        "to_type": to_type,
        "type_match": not mismatch,
    }
    if mismatch:
        # 끊지는 않는다. Houdini 가 암묵 변환을 하는 조합도 있기 때문이다.
        # 대신 그대로 두면 안 되는 경우를 모델이 판단할 수 있게 알려 준다.
        result["warning"] = (
            f"타입이 다릅니다: {from_type} -> {to_type}. "
            f"Houdini 가 변환해 주는 조합도 있지만, 의도한 것이 아니라면 "
            f"mtlxconvert 나 mtlxseparate3c 같은 변환 노드를 사이에 넣으세요."
        )
    if target_node.errors():
        result["errors"] = list(target_node.errors())
    return result


@tool()
@undoable("Disconnect shader")
def disconnect_shader(target: str, to_input: str) -> dict[str, Any]:
    """셰이더 입력 하나를 이름으로 끊는다.

    끊고 나면 그 입력은 노드의 파라미터 값을 쓴다. 끊은 뒤의 값을 함께
    돌려주므로 결과가 어떻게 되는지 바로 알 수 있다.

    Args:
        target: 입력을 끊을 노드 경로.
        to_input: 끊을 입력 이름. 예: base_color
    """
    node = require_vop(target)
    index = _resolve_input(node, to_input)

    removed = None
    for connection in node.inputConnections():
        if connection.outputName() == to_input:
            removed = connection.inputNode().path()
            break

    node.setInput(index, None)

    value: Any = None
    parm_tuple = node.parmTuple(to_input)
    parm = node.parm(to_input)
    if parm_tuple is not None:
        value = list(parm_tuple.eval())
    elif parm is not None:
        value = parm.eval()

    return {
        "path": node.path(),
        "to_input": to_input,
        "disconnected_from": removed,
        "value_now_in_effect": value,
    }


def _apply(node: hou.VopNode, name: str, value: Any) -> dict[str, Any]:
    """파라미터 하나를 건다. 벡터는 리스트로 받는다."""
    parm_tuple = node.parmTuple(name)
    parm = node.parm(name)

    if isinstance(value, (list, tuple)):
        if parm_tuple is None:
            raise ValueError(
                f"{node.path()} 의 {name!r} 은 벡터 파라미터가 아닙니다. "
                f"값 하나를 주세요."
            )
        if len(parm_tuple) != len(value):
            raise ValueError(
                f"{name!r} 은 성분이 {len(parm_tuple)} 개인데 {len(value)} 개를 줬습니다. "
                f"성분 이름: {', '.join(p.name() for p in parm_tuple)}"
            )
        parm_tuple.set(tuple(value))
        return {"name": name, "value": list(parm_tuple.eval())}

    if parm is not None:
        parm.set(value)
        return {"name": name, "value": parm.eval()}

    if parm_tuple is not None:
        components = ", ".join(p.name() for p in parm_tuple)
        raise ValueError(
            f"{name!r} 은 벡터 파라미터입니다. 리스트로 주거나 "
            f"성분 이름으로 거세요: {components}"
        )

    raise ValueError(
        f"{node.path()} 에 {name!r} 파라미터가 없습니다. "
        f"material_info 나 list_parms 로 이름을 먼저 확인하세요."
    )


@tool()
@undoable("Set material parameters")
def set_material_parms(path: str, parms: dict[str, Any]) -> dict[str, Any]:
    """셰이더 파라미터를 건다. 색·벡터는 리스트로 한 번에 준다.

    base 의 set_parms 는 성분 이름(base_colorr, base_colorg, ...)으로만 받지만
    셰이더는 색 입력이 대부분이라 여기서는 [r, g, b] 로 받는다.

    **연결이 걸린 입력에 값을 걸면 그 값은 렌더에 반영되지 않는다.** 텍스처를
    물려 둔 base_color 에 색을 거는 실수가 흔하므로, 그런 입력이 있으면
    overridden_by_connection 에 담아 돌려준다.

    Args:
        path: 셰이더 노드 경로. 예: /mat/wall_stone/mtlxstandard_surface
        parms: 이름과 값. 예: {"base_color": [0.4, 0.25, 0.1],
            "specular_roughness": 0.55, "metalness": 0.0}
    """
    node = require_vop(path)
    if not parms:
        raise ValueError("parms 가 비어 있습니다. 걸 파라미터를 주세요.")

    connected = {
        connection.outputName() for connection in node.inputConnections()
    }

    applied = [_apply(node, name, value) for name, value in parms.items()]
    overridden = [name for name in parms if name in connected]

    result: dict[str, Any] = {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "applied": applied,
    }
    if overridden:
        result["overridden_by_connection"] = overridden
        result["warning"] = (
            f"{', '.join(overridden)} 에는 연결이 걸려 있어 이 값이 렌더에 "
            f"반영되지 않습니다. 값을 쓰려면 disconnect_shader 로 먼저 끊으세요."
        )
    if node.errors():
        result["errors"] = list(node.errors())
    return result


@tool()
def shader_inputs(path: str) -> dict[str, Any]:
    """셰이더 노드가 받을 수 있는 입력과 낼 수 있는 출력을 타입과 함께 준다.

    connect_shader 를 쓰기 전에 이름과 타입을 확인하는 용도다. 어느 입력에
    이미 무엇이 물려 있는지도 함께 준다.

    Args:
        path: 셰이더 노드 경로.
    """
    node = require_vop(path)
    connections = {
        connection.outputName(): connection.inputNode().path()
        for connection in node.inputConnections()
    }
    ports = connector_names(node)
    for entry in ports["inputs"]:
        source = connections.get(entry["name"])
        if source is not None:
            entry["connected_from"] = source
    return {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "render_mask": node.renderMask(),
        **ports,
    }

