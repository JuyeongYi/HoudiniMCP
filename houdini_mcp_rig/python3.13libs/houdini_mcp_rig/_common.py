"""팩 전체가 쓰는 헬퍼. 툴은 여기 없다.

네 가지를 모아 뒀다.

1. **노드 해석과 조립** — SOP 경로를 받아 지오메트리를 꺼내고, 입력 옆에 노드를
   만들어 잇는다. `houdini_mcp_sop/_common.py` 와 같은 `build`/`report` 패턴이다.
2. **스켈레톤 읽기** — KineFX 스켈레톤은 특수 자료구조가 아니라 **점과
   폴리라인**이다. `read_skeleton` 이 이름·부모·월드 위치·회전행렬을 numpy 배열로
   한 번에 꺼낸다.
3. **캡처 웨이트 읽기** — `boneCapture` 는 인덱스 페어 어트리뷰트다. 레이아웃은
   실측으로 확인했다(아래 `read_capture` 주석). 점 10만 개를 numpy 로 한 번에
   받는다.
4. **부모 인덱스 유도** — `parent_idx` 가 없는 스켈레톤은 폴리라인에서 부모를
   찾아야 한다. 파이썬으로 프림을 돌지 않고 attribwrangle **verb** 로 VEX 를
   독립 지오메트리에 돌린다. 사용자의 네트워크는 건드리지 않는다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import hou
import numpy

BONE_CAPTURE = "boneCapture"
"""스킨 웨이트가 들어 있는 점 어트리뷰트 이름. Houdini 전역 규약이다."""

CAPTURE_PATH_PROP = "pCaptPath"
CAPTURE_DATA_PROP = "pCaptData"
"""인덱스 페어 테이블의 프로퍼티 이름. 각각 조인트 이름과 역 바인드 행렬이다."""

TRANSFORM_ATTRIB = "transform"
"""조인트의 월드 회전/스케일. matrix3(9개 float) 이다. 위치는 P 가 갖는다."""

PARENT_ATTRIB = "parent_idx"
"""rigdoctor 가 켜 주는 부모 점 번호. 없으면 폴리라인에서 유도한다."""

NAME_ATTRIB = "name"
"""조인트 이름. 이것이 없으면 스켈레톤으로 볼 수 없다."""


# --------------------------------------------------------------------------
# 노드 해석과 조립
# --------------------------------------------------------------------------


def require_sop(path: str) -> hou.SopNode:
    """SOP 노드를 얻는다. 아니면 무엇을 주면 되는지 알려 주고 실패한다."""
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"list_children 으로 부모 네트워크 안을 먼저 확인하세요."
        )
    if not isinstance(node, hou.SopNode):
        raise ValueError(
            f"{path} 는 SOP 이 아니라 {node.type().category().name()} 노드입니다. "
            f"SOP 경로를 주세요. 예: /obj/character/skeleton"
        )
    return node


def geometry_of(node: hou.SopNode) -> hou.Geometry:
    """SOP 을 쿡해서 지오메트리를 꺼낸다. 쿡 실패는 노드 에러를 그대로 전한다."""
    try:
        node.cook()
    except hou.Error as exc:
        detail = " ".join(node.errors()) or str(exc)
        raise ValueError(
            f"{node.path()} ({node.type().name()}) 쿡에 실패했습니다: {detail} "
            f"파라미터와 입력 연결을 고친 뒤 다시 부르세요."
        ) from exc

    geo = node.geometry()
    if geo is None:
        raise ValueError(
            f"{node.path()} 의 지오메트리를 읽지 못했습니다. "
            f"입력이 연결돼 있는지 확인하세요."
        )
    return geo


def geometry_at(path: str) -> tuple[hou.SopNode, hou.Geometry]:
    """경로 하나로 노드와 지오메트리를 함께 얻는다."""
    node = require_sop(path)
    return node, geometry_of(node)


def require_comment(comment: str) -> None:
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 노드가 무엇을 위한 것인지 영어로 적어 주세요. "
            "Capture tube skin to 3 joints, 2 influences 처럼 구체적으로."
        )


def set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def set_parms(node: hou.Node, parms: dict[str, Any]) -> None:
    """값이 None 인 것은 건너뛴다. 벡터는 parmTuple 로 건다."""
    for name, value in parms.items():
        if value is None:
            continue
        parm = node.parm(name)
        if parm is not None:
            parm.set(value)
            continue
        tuple_parm = node.parmTuple(name)
        if tuple_parm is None:
            raise ValueError(
                f"{node.type().name()} 에 파라미터 {name!r} 가 없습니다. "
                f"list_parms 로 이 노드의 파라미터 이름을 확인하세요."
            )
        tuple_parm.set(tuple(value))


def build(
    source: hou.SopNode,
    node_type: str,
    comment: str,
    name: str | None = None,
    parms: dict[str, Any] | None = None,
    extra_inputs: Sequence[hou.SopNode | None] = (),
) -> hou.SopNode:
    """입력 SOP 옆에 노드를 만들어 잇는다.

    코멘트를 달고 네트워크 뷰에 보이게 하며, 디스플레이/렌더 플래그를 새 노드로
    옮긴다. 새 노드가 체인의 끝이 되기 때문이다.
    """
    require_comment(comment)

    parent = source.parent()
    try:
        node = parent.createNode(node_type, node_name=name)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent.path()} 안에 {node_type!r} 노드를 만들지 못했습니다. "
            f"node_type_info 로 그 네트워크에서 쓸 수 있는 타입인지 확인하세요. ({exc})"
        ) from exc

    node.setFirstInput(source)
    for index, extra in enumerate(extra_inputs, start=1):
        if extra is not None:
            node.setInput(index, extra)

    set_comment(node, comment)
    if parms:
        set_parms(node, parms)

    try:
        node.moveToGoodPosition()
    except hou.Error:
        # 배치는 결과에 영향이 없다. 실패해도 툴을 실패시키지 않는다.
        pass
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return node


def same_parent_hint(first: hou.Node, second: hou.Node) -> None:
    """두 노드가 같은 네트워크에 있는지 확인한다.

    Houdini 는 네트워크를 가로질러 입력을 잇지 못한다. 그대로 두면 `setInput` 이
    조용히 실패하고 노드가 입력 없이 쿡돼 엉뚱한 에러가 나므로, 여기서 막는다.

    HOM 은 같은 노드에도 매번 새 래퍼 객체를 주기 때문에 `is` 나 `==` 가 아니라
    경로로 비교한다.
    """
    if first.parent().path() != second.parent().path():
        raise ValueError(
            f"{first.path()} 와 {second.path()} 가 다른 네트워크에 있습니다 "
            f"({first.parent().path()} vs {second.parent().path()}). "
            f"Houdini 는 네트워크를 건너 입력을 잇지 못합니다. 같은 geo 노드 안으로 "
            f"옮기거나 object_merge 로 끌어온 뒤 다시 부르세요."
        )


def bbox_dict(bbox: hou.BoundingBox) -> dict[str, list[float]]:
    """바운딩 박스를 JSON 으로 낼 수 있는 모양으로."""
    if not bbox.isValid():
        return {"min": [], "max": [], "size": [], "center": []}
    minvec, maxvec = bbox.minvec(), bbox.maxvec()
    size, center = bbox.sizevec(), bbox.center()
    return {
        "min": [minvec[0], minvec[1], minvec[2]],
        "max": [maxvec[0], maxvec[1], maxvec[2]],
        "size": [size[0], size[1], size[2]],
        "center": [center[0], center[1], center[2]],
    }


def node_brief(node: hou.SopNode) -> dict[str, Any]:
    """만든 노드를 가리키는 최소 정보. 코멘트를 반드시 포함한다."""
    return {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "warnings": list(node.warnings()),
    }


# --------------------------------------------------------------------------
# 벌크 어트리뷰트 읽기
# --------------------------------------------------------------------------


def point_floats(geo: hou.Geometry, name: str, size: int) -> numpy.ndarray:
    """점 float 어트리뷰트를 (점 수, size) numpy 배열로.

    `*AsString` 으로 바이트를 통째로 받아 `numpy.frombuffer` 로 꽂는다. 파이썬
    점 루프를 돌지 않는다(README 제3원칙).
    """
    raw = geo.pointFloatAttribValuesAsString(name, hou.numericData.Float32)
    array = numpy.frombuffer(raw, dtype=numpy.float32)
    return array.reshape(-1, size) if size > 1 else array.reshape(-1)


def point_ints(geo: hou.Geometry, name: str) -> numpy.ndarray:
    """점 int 어트리뷰트를 numpy 배열로."""
    raw = geo.pointIntAttribValuesAsString(name, hou.numericData.Int32)
    return numpy.frombuffer(raw, dtype=numpy.int32)


# --------------------------------------------------------------------------
# 스켈레톤
# --------------------------------------------------------------------------


_PARENT_VEX = """
// 폴리라인에서 부모 점을 찾는다. 한 프림 안에서 나보다 하나 앞에 있는 점이
// 부모다. 파이썬 프림 루프 대신 VEX 로 돌려 C++ 쪽에서 처리한다.
int parent = -1;
foreach (int prim; pointprims(0, @ptnum)) {
    int pts[] = primpoints(0, prim);
    int slot = find(pts, @ptnum);
    if (slot > 0) {
        parent = pts[slot - 1];
        break;
    }
}
i@__rig_parent = parent;
"""


@dataclass(frozen=True)
class Skeleton:
    """스켈레톤 지오메트리를 numpy 로 읽어 둔 것.

    KineFX 스켈레톤의 실제 스키마는 이렇다(실측):

        P             점 위치 = 조인트의 월드 위치
        name          조인트 이름 (string)
        transform     월드 회전/스케일 matrix3 (float 9개)
        parent_idx    부모 점 번호. rigdoctor 가 켜 줬을 때만 있다
        폴리라인 프림  부모 -> 자식 순서로 점을 잇는다
    """

    names: list[str]
    parents: numpy.ndarray  # (n,) int32, 루트는 -1
    positions: numpy.ndarray  # (n, 3) float32
    transforms: numpy.ndarray | None  # (n, 3, 3) float32
    parent_source: str

    @property
    def count(self) -> int:
        return len(self.names)

    def roots(self) -> list[int]:
        return [int(i) for i in numpy.flatnonzero(self.parents < 0)]

    def children(self) -> list[list[int]]:
        """부모별 자식 목록. 부모 배열 한 번 훑기로 만든다."""
        out: list[list[int]] = [[] for _ in range(self.count)]
        for child, parent in enumerate(self.parents.tolist()):
            if 0 <= parent < self.count:
                out[parent].append(child)
        return out

    def depths(self) -> numpy.ndarray:
        """루트부터의 깊이. 사이클에 걸린 조인트는 -1 로 남는다."""
        depth = numpy.full(self.count, -1, dtype=numpy.int32)
        children = self.children()
        stack = [(root, 0) for root in self.roots()]
        while stack:
            index, level = stack.pop()
            if depth[index] >= 0:
                continue
            depth[index] = level
            stack.extend((child, level + 1) for child in children[index])
        return depth

    def index_of(self, name: str) -> int:
        """이름으로 조인트 번호를 찾는다. 없으면 비슷한 이름을 알려 준다."""
        try:
            return self.names.index(name)
        except ValueError:
            pass
        lowered = name.lower()
        close = [n for n in self.names if lowered in n.lower()][:8]
        hint = ", ".join(close) if close else ", ".join(self.names[:10])
        raise ValueError(
            f"조인트 {name!r} 가 없습니다. list_joints 로 이름을 확인하세요. "
            f"비슷한 이름: {hint}"
        )

    def descendants(self, index: int, inclusive: bool = True) -> list[int]:
        """자기 자신과 모든 자손. 포즈를 걸 때 함께 움직여야 하는 점들이다."""
        children = self.children()
        out: list[int] = []
        stack = [index]
        seen = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            out.append(current)
            stack.extend(children[current])
        if not inclusive:
            out = [i for i in out if i != index]
        return sorted(out)

    def chain_to_root(self, index: int) -> list[str]:
        """루트에서 이 조인트까지의 이름 경로. 사이클이면 거기서 멈춘다."""
        path: list[int] = []
        seen: set[int] = set()
        current = index
        while 0 <= current < self.count and current not in seen:
            seen.add(current)
            path.append(current)
            current = int(self.parents[current])
        return [self.names[i] for i in reversed(path)]


def read_skeleton(geo: hou.Geometry, path: str = "") -> Skeleton:
    """스켈레톤 지오메트리를 numpy 배열로 읽는다.

    `name` 점 어트리뷰트가 없으면 스켈레톤이 아니다. 그 경우 무엇을 주면 되는지
    알려 주고 실패한다.
    """
    if geo.findPointAttrib(NAME_ATTRIB) is None:
        existing = ", ".join(a.name() for a in geo.pointAttribs()) or "(없음)"
        raise ValueError(
            f"{path or '이 지오메트리'} 는 스켈레톤이 아닙니다. 조인트 이름이 담긴 "
            f"점 어트리뷰트 {NAME_ATTRIB!r} 가 없습니다. 있는 점 어트리뷰트: {existing}. "
            f"create_skeleton 으로 만들거나 kinefx::rigdoctor 를 거친 노드를 주세요."
        )

    names = list(geo.pointStringAttribValues(NAME_ATTRIB))
    positions = point_floats(geo, "P", 3)

    if geo.findPointAttrib(PARENT_ATTRIB) is not None:
        parents = point_ints(geo, PARENT_ATTRIB).astype(numpy.int32)
        source = PARENT_ATTRIB
    else:
        parents = _derive_parents(geo)
        source = "polyline prims"

    transforms = None
    attrib = geo.findPointAttrib(TRANSFORM_ATTRIB)
    if attrib is not None and attrib.size() == 9:
        transforms = point_floats(geo, TRANSFORM_ATTRIB, 9).reshape(-1, 3, 3)

    return Skeleton(
        names=names,
        parents=parents,
        positions=positions,
        transforms=transforms,
        parent_source=source,
    )


def _derive_parents(geo: hou.Geometry) -> numpy.ndarray:
    """폴리라인에서 부모 점 번호를 유도한다.

    attribwrangle **verb** 로 VEX 를 독립 지오메트리에 돌린다. 노드를 만들지
    않으므로 사용자의 네트워크가 더러워지지 않고, 프림 루프가 C++ 쪽에서 돈다.
    """
    if geo.pointCount() == 0:
        return numpy.zeros(0, dtype=numpy.int32)
    verb = hou.sopNodeTypeCategory().nodeVerb("attribwrangle")
    verb.setParms({"class": 2, "snippet": _PARENT_VEX})  # class 2 = points
    out = hou.Geometry()
    verb.execute(out, [geo])
    return point_ints(out, "__rig_parent").astype(numpy.int32)


def skeleton_at(path: str) -> tuple[hou.SopNode, hou.Geometry, Skeleton]:
    """경로 하나로 노드·지오메트리·스켈레톤을 함께 얻는다."""
    node, geo = geometry_at(path)
    return node, geo, read_skeleton(geo, path)


# --------------------------------------------------------------------------
# 캡처 웨이트
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Capture:
    """`boneCapture` 를 numpy 로 읽어 둔 것.

    레이아웃은 실측으로 확인했다. `boneCapture` 는 **Index Pair** 자격을 가진
    float 점 어트리뷰트이고, 크기는 `2 * 최대영향수` 다. 값은

        [조인트번호0, 웨이트0, 조인트번호1, 웨이트1, ...]

    처럼 **끼워 넣기(interleave)** 돼 있다. 쓰이지 않는 슬롯의 조인트 번호는
    -1 이다.

    조인트 번호가 가리키는 이름은 어트리뷰트에 딸린 인덱스 페어 테이블
    (`hou.Attrib.indexPairPropertyTables`)의 `pCaptPath` 에 있다. 같은 테이블의
    `pCaptData` 는 float 20개인데, 앞 16개가 그 조인트의 **역 바인드 월드 행렬**
    (행 우선, 이동 성분이 3행)이다. 뒤 4개는 테이퍼/캡 값으로 스키닝에 쓰이지
    않는다.
    """

    joints: list[str]
    bind_inverse: numpy.ndarray  # (m, 4, 4) float64
    indices: numpy.ndarray  # (n, k) int32, 빈 슬롯은 -1
    weights: numpy.ndarray  # (n, k) float32

    @property
    def point_count(self) -> int:
        return int(self.indices.shape[0])

    @property
    def max_influences(self) -> int:
        return int(self.indices.shape[1])

    def bind_positions(self) -> numpy.ndarray:
        """각 조인트의 바인드 포즈 월드 위치. 역 바인드 행렬을 뒤집어 얻는다."""
        if not len(self.joints):
            return numpy.zeros((0, 3))
        out = numpy.zeros((len(self.joints), 3))
        for i, matrix in enumerate(self.bind_inverse):
            try:
                out[i] = numpy.linalg.inv(matrix)[3, :3]
            except numpy.linalg.LinAlgError:
                # 특이 행렬이면 바인드 위치를 알 수 없다. validate_rig 가 잡는다.
                out[i] = numpy.nan
        return out


def read_capture(geo: hou.Geometry, path: str = "") -> Capture:
    """스킨 지오메트리에서 캡처 웨이트를 numpy 로 읽는다."""
    attrib = geo.findPointAttrib(BONE_CAPTURE)
    if attrib is None:
        existing = ", ".join(a.name() for a in geo.pointAttribs()) or "(없음)"
        raise ValueError(
            f"{path or '이 지오메트리'} 에 스킨 웨이트({BONE_CAPTURE})가 없습니다. "
            f"있는 점 어트리뷰트: {existing}. capture_skin 으로 먼저 스켈레톤에 "
            f"붙이세요."
        )
    if attrib.size() % 2:
        raise ValueError(
            f"{BONE_CAPTURE} 의 크기가 {attrib.size()} 라 인덱스/웨이트 쌍으로 "
            f"나눌 수 없습니다. 어트리뷰트가 손상됐습니다. capture_skin 으로 다시 "
            f"캡처하세요."
        )

    raw = point_floats(geo, BONE_CAPTURE, attrib.size())
    pairs = raw.reshape(geo.pointCount(), -1, 2)
    indices = pairs[:, :, 0].astype(numpy.int32)
    weights = numpy.ascontiguousarray(pairs[:, :, 1])

    joints: list[str] = []
    bind: list[numpy.ndarray] = []
    tables = attrib.indexPairPropertyTables()
    if tables:
        table = tables[0]
        for i in range(table.numIndices()):
            joints.append(table.stringPropertyValueAtIndex(CAPTURE_PATH_PROP, i))
            try:
                data = table.floatListPropertyValueAtIndex(CAPTURE_DATA_PROP, i)
            except hou.OperationFailed:
                data = ()
            if len(data) >= 16:
                bind.append(numpy.array(data[:16], dtype=numpy.float64).reshape(4, 4))
            else:
                bind.append(numpy.eye(4))

    bind_inverse = (
        numpy.stack(bind) if bind else numpy.zeros((0, 4, 4), dtype=numpy.float64)
    )
    return Capture(
        joints=joints, bind_inverse=bind_inverse, indices=indices, weights=weights
    )


def capture_at(path: str) -> tuple[hou.SopNode, hou.Geometry, Capture]:
    """경로 하나로 노드·지오메트리·캡처를 함께 얻는다."""
    node, geo = geometry_at(path)
    return node, geo, read_capture(geo, path)


def effective_weights(capture: Capture) -> numpy.ndarray:
    """빈 슬롯(조인트 번호 -1)을 0 으로 지운 웨이트 배열."""
    return numpy.where(capture.indices >= 0, capture.weights, 0.0)


def sample_indices(count: int, limit: int) -> list[int]:
    """개수가 많으면 고르게 솎아 낸다. 원본을 그대로 돌려주지 않는다."""
    if count <= limit:
        return list(range(count))
    return [int(i) for i in numpy.linspace(0, count - 1, limit).round().astype(int)]
