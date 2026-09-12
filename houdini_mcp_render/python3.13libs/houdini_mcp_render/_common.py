"""렌더 팩이 공유하는 Houdini·경로 헬퍼. 여기에는 툴이 없다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import sys
from pathlib import Path

import hou

MAX_TEXT = 1200
"""로그 한 줄이 응답을 잡아먹지 않도록 자르는 길이."""


def require_node(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def require_lop(path: str) -> hou.LopNode:
    """LOP 노드를 얻는다. 아니면 어디를 봐야 하는지 알려 준다."""
    node = require_node(path)
    if not isinstance(node, hou.LopNode):
        raise ValueError(
            f"{path} 는 LOP 노드가 아닙니다 (category={node.type().category().name()}). "
            f"/stage 아래의 LOP 경로를 주세요. 예: /stage/karmarendersettings1"
        )
    return node


def lop_stage(node: hou.LopNode):
    """LOP 노드가 만들어 내는 USD 스테이지.

    쿡을 강제한다. 쿡하지 않은 LOP 는 스테이지가 비어 있어서, 라이트가 없다는
    잘못된 진단을 내게 된다.
    """
    try:
        node.cook(force=False)
    except hou.OperationFailed as exc:
        raise RuntimeError(
            f"{node.path()} 를 쿡하지 못했습니다: {str(exc).splitlines()[0][:MAX_TEXT]}. "
            f"node_errors 로 원인을 보세요."
        ) from exc
    stage = node.stage()
    if stage is None:
        raise RuntimeError(
            f"{node.path()} 의 스테이지를 읽지 못했습니다. 노드가 쿡되는지 "
            f"cook_node 로 먼저 확인하세요."
        )
    return stage


def houdini_bin(name: str) -> Path:
    """$HFS/bin 의 실행 파일 경로.

    경로를 하드코딩하지 않는다. 확장자도 플랫폼마다 다르므로 $HFS 에서
    실제로 찾은 것을 쓴다.
    """
    root = Path(hou.text.expandString("$HFS")) / "bin"
    candidates = [root / name]
    if sys.platform == "win32":
        candidates.insert(0, root / f"{name}.exe")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(
        f"{name} 을(를) $HFS/bin 에서 찾지 못했습니다 ({root}). "
        f"Houdini 설치가 온전한지 확인하세요."
    )


def expand_path(path: str, frame: float | None = None) -> Path:
    """$HIP/$F4 같은 Houdini 변수를 풀어 실제 경로로 만든다.

    렌더 출력 경로는 거의 항상 변수를 담고 있다. 그대로 파일로 열면 없는
    파일이 된다.
    """
    text = str(path)
    if frame is None:
        expanded = hou.text.expandString(text)
    else:
        expanded = hou.text.expandStringAtFrame(text, float(frame))
    return Path(expanded)


def require_file(path: str, frame: float | None = None) -> Path:
    """파일이 실제로 있는지까지 확인한다."""
    resolved = expand_path(path, frame)
    if not resolved.exists():
        hint = ""
        parent = resolved.parent
        if parent.exists():
            siblings = sorted(p.name for p in parent.iterdir() if p.is_file())[:8]
            if siblings:
                hint = f" 같은 디렉토리에 있는 것: {', '.join(siblings)}"
        else:
            hint = f" 디렉토리 자체가 없습니다: {parent}"
        raise ValueError(f"그런 파일이 없습니다: {resolved}.{hint}")
    if not resolved.is_file():
        raise ValueError(f"{resolved} 는 파일이 아닙니다.")
    return resolved


def writable_dir(path: Path) -> tuple[bool, str]:
    """출력 경로의 디렉토리에 쓸 수 있는지. (가능한가, 이유) 를 돌려준다."""
    parent = path.parent
    if parent.exists():
        if not parent.is_dir():
            return False, f"{parent} 가 디렉토리가 아닙니다."
        return True, "이미 있습니다."
    # husk 는 --make-output-path 로 만들어 준다. 만들 수 있는 자리인지만 본다.
    for ancestor in parent.parents:
        if ancestor.exists():
            return True, f"{ancestor} 아래에 새로 만들어집니다."
    return False, f"{parent} 를 만들 수 있는 상위 디렉토리가 없습니다."


def clip(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
