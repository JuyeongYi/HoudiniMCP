"""스킨 웨이트를 만들고 읽고 적용한다.

`boneCapture` 는 점 10만 개짜리 캐릭터에서 값이 40만 개를 넘는다. 파이썬으로
점을 돌면 못 쓴다. 여기 툴은 전부 `_common.read_capture` 가 numpy 로 한 번에
읽어 온 배열 위에서 돈다 (README 제3원칙).

돌려주는 것도 마찬가지다. 웨이트 원본을 그대로 보내지 않고 합·분포·조인트별
요약으로 줄인다. 특정 점이 궁금하면 find_unweighted_points 나 joint_influence 로
좁혀서 본다.
"""

from __future__ import annotations

from typing import Any

import numpy

from houdini_mcp import tool, undoable

from ._common import (
    Capture,
    bbox_dict,
    build,
    capture_at,
    effective_weights,
    geometry_at,
    geometry_of,
    node_brief,
    point_floats,
    read_capture,
    read_skeleton,
    require_comment,
    require_sop,
    same_parent_hint,
)

CAPTURE_METHODS = {
    "proximity": "kinefx::jointcaptureproximity",
    "biharmonic": "kinefx::jointcapturebiharmonic",
}
"""쓸 수 있는 캡처 방식. proximity 는 거리 기반이라 빠르고, biharmonic 은
메시 내부를 풀어서 매끄럽지만 느리다."""

WEIGHT_TOLERANCE = 1e-4
"""웨이트 합이 1 에서 이만큼 벗어나면 문제로 본다. float32 누적 오차보다는 크게."""

MAX_LISTED = 100
"""한 번에 돌려줄 점·조인트 수 상한."""


@tool()
@undoable("Capture skin")
def capture_skin(
    mesh: str,
    skeleton: str,
    comment: str,
    name: str | None = None,
    method: str = "proximity",
    max_influences: int = 4,
    dropoff: float | None = None,
    normalize: bool = True,
) -> dict[str, Any]:
    """메시를 스켈레톤에 붙이고, 붙은 결과를 통계로 돌려준다.

    노드를 만들고 끝내지 않는다. 웨이트 합이 1인지, 어디에도 안 붙은 점이
    있는지를 바로 확인해 준다. 캡처가 잘못된 채로 다음 단계로 가면 디폼에서야
    알게 되기 때문이다.

    Args:
        mesh: 스킨이 될 메시 SOP 경로.
        skeleton: 스켈레톤 SOP 경로. 바인드 포즈여야 한다.
        comment: 무엇을 캡처하는지 영어로. 예: Capture body mesh to spine joints
        name: 노드 이름. 생략하면 Houdini 가 정한다.
        method: proximity 또는 biharmonic.
        max_influences: 점 하나에 붙일 조인트 수 상한.
        dropoff: 거리 감쇠. 생략하면 노드 기본값.
        normalize: 웨이트 합을 1로 맞출지.
    """
    require_comment(comment)
    if method not in CAPTURE_METHODS:
        raise ValueError(
            f"method 는 {', '.join(CAPTURE_METHODS)} 중 하나여야 합니다: {method!r}"
        )
    if max_influences < 1:
        raise ValueError(
            f"max_influences 는 1 이상이어야 합니다: {max_influences}. "
            f"점 하나가 적어도 조인트 하나에는 붙어야 합니다."
        )

    mesh_node, mesh_geo = geometry_at(mesh)
    skeleton_node = require_sop(skeleton)
    skeleton_data = read_skeleton(geometry_of(skeleton_node), skeleton)
    same_parent_hint(mesh_node, skeleton_node)

    node = build(
        mesh_node,
        CAPTURE_METHODS[method],
        comment,
        name=name,
        parms={
            "maxinfluences": int(max_influences),
            "normweights": bool(normalize),
            "dropoff": dropoff,
        },
        extra_inputs=(skeleton_node,),
    )

    geo = geometry_of(node)
    capture = _read_or_explain(geo, node.path(), method)
    return {
        **node_brief(node),
        "mesh": mesh_node.path(),
        "skeleton": skeleton_node.path(),
        "method": method,
        "mesh_points": int(mesh_geo.pointCount()),
        "skeleton_joints": skeleton_data.count,
        "captured_joints": len(capture.joints),
        "max_influences": capture.max_influences,
        "weights": _weight_summary(capture),
        "unused_joints": _unused_joints(capture),
    }


