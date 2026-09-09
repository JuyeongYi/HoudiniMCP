"""툴 팩 진입점. 툴을 레지스트리에 등록한다.

pythonrc.py 를 쓰는 이유:

  - HOUDINI_PATH 상의 모든 패키지에서 실행된다. 툴 팩을 여러 개 설치해도 전부
    등록된다(123.py 였다면 하나만 이기고 나머지는 조용히 무시된다).
  - 서버 패키지의 uiready.py 보다 반드시 먼저 실행된다. 단계 경계는 Houdini 가
    보장하므로, 툴 팩끼리의 로드 순서는 신경 쓸 필요가 없다.

여기서 서버를 import 하지 않는다는 점이 중요하다. 툴 팩은 레지스트리만 알면
된다.
"""

import traceback

PACKAGE = "houdini_mcp_tools_demo"


def _main() -> None:
    try:
        from houdini_mcp.logs import get_tool_logger
    except Exception:
        print(f"[{PACKAGE}] houdini_mcp 를 찾지 못했습니다. 서버 패키지가 설치됐는지 확인하세요.")
        traceback.print_exc()
        return

    log = get_tool_logger(PACKAGE)
    try:
        import houdini_mcp_tools_demo  # noqa: F401 - import 가 곧 등록이다
    except Exception:
        # 툴 팩 하나가 Houdini 기동을 막으면 안 된다.
        log.exception("툴 등록에 실패했습니다.")
        return

    from houdini_mcp import get_registry

    mine = [s.name for s in get_registry().all() if s.package == PACKAGE]
    log.info("툴 %d개 등록: %s", len(mine), ", ".join(mine))


_main()
