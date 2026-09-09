"""모든 작업의 토대가 되는 툴 팩.

어떤 컨텍스트에서 무엇을 하든 쓰이는 것들을 담는다. 모듈로만 나눈다.

    info      씬·노드·그래프 조회
    edit      네트워크 종류를 가리지 않는 노드 생성·조작·연결
    parms     파라미터 조회
    geometry  지오메트리 통계·어트리뷰트 - SOP 뿐 아니라 DOP 등에서도 필요하다
    viewport  뷰포트 캡처와 프레이밍 - 만든 결과를 눈으로 확인한다

특정 컨텍스트에만 의미가 있는 툴은 전용 팩(houdini_mcp_sop 등)으로 분리한다.
"""

from . import edit, geometry, info, parms, viewport  # noqa: F401 - import 가 곧 등록이다

__all__ = ["edit", "geometry", "info", "parms", "viewport"]
