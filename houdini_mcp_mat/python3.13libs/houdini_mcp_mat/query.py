"""머티리얼을 들여다보고 검증하는 툴.

`validate_material` 이 이 팩의 핵심이다. 기존 구현은 셰이더를 만들고 잇기만
하고 그것이 유효한지 모른다. 여기서는 Houdini 에 번들된 MaterialX 1.39.5 로
**실제로 문서를 만들어 라이브러리에게 검증시킨다.** 타입이 안 맞는 연결,
빠진 정의, 잘못된 값은 MaterialX 가 잡아 준다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool

from .common import (
    MTLX_RENDER_MASK,
    SUBNET_PLUMBING,
    expand_path,
    input_connections,
    lop_stage,
    material_kind,
    node_summary,
    require_material,
    require_node,
    shader_children,
    terminal_shader,
)

MAX_MATERIALS = 200
"""한 번에 돌려줄 머티리얼 수 상한. 넘으면 잘라내고 몇 개인지 알려 준다."""

MAX_GRAPH_NODES = 200
"""shader_graph 가 돌려줄 노드 수 상한."""


# ---- 목록 ------------------------------------------------------------


def _vop_materials(root: hou.Node, limit: int) -> tuple[list[hou.VopNode], int]:
    """root 아래의 머티리얼 노드를 모은다. 머티리얼 플래그로 판별한다."""
    found: list[hou.VopNode] = []
    total = 0
    for node in root.allSubChildren(top_down=True, recurse_in_locked_nodes=False):
        if isinstance(node, hou.VopNode) and node.isMaterialFlagSet():
            total += 1
            if len(found) < limit:
                found.append(node)
    return found, total


def _usd_materials(lop_path: str, limit: int) -> list[dict[str, Any]]:
    """LOP 스테이지에서 UsdShade.Material 프림을 읽는다.

    노드 파라미터가 아니라 컴포지션이 끝난 스테이지에서 읽으므로, 레퍼런스나
    서브레이어로 들어온 머티리얼도 보인다.
    """
    from pxr import UsdShade

    stage = lop_stage(lop_path)
    entries: list[dict[str, Any]] = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdShade.Material):
            continue
        material = UsdShade.Material(prim)
        surfaces = {}
        for context in ("mtlx", "karma", ""):
            source = material.ComputeSurfaceSource(context) if context else material.ComputeSurfaceSource()
            shader = source[0] if source else None
            if shader:
                surfaces[context or "universal"] = str(shader.GetPath())
        entries.append(
            {
                "prim": str(prim.GetPath()),
                "kind": prim.GetTypeName(),
                "surface_sources": surfaces,
                "shaders": [
                    str(child.GetPath())
                    for child in prim.GetChildren()
                    if child.IsA(UsdShade.Shader)
                ],
            }
        )
        if len(entries) >= limit:
            break
    return entries


@tool()
def list_materials(
    root: str = "/", lop: str = "", max_results: int = 100
) -> dict[str, Any]:
    """씬의 머티리얼을 나열한다. 코멘트와 계열을 함께 준다.

    VOP 머티리얼은 머티리얼 플래그로 찾는다. 노드 이름이나 위치로 추측하지
    않으므로 /mat 밖에 있는 것도 빠지지 않는다.

    lop 을 주면 그 LOP 노드의 **컴포지션이 끝난 스테이지**에서 UsdShade.Material
    프림을 읽는다. 레퍼런스나 서브레이어로 들어온 머티리얼도 보인다.

    Args:
        root: 어디부터 훑을지. 기본은 씬 전체. 예: /mat, /obj/castle
        lop: LOP 노드 경로를 주면 USD 머티리얼을 대신 읽는다. 예: /stage/assign_wood
        max_results: 돌려줄 최대 개수.
    """
    if lop:
        materials = _usd_materials(lop, min(max_results, MAX_MATERIALS))
        return {"source": "usd", "lop": lop, "count": len(materials), "materials": materials}

    root_node = require_node(root)
    limit = min(max_results, MAX_MATERIALS)
    nodes, total = _vop_materials(root_node, limit)
    materials = []
    for node in nodes:
        entry = node_summary(node)
        entry["kind"] = material_kind(node)
        entry["shader_count"] = len(shader_children(node))
        materials.append(entry)

    result: dict[str, Any] = {
        "source": "vop",
        "root": root_node.path(),
        "count": len(materials),
        "materials": materials,
    }
    if total > len(materials):
        result["total"] = total
        result["truncated"] = True
        result["hint"] = "root 를 좁히거나 max_results 를 올리세요."
    return result


# ---- 상세 ------------------------------------------------------------


def _texture_parms(material: hou.VopNode) -> list[dict[str, Any]]:
    """머티리얼 안의 이미지 파일 파라미터와 그 값. 존재 여부까지."""
    entries: list[dict[str, Any]] = []
    nodes = [material, *material.allSubChildren(recurse_in_locked_nodes=False)]
    for node in nodes:
        for parm in node.parms():
            template = parm.parmTemplate()
            if not isinstance(template, hou.StringParmTemplate):
                continue
            if template.stringType() != hou.stringParmType.FileReference:
                continue
            if template.fileType() != hou.fileType.Image:
                continue
            raw = parm.unexpandedString()
            if not raw:
                continue
            entries.append(
                {
                    "node": node.path(),
                    "parm": parm.name(),
                    "raw": raw,
                    "resolved": str(expand_path(parm.eval())),
                }
            )
    return entries


def _assignment_users(material_path: str) -> list[dict[str, Any]]:
    """이 머티리얼을 거는 노드들. 파라미터 값으로 실제 참조를 찾는다."""
    users: list[dict[str, Any]] = []
    candidates = (
        (hou.sopNodeTypeCategory(), "material"),
        (hou.lopNodeTypeCategory(), "assignmaterial"),
        (hou.objNodeTypeCategory(), "geo"),
    )
    name = material_path.rsplit("/", 1)[-1]
    for category, type_name in candidates:
        node_type = hou.nodeType(category, type_name)
        if node_type is None:
            continue
        for node in node_type.instances():
            for parm in node.parms():
                if not isinstance(parm.parmTemplate(), hou.StringParmTemplate):
                    continue
                value = parm.eval()
                if not value:
                    continue
                if value == material_path or value.rsplit("/", 1)[-1] == name:
                    users.append(
                        {
                            "node": node.path(),
                            "type": node.type().name(),
                            "parm": parm.name(),
                            "value": value,
                            "comment": node.comment(),
                        }
                    )
    return users


@tool()
def material_info(path: str) -> dict[str, Any]:
    """머티리얼 하나를 전부 본다 — 셰이더, 연결, 텍스처, 이 머티리얼을 거는 노드.

    여러 번 왕복하지 않고 한 번에 판단할 수 있게 다 담는다.

    Args:
        path: 머티리얼 노드 경로. 예: /mat/wall_stone
    """
    material = require_material(path)
    outputs = []
    for name in material.outputNames():
        shader = terminal_shader(material, name)
        outputs.append(
            {
                "output": name,
                "shader": shader.path() if shader is not None else None,
                "shader_type": shader.type().name() if shader is not None else None,
            }
        )

    children = shader_children(material)
    connections = [
        connection for child in material.children() for connection in input_connections(child)
    ]

    return {
        "path": material.path(),
        "name": material.name(),
        "type": material.type().name(),
        "kind": material_kind(material),
        "comment": material.comment(),
        "outputs": outputs,
        "shaders": [node_summary(child) for child in children],
        "connections": connections,
        "textures": _texture_parms(material),
        "assigned_by": _assignment_users(material.path()),
        "errors": list(material.errors()),
        "warnings": list(material.warnings()),
    }


@tool()
def shader_graph(path: str, max_nodes: int = 100) -> dict[str, Any]:
    """머티리얼 안의 셰이더 그래프 구조 — 노드와 연결.

    material_info 보다 가볍다. 그래프가 어떻게 생겼는지만 볼 때 쓴다.

    Args:
        path: 머티리얼 노드 경로.
        max_nodes: 돌려줄 노드 수 상한.
    """
    material = require_material(path)
    limit = min(max_nodes, MAX_GRAPH_NODES)

    nodes = []
    edges = []
    children = list(material.children())
    for child in children[:limit]:
        entry = {
            "name": child.name(),
            "type": child.type().name(),
            "comment": child.comment(),
        }
        if child.type().name() in SUBNET_PLUMBING:
            entry["role"] = "plumbing"
        nodes.append(entry)
        for connection in child.inputConnections():
            edges.append(
                {
                    "from": connection.inputNode().name(),
                    "from_output": connection.inputName(),
                    "to": child.name(),
                    "to_input": connection.outputName(),
                }
            )

    result: dict[str, Any] = {
        "path": material.path(),
        "kind": material_kind(material),
        "comment": material.comment(),
        "nodes": nodes,
        "edges": edges,
    }
    if len(children) > limit:
        result["truncated"] = True
        result["total_nodes"] = len(children)
    return result


# ---- 검증 ------------------------------------------------------------


def _non_materialx_nodes(material: hou.VopNode) -> list[dict[str, str]]:
    """MaterialX 로 내보낼 수 없게 만드는 노드들."""
    offenders = []
    for child in material.children():
        if child.type().name() in SUBNET_PLUMBING:
            continue
        if child.isSubNetwork():
            offenders.extend(_non_materialx_nodes(child))
            continue
        if child.renderMask() != MTLX_RENDER_MASK:
            offenders.append(
                {
                    "path": child.path(),
                    "type": child.type().name(),
                    "render_mask": child.renderMask(),
                }
            )
    return offenders


def _materialx_check(material: hou.VopNode) -> dict[str, Any]:
    """MaterialX 라이브러리에게 그래프를 검증시킨다.

    VOP 그래프를 MaterialX 문서로 내보낸 뒤 doc.validate() 를 부른다. 타입
    불일치나 깨진 정의는 우리가 아니라 라이브러리가 잡는다.
    """
    import MaterialX as mx
    import vop2mtlx

    offenders = _non_materialx_nodes(material)
    if offenders:
        return {
            "exportable": False,
            "non_materialx_nodes": offenders,
            "reason": (
                "MaterialX 가 아닌 노드가 섞여 있어 문서로 내보낼 수 없습니다. "
                "Karma Material Builder(kma_material_properties)가 대표적입니다. "
                "MaterialX 호환이 필요하면 kind='materialx' 로 머티리얼을 만드세요."
            ),
        }

    # 임시 파일에 내보내고 다시 읽어 검증한다. 스크래치에만 쓰고 지운다.
    with tempfile.TemporaryDirectory(prefix="houdini_mcp_mat_") as tmp:
        target = Path(tmp) / f"{material.name()}.mtlx"
        vop2mtlx.saveShaderNetwork(str(target), material)
        if not target.exists():
            return {
                "exportable": False,
                "reason": (
                    "MaterialX 문서를 만들지 못했습니다. 그래프에 MaterialX 가 아닌 "
                    "노드가 있거나 출력이 연결되지 않았을 수 있습니다."
                ),
            }
        doc = mx.createDocument()
        mx.readFromXmlFile(doc, str(target))
        valid, message = doc.validate()
        return {
            "exportable": True,
            "materialx_valid": bool(valid),
            "materialx_message": message or "",
            "document_nodes": len(doc.getNodes()),
            "nodegraphs": [graph.getName() for graph in doc.getNodeGraphs()],
        }


@tool()
def validate_material(path: str) -> dict[str, Any]:
    """머티리얼이 실제로 유효한지 검증한다. MaterialX 라이브러리가 판정한다.

    확인하는 것:

    - 모든 출력(surface, displacement)에 셰이더가 물려 있는가
    - MaterialX 문서로 내보낼 수 있는가. 없다면 어느 노드 때문인가
    - MaterialX 가 문서를 유효하다고 하는가 (타입·정의 검사)
    - 참조하는 텍스처 파일이 실제로 있는가
    - 노드에 에러·경고가 있는가

    Args:
        path: 머티리얼 노드 경로. 예: /mat/wall_stone
    """
    material = require_material(path)

    outputs = []
    for name in material.outputNames():
        shader = terminal_shader(material, name)
        outputs.append({"output": name, "connected": shader is not None})

    missing_textures = []
    for entry in _texture_parms(material):
        resolved = Path(entry["resolved"])
        # UDIM 토큰이 든 경로는 그 자체로는 존재하지 않는다. texture_info 가 센다.
        if "<UDIM>" in entry["raw"] or "<udim>" in entry["raw"]:
            continue
        if not resolved.is_file():
            missing_textures.append({**entry, "exists": False})

    problems: list[str] = []
    for entry in outputs:
        if not entry["connected"]:
            problems.append(
                f"출력 {entry['output']} 에 셰이더가 물려 있지 않습니다."
            )
    for entry in missing_textures:
        problems.append(
            f"텍스처 파일이 없습니다: {entry['raw']} ({entry['node']}/{entry['parm']})"
        )

    check = _materialx_check(material)
    if check.get("exportable") and not check.get("materialx_valid", True):
        problems.append(f"MaterialX 검증 실패: {check.get('materialx_message')}")

    errors = list(material.errors())
    warnings = list(material.warnings())
    problems.extend(errors)

    return {
        "path": material.path(),
        "kind": material_kind(material),
        "comment": material.comment(),
        "valid": not problems,
        "problems": problems,
        "outputs": outputs,
        "missing_textures": missing_textures,
        "materialx": check,
        "errors": errors,
        "warnings": warnings,
    }
