"""리그가 맞는지 검증한다.

조사한 기존 MCP 구현 다섯 중 **리그를 검증하는 것이 하나도 없다.** 전부 만들기만
하고, 맞는지는 사람이 뷰포트에서 보고 판단해야 한다. 리깅에서 가장 값비싼 실수는
"잘못된 채로 다음 단계로 넘어가는 것"이다 — 웨이트 합이 1이 아닌 것은 캐릭터가
애니메이션에서 늘어난 뒤에야 눈에 띈다.

검사는 전부 numpy 벌크 경로로 돈다. 점 10만 개짜리 캐릭터에서 파이썬 루프를
돌면 검증 자체가 못 쓸 물건이 된다 (README 제3원칙).

각 지적에는 **다음에 무엇을 할지**가 붙는다. "웨이트 합이 1이 아니다"로 끝내지
않고 어느 툴로 어떻게 고치는지까지 적는다.
"""

from __future__ import annotations

from typing import Any

import numpy

from houdini_mcp import tool

from ._common import (
    Capture,
    Skeleton,
    capture_at,
    effective_weights,
    point_floats,
    skeleton_at,
)

ERROR = "error"
WARNING = "warning"
INFO = "info"

WEIGHT_TOLERANCE = 1e-4
"""웨이트 합이 1 에서 이만큼 벗어나면 지적한다."""

BONE_EPSILON = 1e-6
"""본 길이가 이보다 짧으면 부모와 겹친 것으로 본다."""

SCALE_TOLERANCE = 1e-3
"""회전행렬 축 길이가 1 에서 이만큼 벗어나면 스케일이 섞인 것으로 본다."""

BIND_TOLERANCE = 1e-3
"""바인드 포즈와 현재 포즈가 이만큼 벌어지면 알려 준다."""

MAX_NAMED = 20
"""지적 하나에 이름을 몇 개까지 붙일지. 전부 보내면 컨텍스트만 태운다."""


def _issue(
    check: str, severity: str, message: str, fix: str, **extra: Any
) -> dict[str, Any]:
    return {"check": check, "severity": severity, "message": message, "fix": fix, **extra}


def _names(skeleton: Skeleton, indices: Any) -> list[str]:
    return [skeleton.names[int(i)] for i in list(indices)[:MAX_NAMED]]


# --------------------------------------------------------------------------
# 스켈레톤 검사
# --------------------------------------------------------------------------


