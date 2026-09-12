"""APEX 리그 그래프를 읽는다.

Houdini 20 부터 리깅의 중심은 APEX 그래프다. 조사한 기존 MCP 구현 다섯 중
**어느 것도 apex 를 건드리지 않는다** — 전부 KineFX SOP 노드를 놓는 수준에
머문다. 이 모듈이 이 팩의 차별점이다.

실측으로 확인한 것 두 가지가 여기의 전제다.

1. **APEX 그래프는 지오메트리다.** 점 하나가 그래프 노드 하나고, `callback`,
   `name`, `parms`, `tags`, `properties` 점 어트리뷰트에 내용이 들어 있다.
   `apex.Graph().loadFromGeometry(geo)` 가 그것을 객체로 읽는다.
2. **그래프를 코드로 되돌릴 수 있다.** `apex.graphscript.GraphDecompiler` 가
   그래프를 APEX 스크립트 텍스트로 디컴파일한다. 노드·와이어를 하나씩 나열하는
   것보다 모델이 훨씬 잘 읽는다 — `apex_rig_script` 가 그것이다.

그리고 `apex.callbackRegistry()` 에는 콜백이 **2,286개** 있다. 시그니처와 파라미터
기본값까지 질의할 수 있어서, 리그를 짜기 전에 무엇을 쓸 수 있는지 찾아볼 수 있다.
"""

from __future__ import annotations

from typing import Any

import apex
import apex.graphscript
import hou

from houdini_mcp import tool, undoable

from ._common import (
    build,
    geometry_at,
    geometry_of,
    node_brief,
    require_comment,
    require_sop,
)

GRAPH_ATTRIBS = ("callback", "name", "parms")
"""APEX 그래프 지오메트리임을 알아보는 점 어트리뷰트. 셋 다 있어야 한다."""

MAX_NODES = 200
"""한 번에 돌려줄 그래프 노드 수 상한."""

MAX_CALLBACKS = 200
"""한 번에 돌려줄 콜백 수 상한. 전체는 2,286개라 그대로 보낼 수 없다."""

MAX_SCRIPT_CHARS = 60000
"""디컴파일 결과의 길이 상한. 큰 리그는 노드 패턴으로 좁혀서 본다."""


# --------------------------------------------------------------------------
# 그래프 읽기
# --------------------------------------------------------------------------


def _load_graph(path: str) -> tuple[hou.SopNode, hou.Geometry, apex.Graph]:
    """SOP 이 내는 지오메트리를 APEX 그래프로 읽는다."""
    node, geo = geometry_at(path)
    missing = [name for name in GRAPH_ATTRIBS if geo.findPointAttrib(name) is None]
    if missing:
        existing = ", ".join(a.name() for a in geo.pointAttribs()) or "(없음)"
        raise ValueError(
            f"{path} 는 APEX 그래프를 내지 않습니다. 그래프 지오메트리에 있어야 할 "
            f"점 어트리뷰트 {', '.join(missing)} 가 없습니다. 있는 것: {existing}. "
            f"apex::graph, apex::buildfkgraph, apex::autorigcomponent 같은 노드의 "
            f"출력을 주거나, build_fk_rig 로 먼저 그래프를 만드세요."
        )

    graph = apex.Graph()
    if not graph.loadFromGeometry(geo):
        raise ValueError(
            f"{path} 의 지오메트리를 APEX 그래프로 읽지 못했습니다. 그래프가 손상됐거나 "
            f"버전이 맞지 않습니다. 상류 노드의 에러를 node_errors 로 확인하세요."
        )
    return node, geo, graph


