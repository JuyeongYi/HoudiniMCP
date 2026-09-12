"""컴포지션이 끝난 USD 스테이지를 조회하는 툴들.

읽기 전용이다. 전부 `hou.LopNode.stage()` 가 주는 `pxr.Usd.Stage` 를 본다.
LOP 노드의 파라미터는 보지 않는다 - 파라미터는 컴포지션 이전의 지시문이지
결과가 아니다.

스테이지는 크다. 프림 수십만 개가 흔하므로 모든 순회 툴에 깊이·개수 제한을
둔다. 제한에 걸리면 결과에 `truncated` 가 붙는다.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from .usdcommon import (
    HOUDINI_LAYER_INFO,
    brief_prim,
    jsonify,
    prim_at,
    resolve_lop,
    stage_of,
)

DEFAULT_LOP = "/stage"
"""LOP 네트워크 기본 경로. 네트워크를 주면 디스플레이 노드의 스테이지를 본다."""


def _predicate(include_inactive: bool, include_unloaded: bool):
    """`Usd.PrimRange` 에 줄 술어를 만든다.

    기본값은 `Usd.PrimDefaultPredicate` - 활성이고 정의됐고 로드된 프림만.
    디버깅할 때는 비활성 프림도 봐야 한다.
    """
    from pxr import Usd

    predicate = Usd.PrimIsDefined & ~Usd.PrimIsAbstract
    if not include_inactive:
        predicate = predicate & Usd.PrimIsActive
    if not include_unloaded:
        predicate = predicate & Usd.PrimIsLoaded
    return predicate


@tool()
def stage_info(lop: str = DEFAULT_LOP, frame: float | None = None) -> dict[str, Any]:
    """스테이지 요약 - 프림 수, 타입별 분포, 레이어 수, up axis, 단위, 시간 범위.

    스테이지를 처음 볼 때 여기서 시작한다. 어떤 타입이 몇 개 있는지 알면
    find_prims 로 무엇을 찾을지 정할 수 있다.

    Args:
        lop: LOP 노드 경로. LOP 네트워크(기본값 /stage)를 주면 디스플레이
            노드의 스테이지를 본다.
        frame: 이 프레임에서 쿡한 스테이지를 본다. 생략하면 현재 프레임.
    """
    from pxr import UsdGeom

    node = resolve_lop(lop)
    stage = stage_of(node, frame)

    default_prim = stage.GetDefaultPrim()
    root = stage.GetRootLayer()

    return {
        "lop": node.path(),
        "comment": node.comment(),
        "prim_counts": node.stagePrimStats(do_kind_counts=True),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "time_codes_per_second": stage.GetTimeCodesPerSecond(),
        "frames_per_second": stage.GetFramesPerSecond(),
        "has_authored_time_range": stage.HasAuthoredTimeCodeRange(),
        "start_time_code": stage.GetStartTimeCode(),
        "end_time_code": stage.GetEndTimeCode(),
        "default_prim": str(default_prim.GetPath()) if default_prim else None,
        "root_layer": root.identifier,
        "root_sublayers": list(root.subLayerPaths),
        "layer_stack_size": len(stage.GetLayerStack()),
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }


@tool()
def list_prims(
    lop: str = DEFAULT_LOP,
    root: str = "/",
    depth: int = 2,
    limit: int = 200,
    include_inactive: bool = False,
    frame: float | None = None,
) -> dict[str, Any]:
    """계층을 깊이·개수 제한을 두고 훑는다.

    씬 그래프의 모양을 파악할 때 쓴다. 제한에 걸리면 `truncated` 가 True 가
    되므로, 그때는 root 를 더 깊은 곳으로 옮겨 가며 나눠 본다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        root: 순회를 시작할 프림 경로. "/" 는 스테이지 전체.
        depth: root 아래로 몇 단계까지 내려갈지. 1 이면 바로 아래 자식만.
        limit: 돌려줄 프림 수 상한. 스테이지는 크므로 반드시 건다.
        include_inactive: True 면 비활성 프림도 포함한다.
        frame: 이 프레임에서 쿡한 스테이지를 본다.
    """
    from pxr import Usd

    node = resolve_lop(lop)
    stage = stage_of(node, frame)

    start = stage.GetPseudoRoot() if root in ("", "/") else prim_at(stage, root)
    base_depth = start.GetPath().pathElementCount

    rng = Usd.PrimRange(start, _predicate(include_inactive, True))
    prims: list[dict[str, Any]] = []
    truncated = False

    for prim in rng:
        if prim == start or prim.GetTypeName() == HOUDINI_LAYER_INFO:
            continue
        level = prim.GetPath().pathElementCount - base_depth
        if level > depth:
            rng.PruneChildren()
            continue
        if len(prims) >= limit:
            truncated = True
            break
        prims.append(brief_prim(prim))

    return {
        "lop": node.path(),
        "root": root,
        "depth": depth,
        "count": len(prims),
        "truncated": truncated,
        "prims": prims,
    }


@tool()
def find_prims(
    lop: str = DEFAULT_LOP,
    pattern: str = "/**",
    limit: int = 200,
    traversal: str = "default",
) -> dict[str, Any]:
    """Houdini 의 프림 패턴으로 프림을 찾는다.

    `hou.LopSelectionRule` 을 쓴다. 와일드카드뿐 아니라 술어도 된다.

        /world/**                   /world 아래 전부
        %type:Sphere                Sphere 타입 전부
        %type:UsdLuxDistantLight    디스턴트 라이트 전부
        /world/lights/*             한 단계만
        %kind:component             kind 로
        /world/** & %type:Mesh      교집합

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        pattern: 프림 패턴.
        limit: 돌려줄 프림 수 상한.
        traversal: 순회 조건. "default"(활성·정의·로드됨), "all"(전부),
            "defined", "active", "loaded" 중 하나.
    """
    node = resolve_lop(lop)
    stage = stage_of(node)

    demands = {
        "default": hou.lopTraversalDemands.Default,
        "all": hou.lopTraversalDemands.NoDemands,
        "defined": hou.lopTraversalDemands.Defined,
        "active": hou.lopTraversalDemands.Active,
        "loaded": hou.lopTraversalDemands.Loaded,
    }
    if traversal not in demands:
        raise ValueError(
            f"traversal 값이 잘못됐습니다: {traversal!r}. "
            f"{', '.join(sorted(demands))} 중 하나를 주세요."
        )

    rule = hou.LopSelectionRule()
    rule.setPathPattern(pattern)
    rule.setTraversalDemands(demands[traversal])

    try:
        paths = rule.expandedPaths(node)
    except hou.Error as exc:
        raise ValueError(
            f"패턴을 풀지 못했습니다: {pattern!r} ({exc}). "
            f"'/world/**' 이나 '%type:Sphere' 같은 형태인지 확인하세요."
        ) from exc

    error = rule.lastError()
    prims = [brief_prim(stage.GetPrimAtPath(p)) for p in paths[:limit]]

    return {
        "lop": node.path(),
        "pattern": pattern,
        "count": len(prims),
        "total_matched": len(paths),
        "truncated": len(paths) > limit,
        "pattern_error": error or None,
        "prims": prims,
    }


@tool()
def prim_info(
    lop: str = DEFAULT_LOP,
    primpath: str = "/",
    include_attributes: bool = True,
    frame: float | None = None,
) -> dict[str, Any]:
    """프림 하나의 전부 - 타입, 스키마, 가시성, 바운드, 머티리얼 바인딩, 배리언트.

    컴포지션이 끝난 뒤의 상태다. 값이 어디서 왔는지 알고 싶으면 prim_origin 을
    쓴다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 프림 경로. 예: /world/ball
        include_attributes: True 면 어트리뷰트 이름과 값이 있는지 여부를 함께
            준다. 값 자체는 get_attribute 로 읽는다.
        frame: 이 프레임에서 쿡한 스테이지를 본다.
    """
    from pxr import Usd, UsdGeom, UsdShade

    node = resolve_lop(lop)
    stage = stage_of(node, frame)
    prim = prim_at(stage, primpath)

    info: dict[str, Any] = {
        "lop": node.path(),
        "path": str(prim.GetPath()),
        "name": prim.GetName(),
        "type": str(prim.GetTypeName()) or None,
        "specifier": str(prim.GetSpecifier()).rsplit(".", 1)[-1],
        "kind": Usd.ModelAPI(prim).GetKind() or None,
        "active": prim.IsActive(),
        "loaded": prim.IsLoaded(),
        "instanceable": prim.IsInstanceable(),
        "is_instance": prim.IsInstance(),
        "has_payload": prim.HasAuthoredPayloads(),
        "applied_schemas": list(prim.GetAppliedSchemas()),
        "children": [child.GetName() for child in prim.GetChildren()],
        "documentation": prim.GetDocumentation() or None,
    }

    imageable = UsdGeom.Imageable(prim)
    if imageable:
        info["visibility"] = str(imageable.ComputeVisibility())
        info["purpose"] = str(imageable.ComputePurpose())
        cache = UsdGeom.BBoxCache(
            Usd.TimeCode(frame) if frame is not None else Usd.TimeCode.Default(),
            [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
        )
        rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        info["world_bbox"] = (
            None if rng.IsEmpty() else [list(rng.GetMin()), list(rng.GetMax())]
        )

    xformable = UsdGeom.Xformable(prim)
    if xformable:
        info["xform_ops"] = [op.GetOpName() for op in xformable.GetOrderedXformOps()]

    binding = UsdShade.MaterialBindingAPI(prim)
    if binding:
        bound = binding.ComputeBoundMaterial()[0]
        info["material_binding"] = str(bound.GetPath()) if bound else None

    variant_sets = prim.GetVariantSets()
    names = variant_sets.GetNames()
    if names:
        info["variant_sets"] = {
            name: {
                "selection": variant_sets.GetVariantSet(name).GetVariantSelection()
                or None,
                "variants": list(
                    variant_sets.GetVariantSet(name).GetVariantNames()
                ),
            }
            for name in names
        }

    if include_attributes:
        info["attributes"] = [
            {
                "name": attr.GetName(),
                "type": str(attr.GetTypeName()),
                "authored": attr.HasAuthoredValue(),
                "time_varying": attr.ValueMightBeTimeVarying(),
            }
            for attr in prim.GetAttributes()
        ]
        info["relationships"] = [rel.GetName() for rel in prim.GetRelationships()]

    return info


@tool()
def prim_stats(
    lop: str = DEFAULT_LOP,
    primpath: str = "/",
    geometry_counts: bool = True,
    frame: float | None = None,
) -> dict[str, Any]:
    """프림 아래의 통계 - 타입별 개수, 지오메트리 양, kind, 페이로드 로드 상태.

    Houdini 가 C++ 쪽에서 한 번에 세 준다. 파이썬으로 순회하는 것보다 훨씬
    빠르고, 점·폴리곤 수까지 나온다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 통계를 낼 프림 경로. "/" 면 스테이지 전체.
        geometry_counts: True 면 점·폴리곤 수까지 센다. 무거우면 끈다.
        frame: 이 프레임에서 쿡한 스테이지를 본다.
    """
    node = resolve_lop(lop)
    kwargs: dict[str, Any] = {
        "do_geometry_counts": geometry_counts,
        "do_kind_counts": True,
        "do_separate_purposes": True,
    }
    if primpath not in ("", "/"):
        # 경로가 실제로 있는지 먼저 확인해야 빈 통계 대신 쓸모 있는 에러가 나간다.
        prim_at(stage_of(node, frame), primpath)
        kwargs["primpath"] = primpath
    if frame is not None:
        kwargs["frame"] = frame

    return {
        "lop": node.path(),
        "primpath": primpath,
        "stats": jsonify(node.stagePrimStats(**kwargs)),
    }