def _check_hierarchy(skeleton: Skeleton) -> list[dict[str, Any]]:
    """계층이 끊겼는지, 루트가 여럿인지, 사이클이 있는지."""
    issues: list[dict[str, Any]] = []
    count = skeleton.count

    if count == 0:
        return [
            _issue(
                "no_joints",
                ERROR,
                "조인트가 하나도 없습니다.",
                "create_skeleton 으로 조인트를 만들거나, 스켈레톤을 내는 노드를 주세요.",
            )
        ]

    roots = skeleton.roots()
    if not roots:
        issues.append(
            _issue(
                "no_root",
                ERROR,
                "루트 조인트가 없습니다. 모든 조인트가 부모를 갖고 있어 계층이 닫혀 "
                "있습니다.",
                "부모 관계가 고리를 이루고 있습니다. list_joints 로 parent 를 훑어 "
                "고리를 끊으세요.",
            )
        )
    elif len(roots) > 1:
        issues.append(
            _issue(
                "multiple_roots",
                WARNING,
                f"루트가 {len(roots)}개입니다. 보통 캐릭터 하나에 루트는 하나입니다.",
                "떨어진 조각을 루트에 잇거나, 여러 캐릭터가 섞여 있는지 확인하세요. "
                "의도한 것이면 무시해도 됩니다.",
                joints=_names(skeleton, roots),
                count=len(roots),
            )
        )

    out_of_range = numpy.flatnonzero(
        (skeleton.parents >= count) | ((skeleton.parents < 0) & (skeleton.parents != -1))
    )
    if out_of_range.size:
        issues.append(
            _issue(
                "orphan_joints",
                ERROR,
                f"부모 번호가 범위 밖인 조인트가 {out_of_range.size}개 있습니다.",
                "스켈레톤 지오메트리가 손상됐습니다. kinefx::rigdoctor 를 다시 "
                "태우거나 create_skeleton 으로 다시 만드세요.",
                joints=_names(skeleton, out_of_range),
                count=int(out_of_range.size),
            )
        )

    self_parent = numpy.flatnonzero(skeleton.parents == numpy.arange(count))
    if self_parent.size:
        issues.append(
            _issue(
                "self_parented",
                ERROR,
                f"자기 자신을 부모로 가리키는 조인트가 {self_parent.size}개 있습니다.",
                "그 조인트의 부모를 다시 지정하세요. 자기 참조는 포즈 계산을 "
                "무한 루프에 빠뜨립니다.",
                joints=_names(skeleton, self_parent),
                count=int(self_parent.size),
            )
        )

    unreachable = numpy.flatnonzero(skeleton.depths() < 0)
    if unreachable.size:
        issues.append(
            _issue(
                "hierarchy_cycle",
                ERROR,
                f"루트에서 닿지 않는 조인트가 {unreachable.size}개 있습니다. "
                f"부모 관계에 고리가 있습니다.",
                "joint_info 의 chain_to_root 로 어디서 고리가 닫히는지 보고, "
                "그 부모 연결을 끊으세요.",
                joints=_names(skeleton, unreachable),
                count=int(unreachable.size),
            )
        )

    return issues


def _check_names(skeleton: Skeleton) -> list[dict[str, Any]]:
    """이름이 유일한지, 비어 있지 않은지. 캡처와 리타깃이 이름으로 조인트를 찾는다."""
    issues: list[dict[str, Any]] = []

    empty = [i for i, name in enumerate(skeleton.names) if not name.strip()]
    if empty:
        issues.append(
            _issue(
                "empty_joint_names",
                ERROR,
                f"이름이 빈 조인트가 {len(empty)}개 있습니다.",
                "캡처와 리타깃이 이름으로 조인트를 찾습니다. 이름 없는 조인트는 "
                "어디에도 붙지 못합니다. 이름을 지어 주세요.",
                indices=[int(i) for i in empty[:MAX_NAMED]],
                count=len(empty),
            )
        )

    seen: dict[str, int] = {}
    duplicated: list[str] = []
    for name in skeleton.names:
        seen[name] = seen.get(name, 0) + 1
    duplicated = [name for name, n in seen.items() if n > 1 and name.strip()]
    if duplicated:
        issues.append(
            _issue(
                "duplicate_joint_names",
                ERROR,
                f"이름이 겹치는 조인트가 {len(duplicated)}종 있습니다.",
                "이름으로 조인트를 찾는 모든 단계(캡처·리타깃·컨트롤)가 엉뚱한 "
                "조인트를 집게 됩니다. 이름을 유일하게 바꾸세요.",
                joints=duplicated[:MAX_NAMED],
                count=len(duplicated),
            )
        )

    generic = [
        name
        for name in skeleton.names
        if name.rstrip("0123456789") in ("joint", "point", "pt", "bone")
    ]
    if generic:
        issues.append(
            _issue(
                "generic_joint_names",
                INFO,
                f"joint1 같은 기본 이름이 {len(generic)}개 있습니다.",
                "hips, spine, upper_arm_L 처럼 역할이 드러나는 이름을 쓰세요. "
                "나중에 이 리그를 여는 사람이 이름만 보고 알아야 합니다.",
                joints=generic[:MAX_NAMED],
                count=len(generic),
            )
        )
    return issues


