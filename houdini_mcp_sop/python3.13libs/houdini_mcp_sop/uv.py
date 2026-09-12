"""UV 를 만들고 품질을 확인하는 툴.

기존 구현들은 uvproject/uvunwrap 노드를 놓고 끝난다. 그런데 UV 는 놓았다고
된 것이 아니다 — 0~1 밖으로 새거나, 아일랜드가 겹치거나, 늘어나 있으면 텍스처가
어긋난다. 그걸 보려면 UV 를 읽어 봐야 한다.

그래서 여기 툴은 UV 를 만든 뒤 곧바로 `uv_report` 와 같은 검사를 돌려
결과에 붙인다. 검사는 numpy 벌크 경로로 한다.
"""

from __future__ import annotations

from typing import Any, Sequence

import hou
import numpy

from houdini_mcp import tool, undoable

from ._common import (
    attrib_array,
    build,
    find_attrib,
    geometry_at,
    report,
    set_menu,
    snapshot,
    vec3,
)

OCCUPANCY_GRID = 64
"""UV 공간을 나눠 볼 격자 해상도. 정점이 닿은 칸을 센다."""

OCCUPANCY_MIN_SAMPLES = OCCUPANCY_GRID * OCCUPANCY_GRID // 4
"""점유율을 믿을 수 있는 최소 UV 정점 수.

점유율은 정점이 닿은 칸만 세므로 성긴 메시에서는 실제 면적보다 훨씬 작게 나온다.
상자 하나(정점 24개)의 점유율이 0.3% 로 나오는 식이다. 표본이 이보다 적으면
reliable=false 로 표시하고 그 값으로 경고하지 않는다."""

UNWRAP_TEXTURE_SIZE = 1024.0
"""UVUnwrap 의 spacing 은 UV 비율이고 UVLayout 의 padding 은 픽셀이다.

두 노드에 padding 을 같은 뜻으로 주려고 기준 텍스처 크기를 하나 정해 둔다."""


def _uv_array(geo: hou.Geometry, uv_attrib: str) -> tuple[numpy.ndarray, str]:
    """UV 를 vertex 에서 먼저 찾고 없으면 point 에서 찾는다.

    UV 는 보통 vertex 어트리뷰트다(솔기에서 한 점이 여러 UV 를 갖기 때문).
    하지만 point 에 있는 경우도 흔해서 양쪽을 본다.
    """
    for owner in ("vertex", "point"):
        try:
            find_attrib(geo, owner, uv_attrib)
        except ValueError:
            continue
        return attrib_array(geo, owner, uv_attrib), owner
    raise ValueError(
        f"어트리뷰트 {uv_attrib!r} 가 vertex 에도 point 에도 없습니다. "
        f"uv_project 나 auto_uv 로 UV 를 먼저 만드세요."
    )


def _uv_metrics(geo: hou.Geometry, uv_attrib: str) -> dict[str, Any]:
    """UV 품질 지표. 전부 numpy 벌크 연산이라 점 루프가 없다."""
    array, owner = _uv_array(geo, uv_attrib)
    uv = array[:, :2].astype(numpy.float64, copy=False)
    if uv.size == 0:
        return {"attribute": uv_attrib, "owner": owner, "count": 0}

    umin, vmin = uv.min(axis=0)
    umax, vmax = uv.max(axis=0)
    outside = numpy.count_nonzero(
        (uv[:, 0] < 0.0) | (uv[:, 0] > 1.0) | (uv[:, 1] < 0.0) | (uv[:, 1] > 1.0)
    )

    # UV 공간을 얼마나 쓰고 있는지 격자 점유로 어림한다. 면적을 정확히 재려면
    # 프림별 UV 폴리곤 면적을 구해야 하는데 그건 파이썬 프림 루프를 부른다.
    # 여기서는 정점 위치만 보고 하한을 낸다 — 그래서 성긴 메시에서는 실제보다
    # 작게 나오고, OCCUPANCY_MIN_SAMPLES 미만이면 reliable=false 로 표시한다.
    inside = uv[(uv[:, 0] >= 0.0) & (uv[:, 0] <= 1.0) & (uv[:, 1] >= 0.0) & (uv[:, 1] <= 1.0)]
    if inside.size:
        cells = numpy.clip((inside * OCCUPANCY_GRID).astype(numpy.int32), 0, OCCUPANCY_GRID - 1)
        occupied = numpy.unique(cells[:, 0] * OCCUPANCY_GRID + cells[:, 1]).size
    else:
        occupied = 0

    return {
        "attribute": uv_attrib,
        "owner": owner,
        "count": int(uv.shape[0]),
        "bbox": {"min": [float(umin), float(vmin)], "max": [float(umax), float(vmax)]},
        "outside_unit_square": {
            "count": int(outside),
            "fraction": float(outside) / float(uv.shape[0]),
        },
        "occupancy": {
            "grid": OCCUPANCY_GRID,
            "cells_used": int(occupied),
            "fraction": float(occupied) / float(OCCUPANCY_GRID * OCCUPANCY_GRID),
            "reliable": bool(uv.shape[0] >= OCCUPANCY_MIN_SAMPLES),
        },
    }


