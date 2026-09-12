"""임포트·익스포트·의존성 툴 팩 — 씬과 디스크 사이를 오간다.

    export   지오메트리·USD·Alembic·FBX 내보내기. 전부 **쓴 뒤 다시 읽어 검증**한다
    load     파일을 씬으로 들이기(`import` 는 예약어라 모듈명이 load 다)
    deps     씬이 무엇에 의존하는지 — 목록·수집·경로 치환
    check    이식성 점검

이 팩이 기존 구현과 갈라지는 지점은 둘이다.

1. **쓰고 끝내지 않는다.** 내보낸 파일을 포맷에 맞는 리더로 다시 열어
   점·프리미티브 수를 대조한다. 안 맞으면 안 맞는다고 돌려준다.
   `hou.Geometry.saveToFile()` 은 `.usd` / `.abc` / `.fbx` 확장자를 받고도
   내용은 ASCII `.geo` 를 쓴다(실측 확인). 다시 읽어 보지 않으면 이 거짓말을
   못 잡는다.
2. **의존성은 `hou.fileReferences()` 로 얻는다.** 파라미터 문자열을 훑지
   않는다. 식이 걸린 참조도 Houdini 가 알고 있다.

이미지 텍스처의 내용(해상도·채널·컬러스페이스)은 `houdini_mcp_mat` 의
`texture_info` / `list_textures` 가 다룬다. 여기는 **파일을 의존성으로** 다루고,
지오메트리·씬 파일의 내용을 읽는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "export",
    "load",
    "deps",
    "check",
)
