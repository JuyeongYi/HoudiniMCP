"""시뮬레이션 안을 들여다보는 툴 — 오브젝트, 릴레이션십, 솔버 구성.

`hou.DopObject` 는 노드가 아니라 **쿡된 시뮬의 상태**다. 그래서 네트워크를 읽는
base 의 `list_children` 으로는 보이지 않는다. 여기 툴은 전부 시뮬을 쿡한 뒤의
결과를 읽는다 — 아직 쿡이 안 됐으면 오브젝트가 0개로 나오는 것이 정상이고,
`step_simulation` 으로 한 프레임 진행시키면 나타난다.

기존 구현의 `get_dop_object` / `list_dop_objects` 는 이름과 경로만 돌려준다.
여기서는 월드 위치, 요소 수, 메모리, 영향 관계, 가진 필드까지 함께 준다.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from ._common import (
    chain_nodes,
    require_dop_node,
    require_dopnet,
    require_sim_object,
    solver_nodes,
)
from ._state import (
    field_names,
    memory_of,
    object_summary,
    record_dict,
)


def _empty_hint(dopnet: hou.Node) -> str:
    return (
        f"{dopnet.path()} 의 시뮬에 오브젝트가 없습니다. "
        f"아직 쿡되지 않았다면 step_simulation 으로 한 프레임 진행시키고, "
        f"오브젝트를 넣지 않았다면 add_dop_object 로 넣으세요."
    )


@tool()
def list_dop_objects(dopnet: str, pattern: str = "*") -> dict[str, Any]:
    """쿡된 시뮬 안의 오브젝트들과 각각의 상태.

    오브젝트마다 월드 위치, 점·프림 수, 메모리, 누구에게 영향을 받는지,
    어떤 필드를 갖고 있는지를 돌려준다. `hou.DopObject.geometry()` 는 오브젝트
    공간이라 좌표를 그대로 쓰면 안 된다 — 월드 위치는 transform 에서 뽑는다.

    Args:
        dopnet: DOP 네트워크 경로. 예: /obj/castle_collapse_sim
        pattern: 오브젝트 이름 패턴. 예: "tower_*". 기본은 전부.
    """
    net = require_dopnet(dopnet)
    sim = net.simulation()
    objects = sim.findAllObjects(pattern) if pattern != "*" else sim.objects()

    summaries = [object_summary(obj) for obj in objects]
    result: dict[str, Any] = {
        "dopnet": net.path(),
        "frame": hou.frame(),
        "sim_time": round(float(sim.time()), 6),
        "count": len(summaries),
        "total_memory_bytes": int(sim.memoryUsage()),
        "objects": summaries,
    }
    if not summaries:
        result["hint"] = _empty_hint(net)
    return result


@tool()
def dop_object_info(dopnet: str, name: str) -> dict[str, Any]:
    """시뮬 오브젝트 하나를 깊게. 레코드, 서브데이터, 만든 노드, 솔버.

    `records`(Basic / Options / 관계)와 `subData`(Position, Forces, 필드 등)를
    함께 준다. 서브데이터는 이름과 종류만 준다 — 필드 값은
    `field_stats` 로 따로 본다.

    Args:
        dopnet: DOP 네트워크 경로.
        name: 오브젝트 이름. list_dop_objects 로 확인한 이름.
    """
    net = require_dopnet(dopnet)
    obj = require_sim_object(net, name)

    records: dict[str, Any] = {}
    for record_type in obj.recordTypes():
        rows = obj.records(record_type)
        records[record_type] = [record_dict(row) for row in rows]

    sub_data = []
    for key, data in sorted(obj.subData().items()):
        sub_data.append(
            {
                "name": key,
                "data_type": data.dataType(),
                "memory_bytes": memory_of(data),
            }
        )

    creator_path = str(record_dict(obj.record("Basic")).get("creator", ""))
    creator_node = hou.node(creator_path.rsplit("/", 1)[0]) if creator_path else None

    return {
        "dopnet": net.path(),
        "frame": hou.frame(),
        **object_summary(obj),
        "records": records,
        "sub_data": sub_data,
        "fields": field_names(obj),
        "creator_node": creator_node.path() if creator_node is not None else creator_path,
        "next_steps": [
            f"field_stats('{net.path()}', '{name}', '<field>') 로 필드 값을 봅니다",
            f"list_dop_fields('{net.path()}', '{name}') 로 필드 목록과 해상도를 봅니다",
        ],
    }


@tool()
def dop_relationships(dopnet: str) -> dict[str, Any]:
    """시뮬의 릴레이션십 — 무엇이 무엇에 영향을 주고 어떤 컨스트레인트가 있는지.

    솔버가 만드는 관계(멀티솔버 연결, 초기 겹침 검사)와 사용자가 건 관계
    (핀·글루·어태치)가 함께 나온다. 강체가 서로 통과해 버릴 때 affector 관계가
    실제로 걸려 있는지 여기서 확인한다.

    Args:
        dopnet: DOP 네트워크 경로.
    """
    net = require_dopnet(dopnet)
    sim = net.simulation()

    relationships = []
    for rel in sim.relationships():
        options = record_dict(rel.options())
        relationships.append(
            {
                "name": rel.name(),
                "data_type": rel.dataType(),
                "options": options,
                "memory_bytes": memory_of(rel),
            }
        )

    affectors = {}
    for obj in sim.objects():
        options = record_dict(obj.options())
        affectors[obj.name()] = {
            "affectors": str(options.get("affectors", "")).split(),
            "groups": str(options.get("groups", "")).split(),
        }

    result: dict[str, Any] = {
        "dopnet": net.path(),
        "frame": hou.frame(),
        "count": len(relationships),
        "relationships": relationships,
        "object_affectors": affectors,
    }
    if not relationships and not affectors:
        result["hint"] = _empty_hint(net)
    return result


@tool()
def simulation_info(dopnet: str) -> dict[str, Any]:
    """시뮬 구성 전체 — 솔버, 타임스텝, 서브스텝, 캐시 설정, 현재 상태.

    돌리기 전에 "지금 이 시뮬이 어떤 설정인가"를 한 번에 본다. 솔버는 머지
    순서대로 준다(정적 -> 강체 -> 천 -> 파티클 -> 유체). 이 순서가 틀리면
    상호작용이 어긋난다.

    Args:
        dopnet: DOP 네트워크 경로.
    """
    net = require_dopnet(dopnet)
    sim = net.simulation()

    solvers = [
        {
            "path": node.path(),
            "type": node.type().name(),
            "comment": node.comment(),
            "bypassed": node.isBypassed(),
            "inputs": [n.path() if n else None for n in node.inputs()],
        }
        for node in solver_nodes(net)
    ]

    timestep = float(net.evalParm("timestep"))
    substeps = int(net.evalParm("substep"))
    fps = hou.fps()

    unconnected = [
        node.path()
        for node in net.children()
        if isinstance(node, hou.DopNode)
        and node.path() not in {n.path() for n in chain_nodes(net)}
    ]

    return {
        "dopnet": net.path(),
        "comment": net.comment(),
        "frame": hou.frame(),
        "sim_time": round(float(sim.time()), 6),
        "sim_timestep": round(float(sim.timestep()), 8),
        "object_count": len(sim.objects()),
        "memory_bytes": int(sim.memoryUsage()),
        "timing": {
            "start_frame": int(net.evalParm("startframe")),
            "timestep": timestep,
            "substeps": substeps,
            "effective_step": round(timestep / max(substeps, 1), 8),
            "time_scale": float(net.evalParm("timescale")),
            "fps": fps,
            "playbar_range": [int(v) for v in hou.playbar.frameRange()],
        },
        "cache": {
            "enabled": bool(net.evalParm("cacheenabled")),
            "max_size_mb": int(net.evalParm("cachemaxsize")),
            "to_disk": bool(net.evalParm("cachetodisk")),
            "cache_substeps": bool(net.evalParm("cachesubsteps")),
            "compressed": bool(net.evalParm("compresssims")),
        },
        "solvers": solvers,
        "output_node": net.displayNode().path() if net.displayNode() else None,
        "unconnected_nodes": unconnected,
        "next_steps": [
            f"validate_simulation('{net.path()}') 로 빠진 것을 찾습니다",
            "관통이 생기면 substeps 를 올립니다 (set_parms 로 dopnet 의 substep)",
        ],
    }


@tool()
def dop_node_info(path: str) -> dict[str, Any]:
    """dopnet 안의 DOP 노드 하나가 실제로 시뮬에 참여하는지와 그 연결.

    노드를 만들었는데 출력 체인에 안 이어져 있으면 시뮬에 아무 영향이 없다.
    네트워크 뷰에서는 보이므로 놓치기 쉬운 실패다. base 의 `node_info` 는
    연결만 알려 주고 "체인에 있는가"는 알려 주지 않는다.

    Args:
        path: DOP 노드 경로. 예: /obj/castle_collapse_sim/rbd_solver
    """
    node = require_dop_node(path)
    net = node.dopNetNode()
    in_chain = node.path() in {n.path() for n in chain_nodes(net)}

    result = {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "dopnet": net.path(),
        "in_solve_chain": in_chain,
        "bypassed": node.isBypassed(),
        "inputs": [
            {"index": i, "path": n.path() if n else None, "label": label}
            for i, (n, label) in enumerate(zip(node.inputs(), node.inputLabels()))
        ],
        "outputs": [n.path() for n in node.outputs()],
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }
    if not in_chain:
        result["hint"] = (
            f"{node.path()} 는 {net.displayNode().path() if net.displayNode() else '출력'} "
            f"으로 이어지지 않아 시뮬에 참여하지 않습니다. "
            f"connect_nodes 로 체인에 물리세요."
        )
    return result