def _read_or_explain(geo: Any, path: str, method: str) -> Capture:
    """캡처 결과를 읽는다. 안 나왔으면 왜 안 나왔는지 짚어 준다."""
    try:
        return read_capture(geo, path)
    except ValueError as exc:
        raise ValueError(
            f"{path} 가 캡처 웨이트를 내지 않았습니다 ({method}). 스켈레톤이 메시를 "
            f"둘러싸고 있는지, 두 입력이 같은 좌표계에 있는지 확인하세요. ({exc})"
        ) from exc


@tool()
def weight_stats(path: str, top: int = 12) -> dict[str, Any]:
    """스킨 웨이트 전체의 분포를 통계로 돌려준다.

    웨이트 합이 1인지, 점마다 조인트가 몇 개씩 붙었는지, 조인트별로 몇 점을
    끌고 있는지를 numpy 로 한 번에 센다. 점 10만 개에서도 파이썬 루프가 없다.

    Args:
        path: boneCapture 를 가진 SOP 노드 경로.
        top: 영향이 큰 조인트를 몇 개까지 보여줄지. 최대 100.
    """
    node, geo, capture = capture_at(path)
    top = max(1, min(int(top), MAX_LISTED))
    weights = effective_weights(capture)
    per_joint = _per_joint(capture, weights)

    order = numpy.argsort(-per_joint["total"])[:top]
    return {
        "path": node.path(),
        "comment": node.comment(),
        "points": capture.point_count,
        "joints": len(capture.joints),
        "max_influences": capture.max_influences,
        "weights": _weight_summary(capture),
        "bbox": bbox_dict(geo.boundingBox()),
        "top_joints": [
            {
                "name": capture.joints[i],
                "points": int(per_joint["points"][i]),
                "total_weight": float(per_joint["total"][i]),
                "max_weight": float(per_joint["max"][i]),
            }
            for i in order
        ],
        "unused_joints": _unused_joints(capture),
    }


def _weight_summary(capture: Capture) -> dict[str, Any]:
    """합·영향 수 분포. validate_rig 와 capture_skin 이 같이 쓴다."""
    weights = effective_weights(capture)
    if not capture.point_count:
        return {"points": 0}

    totals = weights.sum(axis=1)
    influences = (weights > 0).sum(axis=1)
    off = numpy.abs(totals - 1.0) > WEIGHT_TOLERANCE
    counts = numpy.bincount(influences, minlength=capture.max_influences + 1)

    return {
        "points": capture.point_count,
        "sum": {
            "min": float(totals.min()),
            "max": float(totals.max()),
            "mean": float(totals.mean()),
            "not_one": int(off.sum()),
            "tolerance": WEIGHT_TOLERANCE,
        },
        "influences_per_point": {
            "min": int(influences.min()),
            "max": int(influences.max()),
            "mean": float(influences.mean()),
            "histogram": {str(i): int(c) for i, c in enumerate(counts) if c},
        },
        "unweighted_points": int((totals <= 0).sum()),
        "negative_weights": int((weights < 0).sum()),
    }


def _per_joint(capture: Capture, weights: numpy.ndarray) -> dict[str, numpy.ndarray]:
    """조인트별 합계·점 수·최대 웨이트. bincount 로 한 번에 센다."""
    count = max(len(capture.joints), 1)
    flat_index = capture.indices.reshape(-1)
    flat_weight = weights.reshape(-1)
    valid = (flat_index >= 0) & (flat_index < count) & (flat_weight > 0)

    index = flat_index[valid]
    value = flat_weight[valid]
    total = numpy.bincount(index, weights=value, minlength=count)
    points = numpy.bincount(index, minlength=count)
    largest = numpy.zeros(count)
    if index.size:
        numpy.maximum.at(largest, index, value)
    return {"total": total, "points": points, "max": largest}


