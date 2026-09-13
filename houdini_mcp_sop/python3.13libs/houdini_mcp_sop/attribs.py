"""어트리뷰트를 읽고 만드는 툴.

`houdini_mcp_base` 의 `attribute_values` 는 값을 몇 개 들여다보는 것이고,
여기 `attrib_stats` 는 **전체 분포**를 본다. 점 10만 개를 그대로 보내지 않고
numpy 로 통계·분위수·히스토그램까지 줄여서 돌려준다.

읽기 경로는 `pointFloatAttribValuesAsString` 계열이다. C++ 쪽에서 바이트를
통째로 받아 `numpy.frombuffer` 로 꽂으므로 파이썬 점 루프가 없다.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Sequence

import numpy

from houdini_mcp import tool, undoable
from houdini_mcp_base import paths

from ._common import (
    OWNERS,
    attrib_array,
    build,
    element_count,
    find_attrib,
    geometry_at,
    report,
    set_menu,
    snapshot,
    summarize,
)

MAX_BINS = 64
"""히스토그램 구간 수 상한. 더 잘게 나눠 봐야 모델이 읽지 못한다."""

_ATTRIB_TYPES = {
    "float": "float",
    "int": "int",
    "vector": "vector",
    "string": "index",
}


@tool()
def attrib_stats(
    path: str, name: str, owner: str = "point", bins: int = 16
) -> dict[str, Any]:
    """어트리뷰트 전체의 분포를 통계로 돌려준다.

    성분별 min/max/mean/std 와 분위수(p05~p95), 그리고 히스토그램을 준다.
    성분이 여럿인 어트리뷰트(P, N, Cd)는 크기(L2 노름) 통계도 함께 낸다.

    값 자체가 필요하면 base 의 attribute_values 로 몇 개만 보거나,
    export_attribute 로 .npy 에 써서 경로를 받으세요.

    Args:
        path: SOP 노드 경로.
        name: 어트리뷰트 이름. 예: P, N, Cd, pscale
        owner: point / prim / vertex / detail.
        bins: 히스토그램 구간 수. 최대 64.
    """
    if not 1 <= bins <= MAX_BINS:
        raise ValueError(f"bins 는 1 이상 {MAX_BINS} 이하여야 합니다: {bins}")

    _, geo = geometry_at(path)
    if owner == "detail":
        attrib = find_attrib(geo, "detail", name)
        return {
            "path": path,
            "name": name,
            "owner": owner,
            "type": str(attrib.dataType()).rsplit(".", 1)[-1],
            "size": attrib.size(),
            "value": geo.attribValue(name),
        }

    attrib = find_attrib(geo, owner, name)
    stats = summarize(attrib_array(geo, owner, name), bins=bins)
    return {
        "path": path,
        "name": name,
        "owner": owner,
        "type": str(attrib.dataType()).rsplit(".", 1)[-1],
        "qualifier": attrib.qualifier() or None,
        "elements": element_count(geo, owner),
        **stats,
    }


@tool()
def export_attribute(
    path: str, name: str, file_path: str, owner: str = "point"
) -> dict[str, Any]:
    """어트리뷰트 값 전체를 .npy 파일로 쓰고 경로를 돌려준다.

    통계로는 부족하고 원본 배열이 필요할 때 쓴다. MCP 응답으로 점 10만 개를
    실어 보내면 모델 컨텍스트만 태우므로, 값은 파일로 나가고 여기서는 모양과
    경로만 돌려준다.

    Args:
        path: SOP 노드 경로.
        name: 어트리뷰트 이름.
        file_path: 저장할 .npy 경로. 확장자가 없으면 붙여 준다. $HIP 같은 변수를
            그대로 쓴다.
        owner: point / prim / vertex.
    """
    if owner == "detail":
        raise ValueError(
            "detail 어트리뷰트는 값이 하나뿐이라 파일로 쓸 것이 없습니다. "
            "attrib_stats 로 바로 읽으세요."
        )

    _, geo = geometry_at(path)
    array = attrib_array(geo, owner, name)

    # 확장자는 원문에서 고친다. 원문을 Path 로 만들어 mkdir 하면 현재 디렉토리에
    # `$HIP` 폴더가 생긴다(실측). 파일시스템에는 전개판만 넘긴다.
    raw = PurePosixPath(paths.to_parm(file_path))
    if raw.suffix != ".npy":
        raw = raw.with_suffix(".npy")
    paths.require_resolved(raw)
    target = paths.to_path(raw)
    paths.ensure_parent(target)
    numpy.save(target, array)

    return {
        "path": path,
        "name": name,
        "owner": owner,
        "file": paths.describe(raw),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "bytes": target.stat().st_size,
    }


@tool()
@undoable("Add normals")
def add_normals(
    path: str,
    comment: str,
    owner: str = "point",
    cusp_angle: float = 60.0,
    weighting: str = "angle",
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """노멀을 만든다(Normal SOP). 이미 있으면 덮어쓰기 전에 알려 준다.

    Normal SOP 의 22.0 기본값은 vertex 노멀이다. 여기 기본값은 point 로
    두었다 — 뒤 공정(copytopoints 의 방향, 익스트루드)이 점 노멀을 본다.

    Args:
        path: 입력 SOP 경로.
        comment: 왜 노멀이 필요한지. 필수. 영어로.
        owner: point / vertex / prim / detail. 어디에 N 을 달지.
        cusp_angle: 이 각도(도)보다 크게 꺾이면 날카롭게 유지한다.
        weighting: angle(꼭짓점 각도) / area(면적) / uniform(균등).
        group: 대상 패턴. 비우면 전부.
        name: 노드 이름. 예: smooth_wall_normals
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    existing = {
        "point": geo.findPointAttrib("N") is not None,
        "vertex": geo.findVertexAttrib("N") is not None,
        "prim": geo.findPrimAttrib("N") is not None,
    }

    node = build(source, "normal", comment, name, parms={"group": group})
    set_menu(node, "type", {"point": "typepoint", "vertex": "typevertex",
                            "prim": "typeprim", "detail": "typedetail"}.get(owner, owner))
    set_menu(node, "method", weighting)
    node.parm("cuspangle").set(float(cusp_angle))

    result = report(node, before)
    result["existing_normals"] = existing
    if existing.get(owner):
        result["notes"] = [
            f"{path} 에 이미 {owner} 어트리뷰트 N 이 있었습니다. 이 노드가 덮어씁니다."
        ]
    return result


