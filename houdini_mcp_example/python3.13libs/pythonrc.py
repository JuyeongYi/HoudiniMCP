"""houdini_mcp_example 진입점. 툴을 레지스트리에 등록한다.

새 툴 팩을 만들 때 이 파일은 팩 이름만 바꿔서 그대로 쓰면 된다.
"""

PACKAGE = "houdini_mcp_example"

try:
    from houdini_mcp.pack import register_pack
except ImportError:
    print(f"[{PACKAGE}] houdini_mcp 를 찾지 못했습니다. 서버 패키지 설치를 확인하세요.")
else:
    register_pack(PACKAGE)
