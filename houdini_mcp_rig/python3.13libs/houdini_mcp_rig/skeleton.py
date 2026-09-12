"""스켈레톤을 만들고 읽고 포즈를 건다.

KineFX 스켈레톤은 특수 자료구조가 아니라 **점과 폴리라인**이다(실측 확인).
조인트 하나가 점 하나고, 이름은 `name` 점 어트리뷰트, 월드 회전은 `transform`
(matrix3), 계층은 폴리라인이 잇는 순서다. 그래서 여기 툴들은 전부 numpy 벌크
경로로 읽는다 — 조인트 200개짜리 캐릭터에서 파이썬 점 루프를 돌 이유가 없다.

포즈는 `kinefx::rigattribwrangle` 로 건다. 조인트를 돌리면 그 자손이 함께
움직여야 하는데, 자손 목록을 계층에서 뽑아 VEX 에 넘긴다. 회전축(피벗)은 VEX 가
입력 지오메트리에서 직접 읽으므로, 위쪽이 바뀌어도 노드가 계속 맞는다.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

import hou
import numpy

from houdini_mcp import tool, undoable

from ._common import (
    NAME_ATTRIB,
    PARENT_ATTRIB,
    TRANSFORM_ATTRIB,
    Skeleton,
    bbox_dict,
    build,
    geometry_of,
    node_brief,
    read_skeleton,
    require_comment,
    sample_indices,
    skeleton_at,
)

MAX_JOINTS_LISTED = 400
"""한 번에 돌려줄 조인트 수 상한. 더 보내 봐야 모델 컨텍스트만 태운다."""

# 조인트 점과 폴리라인을 만드는 파이썬 SOP 코드. 이 팩을 import 하지 않는다 —
# 팩이 없는 머신에서 씬을 열어도 노드가 쿡돼야 하기 때문이다.
_BUILD_SKELETON = '''\
# houdini_mcp_rig.create_skeleton 이 생성한 코드.
# JOINTS 를 고치면 스켈레톤이 바뀐다.
import json

import hou

JOINTS = json.loads("""{payload}""")

geo = hou.pwd().geometry()
name_attrib = geo.addAttrib(hou.attribType.Point, "name", "")
points = []
for spec in JOINTS:
    point = geo.createPoint()
    point.setPosition(hou.Vector3(*spec["position"]))
    point.setAttribValue(name_attrib, spec["name"])
    points.append(point)
for index, spec in enumerate(JOINTS):
    parent = spec["parent"]
    if parent is None:
        continue
    line = geo.createPolygon(is_closed=False)
    line.addVertex(points[parent])
    line.addVertex(points[index])
'''

_POSE_VEX = '''\
// houdini_mcp_rig.pose_joints 가 생성한 VEX.
// {joint} 와 그 자손을 함께 움직인다. 자손만 움직이면 리그가 찢어진다.
int affected[] = array({affected});
if (find(affected, @ptnum) < 0) return;

// 피벗을 입력에서 직접 읽는다. 위쪽에서 이미 포즈가 걸렸어도 맞는 값이 온다.
vector pivot = point(0, "P", {index});

matrix3 rot = ident();
rotate(rot, radians({rx}), {{1, 0, 0}});
rotate(rot, radians({ry}), {{0, 1, 0}});
rotate(rot, radians({rz}), {{0, 0, 1}});

matrix xform = ident();
translate(xform, -pivot);
xform *= matrix(rot);
translate(xform, pivot + set({tx}, {ty}, {tz}));

@P = @P * xform;
3@transform = 3@transform * rot;
'''


@tool()
@undoable("Create skeleton")
def create_skeleton(
    parent: str, joints: Sequence[dict[str, Any]], comment: str, name: str | None = None
) -> dict[str, Any]:
    """조인트 목록으로 KineFX 스켈레톤을 만든다.

    Houdini 의 Skeleton SOP 은 뷰포트에서 클릭으로 조인트를 놓게 돼 있어 MCP 에서
    쓸 수 없다. 이 툴은 같은 결과(점 + 폴리라인 + name + transform)를 코드로
    만든다. 만들어진 파이썬 SOP 은 사람이 읽고 고칠 수 있다.

    조인트 이름은 역할이 드러나게 짓는다. joint1, joint2 가 아니라 hips, spine,
    upper_arm_L 처럼. 나중에 이 리그를 쓰는 사람이 이름만 보고 알아야 한다.

    Args:
        parent: 스켈레톤을 만들 부모 네트워크. 보통 /obj 아래 geo 노드.
        joints: 조인트 목록. 각각 다음 키를 갖는다.
            name     - 조인트 이름 (영어). 반드시 유일해야 한다.
            position - 월드 위치 [x, y, z].
            parent   - 부모 조인트 이름. 루트는 생략하거나 null.
        comment: 이 스켈레톤이 무엇인지 영어로. 예: Three joint test skeleton
        name: 노드 이름. 생략하면 Houdini 가 정한다.
    """
    require_comment(comment)
    specs = _normalize_joints(joints)

    network = hou.node(parent)
    if network is None:
        raise ValueError(
            f"그런 네트워크가 없습니다: {parent}. "
            f"/obj 아래 geo 노드 경로를 주세요. 예: /obj/character"
        )
    if network.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError(
            f"{parent} 안에는 SOP 을 만들 수 없습니다 "
            f"({network.childTypeCategory().name()} 네트워크입니다). "
            f"/obj 아래 geo 노드 경로를 주세요."
        )

    source = network.createNode("python", node_name=name or "skeleton_points")
    payload = json.dumps(specs).replace("\\", "\\\\").replace('"', '\\"')
    source.parm("python").set(_BUILD_SKELETON.format(payload=payload))
    source.setComment(f"{comment.strip()} (joint definition)")
    source.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    doctor = build(
        source,
        "kinefx::rigdoctor",
        comment,
        name=f"{name}_doctor" if name else "skeleton",
        parms={"inittransforms": True, "outputparentidx": True},
    )
    try:
        source.moveToGoodPosition()
    except hou.Error:
        pass

    geo = geometry_of(doctor)
    skeleton = read_skeleton(geo, doctor.path())
    return {
        **node_brief(doctor),
        "definition_path": source.path(),
        "joints": skeleton.count,
        "roots": [skeleton.names[i] for i in skeleton.roots()],
        "max_depth": int(skeleton.depths().max()) if skeleton.count else 0,
        "bbox": bbox_dict(geo.boundingBox()),
        "has_transform": skeleton.transforms is not None,
    }


def _normalize_joints(joints: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """조인트 목록을 검사하고 부모를 이름에서 번호로 바꾼다."""
    if not joints:
        raise ValueError(
            "joints 가 비어 있습니다. 최소한 루트 조인트 하나는 있어야 합니다. "
            '예: [{"name": "root", "position": [0, 0, 0]}]'
        )

    order: dict[str, int] = {}
    for index, spec in enumerate(joints):
        joint_name = str(spec.get("name", "")).strip()
        if not joint_name:
            raise ValueError(
                f"{index}번째 조인트에 name 이 없습니다. 역할이 드러나는 영어 이름을 "
                f"주세요. 예: hips, spine, upper_arm_L"
            )
        if joint_name in order:
            raise ValueError(
                f"조인트 이름 {joint_name!r} 가 두 번 나옵니다. 이름은 유일해야 "
                f"캡처와 리타깃이 조인트를 찾을 수 있습니다."
            )
        order[joint_name] = index

    out: list[dict[str, Any]] = []
    for index, spec in enumerate(joints):
        position = spec.get("position")
        if position is None or len(position) != 3:
            raise ValueError(
                f"조인트 {spec.get('name')!r} 의 position 은 [x, y, z] 세 개여야 "
                f"합니다. 받은 것: {position!r}"
            )
        parent_name = spec.get("parent")
        if parent_name in (None, ""):
            parent_index = None
        else:
            if parent_name not in order:
                raise ValueError(
                    f"조인트 {spec.get('name')!r} 의 부모 {parent_name!r} 가 목록에 "
                    f"없습니다. 있는 이름: {', '.join(order)}"
                )
            if order[parent_name] == index:
                raise ValueError(
                    f"조인트 {spec.get('name')!r} 가 자기 자신을 부모로 가리킵니다."
                )
            parent_index = order[parent_name]
        out.append(
            {
                "name": str(spec["name"]).strip(),
                "position": [float(v) for v in position],
                "parent": parent_index,
            }
        )
    return out


@tool()
def skeleton_info(path: str) -> dict[str, Any]:
    """스켈레톤 전체를 한눈에 — 조인트 수, 루트, 깊이, 본 길이, 어트리뷰트.

    조인트를 하나씩 나열하지 않고 구조만 준다. 목록이 필요하면 list_joints 를,
    리그가 맞는지 알고 싶으면 validate_rig 를 쓰세요.

    Args:
        path: 스켈레톤을 내보내는 SOP 노드 경로.
    """
    node, geo, skeleton = skeleton_at(path)
    depths = skeleton.depths()
    lengths = _bone_lengths(skeleton)

    return {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "joints": skeleton.count,
        "bones": int(geo.primCount()),
        "roots": [skeleton.names[i] for i in skeleton.roots()],
        "leaves": [
            skeleton.names[i]
            for i, kids in enumerate(skeleton.children())
            if not kids
        ][:MAX_JOINTS_LISTED],
        "max_depth": int(depths.max()) if skeleton.count else 0,
        "hierarchy_source": skeleton.parent_source,
        "bone_length": _length_stats(lengths),
        "bbox": bbox_dict(geo.boundingBox()),
        "has_transform": skeleton.transforms is not None,
        "point_attribs": sorted(a.name() for a in geo.pointAttribs()),
        "detail_attribs": sorted(a.name() for a in geo.globalAttribs()),
    }


def _bone_lengths(skeleton: Skeleton) -> numpy.ndarray:
    """부모가 있는 조인트의 부모까지 거리. 전부 numpy 한 번에."""
    has_parent = skeleton.parents >= 0
    if not has_parent.any():
        return numpy.zeros(0, dtype=numpy.float64)
    child = skeleton.positions[has_parent]
    parent = skeleton.positions[skeleton.parents[has_parent]]
    return numpy.linalg.norm(child - parent, axis=1)


def _length_stats(lengths: numpy.ndarray) -> dict[str, Any]:
    if not lengths.size:
        return {"count": 0}
    return {
        "count": int(lengths.size),
        "min": float(lengths.min()),
        "max": float(lengths.max()),
        "mean": float(lengths.mean()),
        "total": float(lengths.sum()),
    }


@tool()
def list_joints(path: str, pattern: str = "*", limit: int = 200) -> dict[str, Any]:
    """조인트를 계층 정보와 함께 나열한다.

    이름·부모·깊이·자식 수·월드 위치를 준다. 이름만으로는 어느 조인트가 어디에
    붙어 있는지 알 수 없기 때문이다.

    Args:
        path: 스켈레톤을 내보내는 SOP 노드 경로.
        pattern: 이름 패턴. Houdini 글로브를 쓴다. 예: arm_*, *_L
        limit: 돌려줄 조인트 수 상한. 최대 400.
    """
    node, _, skeleton = skeleton_at(path)
    limit = max(1, min(int(limit), MAX_JOINTS_LISTED))

    depths = skeleton.depths()
    children = skeleton.children()
    matched = [
        i for i, name in enumerate(skeleton.names) if hou.text.patternMatch(pattern, name)
    ]

    joints = [
        {
            "name": skeleton.names[i],
            "index": i,
            "parent": (
                skeleton.names[int(skeleton.parents[i])]
                if 0 <= skeleton.parents[i] < skeleton.count
                else None
            ),
            "depth": int(depths[i]),
            "children": len(children[i]),
            "position": [round(float(v), 6) for v in skeleton.positions[i]],
        }
        for i in matched[:limit]
    ]
    return {
        "path": node.path(),
        "comment": node.comment(),
        "pattern": pattern,
        "total": skeleton.count,
        "matched": len(matched),
        "returned": len(joints),
        "truncated": len(matched) > len(joints),
        "joints": joints,
    }


@tool()
def joint_info(path: str, joint: str) -> dict[str, Any]:
    """조인트 하나를 자세히 — 계층 경로, 월드 위치, 회전행렬, 자식, 본 길이.

    Args:
        path: 스켈레톤을 내보내는 SOP 노드 경로.
        joint: 조인트 이름. list_joints 로 확인한다.
    """
    node, _, skeleton = skeleton_at(path)
    index = skeleton.index_of(joint)
    children = skeleton.children()
    parent = int(skeleton.parents[index])

    result: dict[str, Any] = {
        "path": node.path(),
        "comment": node.comment(),
        "name": joint,
        "index": index,
        "parent": skeleton.names[parent] if 0 <= parent < skeleton.count else None,
        "chain_to_root": skeleton.chain_to_root(index),
        "children": [skeleton.names[c] for c in children[index]],
        "descendants": len(skeleton.descendants(index, inclusive=False)),
        "depth": int(skeleton.depths()[index]),
        "position": [float(v) for v in skeleton.positions[index]],
    }

    if 0 <= parent < skeleton.count:
        offset = skeleton.positions[index] - skeleton.positions[parent]
        result["bone_length"] = float(numpy.linalg.norm(offset))
        result["offset_from_parent"] = [float(v) for v in offset]

    if skeleton.transforms is not None:
        matrix = skeleton.transforms[index].astype(numpy.float64)
        result["transform"] = [[float(v) for v in row] for row in matrix]
        result["determinant"] = float(numpy.linalg.det(matrix))
        result["axis_lengths"] = [
            float(v) for v in numpy.linalg.norm(matrix, axis=1)
        ]
    return result


@tool()
@undoable("Pose joints")
def pose_joints(
    path: str, poses: Sequence[dict[str, Any]], comment: str, name: str | None = None
) -> dict[str, Any]:
    """조인트를 돌리거나 옮긴다. 자손이 함께 따라온다.

    조인트마다 `kinefx::rigattribwrangle` 을 하나씩 만들어 얕은 것부터 잇는다.
    부모를 먼저 돌려야 자식의 피벗이 맞기 때문이다. 만들어진 VEX 는 사람이 읽고
    고칠 수 있다.

    회전은 각 조인트의 **현재 월드 위치를 중심으로** X, Y, Z 순서로 돈다.

    Args:
        path: 스켈레톤을 내보내는 SOP 노드 경로.
        poses: 포즈 목록. 각각 다음 키를 갖는다.
            joint     - 조인트 이름.
            rotate    - [rx, ry, rz] 도 단위. 생략하면 0.
            translate - [tx, ty, tz]. 생략하면 0.
        comment: 이 포즈가 무엇인지 영어로. 예: Bend elbow 45 degrees
        name: 노드 이름 앞머리. 생략하면 Houdini 가 정한다.
    """
    require_comment(comment)
    node, _, skeleton = skeleton_at(path)
    if not poses:
        raise ValueError(
            "poses 가 비어 있습니다. 최소한 조인트 하나는 지정하세요. "
            '예: [{"joint": "mid", "rotate": [0, 0, 45]}]'
        )

    depths = skeleton.depths()
    entries = [_normalize_pose(skeleton, spec) for spec in poses]
    entries.sort(key=lambda entry: int(depths[entry["index"]]))

    before = skeleton.positions.copy()
    current = node
    created: list[dict[str, Any]] = []
    for entry in entries:
        affected = skeleton.descendants(entry["index"])
        wrangle = build(
            current,
            "kinefx::rigattribwrangle",
            f"{comment.strip()} ({entry['joint']})",
            name=f"{name}_{entry['joint']}" if name else f"pose_{entry['joint']}",
            parms={
                "class": 2,  # points
                "snippet": _POSE_VEX.format(
                    joint=entry["joint"],
                    index=entry["index"],
                    affected=", ".join(str(i) for i in affected),
                    rx=entry["rotate"][0],
                    ry=entry["rotate"][1],
                    rz=entry["rotate"][2],
                    tx=entry["translate"][0],
                    ty=entry["translate"][1],
                    tz=entry["translate"][2],
                ),
            },
        )
        created.append(
            {
                "joint": entry["joint"],
                "path": wrangle.path(),
                "affected_joints": len(affected),
            }
        )
        current = wrangle

    posed = read_skeleton(geometry_of(current), current.path())
    moved = numpy.linalg.norm(posed.positions - before, axis=1)
    return {
        **node_brief(current),
        "source": node.path(),
        "applied": created,
        "moved_joints": int((moved > 1e-6).sum()),
        "max_joint_move": float(moved.max()) if moved.size else 0.0,
        "joints_moved_most": [
            {"name": posed.names[i], "distance": float(moved[i])}
            for i in numpy.argsort(-moved)[:5]
            if moved[i] > 1e-6
        ],
    }


def _normalize_pose(skeleton: Skeleton, spec: dict[str, Any]) -> dict[str, Any]:
    joint = str(spec.get("joint", "")).strip()
    if not joint:
        raise ValueError(
            'poses 의 각 항목에는 joint 가 있어야 합니다. 예: {"joint": "mid", '
            '"rotate": [0, 0, 45]}'
        )
    index = skeleton.index_of(joint)
    return {
        "joint": joint,
        "index": index,
        "rotate": _triple(spec.get("rotate"), joint, "rotate"),
        "translate": _triple(spec.get("translate"), joint, "translate"),
    }


def _triple(value: Any, joint: str, field: str) -> tuple[float, float, float]:
    if value is None:
        return (0.0, 0.0, 0.0)
    if len(value) != 3:
        raise ValueError(
            f"조인트 {joint!r} 의 {field} 는 값 3개여야 합니다. "
            f"받은 것: {list(value)} ({len(value)}개)"
        )
    return tuple(float(v) for v in value)  # type: ignore[return-value]


@tool()
def compare_poses(path: str, reference: str, limit: int = 20) -> dict[str, Any]:
    """두 스켈레톤의 같은 이름 조인트가 얼마나 벌어졌는지 비교한다.

    포즈를 걸고 나서 무엇이 얼마나 움직였는지, 리타깃한 결과가 원본과 얼마나
    다른지 확인할 때 쓴다. 이름으로 짝을 짓기 때문에 조인트 수가 달라도 된다.

    Args:
        path: 비교할 스켈레톤 SOP 경로.
        reference: 기준이 되는 스켈레톤 SOP 경로. 보통 바인드 포즈.
        limit: 많이 움직인 조인트를 몇 개까지 보여줄지. 최대 100.
    """
    node, _, current = skeleton_at(path)
    ref_node, _, ref = skeleton_at(reference)
    limit = max(1, min(int(limit), 100))

    ref_index = {name: i for i, name in enumerate(ref.names)}
    shared = [(i, ref_index[name]) for i, name in enumerate(current.names) if name in ref_index]
    if not shared:
        raise ValueError(
            f"{path} 와 {reference} 에 같은 이름의 조인트가 하나도 없습니다. "
            f"list_joints 로 양쪽 이름을 비교하세요."
        )

    mine = numpy.array([i for i, _ in shared])
    theirs = numpy.array([j for _, j in shared])
    offsets = current.positions[mine] - ref.positions[theirs]
    distance = numpy.linalg.norm(offsets, axis=1)

    rotation = None
    if current.transforms is not None and ref.transforms is not None:
        # 회전 차이는 R_cur * R_ref^T 의 트레이스로 각도를 낸다.
        delta = current.transforms[mine].astype(numpy.float64) @ numpy.transpose(
            ref.transforms[theirs].astype(numpy.float64), (0, 2, 1)
        )
        trace = numpy.clip((numpy.trace(delta, axis1=1, axis2=2) - 1.0) / 2.0, -1.0, 1.0)
        rotation = numpy.degrees(numpy.arccos(trace))

    order = numpy.argsort(-distance)[:limit]
    return {
        "path": node.path(),
        "reference": ref_node.path(),
        "shared_joints": len(shared),
        "only_here": [n for n in current.names if n not in ref_index][:limit],
        "only_in_reference": [
            n for n in ref.names if n not in set(current.names)
        ][:limit],
        "max_distance": float(distance.max()),
        "mean_distance": float(distance.mean()),
        "moved_joints": int((distance > 1e-6).sum()),
        "max_rotation_degrees": float(rotation.max()) if rotation is not None else None,
        "largest_differences": [
            {
                "name": current.names[int(mine[i])],
                "distance": float(distance[i]),
                "offset": [float(v) for v in offsets[i]],
                "rotation_degrees": (
                    float(rotation[i]) if rotation is not None else None
                ),
            }
            for i in order
            if distance[i] > 1e-6 or (rotation is not None and rotation[i] > 1e-4)
        ],
    }


@tool()
def joint_attributes(path: str, limit: int = 12) -> dict[str, Any]:
    """스켈레톤이 실제로 들고 있는 조인트 어트리뷰트를 값 예시와 함께 보여준다.

    KineFX 스켈레톤에 무엇이 붙어 있는지는 어느 노드를 거쳤느냐에 따라 다르다.
    `transform` 이 있는지, `parent_idx` 가 켜져 있는지, 캡처 관련 어트리뷰트가
    붙었는지를 값까지 확인해야 다음 단계를 정할 수 있다.

    Args:
        path: 스켈레톤을 내보내는 SOP 노드 경로.
        limit: 어트리뷰트마다 보여줄 조인트 수. 최대 40.
    """
    node, geo, skeleton = skeleton_at(path)
    limit = max(1, min(int(limit), 40))
    picks = sample_indices(skeleton.count, limit)

    known = {
        NAME_ATTRIB: "조인트 이름",
        TRANSFORM_ATTRIB: "월드 회전/스케일 matrix3",
        PARENT_ATTRIB: "부모 점 번호 (kinefx::rigdoctor 가 켠다)",
        "localtransform": "부모 기준 로컬 4x4",
        "P": "조인트의 월드 위치",
    }

    attribs = []
    for attrib in geo.pointAttribs():
        entry: dict[str, Any] = {
            "name": attrib.name(),
            "type": str(attrib.dataType()).rsplit(".", 1)[-1],
            "size": attrib.size(),
            "qualifier": attrib.qualifier() or None,
            "array": attrib.isArrayType(),
            "role": known.get(attrib.name()),
        }
        if not attrib.isArrayType() and attrib.size() <= 9:
            entry["samples"] = [
                {
                    "joint": skeleton.names[i],
                    "value": _readable(geo.point(i).attribValue(attrib.name())),
                }
                for i in picks
            ]
        attribs.append(entry)

    return {
        "path": node.path(),
        "comment": node.comment(),
        "joints": skeleton.count,
        "sampled": [skeleton.names[i] for i in picks],
        "point_attribs": sorted(attribs, key=lambda a: a["name"]),
        "detail_attribs": sorted(a.name() for a in geo.globalAttribs()),
    }


def _readable(value: Any) -> Any:
    """튜플을 JSON 으로 낼 수 있게 풀고 소수점을 줄인다."""
    if isinstance(value, (tuple, list)):
        return [round(float(v), 6) if isinstance(v, (int, float)) else v for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value
