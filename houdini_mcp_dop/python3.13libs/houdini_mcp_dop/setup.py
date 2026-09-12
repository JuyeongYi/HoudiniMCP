"""시뮬레이션 네트워크를 짓는 툴.

기존 구현의 `setup_pyro_sim()` 같은 매크로는 노드 열 개를 만들고 경로 하나만
돌려준다. 무엇을 왜 만들었는지 모르면 모델은 고칠 수 없다. 여기서는 만든
노드마다 역할과 건 파라미터를 붙여 돌려주고, 다음에 무엇을 하면 되는지를
`next_steps` 로 준다.

조립은 `doptoolutils` 의 셸프 매크로를 부르지 않고 직접 한다. 실측해 보니
`genericConvertToDopObject` 는 `hou.shelves.runningTool()` 과 `hou.ui` 를 타서
MCP 문맥에서 rbd 계열과 flip 계열이 그대로 실패한다. 대신 doptoolutils 에서
**데이터**(오브젝트-솔버 짝짓기, 솔버 머지 순서)만 가져온다 — `_common.recipes`.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from ._common import (
    chain_nodes,
    create_in,
    described,
    find_solver,
    require_comment,
    require_dopnet,
    require_source_object,
    recipes,
    set_comment,
    set_parms,
    solver_merge,
)

# 시뮬 입력으로 쓰는 널 SOP 의 이름. 원본 SOP 을 직접 가리키지 않고 이 널을
# 가리키면, 나중에 사이에 수정 SOP 을 끼워 넣어도 시뮬이 따라온다.
TO_DOPS = "TO_DOPS"


def _to_dops_null(source: hou.ObjNode) -> tuple[hou.SopNode, bool]:
    """원본 오브젝트의 디스플레이 SOP 뒤에 시뮬 입력용 널을 둔다.

    이미 있으면 그대로 쓴다. 오브젝트 하나를 두 시뮬에 넣어도 널은 하나다.
    """
    existing = source.node(TO_DOPS)
    if existing is not None:
        return existing, False

    display = source.displayNode()
    null = source.createNode("null", TO_DOPS)
    null.setFirstInput(display)
    set_comment(null, "Geometry handed to the DOP network")
    null.setDisplayFlag(True)
    null.setRenderFlag(display.isRenderFlagSet())
    try:
        null.moveToGoodPosition()
    except hou.Error:
        pass
    return null, True


def _dop_import(source: hou.ObjNode, dop_object: hou.DopNode) -> hou.SopNode:
    """시뮬 결과를 원본 오브젝트로 되읽는 DOP Import SOP.

    `dopobjscreatedby` 표현식으로 이 DOP 노드가 만든 오브젝트만 가져온다.
    오브젝트 이름을 하드코딩하면 rbdpackedobject 처럼 여러 개를 만드는
    노드에서 깨진다.
    """
    node = source.createNode("dopimport", f"{dop_object.name()}_import")
    node.parm("doppath").set(dop_object.dopNetNode().path())
    node.parm("importstyle").set("fetch")
    node.parm("pointvels").set("instant")
    node.parm("addtoexistingvel").set(False)
    node.parm("adddopobjectpath").set(True)
    node.parm("objpattern").set(f'`dopobjscreatedby("{dop_object.path()}")`')
    set_comment(node, f"Read {dop_object.name()} back from the simulation")
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    try:
        node.moveToGoodPosition()
    except hou.Error:
        pass
    return node


def _wire_into_solver(
    dopnet: hou.Node, dop_object: hou.DopNode, solver: hou.DopNode, merge_objects: bool
) -> tuple[hou.DopNode | None, bool]:
    """오브젝트를 솔버에 잇는다. 여러 오브젝트를 합치는 솔버면 merge 를 거친다.

    (merge 노드 또는 None, 새로 만들었는지) 를 돌려준다.
    """
    if not merge_objects:
        solver.setFirstInput(dop_object)
        return None, False

    upstream = solver.inputs()
    merge = upstream[0] if upstream and upstream[0] is not None else None
    if merge is None or merge.type().name() != "merge":
        merge = create_in(
            dopnet,
            "merge",
            f"{solver.name()}_objects",
            f"Objects fed into {solver.name()}",
        )
        if upstream and upstream[0] is not None:
            merge.setNextInput(upstream[0])
        solver.setFirstInput(merge)
        merge.setNextInput(dop_object)
        return merge, True

    merge.setNextInput(dop_object)
    return merge, False


@tool()
@undoable("Create DOP network")
def create_dopnet(
    parent: str,
    name: str,
    comment: str,
    gravity: float = -9.81,
    start_frame: int | None = None,
    substeps: int | None = None,
    cache_size_mb: int | None = None,
) -> dict[str, Any]:
    """빈 DOP 네트워크를 만들고 중력·머지·출력을 이어 돌려준다.

    셸프의 "Create New Simulation" 이 하는 것과 같은 구조지만, 만든 노드마다
    역할을 붙여 돌려준다. `doptoolutils.createNewDopNetwork` 를 쓰지 않는 이유는
    그것이 `hou.ui` 를 타서 UI 없는 문맥에서 실패하기 때문이다(실측).

    구조는 이렇게 된다.

        <solver_merge>  ->  gravity  ->  output(display)

    솔버는 이 뒤에 `add_dop_object` 가 solver_merge 로 물린다.

    Args:
        parent: dopnet 을 담을 네트워크. 보통 /obj
        name: dopnet 이름. 무엇을 시뮬하는지 드러나게. 예: castle_collapse_sim
        comment: 이 시뮬이 무엇을 위한 것인지. 필수. 씬에 저장되므로 영어로.
        gravity: 중력 가속도 Y 성분. 0 이면 중력 노드를 만들지 않는다.
        start_frame: 시뮬 시작 프레임. 생략하면 dopnet 기본값(1).
        substeps: 프레임당 서브스텝. 생략하면 1. 관통이 생기면 올린다.
        cache_size_mb: 시뮬 캐시 상한(MB). 생략하면 기본값(5000).
    """
    require_comment(comment)
    container = hou.node(parent)
    if container is None:
        raise ValueError(
            f"그런 네트워크가 없습니다: {parent}. DOP 네트워크는 보통 /obj 아래에 만듭니다."
        )
    if container.childTypeCategory() != hou.objNodeTypeCategory():
        raise ValueError(
            f"{parent} 안에는 dopnet 을 만들 수 없습니다 "
            f"(자식 카테고리: {container.childTypeCategory().name()}). /obj 를 주세요."
        )

    dopnet = container.createNode("dopnet", node_name=name)
    set_comment(dopnet, comment)
    # 시뮬 컨테이너 자체는 뷰포트에 그릴 것이 없다. 결과는 dopimport 로 본다.
    dopnet.setDisplayFlag(False)
    applied = set_parms(
        dopnet,
        {
            "startframe": start_frame,
            "substep": substeps,
            "cachemaxsize": cache_size_mb,
        },
    )

    created: list[dict[str, Any]] = [
        described(dopnet, "Simulation container", applied or None)
    ]

    output = dopnet.displayNode() or dopnet.createNode("output", "sim_output")
    set_comment(output, "End of the simulation chain")
    merge = create_in(dopnet, "merge", "solver_merge", "Merges every solver")
    merge.parm("affectortype").set("mutual")
    created.append(
        described(merge, "Solver merge — every solver hangs off this", {"affectortype": "mutual"})
    )

    tail: hou.DopNode = merge
    if gravity:
        force = create_in(dopnet, "gravity", "gravity_force", f"Gravity {gravity} on Y")
        force.parmTuple("force").set((0.0, gravity, 0.0))
        # uniquedataname 을 꺼야 오브젝트마다 중력이 따로 붙지 않는다.
        force.parm("uniquedataname").set(0)
        force.setNextInput(merge)
        tail = force
        created.append(
            described(force, "Global gravity", {"force": [0.0, gravity, 0.0]})
        )

    output.setInput(0, tail)
    created.append(described(output, "Simulation output (display node)"))
    dopnet.layoutChildren()

    return {
        "path": dopnet.path(),
        "created": created,
        "chain": [node.path() for node in chain_nodes(dopnet)],
        "next_steps": [
            f"add_dop_object('{dopnet.path()}', '<source /obj geo>', 'rbdobject', ...) "
            f"로 시뮬할 지오메트리를 넣으세요",
            "충돌체는 object_type='staticobject' 로 넣습니다",
            f"validate_simulation('{dopnet.path()}') 로 빠진 것을 확인한 뒤 "
            f"test_simulation 으로 몇 프레임 돌려 보세요",
        ],
    }


@tool()
@undoable("Add DOP object")
def add_dop_object(
    dopnet: str,
    source_object: str,
    object_type: str,
    comment: str,
    name: str | None = None,
    solver_type: str | None = None,
    parms: dict[str, Any] | None = None,
    create_import: bool = True,
) -> dict[str, Any]:
    """/obj 의 지오메트리를 시뮬에 편입시키고, 만든 것을 전부 설명해 돌려준다.

    한 번에 이만큼 한다.

    1. 원본 오브젝트 안에 `TO_DOPS` 널을 두고 디스플레이 SOP 을 물린다.
       시뮬은 이 널을 가리키므로, 나중에 사이에 수정 SOP 을 끼워도 따라온다.
    2. dopnet 안에 DOP 오브젝트 노드를 만들고 `soppath` 를 그 널로 건다.
    3. 짝이 되는 솔버를 찾거나 만들어 잇는다. 이미 같은 솔버가 있고 그 솔버가
       오브젝트를 합치는 종류면(강체·정적·천 등) 기존 솔버의 merge 에 붙인다.
    4. 솔버를 dopnet 의 solver_merge 에 문다.
    5. 원본 오브젝트에 DOP Import SOP 을 만들어 결과를 되읽게 한다.

    오브젝트-솔버 짝짓기는 `doptoolutils.theDopObjectTypeDict` 에서 가져온다.
    거기에 없는 타입(popobject, vellumobject 등)은 이 팩의 표로 보충하고,
    둘 다 모르는 타입이면 `solver_type` 을 직접 줘야 한다.

    Args:
        dopnet: DOP 네트워크 경로. 예: /obj/castle_collapse_sim
        source_object: 시뮬에 넣을 /obj 아래 geo 노드. 예: /obj/falling_box
        object_type: DOP 오브젝트 타입. rbdobject(강체), staticobject(충돌체),
            rbdpackedobject(패킹된 조각들), clothobject::2.0(천),
            wireobject(와이어), sandobject(모래), smokeobject(스모크 컨테이너),
            popobject(파티클), vellumobject(벨럼) 등.
        comment: 이 오브젝트가 시뮬에서 무슨 역할인지. 필수. 영어로.
            예: "Tower blocks, active rigid bodies"
        name: DOP 노드 이름. 역할이 드러나게. 예: tower_blocks_rbd
        solver_type: 솔버를 직접 지정할 때만. 생략하면 표에서 고른다.
            예: bulletrbdsolver (rigidbodysolver 대신 불릿을 쓰고 싶을 때)
        parms: DOP 오브젝트 노드에 걸 파라미터. 예: {"divsize": 0.05}
        create_import: 원본 오브젝트에 DOP Import SOP 을 만들지. 정적 충돌체는
            시뮬 결과를 되읽을 필요가 없으므로 자동으로 꺼진다.
    """
    require_comment(comment)
    net = require_dopnet(dopnet)
    source = require_source_object(source_object)

    table = recipes()
    recipe = table.get(object_type)
    if recipe is None and solver_type is None:
        raise ValueError(
            f"{object_type!r} 에 어떤 솔버가 붙는지 모릅니다. "
            f"solver_type 을 함께 주거나, 아는 타입을 쓰세요: "
            f"{', '.join(sorted(table))}"
        )
    chosen_solver = solver_type or recipe["solver"]
    merge_objects = True if recipe is None else recipe["merge_objects"]
    role = "DOP object" if recipe is None else recipe["role"]

    created: list[dict[str, Any]] = []

    null, made_null = _to_dops_null(source)
    if made_null:
        created.append(described(null, "Geometry handed to the simulation"))

    dop_object = create_in(net, object_type, name, comment)
    is_passive = object_type in ("staticobject", "terrainobject")
    wanted = {
        "usetransform": 1,
        "soppath": null.path(),
        "objpath": source.path(),
        "active": 0 if is_passive else None,
    }
    # 오브젝트 타입마다 있는 파라미터가 다르다. 없는 것은 조용히 건너뛴다.
    applied = {
        key: value
        for key, value in wanted.items()
        if value is not None and dop_object.parm(key) is not None
    }
    set_parms(dop_object, applied)
    if parms:
        applied.update(set_parms(dop_object, parms))
    if "soppath" not in applied:
        # vellumobject 처럼 소스를 다른 경로로 받는 타입이다. 모델에게 알린다.
        applied["soppath"] = None
    created.append(described(dop_object, role, applied))

    solver = find_solver(net, chosen_solver)
    reused_solver = solver is not None
    if solver is None:
        solver = create_in(
            net,
            chosen_solver,
            f"{chosen_solver.split('::', 1)[0]}_solver",
            f"Solver for {object_type} objects",
        )
        created.append(described(solver, f"Solver driving {object_type}"))

    merge, made_merge = _wire_into_solver(net, dop_object, solver, merge_objects)
    if made_merge and merge is not None:
        created.append(described(merge, f"Collects objects for {solver.name()}"))

    top = solver_merge(net)
    if top is None:
        raise ValueError(
            f"{net.path()} 에 솔버를 모을 merge 노드가 없습니다. "
            f"create_dopnet 으로 만든 네트워크가 아니라면 merge 를 직접 만들어 "
            f"출력에 이은 뒤 다시 부르세요."
        )
    if solver.path() not in [n.path() for n in top.inputs() if n is not None]:
        top.setNextInput(solver)

    import_node = None
    if create_import and not is_passive:
        import_node = _dop_import(source, dop_object)
        created.append(described(import_node, "Simulation result read back into SOPs"))

    net.layoutChildren()

    next_steps = [
        f"validate_simulation('{net.path()}') 로 빠진 연결을 확인하세요",
        f"test_simulation('{net.path()}', 1, 10) 으로 저해상도 시험 주행을 하세요",
    ]
    if is_passive:
        next_steps.insert(0, "정적 오브젝트는 결과를 되읽을 것이 없어 DOP Import 를 만들지 않았습니다")
    if applied.get("soppath") is None:
        next_steps.insert(
            0,
            f"{object_type} 에는 soppath 파라미터가 없습니다. "
            f"list_parms 로 소스를 받는 파라미터를 확인해 직접 거세요",
        )
    if import_node is not None:
        next_steps.append(f"결과는 {import_node.path()} 에서 geometry_stats 로 봅니다")

    return {
        "dopnet": net.path(),
        "object": dop_object.path(),
        "solver": solver.path(),
        "solver_reused": reused_solver,
        "created": created,
        "chain": [node.path() for node in chain_nodes(net)],
        "next_steps": next_steps,
    }


@tool()
@undoable("Add DOP force")
def add_dop_force(
    dopnet: str,
    force_type: str,
    comment: str,
    name: str | None = None,
    parms: dict[str, Any] | None = None,
    affect_objects: str | None = None,
) -> dict[str, Any]:
    """시뮬 전체에 걸리는 힘을 체인 끝에 끼워 넣고 무엇이 바뀌었는지 돌려준다.

    힘 노드는 솔버 뒤(출력 쪽)에 놓여 모든 오브젝트에 데이터로 붙는다.
    `create_dopnet` 이 만든 중력이 놓이는 자리와 같은 곳이다.

    Args:
        dopnet: DOP 네트워크 경로.
        force_type: DOP 힘 노드 타입. gravity, windforce, drag, fan,
            pointforce, vortexforce, magnetforce, uniformforce 등.
        comment: 이 힘이 무엇을 하는지. 필수. 영어로.
            예: "Side wind pushing the smoke east"
        name: 노드 이름. 예: side_wind
        parms: 힘 노드 파라미터. 벡터는 성분 이름이 따로다 —
            windforce 는 velx/vely/velz, uniformforce 는 forcex/forcey/forcez.
            예: {"velx": 5.0}. 이름이 틀리면 무엇이 있는지 알려 준다.
        affect_objects: 이 힘을 받을 오브젝트 이름 패턴. 생략하면 전부.
            예: "tower_*"
    """
    require_comment(comment)
    net = require_dopnet(dopnet)

    output = net.displayNode()
    if output is None:
        raise ValueError(
            f"{net.path()} 에 출력 노드가 없습니다. "
            f"시뮬 체인의 끝(디스플레이 플래그가 켜진 노드)을 먼저 만드세요."
        )
    upstream = output.inputs()
    tail = upstream[0] if upstream and upstream[0] is not None else None
    if tail is None:
        raise ValueError(
            f"{output.path()} 에 입력이 연결돼 있지 않습니다. "
            f"먼저 add_dop_object 로 솔버를 이은 뒤 힘을 추가하세요."
        )

    force = create_in(net, force_type, name, comment)
    applied = set_parms(force, parms) if parms else {}
    if affect_objects is not None and force.parm("group") is not None:
        force.parm("group").set(affect_objects)
        applied["group"] = affect_objects
    if force.parm("uniquedataname") is not None:
        # 오브젝트마다 같은 이름의 힘 데이터를 하나씩만 붙인다.
        force.parm("uniquedataname").set(0)

    force.setNextInput(tail)
    output.setInput(0, force)
    net.layoutChildren()

    return {
        "dopnet": net.path(),
        "created": [described(force, f"{force_type} applied to the whole simulation", applied)],
        "inserted_between": [tail.path(), output.path()],
        "chain": [node.path() for node in chain_nodes(net)],
        "next_steps": [
            f"list_parms('{force.path()}') 로 세기를 조절할 파라미터를 확인하세요",
            f"test_simulation('{net.path()}', 1, 10) 으로 힘이 먹었는지 확인하세요",
        ],
    }
