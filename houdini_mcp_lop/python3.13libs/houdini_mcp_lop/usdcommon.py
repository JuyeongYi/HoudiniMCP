"""LOP 툴들이 공유하는 헬퍼. 여기에는 툴이 없다.

핵심은 셋이다.

    resolve_lop / stage_of   어느 LOP 노드의 어느 스테이지를 볼 것인가
    jsonify                  pxr 값(Gf, Vt, Sdf)을 JSON 으로 나갈 수 있게
    author_python            씬을 바꾸는 값 쓰기를 pythonscript LOP 로

**값을 쓰는 방법에 대하여.** `hou.LopNode.editableStage()` 는 Python LOP 의 쿡
안에서만 유효하다. 일반 LOP 노드에서 부르면 예외도 없이 `None` 이 온다(실측).
그래서 스테이지에 값을 쓰는 툴은 전부 `pythonscript` LOP 노드를 만들어 그 안에서
쓴다. 이렇게 하면 (1) 편집이 노드로 남아 재쿡·Undo·저장이 자연스럽고,
(2) 사용자가 무엇이 쓰였는지 코드로 볼 수 있고, (3) 스테이지를 몰래 오염시키지
않는다.

생성되는 코드는 이 팩을 import 하지 않는다. 팩이 없는 머신에서 씬을 열어도
노드가 쿡돼야 하기 때문이다.
"""

from __future__ import annotations

import json
from typing import Any

import hou

HOUDINI_LAYER_INFO = "HoudiniLayerInfo"
"""Houdini 가 레이어마다 심어 두는 장부 프림의 타입.

씬의 내용이 아니라 Houdini 의 내부 기록(어느 노드가 이 레이어를 만들었는지)이다.
순회 결과에 섞이면 모델이 진짜 프림으로 착각하므로 걸러 낸다. 대신 그 정보는
layer_brief 가 사람이 읽을 수 있는 이름으로 바꿔 준다.
"""

MAX_ARRAY = 16
"""배열 값을 JSON 으로 내보낼 때 남길 원소 수. 스테이지에는 원소 수십만 개짜리
어트리뷰트가 흔하다. 전부 보내면 컨텍스트만 태운다."""


# ---- 노드와 스테이지 --------------------------------------------------


def resolve_lop(path: str) -> hou.LopNode:
    """경로로 LOP 노드를 찾는다. LOP 네트워크를 주면 그 디스플레이 노드를 쓴다.

    `/stage` 처럼 네트워크를 주는 것이 보통 쓰기 편하다 - 모델이 "지금 보이는
    스테이지"를 그대로 가리킬 수 있다.
    """
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"LOP 노드 경로나 LOP 네트워크 경로(보통 /stage)를 주세요."
        )

    if isinstance(node, hou.LopNode):
        return node

    if node.childTypeCategory() == hou.lopNodeTypeCategory():
        display = node.displayNode()
        if display is None:
            raise ValueError(
                f"{path} 아래에 디스플레이 플래그가 켜진 LOP 노드가 없습니다. "
                f"노드를 만들고 디스플레이 플래그를 켜거나, LOP 노드 경로를 "
                f"직접 주세요."
            )
        return display

    raise ValueError(
        f"{path} 은 LOP 노드가 아닙니다(타입 {node.type().name()}). "
        f"LOP 노드 경로나 LOP 네트워크 경로(보통 /stage)를 주세요."
    )


def stage_of(node: hou.LopNode, frame: float | None = None):
    """노드의 출력 스테이지. 부르면 필요한 만큼 알아서 쿡된다(실측 확인).

    쿡이 실패하면 `None` 이 오므로 여기서 걸러 무엇을 해야 하는지 알려 준다.
    """
    stage = node.stage(frame=frame) if frame is not None else node.stage()
    if stage is None:
        errors = "\n".join(node.errors()) or "(에러 메시지 없음)"
        raise ValueError(
            f"{node.path()} 가 스테이지를 내놓지 못했습니다. 쿡 에러를 먼저 "
            f"고치세요:\n{errors}"
        )
    return stage


def prim_at(stage, primpath: str):
    """스테이지에서 프림을 꺼낸다. 없으면 무엇을 해야 하는지 알려 준다."""
    from pxr import Sdf

    if not Sdf.Path.IsValidPathString(primpath):
        raise ValueError(
            f"USD 프림 경로가 아닙니다: {primpath!r}. "
            f"'/world/ball' 처럼 슬래시로 시작하는 절대 경로를 주세요."
        )
    prim = stage.GetPrimAtPath(primpath)
    if not prim:
        raise ValueError(
            f"스테이지에 그런 프림이 없습니다: {primpath}. "
            f"list_prims 나 find_prims 로 실제 경로를 먼저 확인하세요."
        )
    return prim


