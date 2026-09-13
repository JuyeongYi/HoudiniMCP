"""씬 파일을 저장하고 여는 툴들.

이게 없으면 만든 것이 Houdini 를 닫는 순간 사라진다. 실제로 성을 만들어 놓고
저장하지 못해 날아간 적이 있다.

파일을 덮어쓰거나 저장하지 않은 변경을 버리는 일은 되돌릴 수 없으므로, 그런
동작은 전부 명시적으로 요구한다(`overwrite`, `discard_changes`).

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool

from . import paths

# Apprentice 는 .hipnc 만 저장할 수 있다. 확장자를 강제하지 않고 안내만 한다.
LICENSE_EXT = {
    "Apprentice": ".hipnc",
    "ApprenticeHD": ".hipnc",
    "Indie": ".hiplc",
}


def _license_hint() -> tuple[str, str | None]:
    """(라이선스 이름, 강제되는 확장자 또는 None)."""
    name = str(hou.licenseCategory()).rsplit(".", 1)[-1]
    return name, LICENSE_EXT.get(name)


@tool()
def scene_path() -> dict[str, Any]:
    """현재 씬 파일 경로와 저장 상태.

    저장 전에 무엇을 덮어쓰게 되는지 확인할 때 쓴다.
    """
    name, ext = _license_hint()
    path = hou.hipFile.path()
    return {
        "path": path,
        "name": hou.hipFile.basename(),
        "exists": Path(path).exists(),
        "has_unsaved_changes": hou.hipFile.hasUnsavedChanges(),
        "license": name,
        "required_extension": ext,
    }


@tool()
def save_scene(path: str | None = None, overwrite: bool = False) -> dict[str, Any]:
    """씬을 저장한다.

    경로를 주지 않으면 현재 경로에 덮어쓴다. 새 경로를 주는데 그 파일이 이미
    있으면 overwrite 를 켜야 한다 - 남의 작업을 말없이 덮어쓰지 않기 위해서다.

    Apprentice 라이선스는 .hipnc, Indie 는 .hiplc 만 저장할 수 있다.

    Args:
        path: 저장할 경로. 생략하면 현재 씬 경로.
        overwrite: 이미 있는 파일을 덮어쓸 때 True.
    """
    license_name, required = _license_hint()

    if path:
        # hou.hipFile.save 는 `$HIP` 원문을 받지 않는다(실측). 전개해서 넘긴다.
        paths.require_resolved(path)
        target = paths.to_path(path)
    else:
        target = Path(hou.hipFile.path())
    if required and target.suffix.lower() != required:
        raise ValueError(
            f"{license_name} 라이선스는 {required} 만 저장할 수 있습니다. "
            f"받은 경로: {target.name}"
        )

    if path and target.exists() and not overwrite:
        raise ValueError(
            f"이미 있는 파일입니다: {target}. 덮어쓰려면 overwrite=True 를 주세요."
        )

    paths.ensure_parent(target)
    try:
        hou.hipFile.save(str(target))
    except hou.OperationFailed as exc:
        raise ValueError(f"저장하지 못했습니다: {target} ({exc})") from exc

    return {
        "path": hou.hipFile.path(),
        "bytes": target.stat().st_size if target.exists() else 0,
        "has_unsaved_changes": hou.hipFile.hasUnsavedChanges(),
    }


@tool()
def load_scene(path: str, discard_changes: bool = False) -> dict[str, Any]:
    """씬 파일을 연다.

    저장하지 않은 변경이 있으면 기본적으로 거부한다. 버리고 열려면
    discard_changes 를 켠다 - 되돌릴 수 없는 동작이라 명시적으로 요구한다.

    Args:
        path: 열 .hip / .hipnc / .hiplc 경로.
        discard_changes: 저장하지 않은 변경을 버리고 연다.
    """
    # hou.hipFile.load 도 `$HIP` 원문을 받지 않는다(실측).
    target = paths.require_file(path)

    if hou.hipFile.hasUnsavedChanges() and not discard_changes:
        raise ValueError(
            f"저장하지 않은 변경이 있습니다({hou.hipFile.basename()}). 먼저 "
            f"save_scene 으로 저장하거나, 버리려면 discard_changes=True 를 주세요."
        )

    try:
        hou.hipFile.load(str(target), suppress_save_prompt=True)
    except hou.LoadWarning as warning:
        # 경고는 치명적이지 않다. 무엇이 문제였는지 알려 주고 계속한다.
        return {"path": hou.hipFile.path(), "warnings": str(warning)[:1000]}
    return {"path": hou.hipFile.path(), "name": hou.hipFile.basename()}


@tool()
def new_scene(discard_changes: bool = False) -> dict[str, Any]:
    """씬을 비우고 새로 시작한다.

    Args:
        discard_changes: 저장하지 않은 변경을 버린다.
    """
    if hou.hipFile.hasUnsavedChanges() and not discard_changes:
        raise ValueError(
            f"저장하지 않은 변경이 있습니다({hou.hipFile.basename()}). 먼저 "
            f"save_scene 으로 저장하거나, 버리려면 discard_changes=True 를 주세요."
        )
    hou.hipFile.clear(suppress_save_prompt=True)
    return {"path": hou.hipFile.path(), "name": hou.hipFile.basename()}


@tool()
def set_frame_range(start: float, end: float, current: float | None = None) -> dict[str, Any]:
    """플레이바의 프레임 범위를 정한다.

    Args:
        start: 시작 프레임.
        end: 끝 프레임.
        current: 현재 프레임. 생략하면 그대로 둔다.
    """
    if end < start:
        raise ValueError(f"end 가 start 보다 작습니다: {start} ~ {end}")
    hou.playbar.setFrameRange(start, end)
    hou.playbar.setPlaybackRange(start, end)
    if current is not None:
        hou.setFrame(current)
    rng = hou.playbar.frameRange()
    return {"start": rng[0], "end": rng[1], "current": hou.frame(), "fps": hou.fps()}
