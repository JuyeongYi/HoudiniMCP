"""팩 안에서 공유하는 헬퍼. 툴은 없다.

머티리얼 노드를 찾고, 셰이더 그래프를 걷고, 경로를 펼치는 일을 여기 모은다.
모듈마다 같은 것을 다시 쓰지 않기 위해서다.
"""

from __future__ import annotations

from typing import Any

import hou

MTLX_RENDER_MASK = "mtlx"
"""MaterialX VOP 노드의 renderMask. 이 값이면 MaterialX 문서로 내보낼 수 있다."""

SURFACE = "surface"
DISPLACEMENT = "displacement"

SUBNET_PLUMBING = frozenset(("subinput", "suboutput", "subnetconnector", "parameter"))
"""셰이더가 아니라 서브넷 배선용인 노드 타입들. 그래프를 셀 때 제외한다."""

KIND_MATERIALX = "materialx"
KIND_KARMA = "karma"
KIND_USD_PREVIEW = "usdpreview"
KIND_PRINCIPLED = "principled"


# ---- 노드 얻기 -------------------------------------------------------


def require_node(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def require_vop(path: str) -> hou.VopNode:
    """VOP 노드를 얻는다. 아니면 무엇을 줘야 하는지 알려 준다."""
    node = require_node(path)
    if not isinstance(node, hou.VopNode):
        raise ValueError(
            f"{path} 는 VOP(셰이더) 노드가 아닙니다. "
            f"이 노드는 {node.type().category().name()} 입니다. "
            f"머티리얼이나 셰이더 노드 경로를 주세요. 예: /mat/wood_mtlx"
        )
    return node


def require_material(path: str) -> hou.VopNode:
    """머티리얼 노드를 얻는다. 셰이더 노드 하나를 줬으면 그렇다고 알려 준다."""
    node = require_vop(path)
    if not node.isMaterialFlagSet():
        parent = node.parent()
        hint = (
            f" 이 노드가 속한 머티리얼은 {parent.path()} 인 것 같습니다."
            if isinstance(parent, hou.VopNode) and parent.isMaterialFlagSet()
            else " list_materials 로 씬의 머티리얼 목록을 먼저 보세요."
        )
        raise ValueError(f"{path} 에는 머티리얼 플래그가 없습니다.{hint}")
    return node


def vop_container(path: str) -> hou.Node:
    """VOP 노드를 만들 수 있는 네트워크인지 확인하고 돌려준다."""
    node = require_node(path)
    if node.childTypeCategory() != hou.vopNodeTypeCategory():
        raise ValueError(
            f"{path} 안에는 셰이더 노드를 만들 수 없습니다. "
            f"이 네트워크는 {node.childTypeCategory().name()} 를 담습니다. "
            f"/mat, matnet, 또는 materiallibrary LOP 안을 주세요."
        )
    return node


# ---- 머티리얼 판별 ---------------------------------------------------


def material_kind(node: hou.VopNode) -> str:
    """머티리얼이 어느 계열인지. 내보내기와 렌더러 선택이 여기에 달렸다."""
    type_name = node.type().name()
    if type_name.startswith("principledshader"):
        return KIND_PRINCIPLED
    if node.isSubNetwork():
        children = {child.type().name() for child in node.children()}
        if "kma_material_properties" in children:
            return KIND_KARMA
        if any(name.startswith("mtlx") for name in children):
            return KIND_MATERIALX
        if "usdpreviewsurface" in children:
            return KIND_USD_PREVIEW
    return type_name


def shader_children(material: hou.VopNode) -> list[hou.VopNode]:
    """머티리얼 안의 실제 셰이더 노드들. 서브넷 배선 노드는 뺀다."""
    if not material.isSubNetwork():
        return []
    return [
        child
        for child in material.children()
        if child.type().name() not in SUBNET_PLUMBING
    ]


def terminal_shader(material: hou.VopNode, output: str = SURFACE) -> hou.VopNode | None:
    """머티리얼의 출력(surface/displacement)에 실제로 물린 셰이더 노드.

    MaterialX 빌더는 subnetconnector 로, Karma 빌더와 USD Preview 빌더는
    suboutput 으로 출력을 낸다. 둘 다 같은 방식으로 다룬다.
    """
    if not material.isSubNetwork():
        return material

    try:
        connector, _ = material.subnetTerminalChild(output)
    except (hou.OperationFailed, TypeError):
        return None
    if connector is None:
        return None

    if connector.type().name() == "subnetconnector":
        return connector.input(0)

    names = list(material.outputNames())
    index = names.index(output) if output in names else 0
    return connector.input(index)


# ---- 그래프 ----------------------------------------------------------


def node_summary(node: hou.VopNode) -> dict[str, Any]:
    """셰이더 노드 하나를 요약한다. 코멘트를 반드시 포함한다."""
    entry: dict[str, Any] = {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "render_mask": node.renderMask(),
    }
    if node.errors():
        entry["errors"] = list(node.errors())
    if node.warnings():
        entry["warnings"] = list(node.warnings())
    return entry


def input_connections(node: hou.VopNode) -> list[dict[str, Any]]:
    """이 노드로 들어오는 연결.

    HOM 의 이름이 헷갈리므로 실측해서 고정한 것을 쓴다.
    connection.inputNode() 가 값을 내보내는 쪽이고, inputName() 은 그 쪽의
    출력 커넥터 이름("out")이다. outputName() 이 이 노드의 입력 커넥터 이름이다.
    """
    result = []
    for connection in node.inputConnections():
        result.append(
            {
                "from": connection.inputNode().path(),
                "from_output": connection.inputName(),
                "to": node.path(),
                "to_input": connection.outputName(),
            }
        )
    return result


def connector_names(node: hou.VopNode) -> dict[str, Any]:
    """노드가 받을 수 있는 입력과 낼 수 있는 출력. 타입까지 함께."""
    inputs = list(node.inputNames())
    input_types = list(node.inputDataTypes())
    outputs = list(node.outputNames())
    output_types = list(node.outputDataTypes())
    return {
        "inputs": [
            {"name": name, "type": input_types[i] if i < len(input_types) else ""}
            for i, name in enumerate(inputs)
        ],
        "outputs": [
            {"name": name, "type": output_types[i] if i < len(output_types) else ""}
            for i, name in enumerate(outputs)
        ],
    }


def set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def require_comment(comment: str, subject: str) -> str:
    if not comment or not comment.strip():
        raise ValueError(
            f"comment 가 비어 있습니다. {subject} 이 무엇을 위한 것인지 적어 주세요. "
            f"씬 파일에 저장되므로 영어로 씁니다."
        )
    return comment.strip()


# ---- 머티리얼 조립 ---------------------------------------------------


def _voptoolutils():
    """SideFX 자체 헬퍼. 셸프 툴이 쓰는 것과 같은 조립 로직을 그대로 쓴다."""
    try:
        import voptoolutils
    except Exception as exc:  # noqa: BLE001 - Houdini 설치가 이상한 경우
        raise RuntimeError(
            f"voptoolutils 를 읽지 못했습니다. Houdini 설치가 온전한지 확인하세요. ({exc})"
        ) from exc
    return voptoolutils


def build_material(container: hou.Node, name: str, kind: str) -> hou.VopNode:
    """계열에 맞는 머티리얼 컨테이너를 조립한다.

    빈 서브넷을 주지 않는다. Houdini 셸프가 쓰는 조립 로직을 그대로 불러
    셰이더와 출력 배선까지 갖춘 채로 돌려준다.
    """
    utils = _voptoolutils()

    if kind == KIND_PRINCIPLED:
        return container.createNode("principledshader::2.0", node_name=name)

    if kind == KIND_USD_PREVIEW:
        setup = getattr(utils, "_setupUsdPreviewBuilderSubnet", None)
        if setup is None:
            raise RuntimeError(
                "voptoolutils 에 USD Preview 빌더 조립 함수가 없습니다. "
                "kind='materialx' 를 쓰세요."
            )
        return setup(destination_node=container, name=name)

    setup = getattr(utils, "_setupMtlXBuilderSubnet", None)
    if setup is None:
        raise RuntimeError(
            "voptoolutils 에 MaterialX 빌더 조립 함수가 없습니다. "
            "Houdini 버전이 22.0 인지 확인하세요."
        )
    if kind == KIND_KARMA:
        return setup(
            destination_node=container,
            name=name,
            mask=utils.KARMAMTLX_TAB_MASK,
            folder_label="Karma Material Builder",
            render_context="kma",
        )
    return setup(destination_node=container, name=name)


# ---- LOP / USD -------------------------------------------------------


def lop_stage(path: str):
    """LOP 노드의 컴포지션이 끝난 스테이지를 얻는다.

    머티리얼 바인딩을 파라미터에서 추측하지 않고 스테이지에서 직접 읽기 위한
    입구다. 스테이지 일반 조회는 houdini_mcp_lop 이 맡는다.
    """
    node = require_node(path)
    if not isinstance(node, hou.LopNode):
        raise ValueError(
            f"{path} 는 LOP 노드가 아닙니다 ({node.type().category().name()}). "
            f"/stage 안의 노드 경로를 주세요."
        )
    stage = node.stage()
    if stage is None:
        raise ValueError(
            f"{path} 의 스테이지를 읽지 못했습니다. 노드가 쿡되지 않았을 수 있습니다. "
            f"디스플레이 플래그를 켜고 다시 시도하세요."
        )
    return stage
