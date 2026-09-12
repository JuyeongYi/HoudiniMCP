"""네트워크 전체를 훑어 무슨 일이 벌어지고 있는지 알아내는 툴들.

`explain_node` 가 노드 하나를 보는 것이라면 여기는 네트워크를 본다. 노드가
서른 개쯤 되면 하나씩 물어보는 것으로는 전체 그림이 잡히지 않는다.

**추측하지 않는다.** 어느 노드가 비싼지는 이름이나 타입으로 짐작하지 않고
`lastCookTime()` / `cookCount()` 를 읽는다. 실측값이 없으면(아직 쿡하지 않은
노드) 그 사실을 그대로 알려 준다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import hou

from houdini_mcp import tool

from .diagnose import _messages

MAX_NODES = 500
"""한 번에 훑을 노드 수 상한. 큰 씬을 통째로 뱉으면 읽히지 않는다."""

MAX_LIST = 40
"""목록 하나에 담을 항목 수 상한."""

_SNAPSHOTS: dict[str, dict[str, Any]] = {}
"""`scene_snapshot` 이 남긴 것. 프로세스 안에서만 산다 - 씬에 저장되지 않는다."""


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _walk(root: hou.Node, depth: int) -> Iterator[tuple[hou.Node, int]]:
    """root 아래 노드를 너비 우선으로, 깊이 제한을 두고 훑는다."""
    stack: list[tuple[hou.Node, int]] = [(child, 1) for child in root.children()]
    seen = 0
    while stack:
        node, level = stack.pop(0)
        yield node, level
        seen += 1
        if seen >= MAX_NODES:
            return
        if level < depth:
            stack.extend((child, level + 1) for child in node.children())


def _flag(node: hou.Node, getter: str) -> bool:
    method = getattr(node, getter, None)
    if method is None:
        return False
    try:
        return bool(method())
    except hou.OperationFailed:
        return False


@tool()
def network_overview(path: str = "/obj", depth: int = 1) -> dict[str, Any]:
    """네트워크가 어떻게 생겼는지 한눈에 본다. 씬을 처음 볼 때 부른다.

    다음을 함께 준다.

      - 노드 수와 타입 분포 - 무엇으로 짜여 있는가
      - 출력 체인 - 결과(display/render 플래그)까지 실제로 이어지는 노드들
      - 고아 노드 - 아무 데도 이어지지 않아 결과에 기여하지 않는 것들
      - 문제 노드 - 에러나 경고가 붙은 것들

    고아 노드가 많으면 시행착오의 잔해가 쌓인 것이다. `delete_unused` 로
    치울 수 있다.

    Args:
        path: 네트워크 경로. 예: /obj, /obj/castle
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지.
    """
    root = _require(path)

    types: dict[str, int] = {}
    nodes: list[hou.Node] = []
    problems: list[dict[str, Any]] = []

    for node, _level in _walk(root, depth):
        nodes.append(node)
        name = node.type().name()
        types[name] = types.get(name, 0) + 1
        messages = _messages(node)
        if messages:
            problems.append(
                {"path": node.path(), "type": name, "comment": node.comment(), **messages}
            )

    # 결과로 이어지는 것: 플래그가 걸린 노드와 그 조상 전부.
    outputs = [n for n in root.children() if _flag(n, "isDisplayFlagSet") or _flag(n, "isRenderFlagSet")]
    chain: set[str] = set()
    for anchor in outputs:
        chain.add(anchor.path())
        try:
            chain.update(a.path() for a in anchor.inputAncestors())
        except hou.OperationFailed:
            pass

    # 고아: 출력 체인 밖이면서 아무도 입력으로 쓰지 않는 노드.
    orphans = [
        {"path": n.path(), "type": n.type().name(), "comment": n.comment()}
        for n in root.children()
        if n.path() not in chain and not n.outputs()
    ]

    ordered_types = sorted(types.items(), key=lambda kv: (-kv[1], kv[0]))
    result: dict[str, Any] = {
        "path": root.path(),
        "comment": root.comment(),
        "node_count": len(nodes),
        "type_counts": dict(ordered_types[:MAX_LIST]),
        "distinct_types": len(types),
        "output_nodes": [
            {"path": n.path(), "type": n.type().name(), "comment": n.comment()}
            for n in outputs
        ],
        "output_chain_size": len(chain),
        "orphans": orphans[:MAX_LIST],
        "orphan_count": len(orphans),
        "problem_count": len(problems),
        "problems": problems[:MAX_LIST],
    }
    if not outputs and root.children():
        result["note"] = (
            "display 나 render 플래그가 걸린 노드가 없어 결과가 무엇인지 알 수 "
            "없습니다. set_flags 로 지정하세요."
        )
    if len(nodes) >= MAX_NODES:
        result["truncated"] = (
            f"노드가 {MAX_NODES}개를 넘어 잘렸습니다. depth 를 줄이거나 하위 "
            f"경로를 지정해서 다시 부르세요."
        )
    return result


@tool()
def cook_chain(path: str) -> dict[str, Any]:
    """이 노드가 나오기까지 무엇이 어떤 순서로 쿡되는지 보여 준다.

    결과가 이상할 때 어디서부터 잘못됐는지 거슬러 올라가는 데 쓴다. 순서는
    실제 의존 관계로 만든 것이라, 앞에 있는 노드가 먼저 계산된다.

    입력 연결만 따라간다. Object Merge 나 파라미터 식으로 거는 간접 참조는
    `node_references` 로 따로 본다.

    Args:
        path: 결과가 될 노드 경로. 예: /obj/castle/OUT
    """
    target = _require(path)

    order: list[hou.Node] = []
    seen: set[str] = set()

    def visit(node: hou.Node) -> None:
        # 입력을 먼저 다 훑고 자기를 담는다. 그러면 나온 순서가 곧 쿡 순서다.
        if node.path() in seen or len(order) >= MAX_NODES:
            return
        seen.add(node.path())
        for source in node.inputs():
            if source is not None:
                visit(source)
        order.append(node)

    visit(target)

    steps = []
    for index, node in enumerate(order):
        entry: dict[str, Any] = {
            "step": index,
            "path": node.path(),
            "type": node.type().name(),
            "comment": node.comment(),
        }
        if _flag(node, "isBypassed"):
            entry["bypassed"] = True
        messages = _messages(node)
        if messages:
            entry.update(messages)
        steps.append(entry)

    return {
        "target": target.path(),
        "depth": len(order),
        "chain": steps,
        "truncated": len(order) >= MAX_NODES,
    }


@tool()
def find_expensive_nodes(
    root: str = "/obj", depth: int = 3, top: int = 15
) -> dict[str, Any]:
    """어느 노드가 시간을 잡아먹는지 **실측값으로** 찾는다.

    `lastCookTime()` 과 `cookCount()` 를 읽는다. 타입이나 이름으로 짐작하지
    않는다.

    아직 쿡하지 않은 노드는 시간이 0 이다 - 빠른 것이 아니라 **잰 적이 없는
    것**이다. 결과의 `never_cooked` 가 그런 노드 수다. 제대로 재려면
    `cook_node` 로 한 번 돌린 뒤 다시 부른다.

    Args:
        root: 훑기 시작할 경로.
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지.
        top: 느린 순으로 몇 개까지 보여줄지.
    """
    if top < 1:
        raise ValueError(f"top 은 1 이상이어야 합니다: {top}")
    scope = _require(root)

    measured: list[dict[str, Any]] = []
    never = 0
    total = 0.0
    scanned = 0

    for node, _level in _walk(scope, depth):
        scanned += 1
        count_fn = getattr(node, "cookCount", None)
        time_fn = getattr(node, "lastCookTime", None)
        if count_fn is None or time_fn is None:
            continue
        try:
            count = count_fn()
            seconds = time_fn()
        except hou.OperationFailed:
            continue
        if not count:
            never += 1
            continue
        total += seconds
        measured.append(
            {
                "path": node.path(),
                "type": node.type().name(),
                "comment": node.comment(),
                "last_seconds": round(seconds, 4),
                "cook_count": count,
                "time_dependent": _flag(node, "isTimeDependent"),
            }
        )

    measured.sort(key=lambda e: e["last_seconds"], reverse=True)
    result: dict[str, Any] = {
        "root": scope.path(),
        "scanned": scanned,
        "measured": len(measured),
        "never_cooked": never,
        "total_seconds": round(total, 4),
        "slowest": measured[:top],
    }
    if never:
        result["note"] = (
            f"{never}개 노드는 쿡된 적이 없어 시간을 잴 수 없었습니다. "
            f"cook_node 로 돌린 뒤 다시 부르면 실측값이 나옵니다."
        )
    return result


def _snapshot(root: hou.Node, depth: int) -> dict[str, dict[str, Any]]:
    """비교에 쓸 상태를 뜬다. 무엇이 바뀌면 알고 싶은지가 담는 것을 정한다."""
    state: dict[str, dict[str, Any]] = {}
    for node, _level in _walk(root, depth):
        state[node.path()] = {
            "type": node.type().name(),
            "comment": node.comment(),
            "inputs": [n.path() if n else None for n in node.inputs()],
            # 기본값에서 벗어난 것만. 전부 담으면 스냅샷이 거대해진다.
            "parms": {p.name(): p.eval() for p in node.parms() if not p.isAtDefault()},
        }
    return state


@tool()
def scene_snapshot(label: str, root: str = "/obj", depth: int = 3) -> dict[str, Any]:
    """지금 상태를 떠 둔다. 나중에 `diff_scene` 으로 무엇이 바뀌었는지 본다.

    씬을 여러 번 고치다 보면 내가 무엇을 바꿨는지 잃어버린다. 고치기 전에 한 장
    떠 두고 고친 뒤 비교하면 된다.

    스냅샷은 프로세스 안에서만 산다. 씬 파일에 저장되지 않고 Houdini 를 다시
    띄우면 사라진다. 같은 label 로 다시 부르면 덮어쓴다.

    Args:
        label: 이 스냅샷을 부를 이름. 예: "before_bevel"
        root: 뜰 범위.
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지.
    """
    if not label or not label.strip():
        raise ValueError("label 이 비어 있습니다. 나중에 부를 이름을 주세요.")
    scope = _require(root)
    state = _snapshot(scope, depth)

    _SNAPSHOTS[label.strip()] = {
        "root": scope.path(),
        "depth": depth,
        "taken_at": time.time(),
        "state": state,
    }
    return {
        "label": label.strip(),
        "root": scope.path(),
        "node_count": len(state),
        "stored": sorted(_SNAPSHOTS),
    }


@tool()
def diff_scene(label: str, other: str | None = None) -> dict[str, Any]:
    """스냅샷과 지금(또는 다른 스냅샷)을 비교한다. 무엇이 바뀌었는지 본다.

    추가·삭제된 노드, 이름이 바뀐 연결, 값이 달라진 파라미터를 낸다. 고치기
    전에 `scene_snapshot` 을 먼저 떠 둬야 한다.

    Args:
        label: 기준이 될 스냅샷 이름.
        other: 비교 대상 스냅샷 이름. 생략하면 지금 씬과 비교한다.
    """
    before = _SNAPSHOTS.get(label)
    if before is None:
        stored = ", ".join(sorted(_SNAPSHOTS)) or "없음"
        raise ValueError(
            f"그런 스냅샷이 없습니다: {label!r}. 먼저 scene_snapshot 으로 떠 두세요. "
            f"지금 있는 것: {stored}"
        )

    if other is None:
        scope = hou.node(before["root"])
        if scope is None:
            raise ValueError(
                f"스냅샷을 뜬 경로가 사라졌습니다: {before['root']}. "
                f"비교할 것이 없습니다."
            )
        after_state = _snapshot(scope, before["depth"])
        after_label = "현재"
    else:
        after = _SNAPSHOTS.get(other)
        if after is None:
            raise ValueError(f"그런 스냅샷이 없습니다: {other!r}")
        after_state = after["state"]
        after_label = other

    before_state = before["state"]
    added = sorted(set(after_state) - set(before_state))
    removed = sorted(set(before_state) - set(after_state))

    changed: list[dict[str, Any]] = []
    for path in sorted(set(before_state) & set(after_state)):
        old, new = before_state[path], after_state[path]
        entry: dict[str, Any] = {}
        if old["inputs"] != new["inputs"]:
            entry["inputs"] = {"was": old["inputs"], "now": new["inputs"]}
        if old["comment"] != new["comment"]:
            entry["comment"] = {"was": old["comment"], "now": new["comment"]}

        parm_diff = {}
        for name in set(old["parms"]) | set(new["parms"]):
            was, now = old["parms"].get(name), new["parms"].get(name)
            if was != now:
                parm_diff[name] = {"was": was, "now": now}
        if parm_diff:
            entry["parms"] = parm_diff
        if entry:
            changed.append({"path": path, **entry})

    return {
        "label": label,
        "compared_to": after_label,
        "root": before["root"],
        "added": [{"path": p, "type": after_state[p]["type"]} for p in added[:MAX_LIST]],
        "added_count": len(added),
        "removed": [{"path": p, "type": before_state[p]["type"]} for p in removed[:MAX_LIST]],
        "removed_count": len(removed),
        "changed": changed[:MAX_LIST],
        "changed_count": len(changed),
        "identical": not (added or removed or changed),
    }