def _check_transforms(skeleton: Skeleton) -> list[dict[str, Any]]:
    """조인트 방향(transform 어트리뷰트)이 일관된지. 전부 numpy 한 번에."""
    if skeleton.transforms is None:
        return [
            _issue(
                "missing_transform",
                ERROR,
                "조인트 방향 어트리뷰트 transform 이 없습니다.",
                "kinefx::rigdoctor 의 Initialize Transforms 를 켜서 다시 태우세요. "
                "transform 없이는 포즈도 캡처도 방향을 알 수 없습니다.",
            )
        ]

    issues: list[dict[str, Any]] = []
    matrices = skeleton.transforms.astype(numpy.float64)
    determinant = numpy.linalg.det(matrices)

    degenerate = numpy.flatnonzero(numpy.abs(determinant) < 1e-9)
    if degenerate.size:
        issues.append(
            _issue(
                "degenerate_transform",
                ERROR,
                f"행렬식이 0에 가까운 조인트가 {degenerate.size}개 있습니다. "
                f"축이 무너져 방향을 잃었습니다.",
                "그 조인트의 transform 을 다시 초기화하세요 — kinefx::rigdoctor 의 "
                "Initialize Transforms 를 켜고 다시 태웁니다.",
                joints=_names(skeleton, degenerate),
                count=int(degenerate.size),
            )
        )

    mirrored = numpy.flatnonzero(determinant < -1e-9)
    if mirrored.size:
        issues.append(
            _issue(
                "mirrored_transform",
                WARNING,
                f"행렬식이 음수인 조인트가 {mirrored.size}개 있습니다. 축이 뒤집혀 "
                f"있습니다.",
                "좌우 대칭 리그를 미러링할 때 흔히 생깁니다. "
                "kinefx::orientjoints 로 방향을 다시 잡거나, 미러 쪽 회전이 "
                "반대로 도는지 pose_joints 로 확인하세요.",
                joints=_names(skeleton, mirrored),
                count=int(mirrored.size),
            )
        )

    axis = numpy.linalg.norm(matrices, axis=2)
    scaled = numpy.flatnonzero(
        (numpy.abs(axis - 1.0) > SCALE_TOLERANCE).any(axis=1)
    )
    if scaled.size:
        issues.append(
            _issue(
                "scaled_transform",
                WARNING,
                f"축 길이가 1이 아닌 조인트가 {scaled.size}개 있습니다. 회전에 "
                f"스케일이 섞여 있습니다.",
                "스키닝이 조인트 스케일을 그대로 물려받아 메시가 늘어납니다. "
                "joint_info 로 axis_lengths 를 보고 스케일을 1로 돌리세요.",
                joints=_names(skeleton, scaled),
                count=int(scaled.size),
            )
        )

    nonuniform = numpy.flatnonzero(
        (axis.max(axis=1) - axis.min(axis=1)) > SCALE_TOLERANCE
    )
    if nonuniform.size:
        issues.append(
            _issue(
                "nonuniform_scale",
                WARNING,
                f"축마다 길이가 다른 조인트가 {nonuniform.size}개 있습니다.",
                "비균등 스케일은 자식 조인트로 내려가면서 전단(shear)을 만듭니다. "
                "스케일을 균등하게 맞추세요.",
                joints=_names(skeleton, nonuniform),
                count=int(nonuniform.size),
            )
        )
    return issues


def _check_bones(skeleton: Skeleton) -> list[dict[str, Any]]:
    """부모와 겹친 조인트. 길이 0인 본은 방향을 정의하지 못한다."""
    has_parent = skeleton.parents >= 0
    if not has_parent.any():
        return []

    indices = numpy.flatnonzero(has_parent)
    offsets = skeleton.positions[indices] - skeleton.positions[skeleton.parents[indices]]
    lengths = numpy.linalg.norm(offsets, axis=1)

    zero = indices[lengths < BONE_EPSILON]
    if not zero.size:
        return []
    return [
        _issue(
            "zero_length_bone",
            WARNING,
            f"부모와 위치가 같은 조인트가 {zero.size}개 있습니다. 본 길이가 0입니다.",
            "IK 와 오리엔트가 방향을 정하지 못합니다. 조인트를 부모에서 떨어뜨리거나 "
            "(pose_joints 의 translate), 필요 없는 조인트면 지우세요.",
            joints=_names(skeleton, zero),
            count=int(zero.size),
        )
    ]


