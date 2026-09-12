"""USD 어트리뷰트를 읽고 쓴다.

읽기는 컴포지션이 끝난 스테이지에서 바로 한다. 쓰기는 `pythonscript` LOP 을
끼워 넣어서 한다 - 자세한 이유는 usdcommon 의 모듈 docstring 을 본다.

툴 이름에 `usd` 가 붙는 이유는 `houdini_mcp_base` 에 지오메트리 어트리뷰트를
다루는 `list_attributes` 가 이미 있기 때문이다. 둘은 다른 것이다.
"""

from __future__ import annotations

from typing import Any

from houdini_mcp import tool, undoable

from .usdcommon import (
    attr_spec,
    author_attributes,
    jsonify,
    node_report,
    prim_at,
    resolve_lop,
    stage_of,
)

DEFAULT_LOP = "/stage"

UsdValue = float | int | str | bool | list[Any] | None
"""어트리뷰트에 넣을 수 있는 값. 벡터와 배열은 리스트로 준다.

    3.5                     double / float
    [1, 2, 3]               float3 / double3
    [[0,0,0], [1,1,1]]      float3[]
    "over"                  token / string
"""


@tool()
def list_usd_attributes(
    lop: str = DEFAULT_LOP,
    primpath: str = "/",
    authored_only: bool = True,
    frame: float | None = None,
) -> dict[str, Any]:
    """프림의 어트리뷰트 목록 - 이름, 타입, 값이 걸렸는지, 시간에 따라 변하는지.

    값까지 보려면 get_usd_attribute 를 쓴다. 어트리뷰트 하나가 수십만 원소짜리
    배열일 수 있어서 목록에는 값을 싣지 않는다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 프림 경로.
        authored_only: True 면 실제로 값이 걸린 것만. False 면 스키마가 정의한
            것까지 전부(수십 개가 된다).
        frame: 이 프레임에서 쿡한 스테이지를 본다.
    """
    node = resolve_lop(lop)
    prim = prim_at(stage_of(node, frame), primpath)

    attrs = []
    for attr in prim.GetAttributes():
        if authored_only and not attr.HasAuthoredValue():
            continue
        attrs.append(
            {
                "name": attr.GetName(),
                "type": str(attr.GetTypeName()),
                "authored": attr.HasAuthoredValue(),
                "time_varying": attr.ValueMightBeTimeVarying(),
                "time_sample_count": attr.GetNumTimeSamples(),
                "variability": str(attr.GetVariability()).rsplit(".", 1)[-1],
            }
        )

    return {
        "lop": node.path(),
        "path": str(prim.GetPath()),
        "type": str(prim.GetTypeName()) or None,
        "count": len(attrs),
        "attributes": attrs,
    }


@tool()
def get_usd_attribute(
    lop: str = DEFAULT_LOP,
    primpath: str = "/",
    name: str = "",
    frame: float | None = None,
    max_array: int = 16,
) -> dict[str, Any]:
    """어트리뷰트 값을 컴포지션이 끝난 뒤의 값으로 읽는다.

    시간 샘플이 있으면 샘플 시각들도 함께 준다. 값이 어느 레이어에서 왔는지는
    prim_origin 으로 본다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 프림 경로.
        name: 어트리뷰트 이름. 예: radius, points, inputs:intensity
        frame: 이 시각의 값을 읽는다. 생략하면 default 값.
        max_array: 배열 값에서 돌려줄 원소 수 상한.
    """
    from pxr import Usd

    if not name:
        raise ValueError(
            "읽을 어트리뷰트 이름을 주세요. "
            "이름을 모르면 list_usd_attributes 로 먼저 목록을 봅니다."
        )

    node = resolve_lop(lop)
    prim = prim_at(stage_of(node, frame), primpath)

    attr = prim.GetAttribute(name)
    if not attr:
        available = [a.GetName() for a in prim.GetAttributes() if a.HasAuthoredValue()]
        raise ValueError(
            f"{primpath} 에 그런 어트리뷰트가 없습니다: {name!r}. "
            f"값이 걸린 것: {', '.join(available[:20]) or '(없음)'}"
        )

    time = Usd.TimeCode(frame) if frame is not None else Usd.TimeCode.Default()
    samples = attr.GetTimeSamples()

    return {
        "lop": node.path(),
        "path": str(prim.GetPath()),
        "name": attr.GetName(),
        "type": str(attr.GetTypeName()),
        "authored": attr.HasAuthoredValue(),
        "value": jsonify(attr.Get(time), max_array),
        "time_varying": attr.ValueMightBeTimeVarying(),
        "time_samples": [samples[0], samples[-1]] if samples else None,
        "time_sample_count": len(samples),
    }


