"""모든 작업의 토대가 되는 툴 팩.

어떤 컨텍스트에서 무엇을 하든 쓰이는 것들을 담는다. 모듈로만 나눈다.

    info       씬·노드·그래프 조회
    edit       네트워크 종류를 가리지 않는 노드 생성·조작·연결
    parms      파라미터 조회
    parmedit   파라미터 자체를 고친다 - 스페어 추가, 링크, 잠금, 되돌리기
    transform  노드 변환과 OBJ 계층 - world/parm/local/pre 를 갈라서 본다
    context    노드 트리와 의존 관계 - 직접 연결뿐 아니라 간접 참조까지
    explain    노드 하나를 종합 설명 - 다섯 번 부르던 것을 한 번으로
    analyze    네트워크 전체를 훑는다 - 요약, 쿡 순서, 비싼 노드, 스냅샷 비교
    geometry   지오메트리 통계·어트리뷰트 - SOP 뿐 아니라 DOP 등에서도 필요하다
    cache      디스크 캐시 - 쓰고, 최신인지 보고, 지운다
    viewport   뷰포트 캡처와 프레이밍 - 만든 결과를 눈으로 확인한다
    visualize  어트리뷰트 비주얼라이저 - 값이 어떻게 퍼져 있는지 색으로 본다
    nodetypes  노드 타입 카탈로그 - 무엇을 만들 수 있는지 먼저 본다
    scene      씬 파일 저장·열기, 프레임 범위
    takes      테이크 - 파라미터 변형을 갈라 두고 오간다
    diagnose   에러·경고 조회와 쿡 - 무엇이 잘못됐는지 알아낸다
    anim       파라미터 식과 키프레임
    execute    툴로 안 되는 일을 하는 탈출구. 마지막 수단이다

툴이 없는 모듈은 TOOL_MODULES 에 넣지 않는다.

    parmtemplate  hou.ParmTemplate 을 만드는 공통 헬퍼. parmedit 과
                  houdini_mcp_hda 가 함께 쓴다
    paths         경로 전개·원문 보존·시퀀스·$HFS. 경로를 다루는 팩은 전부
                  이것을 쓰고 자기 헬퍼를 두지 않는다

특정 컨텍스트에만 의미가 있는 툴은 전용 팩(houdini_mcp_sop 등)으로 분리한다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "info",
    "edit",
    "parms",
    "parmedit",
    "transform",
    "context",
    "explain",
    "analyze",
    "geometry",
    "cache",
    "viewport",
    "visualize",
    "nodetypes",
    "scene",
    "takes",
    "diagnose",
    "anim",
    "execute",
)