# --------------------------------------------------------------------------
# 스킨 검사
# --------------------------------------------------------------------------


def _check_weights(capture: Capture, max_influences: int) -> list[dict[str, Any]]:
    """웨이트 합·영향 수·음수 웨이트. 전부 numpy 벌크."""
    issues: list[dict[str, Any]] = []
    if capture.point_count == 0:
        return [
            _issue(
                "empty_skin",
                ERROR,
                "스킨 메시에 점이 없습니다.",
                "capture_skin 의 mesh 입력이 비어 있는지 geometry_stats 로 확인하세요.",
            )
        ]

    weights = effective_weights(capture)
    totals = weights.sum(axis=1)

    unweighted = numpy.flatnonzero(totals <= 0)
    if unweighted.size:
        issues.append(
            _issue(
                "unweighted_points",
                ERROR,
                f"어느 조인트에도 붙지 않은 점이 {unweighted.size}개 있습니다.",
                "디폼할 때 그 점들만 제자리에 남아 메시가 찢어집니다. "
                "find_unweighted_points 로 어디에 몰려 있는지 보고, capture_skin 을 "
                "dropoff 를 키우거나 max_influences 를 늘려 다시 부르세요.",
                count=int(unweighted.size),
                fraction=round(float(unweighted.size) / capture.point_count, 6),
            )
        )

    off = numpy.flatnonzero(
        (numpy.abs(totals - 1.0) > WEIGHT_TOLERANCE) & (totals > 0)
    )
    if off.size:
        issues.append(
            _issue(
                "weight_sum_not_one",
                ERROR,
                f"웨이트 합이 1이 아닌 점이 {off.size}개 있습니다 "
                f"(합 범위 {float(totals.min()):.6f} ~ {float(totals.max()):.6f}).",
                "합이 1보다 작으면 디폼이 덜 먹고, 크면 메시가 부풀어 오릅니다. "
                "capture_skin 을 normalize=true 로 다시 부르세요.",
                count=int(off.size),
                min_sum=float(totals.min()),
                max_sum=float(totals.max()),
            )
        )

    negative = numpy.flatnonzero((weights < 0).any(axis=1))
    if negative.size:
        issues.append(
            _issue(
                "negative_weights",
                ERROR,
                f"음수 웨이트를 가진 점이 {negative.size}개 있습니다.",
                "음수 웨이트는 디폼에서 점을 반대로 끌어당깁니다. capture_skin 으로 "
                "다시 캡처하거나 capturecorrect SOP 으로 정리하세요.",
                count=int(negative.size),
                min_weight=float(weights.min()),
            )
        )

    influences = (weights > 0).sum(axis=1)
    excess = numpy.flatnonzero(influences > max_influences)
    if excess.size:
        issues.append(
            _issue(
                "excess_influences",
                WARNING,
                f"영향 조인트가 {max_influences}개를 넘는 점이 {excess.size}개 "
                f"있습니다 (최대 {int(influences.max())}개).",
                "게임 엔진은 보통 점당 4개까지만 받습니다. capture_skin 의 "
                "max_influences 를 줄여 다시 캡처하세요.",
                count=int(excess.size),
                max_found=int(influences.max()),
                limit=max_influences,
            )
        )

    bad_index = numpy.flatnonzero(
        ((capture.indices >= len(capture.joints)) & (weights > 0)).any(axis=1)
    )
    if bad_index.size:
        issues.append(
            _issue(
                "invalid_joint_index",
                ERROR,
                f"없는 조인트를 가리키는 웨이트가 {bad_index.size}개 점에 있습니다.",
                "boneCapture 의 인덱스 페어 테이블이 깨졌습니다. capture_skin 으로 "
                "다시 캡처하세요.",
                count=int(bad_index.size),
                joint_count=len(capture.joints),
            )
        )
    return issues