def _unused_joints(capture: Capture) -> list[str]:
    """캡처 테이블에는 있는데 어느 점도 끌지 않는 조인트."""
    weights = effective_weights(capture)
    per_joint = _per_joint(capture, weights)
    return [
        capture.joints[i]
        for i in numpy.flatnonzero(per_joint["points"] == 0)[:MAX_LISTED]
    ]


@tool()
def find_unweighted_points(path: str, limit: int = 20) -> dict[str, Any]:
    """어디에도 붙지 않은 점을 찾는다. 디폼할 때 제자리에 남는 점들이다.

    웨이트 합이 0인 점과, 합이 1에서 벗어난 점을 함께 돌려준다. 둘 다 디폼에서
    눈에 띄기 전에는 알 수 없는 종류의 문제다.

    Args:
        path: boneCapture 를 가진 SOP 노드 경로.
        limit: 점을 몇 개까지 보여줄지. 최대 100.
    """
    node, geo, capture = capture_at(path)
    limit = max(1, min(int(limit), MAX_LISTED))

    weights = effective_weights(capture)
    totals = weights.sum(axis=1)
    positions = point_floats(geo, "P", 3)

    zero = numpy.flatnonzero(totals <= 0)
    off = numpy.flatnonzero(
        (numpy.abs(totals - 1.0) > WEIGHT_TOLERANCE) & (totals > 0)
    )

    def describe(indices: numpy.ndarray) -> list[dict[str, Any]]:
        return [
            {
                "point": int(i),
                "position": [round(float(v), 6) for v in positions[i]],
                "weight_sum": float(totals[i]),
            }
            for i in indices[:limit]
        ]

    return {
        "path": node.path(),
        "comment": node.comment(),
        "points": capture.point_count,
        "unweighted": {
            "count": int(zero.size),
            "points": describe(zero),
            "bbox": _subset_bbox(positions, zero),
        },
        "sum_off_one": {
            "count": int(off.size),
            "points": describe(off),
            "bbox": _subset_bbox(positions, off),
        },
    }


def _subset_bbox(positions: numpy.ndarray, indices: numpy.ndarray) -> dict[str, Any]:
    """문제 점들이 어디에 몰려 있는지. 위치를 다 보내는 것보다 훨씬 쓸모 있다."""
    if not indices.size:
        return {}
    subset = positions[indices]
    low, high = subset.min(axis=0), subset.max(axis=0)
    return {
        "min": [float(v) for v in low],
        "max": [float(v) for v in high],
        "center": [float(v) for v in (low + high) / 2.0],
    }