@tool()
@undoable("Set USD attribute")
def set_usd_attribute(
    lop: str,
    primpath: str,
    name: str,
    value: UsdValue,
    comment: str,
    type_name: str | None = None,
    frame: float | None = None,
    node_name: str | None = None,
) -> dict[str, Any]:
    """어트리뷰트에 값을 건다. `pythonscript` LOP 을 끼워 넣는 방식이다.

    편집이 노드로 남으므로 재쿡·Undo·씬 저장이 자연스럽고, 사용자가 무엇이
    쓰였는지 코드로 볼 수 있다. `lop` 의 하류 연결은 새 노드 뒤로 다시 이어진다.

    이미 있는 어트리뷰트면 타입을 따라간다. 새로 만드는 것이면 `type_name` 이
    필요하다.

    Args:
        lop: 편집의 입력이 될 LOP 노드 경로. 네트워크를 주면 디스플레이 노드.
        primpath: 값을 걸 프림 경로.
        name: 어트리뷰트 이름. 예: radius, inputs:intensity, visibility
        value: 넣을 값. 벡터와 배열은 리스트로. 예: 2.5, [1,0,0], [[0,0,0],[1,1,1]]
        comment: 이 편집이 왜 필요한지. 노드 코멘트로 남는다. 영어로 쓴다.
        type_name: 새 어트리뷰트를 만들 때의 USD 타입. 예: double, float3,
            token, float3[], asset
        frame: 값을 이 시각의 시간 샘플로 건다. 생략하면 default 값.
        node_name: 만들 노드 이름. 생략하면 어트리뷰트 이름에서 짓는다.
    """
    from pxr import Sdf, Usd

    node = resolve_lop(lop)
    prim = prim_at(stage_of(node, frame), primpath)

    attr = prim.GetAttribute(name)
    if attr:
        resolved_type = str(attr.GetTypeName())
    else:
        if not type_name:
            raise ValueError(
                f"{primpath} 에 {name!r} 어트리뷰트가 없습니다. 새로 만들려면 "
                f"type_name 을 주세요(예: double, float3, token, float3[])."
            )
        if not Sdf.ValueTypeNames.Find(type_name):
            raise ValueError(
                f"그런 USD 타입이 없습니다: {type_name!r}. "
                f"double, float, float3, double3, token, string, bool, int, "
                f"asset, float3[] 같은 이름을 씁니다."
            )
        resolved_type = type_name

    spec = [attr_spec(str(prim.GetPath()), name, resolved_type, value, frame)]

    safe = name.replace(":", "_")
    created = author_attributes(node, node_name or f"set_{safe}", comment, spec)
    edited = created["node"]

    # 실제로 걸렸는지 읽어서 돌려준다. 툴이 결과를 알려줘야 한다.
    result = prim_at(stage_of(edited, frame), primpath).GetAttribute(name)
    time = Usd.TimeCode(frame) if frame is not None else Usd.TimeCode.Default()

    return node_report(
        edited,
        {
            "path": primpath,
            "attribute": name,
            "attribute_type": resolved_type,
            "value": jsonify(result.Get(time)) if result else None,
            "rewired": created["rewired"],
        },
    )
