"""레이어 스택과 **값의 출처**.

`prim_origin` 이 이 팩의 핵심이다. USD 에서 "이 값이 왜 이 값인가"는 컴포지션
결과이지 한 군데를 읽어서 알 수 있는 것이 아니다. 서브레이어·레퍼런스·배리언트가
겹쳐 있을 때 어느 레이어의 어느 의견이 이겼는지, 그리고 Houdini 에서는 **어느 LOP
노드가 그 레이어를 만들었는지**까지 알려 준다.

레이어가 익명이라도 `husd.GetEditorNodesForLayer` 가 그 레이어를 쓴 LOP 노드를
돌려주므로, "이 값은 /stage/mat_override 가 걸었다"까지 답할 수 있다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from houdini_mcp import tool

from .usdcommon import arc_brief, jsonify, layer_brief, prim_at, resolve_lop, stage_of

DEFAULT_LOP = "/stage"

MAX_LAYER_CHARS = 20000
"""레이어를 텍스트로 내보낼 때의 상한. 레이어 하나가 수백 MB 일 수 있다."""


def _arc_index(prim) -> dict[tuple[str, str], dict[str, Any]]:
    """(레이어 identifier, 프림 경로) -> 그 자리를 만든 아크."""
    from pxr import Usd

    index: dict[tuple[str, str], dict[str, Any]] = {}
    for arc in Usd.PrimCompositionQuery(prim).GetCompositionArcs():
        layer = arc.GetTargetLayer()
        if layer is None:
            continue
        index.setdefault(
            (layer.identifier, str(arc.GetTargetPrimPath())), arc_brief(arc)
        )
    return index


@tool()
def layer_stack(lop: str = DEFAULT_LOP, include_session: bool = False) -> dict[str, Any]:
    """스테이지의 루트 레이어 스택 - 어떤 레이어가 어떤 순서로 겹쳐 있는가.

    Houdini 의 LOP 스테이지는 레이어가 거의 다 익명이라 identifier 만 보면
    주소값뿐이다. 그래서 `husd` 가 붙여 주는 이름과 그 레이어를 만든 LOP 노드를
    함께 준다.

    앞에 오는 것이 강하다(먼저 이긴다).

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        include_session: True 면 세션 레이어(뷰포트 오버라이드, 솔로, 가시성
            토글 등)도 함께 준다. 보통은 볼 필요가 없다.
    """
    import husd

    node = resolve_lop(lop)
    stage = stage_of(node)
    root = stage.GetRootLayer()

    layers = []
    for entry in husd.GetRootLayerStackInfo(root):
        brief = layer_brief(entry.layer)
        brief["parent_layer"] = (
            entry.parentLayer.identifier if entry.parentLayer else None
        )
        brief["offset"] = entry.offset.offset
        brief["scale"] = entry.offset.scale
        brief["prim_specs"] = len(entry.layer.rootPrims)
        layers.append(brief)

    result: dict[str, Any] = {
        "lop": node.path(),
        "root_layer": root.identifier,
        "active_layer": node.activeLayer().identifier,
        "count": len(layers),
        "layers": layers,
    }

    if include_session:
        session = stage.GetSessionLayer()
        result["session_layer"] = session.identifier
        result["session_layers"] = [
            layer_brief(entry.layer) for entry in husd.GetRootLayerStackInfo(session)
        ]

    return result


@tool()
def layer_contents(
    lop: str = DEFAULT_LOP,
    identifier: str = "",
    primpath: str | None = None,
    max_chars: int = MAX_LAYER_CHARS,
) -> dict[str, Any]:
    """레이어의 실제 내용을 USDA 텍스트로 본다.

    컴포지션 결과가 아니라 그 레이어가 **혼자 무엇을 말하고 있는지** 본다.
    "이 노드가 대체 뭘 쓴 거지"를 확인할 때 가장 빠르다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        identifier: 레이어 identifier. layer_stack 이나 prim_origin 이 돌려준
            것을 그대로 넣는다. 비우면 그 LOP 노드의 active layer.
        primpath: 이 프림 스펙만 본다. 생략하면 레이어 전체.
        max_chars: 돌려줄 텍스트 길이 상한.
    """
    from pxr import Sdf

    node = resolve_lop(lop)
    stage = stage_of(node)

    if identifier:
        layer = Sdf.Layer.Find(identifier)
        if layer is None:
            known = [entry.layer.identifier for entry in _all_layers(stage)]
            raise ValueError(
                f"그런 레이어가 열려 있지 않습니다: {identifier!r}. "
                f"layer_stack 이 돌려준 identifier 를 그대로 쓰세요. "
                f"지금 열린 것: {', '.join(known[:10])}"
            )
    else:
        layer = node.activeLayer()

    if primpath:
        spec = layer.GetPrimAtPath(primpath)
        if spec is None:
            raise ValueError(
                f"이 레이어에는 {primpath} 에 대한 의견이 없습니다. "
                f"prim_origin 으로 어느 레이어가 그 프림을 말하는지 먼저 봅니다."
            )
        # Sdf.PrimSpec 에는 ExportToString 이 없다. 임시 레이어로 복사해 뽑는다.
        # CopySpec 은 대상에 부모 스펙이 먼저 있어야 하므로 경로를 만들어 둔다.
        scratch = Sdf.Layer.CreateAnonymous("houdini_mcp_lop_extract")
        Sdf.CreatePrimInLayer(scratch, primpath)
        Sdf.CopySpec(layer, primpath, scratch, primpath)
        text = scratch.ExportToString()
    else:
        text = layer.ExportToString()

    truncated = len(text) > max_chars
    return {
        "lop": node.path(),
        "layer": layer.identifier,
        "label": layer_brief(layer)["label"],
        "primpath": primpath,
        "truncated": truncated,
        "chars": len(text),
        "text": text[:max_chars],
    }


def _all_layers(stage):
    """루트와 세션 양쪽의 레이어 스택 정보를 이어 준다."""
    import husd

    return list(husd.GetRootLayerStackInfo(stage.GetRootLayer())) + list(
        husd.GetRootLayerStackInfo(stage.GetSessionLayer())
    )


@tool()
def prim_origin(
    lop: str = DEFAULT_LOP,
    primpath: str = "/",
    attribute: str | None = None,
    frame: float | None = None,
) -> dict[str, Any]:
    """이 프림(또는 어트리뷰트) 값이 **어느 레이어의 어느 아크에서 왔는가**.

    USD 디버깅의 핵심이다. 값이 예상과 다를 때 노드 파라미터를 아무리 봐도
    답이 안 나오는 이유는, 최종 값이 여러 레이어의 의견 중 가장 강한 것이기
    때문이다. 여기서는 그 의견들을 **강한 순서대로** 전부 보여 준다.

    각 의견에는 그것을 담은 레이어, 그 레이어를 만든 LOP 노드, 그리고 그
    레이어를 끌어온 컴포지션 아크(reference / payload / variant / inherit /
    sublayer)가 붙는다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 프림 경로.
        attribute: 어트리뷰트 이름을 주면 그 어트리뷰트의 의견 스택을 본다.
            생략하면 프림 자체의 스펙 스택.
        frame: 어트리뷰트 의견을 이 시각 기준으로 본다.
    """
    from pxr import Usd

    node = resolve_lop(lop)
    stage = stage_of(node, frame)
    prim = prim_at(stage, primpath)
    arcs = _arc_index(prim)

    opinions: list[dict[str, Any]] = []

    if attribute:
        attr = prim.GetAttribute(attribute)
        if not attr:
            authored = [
                a.GetName() for a in prim.GetAttributes() if a.HasAuthoredValue()
            ]
            raise ValueError(
                f"{primpath} 에 그런 어트리뷰트가 없습니다: {attribute!r}. "
                f"값이 걸린 것: {', '.join(authored[:20]) or '(없음)'}"
            )
        time = Usd.TimeCode(frame) if frame is not None else Usd.TimeCode.Default()
        for rank, spec in enumerate(attr.GetPropertyStack(time)):
            entry = _opinion(spec.layer, spec.path, rank, arcs)
            entry["value"] = jsonify(spec.default)
            entry["time_samples"] = spec.layer.GetNumTimeSamplesForPath(spec.path)
            opinions.append(entry)
        winning = {"value": jsonify(attr.Get(time))}
    else:
        for rank, spec in enumerate(prim.GetPrimStack()):
            entry = _opinion(spec.layer, spec.path, rank, arcs)
            entry["specifier"] = str(spec.specifier).rsplit(".", 1)[-1]
            entry["type"] = spec.typeName or None
            opinions.append(entry)
        winning = {"type": str(prim.GetTypeName()) or None}

    return {
        "lop": node.path(),
        "path": str(prim.GetPath()),
        "attribute": attribute,
        "winning": winning,
        "opinion_count": len(opinions),
        "opinions": opinions,
        "arcs": sorted(
            (a for a in arcs.values()),
            key=lambda a: (a["arc"], a["target_path"]),
        ),
    }


def _opinion(layer, path, rank: int, arcs: dict) -> dict[str, Any]:
    """의견 하나 - 레이어, 그 레이어를 만든 LOP 노드, 그리고 끌어온 아크."""
    brief = layer_brief(layer)
    key = (layer.identifier, str(path.GetPrimPath()))
    return {
        "rank": rank,
        "strongest": rank == 0,
        "layer": brief["identifier"],
        "label": brief["label"],
        "anonymous": brief["anonymous"],
        "editor_nodes": brief["editor_nodes"],
        "file": Path(layer.realPath).name if layer.realPath else None,
        "spec_path": str(path),
        "arc": arcs.get(key, {}).get("arc"),
        "arc_introduced_at": arcs.get(key, {}).get("introducing_path"),
    }