@tool()
def joint_influence(path: str, joint: str, limit: int = 20) -> dict[str, Any]:
    """조인트 하나가 어느 점을 얼마나 끌고 있는지 본다.

    조인트를 돌렸는데 엉뚱한 곳이 움직이면 여기서 원인이 보인다. 웨이트 분포와
    영향 범위(바운딩 박스)를 함께 준다.

    Args:
        path: boneCapture 를 가진 SOP 노드 경로.
        joint: 조인트 이름. weight_stats 의 top_joints 에서 확인한다.
        limit: 웨이트가 큰 점을 몇 개까지 보여줄지. 최대 100.
    """
    node, geo, capture = capture_at(path)
    limit = max(1, min(int(limit), MAX_LISTED))

    if joint not in capture.joints:
        close = [n for n in capture.joints if joint.lower() in n.lower()][:8]
        hint = ", ".join(close) if close else ", ".join(capture.joints[:10])
        raise ValueError(
            f"캡처에 조인트 {joint!r} 가 없습니다. 비슷한 이름: {hint}. "
            f"weight_stats 로 캡처된 조인트 목록을 확인하세요."
        )

    index = capture.joints.index(joint)
    weights = effective_weights(capture)
    mask = capture.indices == index
    per_point = numpy.where(mask, weights, 0.0).sum(axis=1)
    touched = numpy.flatnonzero(per_point > 0)
    positions = point_floats(geo, "P", 3)

    order = touched[numpy.argsort(-per_point[touched])][:limit]
    values = per_point[touched]
    return {
        "path": node.path(),
        "comment": node.comment(),
        "joint": joint,
        "index": index,
        "points": int(touched.size),
        "fraction_of_mesh": (
            round(float(touched.size) / capture.point_count, 6)
            if capture.point_count
            else 0.0
        ),
        "weight": {
            "min": float(values.min()) if values.size else 0.0,
            "max": float(values.max()) if values.size else 0.0,
            "mean": float(values.mean()) if values.size else 0.0,
            "total": float(values.sum()),
            "fully_owned": int((per_point >= 1.0 - WEIGHT_TOLERANCE).sum()),
        },
        "influence_bbox": _subset_bbox(positions, touched),
        "strongest_points": [
            {
                "point": int(i),
                "weight": float(per_point[i]),
                "position": [round(float(v), 6) for v in positions[i]],
            }
            for i in order
        ],
    }


@tool()
@undoable("Deform skin")
def deform_skin(
    rest: str,
    capture_pose: str,
    animated_pose: str,
    comment: str,
    name: str | None = None,
) -> dict[str, Any]:
    """스킨을 포즈에 맞춰 디폼하고, 실제로 움직였는지 측정해서 돌려준다.

    `{"ok": true}` 를 돌려주지 않는다. 몇 점이 얼마나 움직였는지, 바운딩 박스가
    어떻게 바뀌었는지를 준다. 웨이트가 잘못 걸리면 점이 하나도 안 움직이거나
    엉뚱하게 튀는데, 그것을 여기서 바로 알 수 있다.

    Args:
        rest: 캡처된 메시 SOP 경로 (boneCapture 를 가진 것).
        capture_pose: 바인드 포즈 스켈레톤 SOP 경로.
        animated_pose: 목표 포즈 스켈레톤 SOP 경로.
        comment: 무엇을 디폼하는지 영어로. 예: Deform body to bent elbow pose
        name: 노드 이름. 생략하면 Houdini 가 정한다.
    """
    require_comment(comment)
    rest_node, rest_geo, capture = capture_at(rest)
    bind_node = require_sop(capture_pose)
    anim_node = require_sop(animated_pose)
    same_parent_hint(rest_node, bind_node)

    before = point_floats(rest_geo, "P", 3)
    node = build(
        rest_node,
        "kinefx::jointdeform",
        comment,
        name=name,
        extra_inputs=(bind_node, anim_node),
    )

    geo = geometry_of(node)
    after = point_floats(geo, "P", 3)
    if after.shape != before.shape:
        return {
            **node_brief(node),
            "warning": (
                f"점 수가 {before.shape[0]} 에서 {after.shape[0]} 로 바뀌어 "
                f"이동량을 잴 수 없습니다."
            ),
            "bbox": bbox_dict(geo.boundingBox()),
        }

    moved = numpy.linalg.norm(after - before, axis=1)
    return {
        **node_brief(node),
        "rest": rest_node.path(),
        "capture_pose": bind_node.path(),
        "animated_pose": anim_node.path(),
        "points": int(moved.size),
        "moved_points": int((moved > 1e-5).sum()),
        "movement": {
            "min": float(moved.min()),
            "max": float(moved.max()),
            "mean": float(moved.mean()),
        },
        "joints": len(capture.joints),
        "bbox_before": bbox_dict(rest_geo.boundingBox()),
        "bbox_after": bbox_dict(geo.boundingBox()),
    }
