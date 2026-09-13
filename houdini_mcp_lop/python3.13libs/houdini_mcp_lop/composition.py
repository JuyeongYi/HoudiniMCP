"""컴포지션 아크 - 레퍼런스, 페이로드, 서브레이어, 배리언트, 인헤릿.

읽기는 `Usd.PrimCompositionQuery` 로 한다. 쓰기는 각 아크에 해당하는 LOP 노드를
만든다 - `reference`, `sublayer`, `setvariant`. 아크를 스테이지에 직접 박지 않는
이유는 그것이 노드로 남지 않아 재쿡에 사라지기 때문이다.
"""

from __future__ import annotations

from typing import Any

from houdini_mcp import tool, undoable
from houdini_mcp_base import paths

from .usdcommon import (
    arc_brief,
    insert_lop,
    node_report,
    prim_at,
    resolve_lop,
    stage_of,
)

DEFAULT_LOP = "/stage"

REF_TYPES = ("file", "payload", "prim", "inherit", "specialize")
"""`reference` LOP 의 reftype 토큰. 실측으로 확인한 것 그대로다."""


@tool()
def composition_arcs(
    lop: str = DEFAULT_LOP,
    primpath: str = "/",
    arc_types: list[str] | None = None,
    include_ancestral: bool = True,
) -> dict[str, Any]:
    """이 프림에 걸린 컴포지션 아크 전부 - 무엇이 어디서 끌려왔는가.

    `Usd.PrimCompositionQuery` 를 쓴다. 노드 파라미터로는 절대 알 수 없는
    정보다 - 상위 프림에 걸린 레퍼런스가 자식까지 끌고 오는(ancestral) 경우가
    특히 그렇다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 프림 경로.
        arc_types: 이 종류만 본다. 예: ["reference", "payload", "variant"]
            생략하면 전부.
        include_ancestral: False 면 상위에서 상속된 아크를 뺀다. 이 프림에
            직접 걸린 것만 보고 싶을 때.
    """
    from pxr import Usd

    node = resolve_lop(lop)
    prim = prim_at(stage_of(node), primpath)

    arcs = []
    for arc in Usd.PrimCompositionQuery(prim).GetCompositionArcs():
        brief = arc_brief(arc)
        if arc_types and brief["arc"] not in arc_types:
            continue
        if not include_ancestral and brief["ancestral"]:
            continue
        arcs.append(brief)

    by_type: dict[str, int] = {}
    for brief in arcs:
        by_type[brief["arc"]] = by_type.get(brief["arc"], 0) + 1

    return {
        "lop": node.path(),
        "path": str(prim.GetPath()),
        "count": len(arcs),
        "by_type": by_type,
        "arcs": arcs,
    }


@tool()
def list_variants(lop: str = DEFAULT_LOP, primpath: str = "/") -> dict[str, Any]:
    """프림의 배리언트 셋과 각각의 선택지, 현재 선택.

    배리언트는 USD 에서 값이 통째로 갈리는 지점이다. 값이 이상하면 어느 배리언트가
    골라져 있는지부터 본다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 프림 경로.
    """
    node = resolve_lop(lop)
    prim = prim_at(stage_of(node), primpath)

    variant_sets = prim.GetVariantSets()
    sets = {}
    for name in variant_sets.GetNames():
        vset = variant_sets.GetVariantSet(name)
        sets[name] = {
            "variants": list(vset.GetVariantNames()),
            "selection": vset.GetVariantSelection() or None,
        }

    return {
        "lop": node.path(),
        "path": str(prim.GetPath()),
        "count": len(sets),
        "variant_sets": sets,
    }


