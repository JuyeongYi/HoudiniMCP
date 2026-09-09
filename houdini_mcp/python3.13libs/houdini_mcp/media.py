"""툴이 이미지 같은 미디어를 돌려줄 때 쓰는 헬퍼.

MCP SDK 는 함수 안에서 import 한다. 툴 팩이 SDK 유무와 무관하게 등록될 수 있어야
하기 때문이다 - 툴 팩은 pythonrc 단계에서 등록되는데, 그때 SDK 를 끌어오면 SDK 가
없는 환경에서 팩 전체가 등록에 실패한다.
"""

from __future__ import annotations

from typing import Any

IMAGE_FORMATS = ("png", "jpg", "jpeg", "exr")


def image_result(data: bytes, image_format: str = "png") -> Any:
    """바이트를 MCP 이미지 콘텐츠로 감싼다.

    툴이 이것을 돌려주면 모델이 그림을 실제로 볼 수 있다.

    Args:
        data: 이미지 바이트.
        image_format: 확장자 없는 포맷 이름. png, jpg 등.
    """
    from mcp.server.mcpserver.utilities.types import Image

    return Image(data=data, format=image_format)
