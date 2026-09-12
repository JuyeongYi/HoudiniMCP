"""지오메트리에 질문하는 툴 — 근접·레이·인트린식·볼륨·파일 내보내기.

근접 질의를 파이썬 전탐색으로 하지 않는다. `scipy` 는 번들에 없지만
`hou.Geometry` 가 `nearestPoint` / `nearestPoints` / `nearestPrim` / `intersect`
를 이미 갖고 있다(실측 확인). 전부 C++ 쪽 가속 구조를 쓴다.

볼륨도 복셀 값을 통째로 넘기지 않는다. 해상도·복셀 크기·값 범위만 돌려준다.
복셀 10만 개를 JSON 으로 실어 보내면 모델 컨텍스트만 태운다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import hou

from houdini_mcp import tool

from ._common import bbox_dict, geometry_at, vec3

MAX_NEAREST = 100
"""한 번에 돌려줄 근접 포인트 수 상한."""

MAX_INTRINSICS = 60
"""한 번에 돌려줄 인트린식 개수 상한. 볼륨은 30개가 넘는다."""

# saveToFile 이 확장자로 포맷을 정한다. 여기 없는 확장자도 Houdini 가 받을 수
# 있지만, 모델이 무엇을 쓸 수 있는지 알려면 목록이 필요하다.

def _point_entry(point: hou.Point, origin: Sequence[float]) -> dict[str, Any]:
    position = point.position()
    delta = [position[i] - origin[i] for i in range(3)]
    distance = sum(d * d for d in delta) ** 0.5
    return {
        "number": point.number(),
        "P": [position[0], position[1], position[2]],
        "distance": distance,
    }


@tool()
def nearest_point(
    path: str,
    position: Sequence[float],
    count: int = 1,
    max_radius: float | None = None,
    point_group: str | None = None,
) -> dict[str, Any]:
    """주어진 위치에 가장 가까운 포인트를 찾는다.

    hou.Geometry 의 가속 구조를 쓴다. 포인트를 전부 순회하지 않으므로 점이
    많아도 빠르다.

    Args:
        path: SOP 노드 경로.
        position: 기준 위치 (x,y,z).
        count: 몇 개를 찾을지. 최대 100.
        max_radius: 이 반경 밖은 보지 않는다. 생략하면 제한 없음.
        point_group: 이 그룹 안에서만 찾는다. 그룹 이름 또는 패턴.
    """
    if not 1 <= count <= MAX_NEAREST:
        raise ValueError(f"count 는 1 이상 {MAX_NEAREST} 이하여야 합니다: {count}")

    _, geo = geometry_at(path)
    if geo.pointCount() == 0:
        raise ValueError(f"{path} 에 포인트가 없습니다. 입력 지오메트리를 확인하세요.")

    origin = vec3(position, (0.0, 0.0, 0.0))
    radius = 1e18 if max_radius is None else float(max_radius)
    group = point_group or ""

    if count == 1:
        found = geo.nearestPoint(origin, group, radius)
        points = [found] if found is not None else []
    else:
        found = geo.nearestPoints(origin, count, group, radius)
        points = list(found) if found else []

    return {
        "path": path,
        "position": list(origin),
        "total_points": geo.pointCount(),
        "found": len(points),
        "points": [_point_entry(p, origin) for p in points],
    }


@tool()
def nearest_prim(path: str, position: Sequence[float]) -> dict[str, Any]:
    """주어진 위치에 가장 가까운 프리미티브와 그 위의 최근접 점을 찾는다.

    표면 위 좌표(u, v)까지 돌려준다. 어떤 면에 무엇을 붙일지 정할 때 쓴다.

    Args:
        path: SOP 노드 경로.
        position: 기준 위치 (x,y,z).
    """
    _, geo = geometry_at(path)
    if geo.primCount() == 0:
        raise ValueError(f"{path} 에 프리미티브가 없습니다. 입력 지오메트리를 확인하세요.")

    origin = vec3(position, (0.0, 0.0, 0.0))
    prim, distance, u, v = geo.nearestPrim(origin)
    if prim is None:
        return {"path": path, "position": list(origin), "found": False}

    surface = prim.positionAtInterior(u, v, 0.0)
    return {
        "path": path,
        "position": list(origin),
        "found": True,
        "prim": {
            "number": prim.number(),
            "type": prim.type().name(),
            "vertices": prim.numVertices(),
        },
        "distance": float(distance),
        "uv": [float(u), float(v)],
        "surface_position": [surface[0], surface[1], surface[2]],
    }


@tool()
def ray_intersect(
    path: str,
    origin: Sequence[float],
    direction: Sequence[float],
    max_distance: float | None = None,
) -> dict[str, Any]:
    """지오메트리에 레이를 쏴서 맞는 지점을 찾는다.

    "이 점에서 아래로 쏘면 바닥이 어디인가" 같은 질문에 쓴다. 배치할 높이를
    정할 때 유용하다.

    Args:
        path: SOP 노드 경로.
        origin: 레이 시작점 (x,y,z).
        direction: 레이 방향 (x,y,z). 정규화하지 않아도 된다.
        max_distance: 이 거리까지만 본다. 생략하면 제한 없음.
    """
    _, geo = geometry_at(path)
    start = hou.Vector3(vec3(origin, (0.0, 0.0, 0.0)))
    ray = hou.Vector3(vec3(direction, (0.0, -1.0, 0.0)))
    if ray.length() == 0.0:
        raise ValueError("direction 이 영벡터입니다. 방향을 주세요. 예: [0, -1, 0]")

    hit_position, hit_normal, hit_uvw = hou.Vector3(), hou.Vector3(), hou.Vector3()
    prim_number = geo.intersect(
        start,
        ray,
        hit_position,
        hit_normal,
        hit_uvw,
        max_hit=1e18 if max_distance is None else float(max_distance),
    )
    if prim_number < 0:
        return {
            "path": path,
            "origin": list(start),
            "direction": list(ray),
            "hit": False,
        }

    return {
        "path": path,
        "origin": list(start),
        "direction": list(ray),
        "hit": True,
        "prim": prim_number,
        "position": [hit_position[0], hit_position[1], hit_position[2]],
        "normal": [hit_normal[0], hit_normal[1], hit_normal[2]],
        "uvw": [hit_uvw[0], hit_uvw[1], hit_uvw[2]],
        "distance": float((hit_position - start).length()),
    }


@tool()
def prim_intrinsics(
    path: str, prim_number: int = 0, names: Sequence[str] | None = None
) -> dict[str, Any]:
    """프리미티브의 인트린식을 읽는다.

    인트린식은 어트리뷰트가 아니라 프림 자체가 들고 있는 값이다. 면적
    (measuredarea), 부피(measuredvolume), 패킹된 지오메트리의 트랜스폼 같은 것이
    여기 있다. 어트리뷰트 목록만 봐서는 보이지 않는다.

    Args:
        path: SOP 노드 경로.
        prim_number: 볼 프리미티브 번호.
        names: 읽을 인트린식 이름들. 생략하면 전부(최대 60개).
    """
    _, geo = geometry_at(path)
    if not 0 <= prim_number < geo.primCount():
        raise ValueError(
            f"prim_number {prim_number} 가 범위를 벗어났습니다. "
            f"{path} 의 프리미티브는 {geo.primCount()}개입니다 (0 ~ {geo.primCount() - 1})."
        )

    prim = geo.prim(prim_number)
    available = list(prim.intrinsicNames())
    wanted = list(names) if names else available[:MAX_INTRINSICS]

    values: dict[str, Any] = {}
    unknown: list[str] = []
    for key in wanted:
        if key not in available:
            unknown.append(key)
            continue
        try:
            values[key] = _jsonable(prim.intrinsicValue(key))
        except hou.Error as exc:
            values[key] = f"<읽지 못함: {exc}>"

    result: dict[str, Any] = {
        "path": path,
        "prim": prim_number,
        "type": prim.type().name(),
        "intrinsics": values,
        "available": available,
    }
    if unknown:
        result["unknown"] = unknown
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return [_jsonable(item) for item in value]
    except TypeError:
        return str(value)


@tool()
def volume_info(path: str, prim_number: int | None = None) -> dict[str, Any]:
    """볼륨/VDB 프리미티브의 해상도·복셀 크기·값 범위를 돌려준다.

    복셀 값 자체는 돌려주지 않는다. 32^3 만 해도 32768개라 응답으로 낼 것이
    아니다. 값의 범위와 평균만으로 대부분의 판단이 된다.

    Args:
        path: SOP 노드 경로.
        prim_number: 볼 프리미티브 번호. 생략하면 볼륨 프림 전부를 돌려준다.
    """
    _, geo = geometry_at(path)
    candidates = (
        [geo.prim(prim_number)]
        if prim_number is not None
        else [p for p in geo.prims() if isinstance(p, (hou.Volume, hou.VDB))]
    )
    if prim_number is not None and not isinstance(candidates[0], (hou.Volume, hou.VDB)):
        raise ValueError(
            f"{path} 의 프리미티브 {prim_number} 는 "
            f"{candidates[0].type().name()} 이라 볼륨이 아닙니다. "
            f"geometry_stats 의 prim_types 로 볼륨이 몇 번인지 확인하세요."
        )
    if not candidates:
        raise ValueError(
            f"{path} 에 볼륨이나 VDB 프리미티브가 없습니다. "
            f"convert_geometry 로 vdb 로 바꾸거나 볼륨을 만드는 노드를 먼저 놓으세요."
        )

    return {
        "path": path,
        "count": len(candidates),
        "volumes": [_volume_entry(prim) for prim in candidates],
    }


def _volume_entry(prim: hou.Prim) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "number": prim.number(),
        "type": prim.type().name(),
        "resolution": list(prim.resolution()),
        "voxel_size": list(prim.voxelSize()),
        "bbox": bbox_dict(prim.boundingBox()),
        "values": {
            "min": float(prim.volumeMin()),
            "max": float(prim.volumeMax()),
            "average": float(prim.volumeAverage()),
        },
        "is_sdf": bool(prim.isSDF()),
        "is_height_field": bool(prim.isHeightField()),
    }
    name = prim.attribValue("name") if prim.geometry().findPrimAttrib("name") else ""
    if name:
        entry["name"] = name
    if isinstance(prim, hou.VDB):
        entry["vdb_type"] = str(prim.vdbType()).rsplit(".", 1)[-1]
        entry["active_voxels"] = prim.activeVoxelCount()
    else:
        entry["storage"] = str(prim.storageType()).rsplit(".", 1)[-1]
    return entry