@tool()
@undoable("Set variant")
def set_variant(
    lop: str,
    primpath: str,
    variant_set: str,
    variant: str,
    comment: str,
    node_name: str | None = None,
) -> dict[str, Any]:
    """배리언트를 고른다. `setvariant` LOP 을 끼워 넣는다.

    고른 뒤 스테이지를 다시 읽어 실제 선택과 프림 수 변화를 함께 돌려준다.

    Args:
        lop: 입력이 될 LOP 노드 경로.
        primpath: 배리언트 셋을 가진 프림 경로.
        variant_set: 배리언트 셋 이름.
        variant: 고를 배리언트 이름.
        comment: 왜 이 배리언트인지. 노드 코멘트로 남는다. 영어로 쓴다.
        node_name: 만들 노드 이름. 생략하면 배리언트 이름에서 짓는다.
    """
    node = resolve_lop(lop)
    prim = prim_at(stage_of(node), primpath)

    variant_sets = prim.GetVariantSets()
    if variant_set not in variant_sets.GetNames():
        raise ValueError(
            f"{primpath} 에 {variant_set!r} 배리언트 셋이 없습니다. "
            f"있는 것: {', '.join(variant_sets.GetNames()) or '(없음)'}"
        )
    choices = variant_sets.GetVariantSet(variant_set).GetVariantNames()
    if variant not in choices:
        raise ValueError(
            f"{variant_set!r} 에 {variant!r} 배리언트가 없습니다. "
            f"고를 수 있는 것: {', '.join(choices)}"
        )

    created, _ = insert_lop(
        node, "setvariant", node_name or f"pick_{variant_set}", comment
    )
    created.parm("num_variants").set(1)
    created.parm("primpattern1").set(primpath)
    created.parm("variantset1").set(variant_set)
    created.parm("variantname1").set(variant)

    after = prim_at(stage_of(created), primpath)
    return node_report(
        created,
        {
            "path": primpath,
            "variant_set": variant_set,
            "selection": after.GetVariantSets()
            .GetVariantSet(variant_set)
            .GetVariantSelection(),
            "prim_counts": created.stagePrimStats(),
        },
    )


