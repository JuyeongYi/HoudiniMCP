"""테이크를 다루는 툴들.

테이크는 파라미터 값의 변형을 갈라 두는 장치다. 같은 씬에서 "낮 버전"과 "밤
버전"을 만들 때, 노드를 복제하는 대신 테이크를 나누면 달라지는 파라미터만
따로 기억된다.

테이크에 **담긴** 파라미터만 그 테이크에서 따로 움직인다. 담기지 않은 것은
모든 테이크가 같은 값을 공유한다. 그래서 테이크를 만들고 나서 무엇을 담을지
정해 줘야 한다 - `take_include` 가 그 일을 한다.

테이크를 바꾸면 씬의 여러 파라미터 값이 한꺼번에 달라지므로 `@undoable` 로
감싼다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/Take.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

MAX_PARMS = 100


def _require_take(name: str) -> hou.Take:
    take = hou.takes.findTake(name)
    if take is None:
        available = ", ".join(t.name() for t in _all_takes(hou.takes.rootTake()))
        raise ValueError(
            f"그런 테이크가 없습니다: {name!r}. 지금 있는 것: {available}"
        )
    return take


def _all_takes(take: hou.Take) -> list[hou.Take]:
    """테이크 트리를 평평하게 편다."""
    out = [take]
    for child in take.children():
        out.extend(_all_takes(child))
    return out


def _require_node(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _describe(take: hou.Take) -> dict[str, Any]:
    parent = take.parent()
    return {
        "name": take.name(),
        "path": take.path(),
        "parent": parent.name() if parent is not None else None,
        "current": bool(take.isCurrent()),
        "children": [c.name() for c in take.children()],
        "parm_count": len(take.parmTuples()),
    }


@tool()
def list_takes() -> dict[str, Any]:
    """씬의 테이크를 전부 나열하고 지금 어느 것이 켜져 있는지 알려 준다.

    파라미터 값이 예상과 다르면 다른 테이크에 있는지 먼저 확인한다.
    """
    root = hou.takes.rootTake()
    current = hou.takes.currentTake()
    takes = _all_takes(root)
    return {
        "current": current.name(),
        "root": root.name(),
        "count": len(takes),
        "takes": [_describe(t) for t in takes],
    }


@tool()
@undoable("Create take")
def create_take(
    name: str, parent: str | None = None, set_current: bool = True
) -> dict[str, Any]:
    """테이크를 만든다.

    부모 테이크에서 갈라져 나오므로, 부모에서 바꾼 것은 자식에도 반영된다.
    부모를 생략하면 지금 켜져 있는 테이크 아래에 만든다.

    만든 직후에는 담긴 파라미터가 없다 - 아직 아무것도 따로 움직이지 않는다.
    `take_include` 로 무엇을 이 테이크에서 따로 바꿀지 정한다.

    이름은 씬 파일에 저장되고 Houdini UI 에 그대로 뜨므로 영어로 쓴다.

    Args:
        name: 새 테이크 이름. 영어로. 예: "night_lighting"
        parent: 부모 테이크 이름. 생략하면 지금 테이크.
        set_current: 만들고 나서 이 테이크로 전환한다.
    """
    if not name or not name.strip():
        raise ValueError("name 이 비어 있습니다.")
    name = name.strip()
    if hou.takes.findTake(name) is not None:
        raise ValueError(f"이미 있는 테이크 이름입니다: {name!r}. 다른 이름을 쓰세요.")

    base = _require_take(parent) if parent else hou.takes.currentTake()
    try:
        take = base.addChildTake(name)
    except hou.OperationFailed as exc:
        raise ValueError(f"{name!r} 테이크를 만들지 못했습니다. ({exc})") from exc
    if set_current:
        hou.takes.setCurrentTake(take)
    return {**_describe(take), "created_under": base.name()}


@tool()
@undoable("Set current take")
def set_current_take(name: str) -> dict[str, Any]:
    """켜져 있는 테이크를 바꾼다.

    그 테이크에 담긴 파라미터들의 값이 한꺼번에 달라진다. 기본 테이크로
    돌아가려면 `list_takes` 의 root 이름(대개 "Main")을 준다.

    Args:
        name: 전환할 테이크 이름.
    """
    take = _require_take(name)
    was = hou.takes.currentTake().name()
    hou.takes.setCurrentTake(take)
    return {"was": was, "current": hou.takes.currentTake().name(), **_describe(take)}


@tool()
@undoable("Delete take")
def delete_take(name: str, recurse: bool = False) -> dict[str, Any]:
    """테이크를 지운다. 그 테이크에만 있던 파라미터 값은 사라진다.

    기본 테이크(root)는 지울 수 없다. 자식 테이크가 있으면 recurse 를 켜야
    한다 - 함께 사라지는 것을 모르고 지우는 일을 막기 위해서다.

    Args:
        name: 지울 테이크 이름.
        recurse: 자식 테이크까지 함께 지운다.
    """
    take = _require_take(name)
    root = hou.takes.rootTake()
    if take.path() == root.path():
        raise ValueError(
            f"기본 테이크({root.name()})는 지울 수 없습니다. 다른 테이크를 지우세요."
        )

    children = [c.name() for c in take.children()]
    if children and not recurse:
        raise ValueError(
            f"{name!r} 아래에 테이크가 {len(children)}개 있습니다: "
            f"{', '.join(children)}. 함께 지우려면 recurse=True 를 주세요."
        )

    if take.isCurrent():
        # 켜져 있는 테이크는 지울 수 없다. 먼저 빠져나온다.
        hou.takes.setCurrentTake(root)
    removed = [t.name() for t in _all_takes(take)]
    take.destroy()
    return {
        "deleted": removed,
        "count": len(removed),
        "current": hou.takes.currentTake().name(),
    }


@tool()
@undoable("Include parameters in take")
def take_include(
    name: str, path: str, parms: list[str] | None = None, include: bool = True
) -> dict[str, Any]:
    """어떤 파라미터를 이 테이크에서 따로 움직이게 할지 정한다.

    담기지 않은 파라미터는 모든 테이크가 같은 값을 쓴다. 이 테이크에서만 다른
    값을 주고 싶으면 먼저 담아야 한다.

    parms 를 생략하면 그 노드의 **기본값에서 벗어난 파라미터를 전부** 담는다.
    이미 값을 다 걸어 둔 노드를 통째로 테이크에 넣을 때 편하다.

    벡터 파라미터는 튜플 단위로 담긴다 - `tx` 하나만 담아도 `tx/ty/tz` 가
    함께 들어간다. Houdini 가 그렇게 다룬다.

    Args:
        name: 테이크 이름.
        path: 노드 경로.
        parms: 담을 파라미터 이름들. 생략하면 기본값이 아닌 것 전부.
        include: False 면 담긴 것을 도로 뺀다.
    """
    take = _require_take(name)
    node = _require_node(path)

    if parms:
        tuples = []
        for parm_name in parms:
            parm_tuple = node.parmTuple(parm_name)
            if parm_tuple is None:
                parm = node.parm(parm_name)
                parm_tuple = parm.tuple() if parm is not None else None
            if parm_tuple is None:
                raise ValueError(
                    f"{path} 에 그런 파라미터가 없습니다: {parm_name}. "
                    f"list_parms 로 이름을 확인하세요."
                )
            tuples.append(parm_tuple)
    else:
        tuples = [
            parm.tuple()
            for parm in node.parms()
            if not parm.isAtDefault() and parm.tuple() is not None
        ]
        # 벡터는 성분마다 같은 튜플이 나오므로 중복을 없앤다.
        tuples = list({t.name(): t for t in tuples}.values())

    if not tuples:
        raise ValueError(
            f"{path} 에 담을 파라미터가 없습니다. 기본값에서 벗어난 것이 없으면 "
            f"parms 로 직접 지정하세요."
        )

    changed = []
    for parm_tuple in tuples:
        if include:
            take.addParmTuple(parm_tuple)
        else:
            take.removeParmTuple(parm_tuple)
        changed.append(parm_tuple.name())

    return {
        "take": take.name(),
        "path": node.path(),
        "included" if include else "removed": changed,
        "take_parm_count": len(take.parmTuples()),
    }


@tool()
def take_includes(name: str) -> dict[str, Any]:
    """이 테이크가 어떤 파라미터를 담고 있는지 본다.

    테이크를 바꿔도 값이 안 변하면 그 파라미터가 담기지 않은 것이다. 여기서
    확인하고 `take_include` 로 담는다.

    Args:
        name: 테이크 이름.
    """
    take = _require_take(name)
    entries: list[dict[str, Any]] = []
    for parm_tuple in take.parmTuples():
        node = parm_tuple.node()
        entries.append(
            {
                "node": node.path(),
                "comment": node.comment(),
                "parm": parm_tuple.name(),
                "components": [p.name() for p in parm_tuple],
                "value": list(parm_tuple.eval()),
            }
        )
        if len(entries) >= MAX_PARMS:
            break

    return {
        **_describe(take),
        "parms": entries,
        "truncated": len(take.parmTuples()) > MAX_PARMS,
    }
