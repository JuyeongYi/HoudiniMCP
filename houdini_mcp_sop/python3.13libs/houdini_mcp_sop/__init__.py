"""SOP 전문 툴 팩 — 지오메트리를 만들고 고치고 읽는다.

컨텍스트를 가리지 않는 조회(`geometry_stats`, `list_attributes`, `sample_points`
등)는 `houdini_mcp_base` 의 geometry 모듈에 있다. 여기는 SOP 에서만 의미가 있는
것을 담는다.

    create     프리미티브·커브 생성, 포인트에 복사
    polyedit   폴리곤 편집 — 베벨·익스트루드·브리지·미러·리볼브·스킨·불리언
    topology   토폴로지 변환 — 컨버트·삼각화·리메시·감면·트랜스폼·삭제
    attribs    어트리뷰트 — numpy 벌크 통계, 노멀, 어트리뷰트 생성
    groups     그룹 생성과 멤버 조회
    uv         UV 투영·자동 UV·UV 품질 리포트
    query      근접 질의·레이 교차·인트린식·볼륨·파일 내보내기

이 팩의 조작 툴은 노드를 만들고 끝내지 않는다. 반드시 쿡해서 전후 통계를 비교해
돌려준다. 모델이 "베벨이 먹었는지"를 다시 묻지 않아도 되게 하기 위해서다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "create",
    "polyedit",
    "topology",
    "attribs",
    "groups",
    "uv",
    "query",
)
