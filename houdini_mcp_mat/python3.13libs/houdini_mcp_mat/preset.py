"""머티리얼을 파일로 저장하고 다시 읽는 툴. 포맷은 **MaterialX 문서**다.

자체 JSON 포맷을 쓰지 않는다. 자체 포맷으로 저장한 프리셋은 이 MCP 서버
밖에서는 아무도 읽지 못한다. MaterialX 로 저장하면 Blender, Maya, USD,
그리고 MaterialX 를 읽는 모든 렌더러가 그대로 읽는다.

내보내기는 Houdini 가 가진 vop2mtlx 를 쓴다(셸프의 "Save MaterialX" 와 같은
경로). 읽어 들이기는 Houdini 에 없어서 여기서 만들었다 — MaterialX 문서의
노드를 대응하는 mtlx VOP 노드로 세우고, 값과 연결을 복원한다.

파일을 지우는 툴은 만들지 않는다. 되돌릴 수 없고, MCP 툴로 노출할 이유가 없다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool, undoable

from .common import (
    KIND_MATERIALX,
    build_material,
    expand_path,
    material_kind,
    require_comment,
    require_material,
    set_comment,
    vop_container,
)

MTLX_SUFFIX = ".mtlx"

OUTPUT_FOR_TYPE = {
    "surfaceshader": "surface",
    "displacementshader": "displacement",
}
"""MaterialX 출력 타입을 머티리얼 빌더의 출력 커넥터 이름으로."""

SIGNATURE_FOR_MTLX_TYPE = {
    "float": "default",
    "integer": "default",
    "boolean": "default",
    "filename": "default",
    "string": "default",
}
"""MaterialX 타입을 VOP 노드의 signature 파라미터 값으로.

