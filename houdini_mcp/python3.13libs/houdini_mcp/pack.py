"""툴 팩 등록 진입점.

툴 팩의 pythonrc.py 는 이것만 부르면 된다. 팩마다 같은 try/except 와 로깅을
반복하지 않도록 여기 모았다.

    # houdini_mcp_sop/python3.13libs/pythonrc.py
    PACKAGE = "houdini_mcp_sop"
    try:
        from houdini_mcp.pack import register_pack
    except Exception:
        ...
    else:
        register_pack(PACKAGE)

등록은 모듈 단위로 격리한다. 팩의 모듈 하나가 깨져도 나머지 툴은 등록된다.
어느 모듈이 왜 실패했는지는 그 팩의 로거에 남는다.
"""

from __future__ import annotations

import importlib
from typing import Sequence

from .logs import get_tool_logger
from .registry import get_registry

MODULES_ATTR = "TOOL_MODULES"
"""팩의 __init__.py 가 선언하는 툴 모듈 이름들.

    TOOL_MODULES = ("info", "edit")

선언하지 않으면 패키지를 통째로 import 한다(모듈 격리 없음).
"""


def register_pack(
    package: str, modules: Sequence[str] | None = None
) -> list[str]:
    """툴 팩의 툴을 레지스트리에 등록한다. 등록된 툴 이름을 돌려준다.

    등록은 모듈을 읽는 것만으로 일어난다(`@tool` 데코레이터). 그래서 여기서는
    import 만 하면 된다.

    무엇이 실패하든 예외를 밖으로 내보내지 않는다. 툴 팩 하나 때문에 Houdini
    기동이 막히거나 다른 팩이 등록되지 못하는 일이 없어야 한다.

    Args:
        package: 팩의 Python 패키지 이름.
        modules: 등록할 모듈 이름들. 생략하면 팩의 TOOL_MODULES 를 읽고, 그것도
            없으면 패키지를 통째로 import 한다.
    """
    log = get_tool_logger(package)

    targets = _resolve_modules(package, modules, log)
    if targets is None:
        return []

    failed: list[str] = []
    for target in targets:
        try:
            importlib.import_module(target)
        except Exception:
            # 모듈 하나가 깨져도 나머지는 등록한다.
            log.exception("모듈을 읽지 못했습니다: %s", target)
            failed.append(target)

    names = [spec.name for spec in get_registry().all() if spec.package == package]
    if names:
        log.info("툴 %d개 등록: %s", len(names), ", ".join(names))
    elif not failed:
        log.warning("등록된 툴이 없습니다. @tool 데코레이터를 붙였는지 확인하세요.")
    if failed:
        log.warning("%d개 모듈이 등록되지 않았습니다: %s", len(failed), ", ".join(failed))
    return names


def _resolve_modules(
    package: str, modules: Sequence[str] | None, log
) -> list[str] | None:
    """실제로 import 할 모듈 경로들을 정한다. 팩을 못 읽으면 None."""
    if modules is not None:
        return [f"{package}.{name}" for name in modules]

    try:
        pkg = importlib.import_module(package)
    except Exception:
        log.exception("팩을 읽지 못했습니다: %s", package)
        return None

    declared = getattr(pkg, MODULES_ATTR, None)
    if not declared:
        # 모듈을 선언하지 않은 팩은 __init__.py 가 알아서 다 끌어온 것으로 본다.
        return []
    return [f"{package}.{name}" for name in declared]