@tool()
@undoable("Add reference")
def add_reference(
    lop: str,
    primpath: str,
    comment: str,
    file_path: str | None = None,
    reference_type: str = "file",
    source_prim: str | None = None,
    create_prims: bool = True,
    node_name: str | None = None,
) -> dict[str, Any]:
    """레퍼런스·페이로드·인헤릿·스페셜라이즈를 건다. `reference` LOP 을 끼워 넣는다.

    아크에는 두 갈래가 있다.

        file / payload            외부 USD 파일을 끌어온다. file_path 가 필요하다.
        prim / inherit / specialize  같은 스테이지 안의 프림을 끌어온다.
                                  source_prim 이 필요하고 file_path 는 쓰지 않는다.

    건 뒤에 실제로 무엇이 들어왔는지 - 프림 수와 바로 아래 자식들 - 을 함께
    돌려준다. 값이 어디서 왔는지는 prim_origin 으로 확인한다.

    Args:
        lop: 입력이 될 LOP 노드 경로.
        primpath: 아크를 걸 프림 경로. 예: /world/props/chair
        comment: 이 아크가 무엇인지. 노드 코멘트로 남는다. 영어로 쓴다.
        file_path: 끌어올 USD 파일 경로. file / payload 에만 쓴다.
        reference_type: "file"(레퍼런스), "payload"(지연 로드),
            "prim"(같은 스테이지 안의 프림), "inherit", "specialize".
        source_prim: file / payload 면 파일 안에서 끌어올 프림 경로(생략하면
            defaultPrim). prim / inherit / specialize 면 같은 스테이지 안의
            원본 프림 경로이며 반드시 필요하다.
        create_prims: 대상 프림이 없으면 만든다.
        node_name: 만들 노드 이름. 생략하면 대상 프림 이름에서 짓는다.
    """
    if reference_type not in REF_TYPES:
        raise ValueError(
            f"reference_type 이 잘못됐습니다: {reference_type!r}. "
            f"{', '.join(REF_TYPES)} 중 하나를 주세요."
        )

    node = resolve_lop(lop)
    from_file = reference_type in ("file", "payload")

    if from_file:
        if not file_path:
            raise ValueError(
                f"reference_type={reference_type!r} 에는 file_path 가 필요합니다. "
                f"같은 스테이지 안의 프림을 끌어오려면 reference_type 을 "
                f"'prim' / 'inherit' / 'specialize' 로 하고 source_prim 을 주세요."
            )
        # 없는 파일을 걸면 조용히 빈 프림이 되므로 여기서 미리 잡는다.
        try:
            paths.require_file(file_path)
        except ValueError as exc:
            raise ValueError(
                f"{exc} USD 파일 경로(.usd/.usda/.usdc/.usdz)를 확인하세요. "
                f"$HIP 같은 Houdini 변수를 써도 됩니다."
            ) from exc
    else:
        if not source_prim:
            raise ValueError(
                f"reference_type={reference_type!r} 에는 source_prim 이 "
                f"필요합니다. 같은 스테이지 안에서 끌어올 원본 프림 경로를 "
                f"주세요. 외부 파일을 끌어오려면 reference_type 을 'file' 이나 "
                f"'payload' 로 하고 file_path 를 주세요."
            )
        prim_at(stage_of(node), source_prim)

    leaf = primpath.rstrip("/").rsplit("/", 1)[-1] or "root"
    created, _ = insert_lop(node, "reference", node_name or f"ref_{leaf}", comment)
    created.parm("num_files").set(1)
    created.parm("primpath1").set(primpath)
    created.parm("reftype1").set(reference_type)
    created.parm("createprims1").set("on" if create_prims else "off")
    if from_file:
        created.parm("filepath1").set(paths.to_parm(file_path))
    if source_prim:
        # 빈 문자열이 "아래 경로를 그대로 쓴다"는 뜻이다(automaticPrim/defaultPrim 아님).
        created.parm("filerefprim1").set("")
        created.parm("filerefprimpath1").set(source_prim)

    stage = stage_of(created)
    prim = stage.GetPrimAtPath(primpath)

    return node_report(
        created,
        {
            "path": primpath,
            "file": file_path,
            "source_prim": source_prim,
            "reference_type": reference_type,
            "resolved": bool(prim),
            "children": [c.GetName() for c in prim.GetChildren()] if prim else [],
            "prim_counts": created.stagePrimStats(),
        },
    )


@tool()
@undoable("Add sublayer")
def add_sublayer(
    lop: str,
    file_path: str,
    comment: str,
    node_name: str | None = None,
) -> dict[str, Any]:
    """USD 파일을 서브레이어로 깐다. `sublayer` LOP 을 끼워 넣는다.

    레퍼런스와 다르다. 서브레이어는 파일 전체를 루트 레이어 스택에 통째로 얹는다
    - 프림 경로가 그대로 살아 있고, 씬 전체를 합칠 때 쓴다. 특정 프림 아래로
    끌어오려면 add_reference 를 쓴다.

    Args:
        lop: 입력이 될 LOP 노드 경로.
        file_path: 깔 USD 파일 경로.
        comment: 이 레이어가 무엇인지. 노드 코멘트로 남는다. 영어로 쓴다.
        node_name: 만들 노드 이름. 생략하면 파일 이름에서 짓는다.
    """
    node = resolve_lop(lop)

    try:
        expanded = paths.require_file(file_path)
    except ValueError as exc:
        raise ValueError(
            f"{exc} USD 파일 경로(.usd/.usda/.usdc/.usdz)를 확인하세요."
        ) from exc

    stem = expanded.stem or "layer"
    created, _ = insert_lop(node, "sublayer", node_name or f"sub_{stem}", comment)
    created.parm("num_files").set(1)
    created.parm("filepath1").set(paths.to_parm(file_path))

    stage = stage_of(created)
    return node_report(
        created,
        {
            "file": paths.describe(file_path),
            "root_sublayers": list(stage.GetRootLayer().subLayerPaths),
            "prim_counts": created.stagePrimStats(),
        },
    )