def _jsonify(value: Any) -> Any:
    """APEX/HOM 값을 JSON 으로 나갈 수 있게 바꾼다.

    파라미터에는 `hou.Matrix4`, `hou.Vector3`, `apex.Dict` 가 섞여 들어온다.
    """
    if isinstance(value, (hou.Matrix4, hou.Matrix3, hou.Matrix2)):
        return [[float(v) for v in row] for row in value.asTupleOfTuples()]
    if isinstance(value, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return [float(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return {str(k): _jsonify(v) for k, v in dict(value).items()}
    except (TypeError, ValueError):
        return str(value)


def _node_entry(graph: apex.Graph, node_id: int, with_parms: bool) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": int(node_id),
        "name": graph.nodeName(node_id),
        "callback": graph.callbackName(node_id),
        "path": graph.nodePath(node_id),
        "tags": [str(t) for t in graph.nodeTags(node_id)],
    }
    if with_parms:
        entry["parms"] = _jsonify(graph.getNodeParms(node_id))
        entry["inputs"] = [
            graph.portName(p) for p in graph.getInputPorts(node_id)
        ]
        entry["outputs"] = [
            graph.portName(p) for p in graph.getOutputPorts(node_id)
        ]
    return entry


@tool()
def apex_graph_info(path: str) -> dict[str, Any]:
    """APEX 리그 그래프의 구조를 요약한다 — 노드·와이어·포트 수, 콜백 분포, 에러.

    노드를 하나씩 나열하지 않는다. 그래프가 무엇으로 이루어져 있는지, 어디가
    잘못됐는지를 먼저 본다. 노드 목록은 apex_graph_nodes 로, 내용 전체는
    apex_rig_script 로 본다.

    Args:
        path: APEX 그래프를 내보내는 SOP 노드 경로.
    """
    node, geo, graph = _load_graph(path)
    node_ids = list(graph.allNodes())

    callbacks: dict[str, int] = {}
    for node_id in node_ids:
        name = graph.callbackName(node_id)
        callbacks[name] = callbacks.get(name, 0) + 1

    return {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "graph_name": graph.name(),
        "stat": {str(k): int(v) for k, v in graph.stat().items()},
        "nodes": len(node_ids),
        "callbacks": dict(sorted(callbacks.items(), key=lambda kv: -kv[1])),
        "graph_inputs": [graph.portName(p) for p in graph.inputPorts()],
        "graph_outputs": [graph.portName(p) for p in graph.outputPorts()],
        "parameters": _jsonify(graph.parameters()),
        "errors": list(graph.errors()),
        "warnings": list(graph.warnings()),
        "node_warnings": list(node.warnings()),
        "geometry_points": int(geo.pointCount()),
    }


@tool()
def apex_graph_nodes(
    path: str, pattern: str = "*", limit: int = 50, parms: bool = True
) -> dict[str, Any]:
    """APEX 그래프의 노드를 콜백·태그·파라미터와 함께 나열한다.

    이름 패턴으로 좁힐 수 있다. 리그에서 특정 조인트나 컨트롤을 찾을 때 쓴다.

    Args:
        path: APEX 그래프를 내보내는 SOP 노드 경로.
        pattern: 노드 이름 패턴. APEX 매칭 문법을 그대로 쓴다. 예: arm_*, *ik*
        limit: 돌려줄 노드 수 상한. 최대 200.
        parms: 파라미터와 포트 이름까지 함께 줄지.
    """
    node, _, graph = _load_graph(path)
    limit = max(1, min(int(limit), MAX_NODES))

    if pattern in ("", "*"):
        matched = list(graph.allNodes())
    else:
        matched = list(graph.matchNodes(pattern))

    return {
        "path": node.path(),
        "comment": node.comment(),
        "pattern": pattern,
        "total": len(list(graph.allNodes())),
        "matched": len(matched),
        "returned": min(len(matched), limit),
        "truncated": len(matched) > limit,
        "nodes": [_node_entry(graph, i, parms) for i in matched[:limit]],
    }


@tool()
def apex_rig_script(path: str) -> dict[str, Any]:
    """APEX 그래프를 APEX 스크립트 코드로 디컴파일해서 돌려준다.

    이 팩에서 가장 값어치 있는 조회다. 리그 그래프를 노드 목록으로 받으면 무엇을
    하는 리그인지 알 수 없지만, 코드로 받으면 바로 읽힌다. 조인트가 어떻게
    이어져 있고 어떤 콜백이 무슨 값으로 불리는지가 한 화면에 들어온다.

        root_xform, root_localxform = TransformObject(restlocal=Matrix4(...), __name='root')
        mid_xform, mid_localxform = TransformObject(parent=root_xform, ...)

    Args:
        path: APEX 그래프를 내보내는 SOP 노드 경로.
    """
    node, geo, graph = _load_graph(path)
    try:
        decompiler = apex.graphscript.GraphDecompiler(geo=geo)
        code = decompiler.generateCode()
    except Exception as exc:  # 디컴파일러는 별별 예외를 낸다
        raise ValueError(
            f"{path} 의 그래프를 코드로 되돌리지 못했습니다: {type(exc).__name__}: {exc} "
            f"apex_graph_nodes 로 노드를 직접 나열해서 보세요."
        ) from exc

    text = code if isinstance(code, str) else str(code)
    truncated = len(text) > MAX_SCRIPT_CHARS
    return {
        "path": node.path(),
        "comment": node.comment(),
        "graph_name": graph.name(),
        "nodes": len(list(graph.allNodes())),
        "characters": len(text),
        "truncated": truncated,
        "script": text[:MAX_SCRIPT_CHARS],
        "errors": list(graph.errors()),
    }


# --------------------------------------------------------------------------
# 콜백 레지스트리
# --------------------------------------------------------------------------


@tool()
def apex_callbacks(
    pattern: str = "*", limit: int = 50, include_hidden: bool = False
) -> dict[str, Any]:
    """APEX 콜백 레지스트리를 검색한다. 리그 그래프에서 쓸 수 있는 연산 목록이다.

    Houdini 22.0 에는 콜백이 2,286개 등록돼 있다. 무엇을 쓸 수 있는지 모르면
    리그를 짤 수 없으므로, 패턴으로 찾아 이름을 먼저 고르고 apex_callback_info 로
    시그니처를 본다.

    Args:
        pattern: 이름 패턴. 예: *ik*, fbik::*, Transform*
        limit: 돌려줄 개수 상한. 최대 200.
        include_hidden: 내부용으로 숨겨진 콜백까지 포함할지.
    """
    registry = apex.callbackRegistry()
    limit = max(1, min(int(limit), MAX_CALLBACKS))

    names = [str(n) for n in registry.findMatchingNames(pattern)]
    if not include_hidden:
        names = [n for n in names if not registry.getIsHidden(n)]

    return {
        "pattern": pattern,
        "total_registered": len(registry.callbackDefinitions()),
        "subgraphs": len(registry.subGraphNames()),
        "matched": len(names),
        "returned": min(len(names), limit),
        "truncated": len(names) > limit,
        "callbacks": [
            {
                "name": name,
                "hidden": bool(registry.getIsHidden(name)),
                "min_version": registry.getMinProductVersion(name) or None,
            }
            for name in names[:limit]
        ],
    }


@tool()
def apex_callback_info(name: str) -> dict[str, Any]:
    """APEX 콜백 하나의 시그니처 — 입력·출력 이름과 타입, 파라미터 기본값.

    Args:
        name: 콜백 이름. apex_callbacks 로 찾은 이름을 그대로 준다.
    """
    registry = apex.callbackRegistry()
    if name not in set(registry.callbackDefinitions()):
        close = [str(n) for n in registry.findMatchingNames(f"*{name}*")][:10]
        hint = ", ".join(close) if close else "(비슷한 이름 없음)"
        raise ValueError(
            f"등록된 APEX 콜백에 {name!r} 가 없습니다. 비슷한 이름: {hint}. "
            f"apex_callbacks 로 패턴 검색을 먼저 하세요."
        )

    signature = registry.getSignature(name)
    return {
        "name": name,
        "hidden": bool(registry.getIsHidden(name)),
        "min_version": registry.getMinProductVersion(name) or None,
        "overloads": [str(n) for n in registry.getNamesInPrecedenceOrder(name)],
        "inputs": [_parm_entry(p) for p in signature.inputs()],
        "outputs": [_parm_entry(p) for p in signature.outputs()],
        "parm_defaults": _jsonify(registry.getParmDefaults(name)),
    }


def _parm_entry(parm: Any) -> dict[str, Any]:
    """APEX_Parm 을 이름/타입으로 푼다.

    `<APEX_Parm 'restlocal' Matrix4>` 처럼 repr 만 쓸 만한 객체라, 접근자가 있으면
    쓰고 없으면 repr 을 갈라 쓴다.
    """
    name = getattr(parm, "name", None)
    type_name = getattr(parm, "type", None) or getattr(parm, "typeName", None)
    if callable(name):
        name = name()
    if callable(type_name):
        type_name = type_name()
    if name is None:
        text = str(parm).strip("<>").replace("APEX_Parm ", "", 1)
        parts = text.rsplit(" ", 1)
        name = parts[0].strip("'\"")
        type_name = parts[1] if len(parts) > 1 else None
    return {"name": str(name), "type": str(type_name) if type_name else None}


# --------------------------------------------------------------------------
# 그래프 만들기
# --------------------------------------------------------------------------


@tool()
@undoable("Build FK rig graph")
def build_fk_rig(skeleton: str, comment: str, name: str | None = None) -> dict[str, Any]:
    """스켈레톤에서 APEX FK 리그 그래프를 만든다.

    조인트마다 `TransformObject` 콜백 노드를 놓고 부모-자식으로 잇는다. 이것이
    APEX 리그의 출발점이다. 결과는 apex_rig_script 로 코드로 읽을 수 있다.

    `apex::buildfkgraph` 은 입력이 둘이다 — 0번이 바탕 그래프, 1번이 스켈레톤이다
    (실측 확인). 바탕 그래프로 쓸 빈 `apex::graph` 노드도 함께 만든다.

    Args:
        skeleton: 스켈레톤 SOP 경로. transform 어트리뷰트가 있어야 한다
            (create_skeleton 이나 kinefx::rigdoctor 를 거친 것).
        comment: 이 리그가 무엇인지 영어로. 예: FK rig for test tube character
        name: 노드 이름. 생략하면 Houdini 가 정한다.
    """
    require_comment(comment)
    skeleton_node = require_sop(skeleton)
    geometry_of(skeleton_node)

    base = skeleton_node.parent().createNode(
        "apex::graph", node_name=f"{name}_base" if name else "rig_graph_base"
    )
    base.setComment(f"{comment.strip()} (empty base graph)")
    base.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    node = build(
        base,
        "apex::buildfkgraph",
        comment,
        name=name,
        extra_inputs=(skeleton_node,),
    )

    geo = geometry_of(node)
    graph = apex.Graph()
    if not graph.loadFromGeometry(geo):
        raise ValueError(
            f"{node.path()} 가 APEX 그래프를 내지 않았습니다. 스켈레톤에 transform "
            f"어트리뷰트가 있는지 skeleton_info 로 확인하세요 — "
            f"kinefx::rigdoctor 의 Initialize Transforms 가 켜져 있어야 합니다."
        )

    node_ids = list(graph.allNodes())
    return {
        **node_brief(node),
        "base_graph": base.path(),
        "skeleton": skeleton_node.path(),
        "graph_nodes": len(node_ids),
        "stat": {str(k): int(v) for k, v in graph.stat().items()},
        "callbacks": sorted({graph.callbackName(i) for i in node_ids}),
        "errors": list(graph.errors()),
    }