@tool()
@undoable("Create attribute")
def create_attribute(
    path: str,
    comment: str,
    attrib_name: str,
    owner: str = "point",
    attrib_type: str = "float",
    value: Sequence[float] | float | str | None = None,
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """어트리뷰트를 만들어 상수 값을 채운다(AttribCreate SOP).

    detail 어트리뷰트로 메타데이터를 남기거나, copytopoints 가 볼 pscale/orient
    같은 것을 심을 때 쓴다. 값이 값마다 달라야 하면 이 툴이 아니라
    attribwrangle 노드를 create_node 로 만들고 VEX 를 쓰세요.

    Args:
        path: 입력 SOP 경로.
        comment: 이 어트리뷰트가 왜 필요한지. 필수. 영어로.
        attrib_name: 만들 어트리뷰트 이름. 예: pscale, variant, lod
        owner: point / prim / vertex / detail.
        attrib_type: float / int / vector / string.
        value: 채울 값. float/int 는 숫자 하나, vector 는 값 3개, string 은 문자열.
        group: 대상 패턴. 비우면 전부.
        name: 노드 이름. 예: set_merlon_scale
    """
    if owner not in OWNERS:
        raise ValueError(f"owner 는 {', '.join(OWNERS)} 중 하나여야 합니다: {owner!r}")
    if attrib_type not in _ATTRIB_TYPES:
        raise ValueError(
            f"attrib_type {attrib_type!r} 는 모릅니다. "
            f"쓸 수 있는 값: {', '.join(_ATTRIB_TYPES)}"
        )

    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(source, "attribcreate::2.0", comment, name, parms={"group": group})
    node.parm("numattr").set(1)
    node.parm("name1").set(attrib_name)
    set_menu(node, "class1", {"prim": "primitive"}.get(owner, owner))
    set_menu(node, "type1", _ATTRIB_TYPES[attrib_type])

    if value is not None:
        if attrib_type == "string":
            node.parm("string1").set(str(value))
        elif attrib_type == "vector":
            components = list(value) if isinstance(value, (list, tuple)) else [value] * 3
            if len(components) != 3:
                raise ValueError(
                    f"attrib_type='vector' 에는 값 3개가 필요합니다. 받은 것: {value}"
                )
            node.parm("size1").set(3)
            for index, component in enumerate(components, start=1):
                node.parm(f"value1v{index}").set(float(component))
        else:
            scalar = value[0] if isinstance(value, (list, tuple)) else value
            node.parm("size1").set(1)
            node.parm("value1v1").set(float(scalar))

    result = report(node, before)
    created = find_attrib(node.geometry(), owner, attrib_name)
    result["attribute"] = {
        "name": attrib_name,
        "owner": owner,
        "type": str(created.dataType()).rsplit(".", 1)[-1],
        "size": created.size(),
    }
    return result
