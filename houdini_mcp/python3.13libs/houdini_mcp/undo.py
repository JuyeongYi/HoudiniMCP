"""씬을 바꾸는 툴을 Houdini Undo 그룹으로 감싸는 데코레이터.

툴 하나의 호출이 Undo 하나가 되어야 한다. 그래야 사용자가 Ctrl+Z 한 번으로
모델이 한 일을 되돌릴 수 있다. 툴 안에서 노드를 만들고 파라미터를 걸고 연결까지
했더라도 마찬가지다.

    from houdini_mcp import tool, undoable

    @tool()
    @undoable("Create node")
    def create_node(...):
        ...

데코레이터 순서가 중요하다. `@undoable` 이 아래(먼저 적용)에 와야 레지스트리에
등록되는 것이 Undo 로 감싼 함수가 된다.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

LABEL_PREFIX = "MCP: "
"""Undo 히스토리에서 모델이 한 일을 사람이 한 일과 구분하기 위한 접두사."""


def undoable(label: str | None = None) -> Callable[[F], F]:
    """툴 호출 하나를 Undo 하나로 묶는다.

    예외가 나도 그룹은 닫힌다. 중간까지 한 변경은 남으므로, 되돌리려면 사용자가
    Undo 를 누르면 된다.

    Args:
        label: Undo 히스토리에 보일 이름. Houdini UI 에 그대로 뜨므로 영어로 쓴다.
            생략하면 함수 이름을 쓴다.
    """

    def decorate(fn: F) -> F:
        name = label or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import hou

            with hou.undos.group(f"{LABEL_PREFIX}{name}"):
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorate
