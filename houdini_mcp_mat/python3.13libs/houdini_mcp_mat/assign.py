"""머티리얼을 지오메트리에 걸고, 실제로 걸렸는지 확인하는 툴.

거는 것보다 **확인하는 것**이 이 모듈의 요점이다. 파라미터를 세팅하고
{"ok": true} 를 돌려주지 않는다.

    SOP  쿡한 뒤 shop_materialpath 프리미티브 어트리뷰트를 벌크로 읽어
         실제로 몇 개의 프리미티브에 걸렸는지 센다.
    LOP  UsdShade.MaterialBindingAPI 로 **컴포지션이 끝난 스테이지**에서
         바인딩을 질의한다. Assign 노드의 파라미터를 다시 읽지 않는다.
    OBJ  오브젝트 레벨 shop_materialpath 파라미터.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import hou

from houdini_mcp import tool, undoable

from .common import (
    lop_stage,
    require_comment,
    require_node,
    set_comment,
)

MATERIAL_ATTRIB = "shop_materialpath"
"""Houdini 가 SOP 레벨에서 머티리얼 할당에 쓰는 어트리뷰트 이름."""

MAX_PRIMS = 500
"""LOP 스테이지에서 훑을 프림 수 상한. 스테이지는 수십만 프림이 될 수 있다."""


# ---- 머티리얼 경로 ---------------------------------------------------


def _usd_material_path(material: str) -> str:
    """VOP 노드 경로를 USD 머티리얼 프림 경로로 바꾼다.

    materiallibrary LOP 안의 VOP 머티리얼은 스테이지에서 matpathprefix 아래에
    나타난다. 사용자가 노드 경로를 줘도 프림 경로로 알아서 바꾼다.
    """
    node = hou.node(material)
    if node is None:
        # 이미 프림 경로다.
        return material
    if not isinstance(node, hou.VopNode):
        raise ValueError(
            f"{material} 는 셰이더 노드가 아닙니다. USD 머티리얼 프림 경로나 "
            f"VOP 머티리얼 노드 경로를 주세요."
        )

    library = node.parent()
    while library is not None and library.type().name() != "materiallibrary":
        library = library.parent()
    if library is None:
        raise ValueError(
            f"{material} 가 materiallibrary LOP 안에 있지 않습니다. "
            f"LOP 에 걸려면 머티리얼이 materiallibrary 안에 있어야 합니다. "
            f"또는 스테이지의 프림 경로를 직접 주세요. 예: /materials/wall_stone"
        )
    prefix_parm = library.parm("matpathprefix")
    prefix = prefix_parm.eval() if prefix_parm is not None else "/materials/"
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    return prefix + node.name()


# ---- 할당 ------------------------------------------------------------


def _assign_sop(
    target: hou.SopNode, material: str, comment: str, group: str
) -> dict[str, Any]:
    """SOP 뒤에 material SOP 을 달아 건다. 걸고 나서 어트리뷰트로 확인한다."""
    if hou.node(material) is None:
        raise ValueError(
            f"머티리얼 노드가 없습니다: {material}. "
            f"list_materials 로 씬의 머티리얼을 먼저 보세요."
        )

    parent = target.parent()
    node = parent.createNode("material", node_name=f"assign_{target.name()}")
    node.setInput(0, target)
    node.parm("shop_materialpath1").set(material)
    if group:
        node.parm("group1").set(group)
    set_comment(node, comment)
    node.moveToGoodPosition()

    # 디스플레이·렌더 플래그를 넘겨받아야 결과가 실제로 보인다.
    if target.isGenericFlagSet(hou.nodeFlag.Display):
        node.setDisplayFlag(True)
    if target.isGenericFlagSet(hou.nodeFlag.Render):
        node.setRenderFlag(True)

    geometry = node.geometry()
    counts: dict[str, int] = {}
    if geometry is not None and geometry.findPrimAttrib(MATERIAL_ATTRIB) is not None:
        # 벌크 경로로 한 번에 읽는다. 프리미티브를 파이썬으로 돌지 않는다.
        counts = dict(Counter(geometry.primStringAttribValues(MATERIAL_ATTRIB)))

    assigned = counts.get(material, 0)
    return {
        "context": "sop",
        "node": node.path(),
        "comment": node.comment(),
        "material": material,
        "group": group or "*",
        "prims_assigned": assigned,
        "prims_total": len(geometry.prims()) if geometry is not None else 0,
        "assignments_by_material": counts,
        "verified": assigned > 0,
    }


def _assign_lop(
    target: hou.LopNode, material: str, comment: str, prim_pattern: str
) -> dict[str, Any]:
    """LOP 뒤에 assignmaterial 을 달고, 스테이지에서 바인딩을 확인한다."""
    from pxr import UsdShade

    prim_path = _usd_material_path(material)
    parent = target.parent()
    node = parent.createNode("assignmaterial", node_name=f"assign_{target.name()}")
    node.setInput(0, target)
    node.parm("primpattern1").set(prim_pattern or "%type:Mesh")
    node.parm("matspecpath1").set(prim_path)
    set_comment(node, comment)
    node.moveToGoodPosition()
    node.setDisplayFlag(True)

    stage = node.stage()
    bound = []
    if stage is not None:
        for index, prim in enumerate(stage.Traverse()):
            if index >= MAX_PRIMS:
                break
            if not prim.HasRelationship("material:binding"):
                continue
            api = UsdShade.MaterialBindingAPI(prim)
            material_prim, _ = api.ComputeBoundMaterial()
            if material_prim and str(material_prim.GetPath()) == prim_path:
                bound.append(str(prim.GetPath()))

    return {
        "context": "lop",
        "node": node.path(),
        "comment": node.comment(),
        "material": prim_path,
        "prim_pattern": node.parm("primpattern1").eval(),
        "bound_prims": bound,
        "bound_count": len(bound),
        "verified": bool(bound),
        "hint": (
            None
            if bound
            else "바인딩된 프림이 없습니다. prim_pattern 을 확인하세요. "
            "list_prims 로 스테이지의 프림 경로를 먼저 보는 것이 빠릅니다."
        ),
    }


def _assign_obj(target: hou.ObjNode, material: str) -> dict[str, Any]:
    """오브젝트 레벨에 통째로 건다."""
    parm = target.parm("shop_materialpath")
    if parm is None:
        raise ValueError(
            f"{target.path()} 에는 shop_materialpath 파라미터가 없습니다. "
            f"지오메트리 오브젝트(geo)가 아닌 것 같습니다."
        )
    parm.set(material)
    return {
        "context": "obj",
        "node": target.path(),
        "material": parm.eval(),
        "verified": parm.eval() == material,
        "note": "오브젝트 전체에 걸렸습니다. 일부만 걸려면 SOP 경로를 주세요.",
    }


@tool()
@undoable("Assign material")
def assign_material(
    target: str,
    material: str,
    comment: str,
    group: str = "",
    prim_pattern: str = "",
) -> dict[str, Any]:
    """머티리얼을 지오메트리에 걸고, **실제로 걸렸는지 확인해서** 돌려준다.

    target 이 무엇이냐에 따라 올바른 방식을 고른다.

        SOP  뒤에 material SOP 을 달고 쿡한 뒤, shop_materialpath 어트리뷰트를
             읽어 몇 개의 프리미티브에 걸렸는지 센다. 0 이면 group 이 잘못된 것이다.
        LOP  뒤에 assignmaterial 을 달고, UsdShade 로 스테이지에서 바인딩을 질의한다.
        OBJ  shop_materialpath 파라미터를 걸어 오브젝트 전체에 적용한다.

    Args:
        target: 머티리얼을 걸 노드. SOP / LOP / OBJ 경로.
        material: 머티리얼 경로. VOP 노드 경로를 주면 LOP 에서는 USD 프림
            경로로 알아서 바꾼다. 예: /mat/wall_stone, /materials/wall_stone
        comment: 만들어지는 할당 노드에 달 코멘트. 필수. 영어로.
            예: "Stone material on the wall body"
        group: SOP 일 때만. 프리미티브 그룹이나 패턴. 비우면 전부.
        prim_pattern: LOP 일 때만. 프림 패턴. 비우면 %type:Mesh.
    """
    comment = require_comment(comment, "이 할당 노드")
    node = require_node(target)

    if isinstance(node, hou.SopNode):
        return _assign_sop(node, material, comment, group)
    if isinstance(node, hou.LopNode):
        return _assign_lop(node, material, comment, prim_pattern)
    if isinstance(node, hou.ObjNode):
        return _assign_obj(node, material)

    raise ValueError(
        f"{target} 에는 머티리얼을 걸 수 없습니다 "
        f"({node.type().category().name()}). SOP, LOP, 또는 OBJ 노드를 주세요."
    )


# ---- 조회 ------------------------------------------------------------


def _sop_assignments(node: hou.SopNode) -> dict[str, Any]:
    """SOP 지오메트리의 머티리얼 어트리뷰트를 벌크로 읽는다."""
    geometry = node.geometry()
    if geometry is None:
        raise ValueError(
            f"{node.path()} 의 지오메트리를 읽지 못했습니다. "
            f"노드가 쿡되지 않았을 수 있습니다."
        )

    result: dict[str, Any] = {
        "context": "sop",
        "node": node.path(),
        "comment": node.comment(),
        "prims": len(geometry.prims()),
        "by_material": {},
        "unassigned_prims": len(geometry.prims()),
    }

    scopes = (
        ("prim", geometry.findPrimAttrib, geometry.primStringAttribValues),
        ("point", geometry.findPointAttrib, geometry.pointStringAttribValues),
    )
    for scope, finder, values_of in scopes:
        if finder(MATERIAL_ATTRIB) is None:
            continue
        counts = Counter(values_of(MATERIAL_ATTRIB))
        result[f"{scope}_attribute"] = True
        if scope == "prim":
            result["by_material"] = dict(counts)
            result["unassigned_prims"] = counts.get("", 0)
        else:
            result["by_material_points"] = dict(counts)

    detail = geometry.findGlobalAttrib(MATERIAL_ATTRIB)
    if detail is not None:
        result["detail_material"] = geometry.stringAttribValue(MATERIAL_ATTRIB)

    # 걸린 머티리얼이 실제로 존재하는지까지 확인한다.
    missing = [
        path
        for path in result["by_material"]
        if path and hou.node(path) is None
    ]
    if missing:
        result["missing_materials"] = missing
        result["hint"] = (
            "이 경로에 머티리얼 노드가 없습니다. 이름이 바뀌었거나 지워졌습니다."
        )
    return result


def _lop_assignments(node: hou.LopNode, max_prims: int) -> dict[str, Any]:
    """LOP 스테이지의 실제 바인딩을 UsdShade 로 질의한다."""
    from pxr import UsdShade

    stage = lop_stage(node.path())
    direct: list[dict[str, str]] = []
    collections = 0
    scanned = 0
    for prim in stage.Traverse():
        scanned += 1
        if scanned > max_prims:
            break
        api = UsdShade.MaterialBindingAPI(prim)
        if prim.HasRelationship("material:binding"):
            material, relationship = api.ComputeBoundMaterial()
            if material:
                direct.append(
                    {
                        "prim": str(prim.GetPath()),
                        "type": str(prim.GetTypeName()),
                        "material": str(material.GetPath()),
                        "bound_by": str(relationship.GetPath()) if relationship else "",
                    }
                )
        if api.GetCollectionBindings():
            collections += 1

    by_material = Counter(entry["material"] for entry in direct)
    return {
        "context": "lop",
        "node": node.path(),
        "comment": node.comment(),
        "scanned_prims": min(scanned, max_prims),
        "truncated": scanned > max_prims,
        "bindings": direct,
        "by_material": dict(by_material),
        "prims_with_collection_bindings": collections,
    }


@tool()
def list_assignments(path: str, max_prims: int = 200) -> dict[str, Any]:
    """무엇에 어떤 머티리얼이 걸려 있는지 본다. 파라미터가 아니라 결과를 읽는다.

    SOP 이면 쿡된 지오메트리의 shop_materialpath 어트리뷰트를, LOP 이면
    컴포지션이 끝난 스테이지의 UsdShade 바인딩을 읽는다. Assign 노드가 무엇을
    걸었다고 주장하는지가 아니라 실제로 걸린 것을 본다.

    Args:
        path: SOP 또는 LOP 노드 경로.
        max_prims: LOP 일 때 훑을 프림 수 상한.
    """
    node = require_node(path)
    if isinstance(node, hou.SopNode):
        return _sop_assignments(node)
    if isinstance(node, hou.LopNode):
        return _lop_assignments(node, min(max_prims, MAX_PRIMS))
    raise ValueError(
        f"{path} 에서는 머티리얼 할당을 읽을 수 없습니다 "
        f"({node.type().category().name()}). SOP 이나 LOP 노드를 주세요."
    )