def _uv_notes(metrics: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    outside = metrics.get("outside_unit_square", {})
    if outside.get("count"):
        notes.append(
            f"UV 의 {outside['fraction']:.1%} 가 0~1 밖에 있습니다. 타일링이 의도가 "
            f"아니면 auto_uv 로 레이아웃을 다시 잡으세요."
        )
    occupancy = metrics.get("occupancy", {})
    if occupancy.get("reliable") and occupancy.get("fraction", 0.0) < 0.05:
        notes.append(
            f"UV 가 0~1 공간의 {occupancy['fraction']:.1%} 만 쓰고 있습니다. "
            f"텍스처 해상도가 낭비됩니다. auto_uv 의 pack_scale 을 키우세요."
        )
    return notes


@tool()
def uv_report(path: str, uv_attrib: str = "uv") -> dict[str, Any]:
    """UV 가 제대로 깔렸는지 확인한다.

    UV 바운딩 박스, 0~1 밖으로 나간 비율, 점유 격자 사용률을 돌려준다.
    "uvproject 를 놓았다"와 "UV 가 쓸 만하다"는 다르다.

    점유율은 UV 정점이 닿은 격자 칸만 세므로 실제 면적의 하한이다. 표본이 적으면
    occupancy.reliable 이 false 로 온다 — 그때는 그 값으로 판단하지 마세요.

    Args:
        path: SOP 노드 경로.
        uv_attrib: UV 어트리뷰트 이름. 기본 uv.
    """
    _, geo = geometry_at(path)
    metrics = _uv_metrics(geo, uv_attrib)
    result: dict[str, Any] = {"path": path, **metrics}
    notes = _uv_notes(metrics)
    if notes:
        result["notes"] = notes
    return result


@tool()
@undoable("Project UVs")
def uv_project(
    path: str,
    comment: str,
    projection: str = "texture",
    uv_attrib: str = "uv",
    fit_to_bounds: bool = True,
    translate: Sequence[float] | None = None,
    rotate: Sequence[float] | None = None,
    scale: Sequence[float] | None = None,
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """투영으로 UV 를 만든다(UVProject SOP). 만든 뒤 UV 품질까지 확인해 돌려준다.

    UVProject 를 그냥 놓기만 하면 투영 기준이 단위 크기라서, 지오메트리가 조금만
    커도 UV 가 0~1 밖으로 한참 벗어난다. Houdini UI 에서 "Initialize" 를 눌러야
    맞춰지는 부분인데 그 버튼은 스크립트에서 부를 수 없다. 대신 입력 바운딩 박스로
    직접 맞춘다(fit_to_bounds) — 실측으로 UV 가 정확히 0~1 에 들어온다.

    projection 값이 Houdini UI 라벨과 다르다. "texture" 가 Orthographic 이다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇에 왜 UV 를 까는지. 필수. 영어로.
        projection: texture(정사영) / polar / cylin(원통) / torus / wrap.
        uv_attrib: 만들 UV 어트리뷰트 이름.
        fit_to_bounds: 투영 기준을 입력 바운딩 박스에 맞춰 UV 가 0~1 에 들어오게
            할지. translate/scale 을 직접 주면 그쪽이 이긴다.
        translate: 투영 기준의 이동 (x,y,z).
        rotate: 투영 기준의 회전 (rx,ry,rz) 도 단위. 정사영 방향을 이걸로 돌린다.
        scale: 투영 기준의 배율 (sx,sy,sz).
        group: 대상 프림 패턴. 비우면 전부.
        name: 노드 이름. 예: uv_wall_front
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    bounds = geo.boundingBox()
    if fit_to_bounds and bounds.isValid():
        center, extent = bounds.center(), bounds.sizevec()
        # 크기가 0 인 축(평면 지오메트리)은 1 로 둔다. 0 으로 나누면 UV 가 깨진다.
        fit_t = (center[0], center[1], center[2])
        fit_s = tuple(extent[i] if extent[i] > 0.0 else 1.0 for i in range(3))
    else:
        fit_t, fit_s = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)

    tx, ty, tz = vec3(translate, fit_t)
    rx, ry, rz = vec3(rotate, (0.0, 0.0, 0.0))
    sx, sy, sz = vec3(scale, fit_s)

    node = build(
        source,
        "uvproject",
        comment,
        name,
        parms={
            "group": group,
            "uvattrib": uv_attrib,
            "tx": tx, "ty": ty, "tz": tz,
            "rx": rx, "ry": ry, "rz": rz,
            "sx": sx, "sy": sy, "sz": sz,
        },
    )
    set_menu(node, "projtype", projection)

    result = report(node, before)
    metrics = _uv_metrics(node.geometry(), uv_attrib)
    result["uv"] = metrics
    notes = _uv_notes(metrics)
    if notes:
        result.setdefault("notes", []).extend(notes)
    return result


@tool()
@undoable("Auto UV")
def auto_uv(
    path: str,
    comment: str,
    method: str = "flatten",
    uv_attrib: str = "uv",
    pack_scale: float = 1.0,
    padding: int = 2,
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """UV 를 자동으로 펴고 0~1 안에 배치한다. 결과 품질까지 확인해 돌려준다.

    method="flatten" 은 UVFlatten + UVLayout 두 노드를 만든다. 펴기와 배치는
    별개의 일이라 Houdini 도 노드를 나눠 두었다. 여기서는 한 번의 호출로 둘을
    만들고 마지막 노드를 돌려준다.

    method="unwrap" 은 UVUnwrap 하나다. 육면 투영이라 빠르지만 왜곡이 크다.
    기계적인 형태에 쓴다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇에 왜 UV 를 까는지. 필수. 영어로.
        method: flatten(펴기+배치) / unwrap(육면 투영).
        uv_attrib: 만들 UV 어트리뷰트 이름.
        pack_scale: 배치 후 전체 배율. 1.0 이면 0~1 을 채운다.
        padding: 아일랜드 사이 여백. 텍스처 픽셀 수로 준다. UVLayout 은 픽셀을
            그대로 받고, UVUnwrap 은 UV 비율만 받으므로 1024 로 나눠 넘긴다.
        group: 대상 프림 패턴. 비우면 전부.
        name: 노드 이름. 예: uv_rock_auto
    """
    if method not in ("flatten", "unwrap"):
        raise ValueError(
            f"method {method!r} 는 모릅니다. 쓸 수 있는 값: flatten, unwrap"
        )

    source, geo = geometry_at(path)
    before = snapshot(geo)

    if method == "unwrap":
        node = build(
            source,
            "uvunwrap",
            comment,
            name,
            parms={"group": group, "uvattrib": uv_attrib, "scale": float(pack_scale),
                   "spacing": float(padding) / UNWRAP_TEXTURE_SIZE},
        )
    else:
        flatten = build(
            source,
            "uvflatten",
            f"{comment} (flatten)",
            None if name is None else f"{name}_flatten",
            parms={"group": group, "uvattrib": uv_attrib},
        )
        node = build(
            flatten,
            "uvlayout",
            comment,
            name,
            parms={"group": group, "uvattrib": uv_attrib, "scale": float(pack_scale),
                   "padding": int(padding)},
        )

    result = report(node, before)
    metrics = _uv_metrics(node.geometry(), uv_attrib)
    result["uv"] = metrics
    notes = _uv_notes(metrics)
    if notes:
        result.setdefault("notes", []).extend(notes)
    return result
