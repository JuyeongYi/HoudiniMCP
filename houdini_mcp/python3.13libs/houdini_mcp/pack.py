"""툴 팩 등록 진입점.

툴 팩의 pythonrc.py 는 이것만 부르면 된다. 팩마다 같은 try/except 와 로깅을
반복하지 않도록 여기 모았다.

    # houdini_mcp_sop/python3.13libs/pythonrc.py
    try:
        from houdini_mcp.pack import register_pack
    except ImportError:
        print("[houdini_mcp_sop] houdini_mcp 를 찾지 못했습니다.")
    else:
        register_pack("houdini_mcp_sop")
"""

from __future__ import annotations

import importlib

from .logs import get_tool_logger
from .registry import get_registry


def register_pack(package: str) -> list[str]:
    """툴 팩 모듈을 import 해서 툴을 등록한다. 등록된 툴 이름을 돌려준다.

    등록은 모듈을 읽는 것만으로 일어난다(`@tool` 데코레이터). 그래서 여기서는
    import 만 하면 된다.

    팩 하나가 실패해도 Houdini 기동이나 다른 팩을 막지 않는다. 실패는 그 팩의
    로거로 남으므로, 로그의 category 만 봐도 어느 팩이 문제인지 알 수 있다.
    """
    log = get_tool_logger(package)

    try:
        importlib.import_module(package)
    except Exception:
        log.exception("툴 등록에 실패했습니다.")
        return []

    names = [spec.name for spec in get_registry().all() if spec.package == package]
    if names:
        log.info("툴 %d개 등록: %s", len(names), ", ".join(names))
    else:
        log.warning("등록된 툴이 없습니다. @tool 데코레이터를 붙였는지 확인하세요.")
    return names