# ---- 값 변환 ----------------------------------------------------------


def jsonify(value: Any, max_array: int = MAX_ARRAY) -> Any:
    """pxr 값을 JSON 으로 나갈 수 있는 모양으로 바꾼다.

    Gf 벡터·행렬은 리스트로, Vt 배열은 잘라서 리스트로, Sdf.Path 와 Tf.Token 은
    문자열로. 배열이 잘리면 `{"truncated": ...}` 로 감싸 원래 길이를 함께 준다.
    """
    from pxr import Gf, Sdf

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Sdf.AssetPath):
        return {"asset_path": value.path, "resolved": value.resolvedPath or None}

    if isinstance(value, (Sdf.Path, Sdf.ValueTypeName)):
        return str(value)

    # Vt 배열에는 공통 베이스 클래스가 없다(pxr.Vt.Array 는 존재하지 않는다).
    # 모듈과 이름으로 가른다.
    if type(value).__module__ == "pxr.Vt" and type(value).__name__.endswith("Array"):
        total = len(value)
        head = [jsonify(v, max_array) for v in value[:max_array]]
        if total <= max_array:
            return head
        return {"count": total, "head": head, "truncated": True}

    if isinstance(value, (Gf.Matrix2d, Gf.Matrix3d, Gf.Matrix4d, Gf.Matrix4f)):
        return [list(row) for row in value]

    if isinstance(value, dict):
        return {str(k): jsonify(v, max_array) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [jsonify(v, max_array) for v in value]

    # Gf.Vec*, Gf.Quat*, Gf.Range* 등 시퀀스로 풀리는 것들.
    try:
        return [jsonify(v, max_array) for v in value]
    except TypeError:
        return str(value)


def brief_prim(prim) -> dict[str, Any]:
    """프림 하나를 짧게. 목록에 쓴다."""
    return {
        "path": str(prim.GetPath()),
        "name": prim.GetName(),
        "type": str(prim.GetTypeName()) or None,
        "specifier": str(prim.GetSpecifier()).rsplit(".", 1)[-1],
        "active": prim.IsActive(),
        "children": len(prim.GetChildren()),
    }


def arc_brief(arc) -> dict[str, Any]:
    """`Usd.CompositionArc` 하나를 요약한다.

    레퍼런스·페이로드·배리언트·인헤릿·스페셜라이즈·서브레이어가 모두 여기로
    나온다. 어느 레이어의 어느 프림을 어디에 끌어왔는지가 핵심이다.
    """
    target_layer = arc.GetTargetLayer()
    introducing = arc.GetIntroducingLayer()
    return {
        "arc": str(arc.GetArcType().displayName),
        "target_layer": target_layer.identifier if target_layer else None,
        "target_path": str(arc.GetTargetPrimPath()),
        "introducing_layer": introducing.identifier if introducing else None,
        "introducing_path": str(arc.GetIntroducingPrimPath()),
        "has_specs": arc.HasSpecs(),
        "ancestral": arc.IsAncestral(),
        "implicit": arc.IsImplicit(),
        "in_root_layer_stack": arc.IsIntroducedInRootLayerStack(),
    }


def layer_brief(layer) -> dict[str, Any]:
    """레이어 하나를 짧게. 익명 레이어는 husd 가 붙여 주는 이름을 쓴다.

    Houdini 의 LOP 스테이지는 레이어가 거의 다 익명이다. 그냥 identifier 를
    보여 주면 `anon:0000000041645800:LOP` 같은 주소라 아무 쓸모가 없다.
    `husd.GetLabelForLayer` 가 그 레이어를 만든 LOP 노드 경로를 붙여 준다.
    """
    import husd

    try:
        label = husd.GetLabelForLayer(layer)
    except Exception:
        label = layer.GetDisplayName()

    try:
        editors = [node.path() for node in husd.GetEditorNodesForLayer(layer)]
    except Exception:
        editors = []

    return {
        "identifier": layer.identifier,
        "label": label,
        "anonymous": layer.anonymous,
        "editor_nodes": editors,
    }


# ---- 씬을 바꾸는 경로 --------------------------------------------------

_HEADER = "# Authored by houdini_mcp_lop. Edit freely - this is plain USD."


def python_lop_code(body: str, spec: Any) -> str:
    """pythonscript LOP 에 넣을 코드를 만든다.

    `spec` 은 JSON 으로 직렬화해 코드 안에 박는다. 이 팩을 import 하지 않는
    자족적인 코드라, 팩이 없는 머신에서 씬을 열어도 쿡된다.
    """
    # json.dumps 는 따옴표를 이스케이프하므로 r\"\"\" ... \"\"\" 안에서 안전하다.
    payload = json.dumps(spec, indent=4)
    return f'{_HEADER}\nimport json\n\nfrom pxr import Sdf, Usd\n\nnode = hou.pwd()\nstage = node.editableStage()\nspec = json.loads(r"""{payload}""")\n\n{body}'


def insert_lop(
    lop: hou.LopNode, type_name: str, name: str, comment: str
) -> tuple[hou.LopNode, list[str]]:
    """`lop` 바로 뒤에 노드를 끼워 넣는다. 만든 노드와 다시 이은 하류 노드들.

    원래 `lop` 의 출력으로 가던 연결은 새 노드 뒤로 다시 잇는다(splice). 그래야
    편집이 하류에 실제로 반영된다. 디스플레이 플래그도 따라온다.

    Args:
        lop: 편집의 입력이 될 LOP 노드.
        type_name: 만들 LOP 노드 타입.
        name: 새 노드 이름. 역할이 드러나게 짓는다.
        comment: 노드 코멘트. 왜 이 노드가 있는지. Houdini 에 남으므로 영어로.
    """
    parent = lop.parent()
    downstream = list(lop.outputConnections())

    node = parent.createNode(type_name, name)
    node.setInput(0, lop)

    # 코멘트는 노드 생성 시점에 넣을 수 없다. 만든 직후에 달고 네트워크 뷰에도
    # 보이게 한다.
    node.setComment(comment)
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    rewired = []
    for connection in downstream:
        target = connection.outputNode()
        target.setInput(connection.inputIndex(), node, 0)
        rewired.append(target.path())

    if lop.isDisplayFlagSet():
        node.setDisplayFlag(True)
    node.moveToGoodPosition()

    return node, rewired


def author_python(
    lop: hou.LopNode,
    name: str,
    comment: str,
    code: str,
) -> dict[str, Any]:
    """`lop` 바로 뒤에 pythonscript LOP 을 끼워 넣어 스테이지에 값을 쓴다."""
    node, rewired = insert_lop(lop, "pythonscript", name, comment)
    node.parm("python").set(code)
    return {"node": node, "rewired": rewired}


SET_ATTR_BODY = '''\
for item in spec:
    prim = stage.GetPrimAtPath(item["prim"])
    if not prim:
        raise hou.NodeError("No such prim: " + item["prim"])

    attr = prim.GetAttribute(item["name"])
    if not attr:
        attr = prim.CreateAttribute(
            item["name"], Sdf.ValueTypeNames.Find(item["type"])
        )

    value = item["value"]
    type_name = attr.GetTypeName()
    if type_name == Sdf.ValueTypeNames.Asset and isinstance(value, str):
        value = Sdf.AssetPath(value)
    else:
        python_class = type_name.type.pythonClass
        if python_class is not None and value is not None:
            value = python_class(value)

    if item["time"] is None:
        attr.Set(value)
    else:
        attr.Set(value, item["time"])
'''
"""어트리뷰트를 거는 pythonscript 본문.

`spec` 은 {prim, name, type, value, time} 딕셔너리의 리스트다. 라이트 속성도
결국 어트리뷰트라서 lights 모듈이 이 경로를 그대로 쓴다.
"""


def attr_spec(
    primpath: str, name: str, type_name: str, value: Any, time: float | None = None
) -> dict[str, Any]:
    """SET_ATTR_BODY 가 먹는 항목 하나."""
    return {
        "prim": primpath,
        "name": name,
        "type": type_name,
        "value": value,
        "time": time,
    }


def author_attributes(
    lop: hou.LopNode, name: str, comment: str, spec: list[dict[str, Any]]
) -> dict[str, Any]:
    """어트리뷰트 여러 개를 한 노드로 건다."""
    return author_python(lop, name, comment, python_lop_code(SET_ATTR_BODY, spec))


def node_report(node: hou.LopNode, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """만든 노드를 돌려줄 때 쓰는 공통 보고. 경고·에러를 반드시 함께 준다."""
    report: dict[str, Any] = {
        "node": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }
    if extra:
        report.update(extra)
    return report
