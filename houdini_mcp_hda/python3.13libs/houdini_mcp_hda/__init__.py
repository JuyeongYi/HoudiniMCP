"""HDA 저작·관리 툴 팩 — 서브넷을 디지털 에셋으로 굽고, 인터페이스를 짓고,
설치하고, 버전 관리한다.

    create      서브넷 → HDA, 정의 복사
    interface   HDA **정의**의 파라미터 인터페이스 — 추가·승격·삭제·재배치
    sections    정의 안의 섹션 — PythonModule, OnCreated 등 콜백 스크립트
    manage      설치·해제·리로드·조회
    vcs         Git 친화 디렉토리로 펼치고 다시 접기
    check       인스턴스를 실제로 놓고 쿡해서 검증

`houdini_mcp_base` 의 parmedit 과 경계가 다르다. 거기는 **노드 인스턴스 하나**에
스페어 파라미터를 붙인다(그 노드에만 남는다). 여기는 **HDA 정의**의 인터페이스를
고친다(그 타입의 모든 인스턴스가 함께 바뀌고 .hda 파일에 저장된다).

파라미터 템플릿을 만드는 일은 base 의 `parmtemplate` 헬퍼를 그대로 쓴다.
DialogScript 문자열을 손으로 조립하지 않는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "create",
    "interface",
    "sections",
    "manage",
    "vcs",
    "check",
)