def _check_binding(skeleton: Skeleton, capture: Capture) -> list[dict[str, Any]]:
    """캡처된 조인트와 스켈레톤이 서로 맞는지, 바인드 포즈가 현재 포즈와 같은지."""
    issues: list[dict[str, Any]] = []
    skeleton_names = set(skeleton.names)

    unknown = [name for name in capture.joints if name not in skeleton_names]
    if unknown:
        issues.append(
            _issue(
                "unknown_capture_joints",
                ERROR,
                f"스켈레톤에 없는 조인트를 캡처가 가리키고 있습니다 ({len(unknown)}개).",
                "스킨과 스켈레톤이 다른 리그에서 왔습니다. capture_skin 으로 지금 "
                "스켈레톤에 다시 캡처하세요.",
                joints=unknown[:MAX_NAMED],
                count=len(unknown),
            )
        )

    weights = effective_weights(capture)
    used = set()
    if capture.joints:
        flat_index = capture.indices.reshape(-1)
        flat_weight = weights.reshape(-1)
        valid = (flat_index >= 0) & (flat_index < len(capture.joints)) & (flat_weight > 0)
        used = {capture.joints[int(i)] for i in numpy.unique(flat_index[valid])}

    idle = [name for name in skeleton.names if name not in used and name in set(capture.joints)]
    if idle:
        issues.append(
            _issue(
                "unused_joints",
                WARNING,
                f"캡처에는 있는데 어느 점도 끌지 않는 조인트가 {len(idle)}개 있습니다.",
                "그 조인트를 돌려도 메시가 움직이지 않습니다. 의도한 것이 아니면 "
                "capture_skin 의 dropoff 를 키워 다시 캡처하세요.",
                joints=idle[:MAX_NAMED],
                count=len(idle),
            )
        )

    uncaptured = [name for name in skeleton.names if name not in set(capture.joints)]
    if uncaptured:
        issues.append(
            _issue(
                "uncaptured_joints",
                INFO,
                f"캡처 테이블에 들어가지 않은 조인트가 {len(uncaptured)}개 있습니다.",
                "보조 조인트나 컨트롤용이면 정상입니다. 스킨을 끌어야 할 조인트라면 "
                "capture_skin 으로 다시 캡처하세요.",
                joints=uncaptured[:MAX_NAMED],
                count=len(uncaptured),
            )
        )

    # 바인드 포즈는 pCaptData 의 역 바인드 행렬에 들어 있다. 뒤집으면 캡처 당시의
    # 조인트 월드 위치가 나온다(실측 확인).
    bind = capture.bind_positions()
    if bind.size:
        index = {name: i for i, name in enumerate(skeleton.names)}
        pairs = [
            (i, index[name]) for i, name in enumerate(capture.joints) if name in index
        ]
        if pairs:
            mine = numpy.array([i for i, _ in pairs])
            theirs = numpy.array([j for _, j in pairs])
            distance = numpy.linalg.norm(bind[mine] - skeleton.positions[theirs], axis=1)
            distance = numpy.nan_to_num(distance, nan=0.0)
            drifted = numpy.flatnonzero(distance > BIND_TOLERANCE)
            if drifted.size:
                order = drifted[numpy.argsort(-distance[drifted])][:MAX_NAMED]
                issues.append(
                    _issue(
                        "bind_pose_drift",
                        WARNING,
                        f"바인드 포즈와 지금 스켈레톤이 다른 조인트가 {drifted.size}개 "
                        f"있습니다 (최대 {float(distance.max()):.6f}).",
                        "지금 스켈레톤은 바인드 포즈가 아닙니다. deform_skin 의 "
                        "capture_pose 에는 캡처할 때 쓴 스켈레톤을 주세요. "
                        "지금 포즈로 다시 바인드하려면 capture_skin 을 다시 부릅니다.",
                        count=int(drifted.size),
                        max_distance=float(distance.max()),
                        joints=[
                            {
                                "name": capture.joints[int(i)],
                                "distance": float(distance[int(i)]),
                            }
                            for i in order
                        ],
                    )
                )
    return issues


