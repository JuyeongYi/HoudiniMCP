"""노드의 변환과 계층을 다루는 툴들.

OBJ 노드는 자기 변환을 갖는다. 그런데 "이 노드가 어디 있나"는 물음에 답이
여럿이다. 실측으로 확인한 차이는 이렇다.

| 무엇 | 담는 것 |
|---|---|
| `worldTransform()` | 부모 체인까지 누적한 최종 위치. 뷰포트에 보이는 그것 |
| `parmTransform()` | t/r/s 파라미터만. 부모를 무시한다 |
| `localTransform()` | parmTransform 에 pre-transform 을 곱한 것 |
| `preTransform()` | 파라미터에 안 보이는 숨은 변환. "Clean Transform" 이 여기 쌓는다 |

부모에 tx=5 를 걸고 자식을 보면 world 의 translate 는 [5,0,0] 인데
parm/local 은 [0,0,0] 이다. **부모를 옮겨도 자식의 파라미터는 그대로다.**
어느 것을 고쳐야 하는지 헷갈리면 `get_transform` 으로 넷을 다 보고 정한다.

`hou.Matrix4` 를 그대로 돌려주지 않는다. 숫자 16개는 읽을 수 없으므로
`explode()` 로 t/r/s 로 풀어서 준다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/ObjNode.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

SPACES = ("world", "parm", "local", "pre")

# t/r/s 파라미터 이름. OBJ 노드는 전부 이 이름을 쓴다.
PARM_TRIPLES = {
    "translate": ("tx", "ty", "tz"),
    "rotate": ("rx", "ry", "rz"),
    "scale": ("sx", "sy", "sz"),
    "pivot": ("px", "py", "pz"),
    "pivot_rotate": ("prx", "pry", "prz"),
}


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _require_transformable(path: str) -> hou.Node:
    """변환을 가진 노드인지 확인한다. SOP 을 잘못 준 경우가 흔하다."""
    node = _require(path)
    if getattr(node, "worldTransform", None) is None:
        raise ValueError(
            f"{path} 에는 변환이 없습니다. OBJ 노드 경로를 주세요. "
            f"(이 노드는 {node.type().category().name()} 입니다. SOP 지오메트리를 "
            f"옮기려면 transform SOP 을 쓰거나 그 부모 OBJ 를 지정하세요.)"
        )
    return node


def _explode(matrix: hou.Matrix4) -> dict[str, list[float]]:
    """행렬을 t/r/s 로 푼다. 숫자 16개는 사람도 모델도 읽지 못한다."""
    try:
        parts = matrix.explode()
    except hou.OperationFailed as exc:
        # 특이 행렬은 분해되지 않는다. 그 사실을 알려 준다.
        raise ValueError(
            f"변환 행렬을 t/r/s 로 풀지 못했습니다 ({exc}). 스케일이 0 이거나 "
            f"행렬이 특이할 수 있습니다."
        ) from exc
    return {key: [v[0], v[1], v[2]] for key, v in parts.items()}


def _parm_values(node: hou.Node) -> dict[str, list[float]]:
    """t/r/s/pivot 파라미터 값. 고쳐야 할 대상이 무엇인지 바로 보이게."""
    out: dict[str, list[float]] = {}
    for key, names in PARM_TRIPLES.items():
        parms = [node.parm(name) for name in names]
        if all(parm is not None for parm in parms):
            out[key] = [parm.eval() for parm in parms]
    return out


def _set_triple(node: hou.Node, key: str, values: list[float]) -> list[str]:
    """t/r/s 세 성분을 건다. 건 파라미터 이름을 돌려준다."""
    names = PARM_TRIPLES[key]
    if len(values) != 3:
        raise ValueError(f"{key} 는 값 세 개여야 합니다: {values}")
    applied = []
    for name, value in zip(names, values):
        parm = node.parm(name)
        if parm is None:
            raise ValueError(
                f"{node.path()} 에 {name} 파라미터가 없습니다. "
                f"이 노드는 {key} 를 지원하지 않습니다."
            )
        parm.set(float(value))
        applied.append(name)
    return applied


@tool()
def get_transform(path: str) -> dict[str, Any]:
    """노드의 변환을 네 가지 공간으로 모두 본다.

    어느 것을 고쳐야 할지 정하려면 넷을 함께 봐야 한다.

      - `world`: 부모 체인까지 누적한 최종 위치. 뷰포트에 보이는 그것
      - `parm`: t/r/s 파라미터만. 부모를 무시한다
      - `local`: parm 에 pre-transform 을 곱한 것
      - `pre`: 파라미터에 안 보이는 숨은 변환

    world 와 parm 이 다르면 부모가 걸려 있다는 뜻이다. local 과 parm 이
    다르면 pre-transform 이 쌓여 있다.

    Args:
        path: OBJ 노드 경로. 예: /obj/castle
    """
    node = _require_transformable(path)
    parent = node.parent()
    result: dict[str, Any] = {
        "path": node.path(),
        "comment": node.comment(),
        "world": _explode(node.worldTransform()),
        "parm": _explode(node.parmTransform()),
        "local": _explode(node.localTransform()),
        "pre": _explode(node.preTransform()),
        "parms": _parm_values(node),
        "network_parent": parent.path() if parent is not None else None,
    }

    # OBJ 계층의 부모는 0번 입력이다. 네트워크 부모(/obj)와는 다른 것이다.
    inputs = node.inputs()
    result["transform_parent"] = inputs[0].path() if inputs and inputs[0] else None
    return result


@tool()
@undoable("Set transform")
def set_transform(
    path: str,
    translate: list[float] | None = None,
    rotate: list[float] | None = None,
    scale: list[float] | None = None,
    space: str = "parm",
) -> dict[str, Any]:
    """노드의 변환을 정한다. 준 것만 바뀐다.

    space 가 `parm`(기본)이면 t/r/s 파라미터를 그대로 건다. 부모가 걸려 있으면
    결과 위치는 부모 변환이 곱해진 것이 된다.

    space 가 `world` 면 **최종 위치**를 지정한다 - 부모 변환을 상쇄하도록
    파라미터가 역산되어 들어간다. 이때는 세 값을 다 줘야 한다(행렬을 통째로
    다시 세우기 때문이다). 생략한 것은 지금 world 값을 쓴다.

    회전은 도 단위 오일러 각이고 순서는 Houdini 기본인 xyz 다.

    Args:
        path: OBJ 노드 경로.
        translate: 위치 세 값. 예: [0, 2, 0]
        rotate: 회전 세 값(도). 예: [0, 45, 0]
        scale: 스케일 세 값. 예: [1, 2, 1]
        space: parm 또는 world.
    """
    if space not in ("parm", "world"):
        raise ValueError(
            f"space 는 'parm' 또는 'world' 여야 합니다: {space!r}. "
            f"parm 은 파라미터를 그대로, world 는 최종 위치를 지정합니다."
        )
    if translate is None and rotate is None and scale is None:
        raise ValueError("translate, rotate, scale 중 적어도 하나는 줘야 합니다.")

    node = _require_transformable(path)

    if space == "parm":
        applied: list[str] = []
        for key, values in (
            ("translate", translate),
            ("rotate", rotate),
            ("scale", scale),
        ):
            if values is not None:
                applied.extend(_set_triple(node, key, values))
        return {
            "path": node.path(),
            "applied": applied,
            "parms": _parm_values(node),
            "world": _explode(node.worldTransform()),
        }

    # world - 지금 world 를 기준으로 준 것만 갈아 끼우고 행렬을 다시 세운다.
    current = _explode(node.worldTransform())
    matrix = hou.hmath.buildTransform(
        {
            "translate": hou.Vector3(translate if translate is not None else current["translate"]),
            "rotate": hou.Vector3(rotate if rotate is not None else current["rotate"]),
            "scale": hou.Vector3(scale if scale is not None else current["scale"]),
        }
    )
    try:
        node.setWorldTransform(matrix)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{path} 의 월드 변환을 걸지 못했습니다 ({exc}). 부모 변환이 특이 "
            f"행렬이면 역산할 수 없습니다."
        ) from exc
    return {
        "path": node.path(),
        "space": "world",
        "parms": _parm_values(node),
        "world": _explode(node.worldTransform()),
    }


@tool()
@undoable("Set pivot")
def set_pivot(
    path: str, pivot: list[float] | None = None, pivot_rotate: list[float] | None = None
) -> dict[str, Any]:
    """회전·스케일의 중심점을 정한다.

    노드를 회전시켰는데 엉뚱한 곳을 축으로 돌면 피벗이 원점에 있어서다.
    예를 들어 문짝을 경첩에서 돌리려면 피벗을 경첩 위치로 옮긴다.

    피벗을 옮겨도 위치·회전·스케일 값은 그대로다. 회전이 이미 걸려 있으면
    최종 위치가 함께 움직이므로, `get_transform` 으로 결과를 확인한다.

    Args:
        path: OBJ 노드 경로.
        pivot: 중심점 세 값. 예: [0, 0, -1]
        pivot_rotate: 중심점의 기준 회전 세 값(도).
    """
    if pivot is None and pivot_rotate is None:
        raise ValueError("pivot 이나 pivot_rotate 중 적어도 하나는 줘야 합니다.")
    node = _require_transformable(path)

    applied: list[str] = []
    if pivot is not None:
        applied.extend(_set_triple(node, "pivot", pivot))
    if pivot_rotate is not None:
        applied.extend(_set_triple(node, "pivot_rotate", pivot_rotate))

    return {
        "path": node.path(),
        "applied": applied,
        "parms": _parm_values(node),
        "world": _explode(node.worldTransform()),
    }


@tool()
@undoable("Parent node")
def parent_node(path: str, parent: str, keep_position: bool = True) -> dict[str, Any]:
    """OBJ 노드를 다른 OBJ 노드에 붙인다. 부모가 움직이면 자식이 따라간다.

    Houdini 의 OBJ 계층은 **0번 입력**이다. 네트워크 안에서 어디에 놓여 있는지
    (`/obj` 아래냐 서브넷 안이냐)와는 다른 것이다.

    keep_position 이 True 면 붙인 뒤에도 눈에 보이는 위치가 그대로다 - 부모
    변환을 상쇄하도록 파라미터가 역산된다. False 면 파라미터를 그대로 둔 채
    부모 변환이 얹히므로 노드가 움직인다.

    끊으려면 `unparent_node` 를 쓴다.

    Args:
        path: 자식이 될 노드 경로.
        parent: 부모가 될 노드 경로.
        keep_position: 붙인 뒤에도 보이는 위치를 유지한다.
    """
    child = _require_transformable(path)
    new_parent = _require_transformable(parent)
    if child.path() == new_parent.path():
        raise ValueError(f"자기 자신을 부모로 삼을 수 없습니다: {path}")
    # 순환은 Houdini 가 막아 주지만 메시지가 불친절하다. 먼저 짚어 준다.
    if new_parent in child.inputAncestors():
        raise ValueError(
            f"{parent} 는 이미 {path} 아래에 있습니다. 붙이면 순환이 생깁니다. "
            f"먼저 unparent_node 로 떼어 내세요."
        )

    before = child.worldTransform()
    try:
        child.setFirstInput(new_parent)
    except hou.OperationFailed as exc:
        raise ValueError(f"{path} 를 {parent} 에 붙이지 못했습니다. ({exc})") from exc
    if keep_position:
        child.setWorldTransform(before)

    return {
        "path": child.path(),
        "parent": new_parent.path(),
        "parent_comment": new_parent.comment(),
        "keep_position": keep_position,
        "parms": _parm_values(child),
        "world": _explode(child.worldTransform()),
    }


@tool()
@undoable("Unparent node")
def unparent_node(path: str, keep_position: bool = True) -> dict[str, Any]:
    """OBJ 계층에서 부모를 뗀다.

    Args:
        path: 떼어 낼 노드 경로.
        keep_position: 뗀 뒤에도 보이는 위치를 유지한다.
    """
    child = _require_transformable(path)
    inputs = child.inputs()
    if not inputs or inputs[0] is None:
        raise ValueError(
            f"{path} 에는 붙은 부모가 없습니다. get_transform 의 "
            f"transform_parent 로 확인할 수 있습니다."
        )

    was = inputs[0].path()
    before = child.worldTransform()
    child.setFirstInput(None)
    if keep_position:
        child.setWorldTransform(before)

    return {
        "path": child.path(),
        "was_parented_to": was,
        "keep_position": keep_position,
        "parms": _parm_values(child),
        "world": _explode(child.worldTransform()),
    }


@tool()
@undoable("Set node lock")
def set_node_lock(
    path: str, hard: bool | None = None, soft: bool | None = None
) -> dict[str, Any]:
    """노드의 쿡 결과를 굳힌다. 하드 락과 소프트 락은 다르다.

    **하드 락**은 지금 쿡 결과를 노드 안에 통째로 저장한다. 입력을 바꿔도
    결과가 변하지 않고, 씬 파일에도 그 지오메트리가 들어가 파일이 커진다.
    무거운 계산 결과를 굳혀 두거나, 입력 없이 결과만 남길 때 쓴다.

    **소프트 락**은 결과를 저장하지 않고 다시 쿡하지 않게만 한다. 씬 파일이
    커지지 않는 대신, 씬을 다시 열면 결과가 없다.

    둘 다 파라미터 잠금(`lock_parm`)과는 다르다. 그쪽은 값이 바뀌는 것을
    막고, 이쪽은 결과가 다시 계산되는 것을 막는다.

    Args:
        path: 노드 경로. 락을 지원하는 것은 대개 SOP 이다.
        hard: 하드 락을 걸거나 푼다.
        soft: 소프트 락을 걸거나 푼다.
    """
    if hard is None and soft is None:
        raise ValueError("hard 나 soft 중 적어도 하나는 줘야 합니다.")
    node = _require(path)

    changed: dict[str, bool] = {}
    for key, value, setter in (("hard", hard, "setHardLocked"), ("soft", soft, "setSoftLocked")):
        if value is None:
            continue
        method = getattr(node, setter, None)
        if method is None:
            raise ValueError(
                f"{path} 는 {key} 락을 지원하지 않습니다. "
                f"(이 노드는 {node.type().category().name()} 입니다. 락은 대개 "
                f"SOP 에서 쓸 수 있습니다.)"
            )
        try:
            method(value)
        except hou.OperationFailed as exc:
            raise ValueError(
                f"{path} 에 {key} 락을 걸지 못했습니다 ({exc}). 노드가 쿡될 수 "
                f"있는 상태인지 cook_node 로 먼저 확인하세요."
            ) from exc
        changed[key] = value

    state: dict[str, Any] = {"path": node.path(), "comment": node.comment(), "changed": changed}
    for key, getter in (("hard_locked", "isHardLocked"), ("soft_locked", "isSoftLocked")):
        method = getattr(node, getter, None)
        if method is not None:
            state[key] = bool(method())
    return state
