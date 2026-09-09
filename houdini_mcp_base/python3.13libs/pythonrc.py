"""houdini_mcp_base 진입점. 툴을 레지스트리에 등록한다.

pythonrc.py 는 HOUDINI_PATH 상의 모든 패키지에서 실행되고, 서버 패키지의
uiready.py 보다 반드시 먼저 실행된다. 그래서 팩끼리의 로드 순서는 신경 쓸
필요가 없다.
"""

PACKAGE = "houdini_mcp_base"

try:
    from houdini_mcp.pack import register_pack
except ImportError:
    print(f"[{PACKAGE}] houdini_mcp 를 찾지 못했습니다. 서버 패키지 설치를 확인하세요.")
else:
    register_pack(PACKAGE)
