"""RBD 조각과 시뮬을 진단한다 - 무너지면 왜 무너졌는지 수치로 안다.

DOP 네트워크 없이 도는 RBD 가 흔하다. RBD Bullet Solver SOP 은 안에 DOP 을
감추고 packed 조각을 SOP 으로 내보내므로, houdini_mcp_dop 의 test_simulation
(dopnet 전용)으로는 볼 수 없다. 여기 툴은 packed 지오메트리를 내는 SOP 이면
무엇이든 받는다.

    rbd_piece_stats  시뮬 전에 조각을 본다 - 실제 부피와 질량, 얇은 파편,
                     glue 가 안 걸린 조각, 이웃 조각 사이 거리
    rbd_sim_report   시뮬을 프레임별로 읽는다 - 움직인 조각, 끊긴 제약,
                     부딪히기 전에 움직인 것

만든 계기(2026-09-13, 성 파괴 씬): 성이 투사체에 맞기 전부터 무너졌다. 원인을
겹침, 바닥 접촉, 오목 조각 순으로 세 번 잘못 짚었고, 실제로는 부피가 거의 0인
얇은 파편과 glue 가 걸리지 않은 조각이었다. 조각 부피 분포와 제약 수를 처음에
봤다면 한 번에 끝났다. bbox 크기는 얇은 판을 크게 보이게 하므로 판단에 쓰지
않는다.

실측 메모 (Houdini 22.0.368)
- PackedFragment 의 intrinsic measuredvolume 은 0 이고 getEmbeddedGeometry 도
  없다. unpack verb 로 풀어(조각 1,062개에 0.02초) 폴리곤의 measuredvolume 을
  이름별로 합하면 정확하다(사면체 합과 소수점 넷째 자리까지 같다).
- 조각 이름은 assemble 출력에서 점 어트리뷰트, 솔버 출력에서 프림 어트리뷰트다.
- geometryAtFrame(frame, output) 은 사용자의 현재 프레임을 바꾸지 않는다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import fnmatch
import time
from typing import Any, Sequence

import hou
import numpy

from houdini_mcp import tool

MAX_LIMIT = 50
NEIGHBOUR_CHUNK = 512
"""이웃 거리를 셀 때 한 번에 비교할 조각 수. 조각이 많아도 메모리가 터지지 않게."""

THIN_RATIO = 0.1
"""가장 짧은 변 / 가장 긴 변이 이보다 작으면 얇은 판으로 본다."""

START_BREAK_WARN = 0.2
"""첫 두 표본 사이에 제약이 이만큼 넘게 끊기면 시작하자마자 깨지는 것으로 본다."""


# --------------------------------------------------------------------------
# 공통
# --------------------------------------------------------------------------


def _require_sop(path: str) -> hou.SopNode:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    if not isinstance(node, hou.SopNode):
        raise ValueError(
            f"{path} 는 SOP 이 아닙니다({node.type().category().name()}). packed 조각을 "
            f"내는 SOP 경로를 주세요. 예: assemble, rbdmaterialfracture, rbdbulletsolver"
        )
    return node


def _port(node: hou.SopNode, output: int) -> None:
    labels = list(node.outputLabels())
    if output < 0 or output >= len(labels):
        listed = ", ".join(f"{i}={name}" for i, name in enumerate(labels))
        raise ValueError(f"{node.path()} 에는 {output}번 출력이 없습니다. 출력 포트: {listed}")


def _geometry(node: hou.SopNode, output: int, frame: float | None = None) -> hou.Geometry:
    _port(node, output)
    geo = node.geometry(output) if frame is None else node.geometryAtFrame(frame, output)
    if geo is None:
        raise ValueError(
            f"{node.path()} 의 {output}번 출력을 읽지 못했습니다. node_errors 로 쿡 에러를 보세요."
        )
    return geo


def _require_packed(geo: hou.Geometry, path: str) -> None:
    total = geo.intrinsicValue("primitivecount")
    packed = geo.countPrimType(hou.primType.PackedPrim)
    if total == 0:
        raise ValueError(f"{path} 에 프리미티브가 없습니다.")
    if packed < total:
        raise ValueError(
            f"{path} 의 프림 {total}개 중 packed 는 {packed}개입니다. 조각이 packed 가 "
            f"아니면 강체 하나로 쪼개지지 않습니다. assemble 이면 Create Packed "
            f"Primitives(pack_geo)를 켜세요."
        )


def _names(geo: hou.Geometry) -> list[str]:
    """packed 프림마다 이름. 프림 name 이 없으면 그 프림의 점 name 을 쓴다."""
    if geo.findPrimAttrib("name") is not None:
        return list(geo.primStringAttribValues("name"))
    if geo.findPointAttrib("name") is not None:
        point_names = geo.pointStringAttribValues("name")
        return [point_names[prim.vertices()[0].point().number()] for prim in geo.prims()]
    raise ValueError(
        "조각에 name 어트리뷰트가 없습니다. Bullet 은 조각을 name 으로 구분합니다. "
        "assemble 의 Create Name Attribute 를 켜세요."
    )


def _positions(geo: hou.Geometry) -> numpy.ndarray:
    """packed 프림 하나에 점 하나다. 점 순서가 프림 순서와 같다."""
    return numpy.asarray(geo.pointFloatAttribValues("P"), dtype=numpy.float64).reshape(-1, 3)


def _sig(value: Any) -> float:
    """유효숫자 4자리. 소수점 자리로 자르면 얇은 파편 부피가 0.0 으로 보인다."""
    return float(f"{float(value):.4g}")


def _percentiles(values: numpy.ndarray) -> dict[str, float] | None:
    if values.size == 0:
        return None
    return {f"p{p}": _sig(numpy.percentile(values, p)) for p in (1, 10, 50, 90, 99)}


def _patterns(text: str) -> list[str]:
    return [p for p in text.split() if p]


def _matches(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


# --------------------------------------------------------------------------
# rbd_piece_stats
# --------------------------------------------------------------------------


def _volumes(geo: hou.Geometry) -> dict[str, float]:
    unpacked = hou.Geometry()
    hou.sopNodeTypeCategory().nodeVerb("unpack").execute(unpacked, [geo])
    if unpacked.findPrimAttrib("name") is None:
        return {}
    names = unpacked.primStringAttribValues("name")
    volumes: dict[str, float] = {}
    for prim in unpacked.prims():
        key = names[prim.number()]
        volumes[key] = volumes.get(key, 0.0) + prim.intrinsicValue("measuredvolume")
    return {key: abs(value) for key, value in volumes.items()}


def _constraint_counts(geo: hou.Geometry) -> dict[str, int]:
    if geo.findPointAttrib("name") is None:
        raise ValueError(
            "제약 지오메트리의 점에 name 이 없어 어느 조각에 걸렸는지 알 수 없습니다. "
            "connectadjacentpieces 나 RBD Constraint Properties 의 제약 출력(1번)을 주세요."
        )
    point_names = geo.pointStringAttribValues("name")
    counts: dict[str, int] = {}
    for prim in geo.prims():
        for vertex in prim.vertices():
            key = point_names[vertex.point().number()]
            counts[key] = counts.get(key, 0) + 1
    return counts


def _nearest_distances(centers: numpy.ndarray) -> numpy.ndarray:
    nearest = numpy.full(len(centers), numpy.inf)
    for start in range(0, len(centers), NEIGHBOUR_CHUNK):
        block = centers[start : start + NEIGHBOUR_CHUNK]
        dist = numpy.linalg.norm(block[:, None, :] - centers[None, :, :], axis=-1)
        rows = numpy.arange(len(block))
        dist[rows, rows + start] = numpy.inf
        nearest[start : start + len(block)] = dist.min(axis=1)
    return nearest


@tool()
def rbd_piece_stats(
    path: str,
    constraints: str | None = None,
    constraints_output: int = 0,
    density: float = 1000.0,
    sliver_volume: float = 0.05,
    output: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """RBD 조각을 시뮬 전에 점검한다. 시작하자마자 떨어질 조각을 미리 찾는다.

    조각마다 **실제 부피**(bbox 가 아니다 - 얇은 판은 bbox 가 크다)와 추정 질량,
    얇기, glue 가 몇 개 걸렸는지를 재고, 이웃 조각 중심 사이 거리를 준다.

    다음을 잡는다.
    - 얇은 파편: 부피가 sliver_volume 보다 작은 조각. 무거운 이웃과 붙어 있으면
      시작 충격에 glue 가 통째로 끊겨 떨어진다.
    - glue 가 하나도 없는 조각: 그냥 쌓여만 있다가 무너진다. 이웃 거리 p99 보다
      제약 검색 반경이 작으면 생긴다.
    - packed 가 아닌 조각: 강체로 쪼개지지 않는다.

    Args:
        path: packed 조각을 내는 SOP. 예: assemble, rbdmaterialfracture
        constraints: 제약 지오메트리를 내는 SOP. 주면 조각마다 glue 수를 센다.
            예: connectadjacentpieces
        constraints_output: constraints 노드의 출력 번호. RBD Constraint
            Properties 는 1.
        density: 질량 추정에 쓸 밀도(kg/m³). 조각에 density 가 있으면 그것을 쓴다.
        sliver_volume: 이보다 부피가 작으면 얇은 파편으로 센다(m³).
        output: path 노드의 출력 번호.
        limit: 목록에 담을 조각 수. 최대 50.
    """
    if density <= 0:
        raise ValueError(f"density 는 0보다 커야 합니다: {density}")
    limit = max(1, min(int(limit), MAX_LIMIT))
    node = _require_sop(path)
    geo = _geometry(node, output)
    _require_packed(geo, path)

    names = _names(geo)
    volumes_by_name = _volumes(geo)
    volumes = numpy.array([volumes_by_name.get(n, 0.0) for n in names])
    if geo.findPointAttrib("density") is not None:
        densities = numpy.asarray(geo.pointFloatAttribValues("density"), dtype=numpy.float64)
    else:
        densities = numpy.full(len(names), float(density))
    masses = volumes * densities

    extents = []
    for prim in geo.prims():
        b = prim.intrinsicValue("bounds")
        extents.append((b[1] - b[0], b[3] - b[2], b[5] - b[4]))
    extents = numpy.asarray(extents)
    thinness = extents.min(axis=1) / numpy.maximum(extents.max(axis=1), 1e-9)
    nearest = _nearest_distances(_positions(geo))

    slivers = numpy.where(volumes < sliver_volume)[0]
    thin = numpy.where(thinness < THIN_RATIO)[0]
    order = numpy.argsort(volumes)

    result: dict[str, Any] = {
        "path": node.path(),
        "pieces": len(names),
        "volume_m3": _percentiles(volumes),
        "mass_kg": _percentiles(masses),
        "mass_ratio_max_to_p50": round(float(masses.max() / max(numpy.median(masses), 1e-9)), 1),
        "nearest_neighbour_m": _percentiles(nearest),
        "slivers": {"threshold_m3": sliver_volume, "count": int(slivers.size)},
        "thin": {"ratio_below": THIN_RATIO, "count": int(thin.size)},
        "smallest": [
            {"name": names[i], "volume_m3": _sig(volumes[i]),
             "extent_m": [round(float(v), 2) for v in extents[i]]}
            for i in order[:limit]
        ],
    }

    hints: list[str] = []
    if constraints:
        cnode = _require_sop(constraints)
        counts = _constraint_counts(_geometry(cnode, constraints_output))
        per_piece = numpy.array([counts.get(n, 0) for n in names])
        unconstrained = [names[i] for i in numpy.where(per_piece == 0)[0]]
        result["constraints"] = {
            "path": cnode.path(),
            "per_piece": _percentiles(per_piece.astype(float)),
            "unconstrained_count": len(unconstrained),
            "unconstrained": unconstrained[:limit],
        }
        if unconstrained:
            hints.append(
                f"glue 가 하나도 없는 조각이 {len(unconstrained)}개입니다. 쌓여만 있다가 "
                f"무너집니다. 제약 검색 반경을 이웃 거리 p99({result['nearest_neighbour_m']['p99']}m)"
                f" 보다 크게 잡으세요."
            )
    if slivers.size:
        hints.append(
            f"부피 {sliver_volume}m³ 미만인 얇은 파편이 {slivers.size}개입니다. 시작 충격에 "
            f"glue 가 통째로 끊겨 떨어지기 쉽습니다. 부피로 골라 지우거나 이웃에 합치세요."
        )
    if not hints:
        hints.append("조각 구성에서 눈에 띄는 문제는 없습니다.")
    result["hints"] = hints
    return result


# --------------------------------------------------------------------------
# rbd_sim_report
# --------------------------------------------------------------------------


def _sample_frames(frames: Sequence[float] | None, start: float, end: float) -> list[float]:
    if frames:
        picked = sorted({float(f) for f in frames})
    else:
        if end < start:
            raise ValueError(f"end({end}) 가 start({start}) 보다 앞섭니다.")
        count = min(12, int(end - start) + 1)
        picked = sorted({float(round(v)) for v in numpy.linspace(start, end, count)})
    if len(picked) > MAX_LIMIT:
        raise ValueError(f"프레임이 {len(picked)}개입니다. {MAX_LIMIT}개 이하로 고르세요.")
    return picked


def _constraint_port(node: hou.SopNode, requested: int | None) -> int | None:
    labels = list(node.outputLabels())
    if requested is not None:
        _port(node, requested)
        return requested
    for index, label in enumerate(labels):
        if index and "constraint" in label.lower():
            return index
    return None


@tool()
def rbd_sim_report(
    path: str,
    frames: list[float] | None = None,
    start: float = 1,
    end: float = 24,
    exclude: str = "",
    quiet_until: float | None = None,
    constraints_output: int | None = None,
    moved_threshold: float = 0.1,
    limit: int = 10,
) -> dict[str, Any]:
    """RBD 시뮬을 프레임별로 읽어 무엇이 언제 움직이고 끊겼는지 돌려준다.

    RBD Bullet Solver SOP 처럼 packed 조각을 내는 SOP 을 받는다(dopnet 은
    houdini_mcp_dop 의 test_simulation). 첫 표본 프레임을 기준 자세로 삼아 조각마다
    이동 거리를 재고, 제약 출력이 있으면 끊긴 수를 센다. 사용자의 현재 프레임은
    바꾸지 않는다.

    무너지는 원인을 찾을 때 이렇게 쓴다.
    - quiet_until 에 충돌 프레임을 주면, 그 전에 움직인 조각을 이름·이동 방향과
      함께 알려 준다. "부딪히기 전부터 무너진다" 를 수치로 잡는다.
    - 첫 두 표본 사이에 제약이 크게 끊기면 시작 충격 문제로 알린다. 그때는
      rbd_piece_stats 로 얇은 파편과 glue 없는 조각을 본다.

    Args:
        path: 시뮬 결과 packed 조각을 내는 SOP. 예: rbdbulletsolver, dopimport
        frames: 볼 프레임들. 생략하면 start~end 를 12개쯤으로 나눈다.
        start: frames 를 생략했을 때 시작 프레임.
        end: frames 를 생략했을 때 끝 프레임.
        exclude: 통계에서 뺄 조각 이름 패턴. 공백으로 여러 개. 예: "projectile".
            빠진 조각은 위치만 따로 보여 준다.
        quiet_until: 이 프레임까지는 조각이 가만히 있어야 한다(보통 충돌 직전).
        constraints_output: 제약 출력 번호. 생략하면 라벨에 Constraint 가 든
            출력을 찾는다(RBD Bullet Solver 는 1).
        moved_threshold: 이보다 많이 움직이면 "움직였다" 로 센다(m).
        limit: 목록에 담을 조각 수. 최대 50.
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    node = _require_sop(path)
    picked = _sample_frames(frames, start, end)
    cport = _constraint_port(node, constraints_output)
    skip = _patterns(exclude)

    rest: dict[str, numpy.ndarray] = {}
    tracked_names: list[str] = []
    excluded_names: list[str] = []
    rows: list[dict[str, Any]] = []
    first_constraints: int | None = None
    quiet_movers: list[dict[str, Any]] = []
    last_disp: dict[str, numpy.ndarray] = {}

    for frame in picked:
        began = time.perf_counter()
        geo = _geometry(node, 0, frame)
        elapsed = time.perf_counter() - began
        _require_packed(geo, path)
        names = _names(geo)
        pos = _positions(geo)
        index = {name: i for i, name in enumerate(names)}

        if not rest:
            for name, i in index.items():
                rest[name] = pos[i].copy()
            tracked_names = [n for n in names if not _matches(n, skip)]
            excluded_names = [n for n in names if _matches(n, skip)]

        present = [n for n in tracked_names if n in index]
        disp_vec = numpy.array([pos[index[n]] - rest[n] for n in present]) if present else numpy.zeros((0, 3))
        disp = numpy.linalg.norm(disp_vec, axis=1) if present else numpy.zeros(0)

        row: dict[str, Any] = {
            "frame": frame,
            "cook_s": round(elapsed, 2),
            "bodies": len(names),
            "moved": int((disp > moved_threshold).sum()),
            "moved_1m": int((disp > 1.0).sum()),
            "max_disp_m": round(float(disp.max()), 3) if disp.size else 0.0,
            "lowest_y": round(float(pos[:, 1].min()), 3) if len(pos) else None,
        }
        if cport is not None:
            count = _geometry(node, cport, frame).intrinsicValue("primitivecount")
            if first_constraints is None:
                first_constraints = count
            row["constraints"] = count
            row["broken"] = first_constraints - count
        if excluded_names:
            row["excluded_positions"] = {
                n: [round(float(v), 2) for v in pos[index[n]]] for n in excluded_names if n in index
            }
        rows.append(row)

        last_disp = {n: disp_vec[k] for k, n in enumerate(present)}
        if quiet_until is not None and frame <= quiet_until:
            order = numpy.argsort(-disp)
            quiet_movers = [
                {"name": present[k], "disp_m": round(float(disp[k]), 3),
                 "direction": [round(float(v), 2) for v in disp_vec[k]],
                 "rest": [round(float(v), 2) for v in rest[present[k]]]}
                for k in order[:limit] if disp[k] > moved_threshold
            ]

    result: dict[str, Any] = {
        "path": node.path(),
        "rest_frame": picked[0],
        "constraint_output": cport,
        "frames": rows,
    }

    warnings: list[str] = []
    if cport is not None and len(rows) > 1 and first_constraints:
        lost = first_constraints - rows[1]["constraints"]
        if lost / first_constraints > START_BREAK_WARN:
            warnings.append(
                f"프레임 {rows[0]['frame']:g} → {rows[1]['frame']:g} 사이에 제약 "
                f"{first_constraints}개 중 {lost}개({lost / first_constraints:.0%})가 끊겼습니다. "
                f"아무것도 부딪히기 전이라면 시작 충격입니다 - rbd_piece_stats 로 얇은 파편과 "
                f"glue 없는 조각을 보세요."
            )
    if quiet_until is not None:
        result["moved_before_quiet_until"] = quiet_movers
        if quiet_movers:
            warnings.append(
                f"프레임 {quiet_until:g} 까지 가만히 있어야 할 조각 중 {len(quiet_movers)}개 이상이 "
                f"{moved_threshold}m 넘게 움직였습니다. moved_before_quiet_until 에 이름과 방향이 있습니다."
            )
    order = sorted(last_disp.items(), key=lambda item: -float(numpy.linalg.norm(item[1])))
    result["top_movers_last_frame"] = [
        {"name": n, "disp_m": round(float(numpy.linalg.norm(v)), 3),
         "direction": [round(float(x), 2) for x in v]}
        for n, v in order[:limit]
    ]
    result["warnings"] = warnings or ["눈에 띄는 문제는 없습니다."]
    return result
