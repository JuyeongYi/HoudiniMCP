"""팩 전체가 쓰는 헬퍼 1 — 레시피 표와 노드 조립.

쿡된 시뮬의 상태를 읽는 쪽은 `_state.py` 에 있다. 둘을 가른 기준은
**씬을 만지는가 / 결과를 읽는가** 다.

여기 담긴 것은 셋.

1. **레시피 표** — DOP 오브젝트 타입에 어떤 솔버가 붙고 여러 오브젝트를 한
   솔버로 합치는지. 이 짝짓기는 SideFX 의 `doptoolutils.theDopObjectTypeDict`
   에서 가져오고, 거기에 없는 타입만 우리 표로 보탠다.
2. **노드 해석과 조립** — dopnet 경로를 받아 검증하고, 노드를 만들어 잇고
   코멘트를 단다.
3. **dopnet 구조 읽기** — 출력까지 실제로 이어진 노드가 무엇인지. dopnet 안에
   있어도 체인 밖이면 시뮬에 참여하지 않는다.

실측으로 확인한 것(Houdini 22.0.368):

- `doptoolutils` 의 셋업 매크로(`genericConvertToDopObject`)는 셸프 툴 문맥을
  요구한다. `hou.shelves.runningTool()` 과 `hou.ui` 를 타므로 MCP 에서는
  rbd 계열·flip 계열이 그대로 실패한다. 그래서 조립은 우리가 직접 하고,
  doptoolutils 에서는 **데이터(타입 짝짓기, 솔버 순서)만** 가져온다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

# --------------------------------------------------------------------------
# 레시피 표 — 오브젝트 타입에 붙는 솔버
# --------------------------------------------------------------------------

# doptoolutils 에 없거나 정보가 부족한 타입을 보탠다. 값은
# (솔버 타입, 여러 오브젝트를 한 솔버로 합치는가, 역할 설명).
_EXTRA_RECIPES: dict[str, tuple[str, bool, str]] = {
    "popobject": ("popsolver::2.0", True, "Particle system"),
    "vellumobject": ("vellumsolver", True, "Vellum cloth / hair / softbody"),
    "mpmobject": ("mpmsolver", True, "MPM continuum material"),
    "smokeobject_sparse": ("smokesolver_sparse", False, "Sparse smoke container"),
    "filamentobject": ("filamentsolver", True, "Vortex filament"),
    "rippleobject": ("ripplesolver", True, "Surface ripple"),
    "crowdobject": ("crowdsolver::3.0", True, "Crowd agents"),
}

# 오브젝트 타입별 사람이 읽을 역할. doptoolutils 에서 오는 타입에 붙인다.
_ROLES: dict[str, str] = {
    "rbdobject": "Rigid body from geometry",
    "rbdfracturedobject": "Fractured rigid body",
    "rbdglueobject": "Glued fractured rigid body",
    "rbdpackedobject": "Packed rigid bodies (one object per packed prim)",
    "rbdpointobject": "Rigid bodies instanced onto points",
    "staticobject": "Passive collider",
    "terrainobject": "Passive heightfield collider",
    "clothobject": "Cloth",
    "clothobject::2.0": "Cloth",
    "wireobject": "Wire / hair strands",
    "femsolidobject": "FEM solid",
    "femhybridobject": "FEM hybrid solid",
    "solidobject": "FEM solid",
    "sandobject": "Granular sand",
    "smokeobject": "Dense smoke container",
    "fluidobject": "Dense fluid container",
    "flipfluidobject": "FLIP liquid",
    "particlefluidobject": "SPH particle fluid",
}


def recipes() -> dict[str, dict[str, Any]]:
    """오브젝트 타입 -> {solver, merge_objects, role}.

    SideFX 의 `doptoolutils.theDopObjectTypeDict` 를 먼저 읽고 그 위에 우리
    표를 덮는다. doptoolutils 가 깨져도 우리 표만으로 동작한다.
    """
    table: dict[str, dict[str, Any]] = {}
    try:
        import doptoolutils

        for name, info in doptoolutils.theDopObjectTypeDict.items():
            table[name] = {
                "solver": info.solvertype,
                "merge_objects": bool(info.mergeobjects),
                "role": _ROLES.get(name, "DOP object"),
                "source": "doptoolutils",
            }
    except Exception:
        # doptoolutils 없이도 팩은 동작해야 한다. 아래 표로 간다.
        pass

    for name, (solver, merge, role) in _EXTRA_RECIPES.items():
        table[name] = {
            "solver": solver,
            "merge_objects": merge,
            "role": role,
            "source": "houdini_mcp_dop",
        }
    return table


def solver_order() -> list[str]:
    """솔버 머지 순서. 정적 -> 강체 -> 천 -> 파티클 -> 유체 순이다.

    이 순서를 지켜야 상호작용이 제대로 잡힌다. doptoolutils 에서 가져오고,
    없으면 실측해 둔 22.0 의 순서를 쓴다.
    """
    try:
        import doptoolutils

        return list(doptoolutils.theSolverOrder)
    except Exception:
        return [
            "staticsolver",
            "rigidbodysolver",
            "rbdsolver",
            "clothsolver",
            "femsolver",
            "wiresolver",
            "popsolver",
            "sandsolver",
            "particlefluidsolver",
            "flipsolver",
            "fluidsolver",
            "pyrosolver",
            "smokesolver",
        ]


def _solver_rank(type_name: str) -> int:
    """솔버 타입의 머지 순위. 모르는 솔버는 맨 뒤로."""
    base = type_name.split("::", 1)[0]
    order = solver_order()
    for index, name in enumerate(order):
        if base == name or base.startswith(name):
            return index
    return len(order)


# --------------------------------------------------------------------------
# 노드 해석
# --------------------------------------------------------------------------


def require_dopnet(path: str) -> hou.Node:
    """DOP 네트워크(dopnet)를 얻는다. 아니면 무엇을 주면 되는지 알려 준다."""
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"list_children 으로 /obj 안을 확인하거나 create_dopnet 으로 먼저 만드세요."
        )
    if node.childTypeCategory() != hou.dopNodeTypeCategory():
        raise ValueError(
            f"{path} 는 DOP 네트워크가 아닙니다 "
            f"(자식 카테고리: {node.childTypeCategory().name()}). "
            f"/obj 아래의 dopnet 경로를 주세요. 예: /obj/rbd_sim"
        )
    return node


def require_dop_node(path: str) -> hou.DopNode:
    """dopnet 안의 DOP 노드 하나를 얻는다."""
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"list_children 으로 dopnet 안을 확인하세요."
        )
    if not isinstance(node, hou.DopNode):
        raise ValueError(
            f"{path} 는 DOP 노드가 아니라 {node.type().category().name()} 노드입니다. "
            f"dopnet 안의 노드 경로를 주세요."
        )
    return node


def require_source_object(path: str) -> hou.ObjNode:
    """시뮬에 넣을 원본 지오메트리 오브젝트(/obj 아래 geo)를 얻는다."""
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 오브젝트가 없습니다: {path}. "
            f"시뮬에 넣을 지오메트리는 /obj 아래 geo 노드여야 합니다. 예: /obj/falling_box"
        )
    if node.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError(
            f"{path} 안에는 SOP 이 없습니다 "
            f"(자식 카테고리: {node.childTypeCategory().name()}). "
            f"Geometry 오브젝트(/obj 아래 geo 노드) 경로를 주세요."
        )
    if node.displayNode() is None:
        raise ValueError(
            f"{path} 에 디스플레이 SOP 이 없어 시뮬에 넣을 지오메트리가 없습니다. "
            f"안에 지오메트리를 만들고 디스플레이 플래그를 켠 뒤 다시 부르세요."
        )
    return node


def require_sim_object(dopnet: hou.Node, name: str) -> hou.DopObject:
    """시뮬레이션 오브젝트를 이름으로 찾는다. 없으면 있는 이름을 알려 준다."""
    sim = dopnet.simulation()
    found = sim.findObject(name)
    if found is None:
        existing = [obj.name() for obj in sim.objects()]
        raise ValueError(
            f"{dopnet.path()} 의 시뮬에 {name!r} 오브젝트가 없습니다. "
            f"있는 것: {', '.join(existing) or '(없음 — 아직 쿡되지 않았거나 오브젝트가 없습니다)'}. "
            f"쿡이 안 됐다면 step_simulation 으로 한 프레임 진행시켜 보세요."
        )
    return found


def require_comment(comment: str) -> None:
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 노드가 무엇을 위한 것인지 영어로 적어 주세요. "
            "Falling box rigid body, 2kg 처럼 구체적으로."
        )


def set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def set_parms(node: hou.Node, parms: dict[str, Any]) -> dict[str, Any]:
    """값이 None 인 것은 건너뛴다. 벡터는 parmTuple 로 건다. 실제로 건 것을 돌려준다."""
    applied: dict[str, Any] = {}
    for name, value in parms.items():
        if value is None:
            continue
        parm = node.parm(name)
        if parm is not None:
            parm.set(value)
            applied[name] = value
            continue
        tuple_parm = node.parmTuple(name)
        if tuple_parm is None:
            raise ValueError(
                f"{node.type().name()} 에 파라미터 {name!r} 가 없습니다. "
                f"list_parms 로 이 노드의 파라미터 이름을 확인하세요."
            )
        tuple_parm.set(tuple(value))
        applied[name] = list(value)
    return applied


def set_menu(node: hou.Node, parm_name: str, token: str) -> None:
    """메뉴 파라미터를 토큰으로 건다. 토큰을 못 받는 메뉴는 인덱스로 다시 건다.

    File DOP 의 mode 처럼 메뉴가 달린 정수 파라미터는 토큰을 거부한다.
    """
    parm = node.parm(parm_name)
    if parm is None:
        raise ValueError(f"{node.type().name()} 에 파라미터 {parm_name!r} 가 없습니다.")
    items = parm.parmTemplate().menuItems()
    usable = [item for item in items if item != "_separator_"]
    if token not in usable:
        raise ValueError(
            f"{parm_name} 에 {token!r} 은 쓸 수 없습니다. "
            f"쓸 수 있는 값: {', '.join(usable)}"
        )
    try:
        parm.set(token)
    except TypeError:
        parm.set(items.index(token))


def create_in(
    parent: hou.Node, node_type: str, name: str | None, comment: str
) -> hou.DopNode:
    """dopnet 안에 노드를 만들고 코멘트를 단다."""
    try:
        node = parent.createNode(node_type, node_name=name)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent.path()} 안에 {node_type!r} 노드를 만들지 못했습니다. "
            f"list_node_types 로 DOP 카테고리에서 쓸 수 있는 타입인지 확인하세요. ({exc})"
        ) from exc
    set_comment(node, comment)
    return node


def described(node: hou.DopNode, role: str, parms: dict[str, Any] | None = None) -> dict[str, Any]:
    """만든 노드 하나를 설명으로. 셋업 툴이 블랙박스가 되지 않게 하는 장치다."""
    entry: dict[str, Any] = {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "role": role,
        "comment": node.comment(),
    }
    if parms:
        entry["key_parms"] = parms
    return entry


# --------------------------------------------------------------------------
# dopnet 구조 읽기
# --------------------------------------------------------------------------


def output_node(dopnet: hou.Node) -> hou.DopNode | None:
    """dopnet 의 디스플레이 노드. 시뮬 체인의 끝이다."""
    return dopnet.displayNode()


def chain_nodes(dopnet: hou.Node) -> list[hou.DopNode]:
    """디스플레이 노드로 실제로 흘러 들어가는 노드 전부.

    dopnet 안에 노드가 있어도 출력에 연결돼 있지 않으면 시뮬에 참여하지 않는다.
    검증 툴이 "만들었는데 안 이어졌다"를 잡는 근거가 이것이다.
    """
    out = output_node(dopnet)
    if out is None:
        return []
    seen: dict[str, hou.DopNode] = {out.path(): out}
    stack = [out]
    while stack:
        node = stack.pop()
        for upstream in node.inputs():
            if upstream is None or upstream.path() in seen:
                continue
            seen[upstream.path()] = upstream
            stack.append(upstream)
    return list(seen.values())


def solver_nodes(dopnet: hou.Node) -> list[hou.DopNode]:
    """체인에 연결된 솔버 노드들. 머지 순서대로 정렬해 돌려준다."""
    solvers = [
        node
        for node in chain_nodes(dopnet)
        if "solver" in node.type().name().split("::", 1)[0]
    ]
    return sorted(solvers, key=lambda n: _solver_rank(n.type().name()))


def find_solver(dopnet: hou.Node, solver_type: str) -> hou.DopNode | None:
    """체인에서 같은 타입의 솔버를 찾는다. 버전 접미사(::2.0)는 무시한다."""
    base = solver_type.split("::", 1)[0]
    for node in chain_nodes(dopnet):
        if node.type().name().split("::", 1)[0] == base:
            return node
    return None


def solver_merge(dopnet: hou.Node) -> hou.DopNode | None:
    """솔버들을 모으는 최상위 merge 노드. create_dopnet 이 만든 것이다."""
    for node in chain_nodes(dopnet):
        if node.type().name() == "merge" and node.name().endswith("solver_merge"):
            return node
    # 이름이 바뀌었을 수 있다. 출력에서 가장 가까운 merge 를 쓴다.
    for node in chain_nodes(dopnet):
        if node.type().name() == "merge":
            return node
    return None
