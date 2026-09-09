"""Houdini UI 가 준비된 뒤 MCP 서버를 띄운다.

이 파일이 서버 패키지의 진입점이다. uiready.py 를 고른 이유:

  - HOUDINI_PATH 상의 모든 패키지에서 실행된다(123.py 처럼 하나만 이기지 않는다).
  - 툴 패키지의 pythonrc.py 가 전부 끝난 뒤에 실행된다. 단계 경계는 Houdini 가
    보장하므로, 이 시점에는 모든 툴이 이미 레지스트리에 등록되어 있다.
  - UI 가 완전히 뜬 뒤라 hdefereval 의 이벤트 루프를 믿을 수 있다.

근거는 tests/package_order 의 실측 테스트에 고정해 두었다.
"""

import traceback

SDK_HINT = (
    "MCP SDK 를 찾지 못해 서버를 띄우지 않습니다. "
    'Houdini 의 파이썬에 설치하세요:  "$HFS/bin/hython" -m pip install mcp'
)


def _main() -> None:
    try:
        from houdini_mcp.logs import configure, get_logger
    except Exception:
        # 로거조차 못 가져오면 패키지 경로 자체가 잘못된 것이다.
        print("[houdini_mcp] 패키지를 로드하지 못했습니다. hpath 설정을 확인하세요.")
        traceback.print_exc()
        return

    log_dir = configure()
    log = get_logger("startup")
    if log_dir is not None:
        log.info("로그 디렉토리: %s", log_dir)

    try:
        from houdini_mcp import server
    except ImportError:
        log.error("%s", SDK_HINT)
        log.debug("%s", traceback.format_exc())
        return

    try:
        server.start()
    except Exception:
        # 서버 실패가 Houdini 기동을 막으면 안 된다.
        log.exception("서버 기동에 실패했습니다. Houdini 는 계속 사용할 수 있습니다.")


_main()
