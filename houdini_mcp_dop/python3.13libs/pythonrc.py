"""houdini_mcp_dop 진입점. 툴을 레지스트리에 등록한다.

pythonrc.py 는 HOUDINI_PATH 상의 모든 패키지에서 실행되고, 서버 패키지의
uiready.py 보다 반드시 먼저 실행된다. 그래서 팩끼리의 로드 순서는 신경 쓸
필요가 없다.

서버 패키지가 없거나 깨져 있어도 Houdini 기동을 막지 않는다. 그 경우 이 팩의
툴만 빠진다.
"""

import traceback

PACKAGE = "houdini_mcp_dop"

try:
    from houdini_mcp.pack import register_pack
except Exception:
    # ImportError 만이 아니라 무엇이든 잡는다. 서버 패키지가 깨져 있어도
    # Houdini 는 정상적으로 떠야 한다.
    print(f"[{PACKAGE}] houdini_mcp 를 읽지 못해 툴을 등록하지 않습니다.")
    traceback.print_exc()
else:
    register_pack(PACKAGE)
