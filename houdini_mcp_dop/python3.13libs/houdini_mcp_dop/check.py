"""돌리기 전에 무엇이 빠졌는지 찾는 툴.

시뮬은 한 번 돌리는 데 몇 분에서 몇 시간이 걸린다. 소스가 안 붙어 있거나
충돌체가 빠진 것을 20분 뒤에 아는 것이 이 팩이 막으려는 일이다.

여기서 보는 것은 **쿡 없이 알 수 있는 것**뿐이다. 네트워크 연결, 파라미터가
가리키는 경로, 프레임 범위, 노드 에러. 실제로 터지는지는 `test_simulation`
이 저해상도로 돌려 본다. 둘을 이 순서로 쓰는 것이 이 팩이 권하는 흐름이다.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from ._common import (
    chain_nodes,
    require_dopnet,
    solver_nodes,
)

# 소스 지오메트리를 가리키는 파라미터 이름들. 오브젝트 타입마다 다르다.
_SOURCE_PARMS = ("soppath", "geopath", "source_path", "objpath")

# 충돌체 없이 돌아가도 이상하지 않은 솔버. 경고를 내지 않는다.
# 가스 계열(스모크·파이로·유체 컨테이너)은 컨테이너 자체가 경계라 바닥이 없어도
# 된다. 강체·천·모래는 부딪힐 것이 없으면 계속 떨어지므로 경고를 낸다.
_NO_COLLIDER_NEEDED = (
    "staticsolver",
    "popsolver",
    "ripplesolver",
    "filamentsolver",
    "smokesolver",
    "pyrosolver",
    "fluidsolver",
)


def _issue(level: str, message: str, fix: str, where: str | None = None) -> dict[str, Any]:
    entry = {"level": level, "message": message, "fix": fix}
    if where:
        entry["node"] = where
    return entry


def _check_chain(net: hou.Node, chain: list[hou.DopNode]) -> list[dict[str, Any]]:
    """출력까지 이어져 있는가. 안 이어진 노드는 시뮬에 참여하지 않는다."""
    issues: list[dict[str, Any]] = []
    if net.displayNode() is None:
        issues.append(
            _issue(
                "error",
                "출력 노드가 없습니다. 시뮬 체인의 끝이 없으면 아무것도 풀리지 않습니다.",
                f"create_node('{net.path()}', 'output', ...) 로 만들고 디스플레이 플래그를 켜세요.",
            )
        )
        return issues

    in_chain = {node.path() for node in chain}
    orphans = [
        node
        for node in net.children()
        if isinstance(node, hou.DopNode) and node.path() not in in_chain
    ]
    for node in orphans:
        issues.append(
            _issue(
                "warning",
                f"{node.name()} ({node.type().name()}) 가 출력으로 이어지지 않아 "
                "시뮬에 참여하지 않습니다.",
                "connect_nodes 로 체인에 물리거나, 필요 없으면 delete_node 하세요.",
                node.path(),
            )
        )
    return issues


def _check_solvers(net: hou.Node, chain: list[hou.DopNode]) -> tuple[list[dict[str, Any]], list[hou.DopNode]]:
    solvers = solver_nodes(net)
    issues: list[dict[str, Any]] = []
    if not solvers:
        issues.append(
            _issue(
                "error",
                "체인에 솔버가 하나도 없습니다. 오브젝트만 있으면 아무 일도 일어나지 않습니다.",
                f"add_dop_object('{net.path()}', '<source>', 'rbdobject', ...) 로 "
                "오브젝트와 솔버를 함께 넣으세요.",
            )
        )
    for solver in solvers:
        if solver.isBypassed():
            issues.append(
                _issue(
                    "error",
                    f"{solver.name()} 이 바이패스돼 있습니다. 이 솔버는 아무것도 풀지 않습니다.",
                    "set_flags 로 bypass 를 끄세요.",
                    solver.path(),
                )
            )
        if not [n for n in solver.inputs() if n is not None]:
            issues.append(
                _issue(
                    "error",
                    f"{solver.name()} 에 오브젝트가 하나도 연결돼 있지 않습니다.",
                    "add_dop_object 로 오브젝트를 넣거나 connect_nodes 로 이으세요.",
                    solver.path(),
                )
            )
    return issues, solvers


def _check_sources(chain: list[hou.DopNode]) -> list[dict[str, Any]]:
    """소스 경로 파라미터가 실제 노드를 가리키고 그 노드가 비어 있지 않은가."""
    issues: list[dict[str, Any]] = []
    for node in chain:
        for parm_name in _SOURCE_PARMS:
            parm = node.parm(parm_name)
            if parm is None:
                continue
            value = parm.evalAsString().strip()
            if not value:
                if parm_name in ("soppath", "geopath"):
                    issues.append(
                        _issue(
                            "warning",
                            f"{node.name()} 의 {parm_name} 가 비어 있습니다. "
                            "이 오브젝트는 지오메트리 없이 시작합니다.",
                            "set_parms 로 소스 SOP 경로를 거세요.",
                            node.path(),
                        )
                    )
                continue
            target = hou.node(value)
            if target is None:
                issues.append(
                    _issue(
                        "error",
                        f"{node.name()} 의 {parm_name} 가 없는 노드를 가리킵니다: {value}",
                        "set_parms 로 올바른 경로를 거세요. find_nodes 로 찾을 수 있습니다.",
                        node.path(),
                    )
                )
                continue
            issues.extend(_check_source_geometry(node, parm_name, target))
    return issues


def _check_source_geometry(node: hou.DopNode, parm_name: str, target: hou.Node) -> list[dict[str, Any]]:
    """소스 SOP 을 쿡해서 실제로 지오메트리가 나오는지 본다."""
    if not isinstance(target, hou.SopNode):
        return []
    try:
        target.cook()
    except hou.Error as exc:
        return [
            _issue(
                "error",
                f"{node.name()} 의 소스 {target.path()} 가 쿡되지 않습니다: {exc}",
                "소스 SOP 의 에러를 먼저 고치세요. node_errors 로 볼 수 있습니다.",
                node.path(),
            )
        ]
    geo = target.geometry()
    if geo is None or (geo.pointCount() == 0 and geo.primCount() == 0):
        return [
            _issue(
                "error",
                f"{node.name()} 의 소스 {target.path()} 가 비어 있습니다 "
                "(점 0, 프림 0). 시뮬에 들어갈 것이 없습니다.",
                "소스 SOP 이 실제로 지오메트리를 내는지 geometry_stats 로 확인하세요.",
                node.path(),
            )
        ]
    return []


def _check_colliders(net: hou.Node, solvers: list[hou.DopNode], chain: list[hou.DopNode]) -> list[dict[str, Any]]:
    """충돌체가 필요해 보이는데 없는가. 강체가 바닥 없이 떨어지는 일이 흔하다."""
    needs = [
        solver
        for solver in solvers
        if solver.type().name().split("::", 1)[0] not in _NO_COLLIDER_NEEDED
    ]
    if not needs:
        return []
    has_collider = any(
        node.type().name() in ("staticobject", "terrainobject") for node in chain
    )
    if has_collider:
        return []
    return [
        _issue(
            "warning",
            "충돌체(staticobject)가 없습니다. "
            f"{', '.join(s.name() for s in needs)} 가 부딪힐 것이 없어 계속 떨어집니다.",
            f"add_dop_object('{net.path()}', '<ground /obj geo>', 'staticobject', ...) "
            "로 바닥을 넣으세요.",
        )
    ]


def _check_timing(net: hou.Node, solvers: list[hou.DopNode]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    start = int(net.evalParm("startframe"))
    playbar = [int(v) for v in hou.playbar.frameRange()]
    if start < playbar[0]:
        issues.append(
            _issue(
                "warning",
                f"시뮬 시작 프레임({start})이 플레이바 시작({playbar[0]})보다 앞섭니다. "
                "플레이바를 스크럽해도 첫 프레임을 볼 수 없습니다.",
                f"set_parms('{net.path()}', {{'startframe': {playbar[0]}}}) 또는 "
                "set_frame_range 로 맞추세요.",
            )
        )
    substeps = int(net.evalParm("substep"))
    if substeps <= 1 and any(
        "rigidbody" in s.type().name() or "bullet" in s.type().name() for s in solvers
    ):
        issues.append(
            _issue(
                "info",
                "서브스텝이 1입니다. 빠르게 움직이는 강체가 얇은 충돌체를 통과할 수 있습니다.",
                f"관통이 보이면 set_parms('{net.path()}', {{'substep': 2}}) 로 올리세요.",
            )
        )
    return issues


def _check_node_messages(chain: list[hou.DopNode]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for node in chain:
        for text in node.errors():
            issues.append(
                _issue("error", f"{node.name()}: {text}", "노드 에러를 고친 뒤 다시 돌리세요.", node.path())
            )
        for text in node.warnings():
            issues.append(
                _issue("warning", f"{node.name()}: {text}", "경고를 확인하세요.", node.path())
            )
    return issues


@tool()
def validate_simulation(dopnet: str) -> dict[str, Any]:
    """돌리기 전에 시뮬 셋업을 점검하고, 무엇이 빠졌고 어떻게 고치는지 돌려준다.

    쿡 없이 알 수 있는 것만 본다.

    - 출력 노드가 있는가, 체인에 안 이어진 노드가 있는가
    - 솔버가 있는가, 바이패스돼 있지 않은가, 오브젝트가 물려 있는가
    - 소스 경로 파라미터가 실제 노드를 가리키는가, 그 노드가 비어 있지 않은가
    - 충돌체가 필요해 보이는데 없는가
    - 시작 프레임이 플레이바와 맞는가, 서브스텝이 충분한가
    - 체인의 노드에 에러·경고가 붙어 있는가

    실제로 터지는지는 여기서 알 수 없다. 이걸 통과한 뒤
    `test_simulation` 으로 저해상도 몇 프레임을 돌려 보는 것이 이 팩이 권하는
    순서다.

    Args:
        dopnet: DOP 네트워크 경로.
    """
    net = require_dopnet(dopnet)
    chain = chain_nodes(net)

    issues: list[dict[str, Any]] = []
    issues.extend(_check_chain(net, chain))
    solver_issues, solvers = _check_solvers(net, chain)
    issues.extend(solver_issues)
    issues.extend(_check_sources(chain))
    issues.extend(_check_colliders(net, solvers, chain))
    issues.extend(_check_timing(net, solvers))
    issues.extend(_check_node_messages(chain))

    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]
    notes = [i for i in issues if i["level"] == "info"]

    objects_in_chain = [
        {"path": node.path(), "type": node.type().name(), "comment": node.comment()}
        for node in chain
        if "object" in node.type().name()
    ]

    next_steps: list[str] = []
    if errors:
        next_steps.append("errors 를 먼저 고치세요. 지금 돌리면 아무것도 나오지 않습니다.")
    elif warnings:
        next_steps.append("warnings 를 확인한 뒤 test_simulation 으로 시험 주행하세요.")
    else:
        next_steps.append(
            f"셋업에 빠진 것이 없습니다. test_simulation('{net.path()}', 1, 10) 으로 "
            "저해상도 시험 주행을 하세요."
        )

    return {
        "dopnet": net.path(),
        "ok": not errors,
        "counts": {"errors": len(errors), "warnings": len(warnings), "info": len(notes)},
        "errors": errors,
        "warnings": warnings,
        "info": notes,
        "solvers": [{"path": s.path(), "type": s.type().name()} for s in solvers],
        "objects": objects_in_chain,
        "chain_length": len(chain),
        "next_steps": next_steps,
    }