mtlx VOP 노드의 signature 메뉴는 float 를 "default" 라고 부른다. 그리고 새로
만든 mtlximage 의 기본 signature 는 color3 다(실측 확인) — 그대로 두면 float
입력에 color 를 물리게 되므로 문서의 타입대로 반드시 되돌려야 한다."""


def _materialx():
    try:
        import MaterialX as mx
    except Exception as exc:  # noqa: BLE001 - 번들이 깨진 경우
        raise RuntimeError(
            f"MaterialX 를 읽지 못했습니다. Houdini 설치가 온전한지 확인하세요. ({exc})"
        ) from exc
    return mx


def _vop2mtlx():
    try:
        import vop2mtlx
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"vop2mtlx 를 읽지 못했습니다. Houdini 설치가 온전한지 확인하세요. ({exc})"
        ) from exc
    return vop2mtlx


def _target_file(file: str) -> Path:
    path = expand_path(file)
    if path.suffix.lower() != MTLX_SUFFIX:
        path = path.with_suffix(MTLX_SUFFIX)
    return path


@tool()
def save_material(material: str, file: str) -> dict[str, Any]:
    """머티리얼을 MaterialX 문서(.mtlx)로 저장하고, 저장한 것을 다시 읽어 검증한다.

    저장만 하고 끝내지 않는다. 쓴 파일을 MaterialX 라이브러리로 다시 읽어
    유효한지 확인하고, 문서에 노드가 몇 개 들어갔는지 돌려준다.

    MaterialX 로 내보낼 수 있는 것은 MaterialX 계열 머티리얼뿐이다. Karma
    Material Builder 는 kma_material_properties 때문에 내보낼 수 없다
    (실측 확인). 그 경우 어느 노드가 막고 있는지 알려 준다.

    Args:
        material: 머티리얼 노드 경로. 예: /mat/wall_stone
        file: 저장할 경로. 확장자가 없으면 .mtlx 를 붙인다.
            예: $HIP/materials/wall_stone.mtlx
    """
    mx = _materialx()
    vop2mtlx = _vop2mtlx()

    node = require_material(material)
    if not vop2mtlx.canSaveMaterialX(node):
        offenders = [
            child.path()
            for child in node.children()
            if child.renderMask() not in ("mtlx", "")
        ]
        raise ValueError(
            f"{material} 는 MaterialX 로 내보낼 수 없습니다. MaterialX 가 아닌 "
            f"노드가 섞여 있습니다{': ' + ', '.join(offenders) if offenders else ''}. "
            f"kind='materialx' 로 만든 머티리얼만 내보낼 수 있습니다. "
            f"validate_material 로 무엇이 막고 있는지 볼 수 있습니다."
        )

    path = _target_file(file)
    path.parent.mkdir(parents=True, exist_ok=True)
    vop2mtlx.saveShaderNetwork(str(path), node)
    if not path.is_file():
        raise ValueError(
            f"MaterialX 문서를 쓰지 못했습니다: {path}. "
            f"그래프의 출력이 연결돼 있는지 validate_material 로 확인하세요."
        )

    document = mx.createDocument()
    mx.readFromXmlFile(document, str(path))
    valid, message = document.validate()
    graphs = document.getNodeGraphs()

    return {
        "material": node.path(),
        "kind": material_kind(node),
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "materialx_valid": bool(valid),
        "materialx_message": message or "",
        "nodegraphs": [graph.getName() for graph in graphs],
        "node_count": sum(len(graph.getNodes()) for graph in graphs),
        "outputs": [
            {"name": output.getName(), "type": output.getType()}
            for graph in graphs
            for output in graph.getOutputs()
        ],
    }


@tool()
def list_presets(directory: str = "$HIP/materials") -> dict[str, Any]:
    """디렉토리의 MaterialX 문서를 나열한다. 안에 무엇이 들었는지까지.

    파일 이름만 주지 않는다. 각 문서를 열어 노드그래프 이름, 노드 수, 출력을
    읽고 유효한지 검증한다.

    Args:
        directory: 훑을 디렉토리. 예: $HIP/materials
    """
    mx = _materialx()
    root = expand_path(directory)
    if not root.is_dir():
        return {
            "directory": str(root),
            "count": 0,
            "presets": [],
            "hint": (
                f"디렉토리가 없습니다: {root}. "
                f"save_material 로 저장하면 만들어집니다."
            ),
        }

    presets = []
    for path in sorted(root.glob(f"*{MTLX_SUFFIX}")):
        entry: dict[str, Any] = {"file": str(path), "size_bytes": path.stat().st_size}
        try:
            document = mx.createDocument()
            mx.readFromXmlFile(document, str(path))
            valid, message = document.validate()
            graphs = document.getNodeGraphs()
            entry.update(
                {
                    "materialx_valid": bool(valid),
                    "materialx_message": message or "",
                    "nodegraphs": [graph.getName() for graph in graphs],
                    "node_count": sum(len(graph.getNodes()) for graph in graphs),
                }
            )
        except Exception as exc:  # noqa: BLE001 - 깨진 문서 하나가 목록을 막으면 안 된다
            entry["error"] = str(exc)
        presets.append(entry)

    return {"directory": str(root), "count": len(presets), "presets": presets}


# ---- 읽어 들이기 -----------------------------------------------------


def _vop_type_for(category: str) -> str | None:
    """MaterialX 카테고리에 대응하는 VOP 노드 타입 이름."""
    for candidate in (f"mtlx{category}", category):
        if hou.nodeType(hou.vopNodeTypeCategory(), candidate) is not None:
            return candidate
    return None


def _python_value(value: Any) -> Any:
    """MaterialX 값을 Houdini 파라미터에 넣을 수 있는 형태로."""
    if isinstance(value, (str, bool, int, float)):
        return value
    try:
        return tuple(value)
    except TypeError:
        return str(value)


def _parm_names(node: hou.VopNode, name: str) -> list[str]:
    """입력 이름에 대응할 수 있는 파라미터 이름들.

    signature 가 붙는 노드는 파라미터 이름이 default_color3 처럼 확장된다.
    """
    candidates = [name]
    signature = node.parm("signature")
    if signature is not None:
        value = signature.eval()
        if value and value != "default":
            candidates.append(f"{name}_{value}")
    return candidates


def _set_input_value(node: hou.VopNode, name: str, value: Any) -> str | None:
    """입력 값을 파라미터에 건다. 못 걸면 이유를 돌려준다."""
    converted = _python_value(value)
    for candidate in _parm_names(node, name):
        if isinstance(converted, tuple):
            parm_tuple = node.parmTuple(candidate)
            if parm_tuple is not None and len(parm_tuple) == len(converted):
                parm_tuple.set(converted)
                return None
            continue

        parm = node.parm(candidate)
        if parm is not None:
            parm.set(converted)
            return None
        parm_tuple = node.parmTuple(candidate)
        if parm_tuple is not None and len(parm_tuple) == 1:
            parm_tuple.set((converted,))
            return None
    return f"{node.name()}.{name}: 대응하는 파라미터를 찾지 못했습니다."


def _connector_for(material: hou.VopNode, output_name: str) -> hou.VopNode | None:
    for child in material.children():
        if child.type().name() != "subnetconnector":
            continue
        parm = child.parm("parmname")
        if parm is not None and parm.eval() == output_name:
            return child
    return None


def _rebuild(material: hou.VopNode, graph) -> dict[str, Any]:
    """MaterialX 노드그래프를 VOP 노드로 세운다."""
    warnings: list[str] = []
    created: dict[str, hou.VopNode] = {}

    # 1) 노드를 먼저 전부 만든다. 연결은 그 다음이다.
    for mx_node in graph.getNodes():
        category = mx_node.getCategory()
        vop_type = _vop_type_for(category)
        if vop_type is None:
            warnings.append(
                f"MaterialX 노드 {mx_node.getName()!r}(카테고리 {category!r})에 "
                f"대응하는 VOP 노드 타입이 없어 건너뜁니다."
            )
            continue
        node = material.createNode(vop_type, node_name=mx_node.getName())
        created[mx_node.getName()] = node

        # signature 를 먼저 정한다. 파라미터 이름이 signature 에 딸려 있어서
        # (default_color3r 처럼) 값보다 앞서야 한다.
        signature = node.parm("signature")
        if signature is not None:
            mtlx_type = mx_node.getType()
            wanted = SIGNATURE_FOR_MTLX_TYPE.get(mtlx_type, mtlx_type)
            if wanted in signature.menuItems():
                signature.set(wanted)

    # 2) 값과 연결.
    for mx_node in graph.getNodes():
        node = created.get(mx_node.getName())
        if node is None:
            continue
        for mx_input in mx_node.getInputs():
            name = mx_input.getName()
            source_name = mx_input.getNodeName()
            if source_name:
                source = created.get(source_name)
                if source is None:
                    warnings.append(
                        f"{mx_node.getName()}.{name} 의 입력 노드 {source_name!r} 를 "
                        f"만들지 못해 연결을 건너뜁니다."
                    )
                    continue
                output = mx_input.getOutputString() or "out"
                if output not in source.outputNames():
                    output = source.outputNames()[0]
                node.setNamedInput(name, source, output)
                continue

            value = mx_input.getValue()
            if value is None:
                continue
            problem = _set_input_value(node, name, value)
            if problem:
                warnings.append(problem)

    # 3) 그래프 출력을 머티리얼의 출력 커넥터에 잇는다.
    outputs = []
    for mx_output in graph.getOutputs():
        source = created.get(mx_output.getNodeName())
        connector_name = OUTPUT_FOR_TYPE.get(mx_output.getType())
        connector = (
            _connector_for(material, connector_name) if connector_name else None
        )
        if source is None or connector is None:
            warnings.append(
                f"출력 {mx_output.getName()!r}(타입 {mx_output.getType()!r})을 "
                f"머티리얼 출력에 잇지 못했습니다."
            )
            continue
        connector.setInput(0, source)
        outputs.append({"output": connector_name, "shader": source.path()})

    return {"created": created, "warnings": warnings, "outputs": outputs}


@tool()
@undoable("Load material preset")
def load_material(
    file: str, parent: str, name: str, comment: str, nodegraph: str = ""
) -> dict[str, Any]:
    """MaterialX 문서를 읽어 머티리얼로 세운다. save_material 의 반대다.

    Houdini 에는 MaterialX 문서를 VOP 그래프로 되돌리는 경로가 없다(실측
    확인 — vop2mtlx 는 내보내기만, mtlx2hda 는 노드 정의를 HDA 로 만드는 것이다).
    그래서 문서의 노드를 대응하는 mtlx VOP 노드로 세우고 값과 연결을 복원한다.

    대응하는 VOP 노드 타입이 없는 것은 건너뛰고 warnings 에 담는다. 조용히
    빠뜨리지 않는다. 읽은 뒤에는 validate_material 로 확인한다.

    Args:
        file: 읽을 MaterialX 문서. 예: $HIP/materials/wall_stone.mtlx
        parent: 머티리얼을 만들 네트워크. 예: /mat
        name: 만들 머티리얼 이름. 역할이 드러나게. 영어로.
        comment: 이 머티리얼이 무엇인지. 필수. 영어로.
        nodegraph: 문서에 노드그래프가 여럿일 때 고를 이름. 비우면 첫 번째.
    """
    mx = _materialx()
    comment = require_comment(comment, "이 머티리얼")

    path = expand_path(file)
    if not path.is_file():
        raise ValueError(
            f"MaterialX 문서가 없습니다: {path}. "
            f"list_presets 로 디렉토리의 프리셋을 먼저 보세요."
        )

    document = mx.createDocument()
    mx.readFromXmlFile(document, str(path))
    valid, message = document.validate()

    graphs = document.getNodeGraphs()
    if not graphs:
        raise ValueError(
            f"{path} 에 노드그래프가 없습니다. save_material 로 저장한 문서이거나 "
            f"nodegraph 를 담은 MaterialX 문서여야 합니다."
        )
    if nodegraph:
        selected = [graph for graph in graphs if graph.getName() == nodegraph]
        if not selected:
            raise ValueError(
                f"{nodegraph!r} 이라는 노드그래프가 없습니다. "
                f"있는 것: {', '.join(graph.getName() for graph in graphs)}"
            )
        graph = selected[0]
    else:
        graph = graphs[0]

    # MaterialX 빌더를 세우고 기본 셰이더를 치운 뒤 문서 내용으로 채운다.
    container = vop_container(parent)
    material = build_material(container, name, KIND_MATERIALX)
    set_comment(material, comment)
    for child in material.children():
        if child.type().name().startswith("mtlx"):
            child.destroy()

    built = _rebuild(material, graph)
    material.layoutChildren()
    material.moveToGoodPosition()

    return {
        "path": material.path(),
        "name": material.name(),
        "kind": material_kind(material),
        "comment": material.comment(),
        "file": str(path),
        "nodegraph": graph.getName(),
        "source_materialx_valid": bool(valid),
        "source_materialx_message": message or "",
        "nodes_created": len(built["created"]),
        "nodes_in_document": len(graph.getNodes()),
        "outputs": built["outputs"],
        "warnings": built["warnings"],
        "next": "validate_material 로 복원 결과를 확인하세요.",
    }