# --------------------------------------------------------------------------
# 툴
# --------------------------------------------------------------------------


@tool()
def validate_rig(
    skeleton: str, skin: str | None = None, max_influences: int = 4
) -> dict[str, Any]:
    """리그가 맞는지 검사한다. 이 팩의 간판이다.

    조사한 기존 MCP 구현 다섯 중 리그를 검증하는 것이 하나도 없다. 리깅에서 가장
    비싼 실수는 잘못된 채로 다음 단계로 가는 것이고, 그 대부분은 숫자로 잡힌다.

    스켈레톤에서 보는 것:
        계층이 끊겼는지 · 루트가 여럿인지 · 부모 관계에 고리가 있는지
        이름이 겹치거나 비었는지
        조인트 방향(transform)이 뒤집혔는지 · 스케일이 섞였는지
        부모와 겹쳐 길이 0인 본이 있는지

    스킨까지 주면 더 보는 것:
        웨이트 합이 1인지 · 어디에도 안 붙은 점이 있는지
        음수 웨이트 · 영향 조인트가 너무 많은 점
        캡처가 가리키는 조인트가 스켈레톤에 실제로 있는지
        바인드 포즈와 지금 포즈가 벌어졌는지

    지적마다 다음에 무엇을 할지(fix)가 붙는다.

    Args:
        skeleton: 스켈레톤 SOP 경로.
        skin: boneCapture 를 가진 스킨 메시 SOP 경로. 생략하면 스켈레톤만 본다.
        max_influences: 점 하나에 허용할 영향 조인트 수. 게임 엔진은 보통 4다.
    """
    skeleton_node, skeleton_geo, skeleton_data = skeleton_at(skeleton)

    issues: list[dict[str, Any]] = []
    issues += _check_hierarchy(skeleton_data)
    issues += _check_names(skeleton_data)
    issues += _check_transforms(skeleton_data)
    issues += _check_bones(skeleton_data)

    checked = ["hierarchy", "names", "transforms", "bones"]
    skin_summary: dict[str, Any] | None = None

    if skin:
        skin_node, skin_geo, capture = capture_at(skin)
        issues += _check_weights(capture, int(max_influences))
        issues += _check_binding(skeleton_data, capture)
        checked += ["weights", "binding"]

        weights = effective_weights(capture)
        totals = weights.sum(axis=1) if capture.point_count else numpy.zeros(0)
        skin_summary = {
            "path": skin_node.path(),
            "comment": skin_node.comment(),
            "points": capture.point_count,
            "captured_joints": len(capture.joints),
            "max_influences_stored": capture.max_influences,
            "weight_sum": {
                "min": float(totals.min()) if totals.size else 0.0,
                "max": float(totals.max()) if totals.size else 0.0,
                "mean": float(totals.mean()) if totals.size else 0.0,
            },
            "bbox_points": int(point_floats(skin_geo, "P", 3).shape[0]),
        }

    severity_rank = {ERROR: 0, WARNING: 1, INFO: 2}
    issues.sort(key=lambda issue: (severity_rank[issue["severity"]], issue["check"]))
    counts = {
        level: sum(1 for i in issues if i["severity"] == level)
        for level in (ERROR, WARNING, INFO)
    }

    return {
        "ok": counts[ERROR] == 0,
        "skeleton": {
            "path": skeleton_node.path(),
            "comment": skeleton_node.comment(),
            "joints": skeleton_data.count,
            "bones": int(skeleton_geo.primCount()),
            "roots": [skeleton_data.names[i] for i in skeleton_data.roots()],
            "hierarchy_source": skeleton_data.parent_source,
            "has_transform": skeleton_data.transforms is not None,
        },
        "skin": skin_summary,
        "checked": checked,
        "counts": counts,
        "issues": issues,
    }
