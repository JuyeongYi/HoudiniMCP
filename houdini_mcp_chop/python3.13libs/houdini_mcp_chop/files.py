"""채널을 Houdini 포맷 파일로 주고받는다. 자체 JSON 포맷을 만들지 않는다.

**두 포맷은 서로 다른 경로다.** 실측으로 확인했고 교차는 통하지 않는다.

    .clip .bclip .bclip.sc   CHOP 클립.  hou.ChopNode.saveClip / hou.Clip
    .chan .bchan             파라미터 채널. hscript chwrite / chread

`chopnode.saveClip("x.chan")` 은 실패하고, `chwrite ... x.clip` 은
"Unrecognized channel extension" 을 낸다. File CHOP 은 넷 다 읽는다 — 다만
`.chan`/`.bchan` 에는 채널 이름이 없어 `chan0`, `chan1`... 로 붙는다.

`.chan` 은 컬럼 텍스트라 Maya 나 Nuke 가 읽는다. 다른 DCC 와 주고받을 때 쓴다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import hou

from houdini_mcp import tool, undoable

from . import _common as c

CLIP_SUFFIXES = (".clip", ".bclip", ".bclip.sc")
"""CHOP 클립 포맷. saveClip 이 확장자로 포맷을 정한다."""

CHAN_SUFFIXES = (".chan", ".bchan")
"""파라미터 채널 포맷. hscript chwrite/chread 만 다룬다."""


def _suffix_of(path: Path) -> str:
    """`.bclip.sc` 처럼 두 겹인 확장자까지 알아본다."""
    name = path.name.lower()
    for suffix in CLIP_SUFFIXES + CHAN_SUFFIXES:
        if name.endswith(suffix):
            return suffix
    return path.suffix.lower()


def _hscript_path(path: Path) -> str:
    """hscript 인자로 넣을 경로. 큰따옴표로 감싸면 공백이 든 경로도 통한다(실측).

    Houdini 는 어느 플랫폼에서든 슬래시 경로를 받는다. hscript 는 역슬래시를
    이스케이프로 읽으므로 여기서만 바꿔 넣는다.
    """
    text = path.as_posix()
    if '"' in text:
        raise ValueError(
            f'경로에 큰따옴표가 들어 있어 hscript 로 넘길 수 없습니다: {text}'
        )
    return f'"{text}"'


def _run_hscript(command: str, what: str) -> str:
    out, err = hou.hscript(command)
    if err.strip():
        raise ValueError(f"{what} 에 실패했습니다: {err.strip()}")
    return out.strip()


@tool()
def export_channels(path: str, file_path: str) -> dict[str, Any]:
    """CHOP 출력을 클립 파일로 쓴다. 채널 이름이 보존된다.

    확장자가 포맷을 정한다. `.clip` 은 텍스트, `.bclip` 은 바이너리,
    `.bclip.sc` 는 Blosc 압축이다. **`.chan` 은 여기 쓸 수 없다** — 그것은
    파라미터 채널 포맷이라 export_parm_channels 를 쓴다.

    샘플을 모델에게 전부 보내는 대신 파일로 내보내고 경로만 받을 때 쓴다.

    `saveClip` 은 프레임 범위 인자를 받지 않는다(실측). 구간을 잘라 내보내려면
    apply_chop_filter 로 `shift` 나 trim CHOP 을 앞에 달아 출력 자체를 좁힌 뒤
    그 노드를 준다.

    Args:
        path: CHOP 경로.
        file_path: 쓸 파일 경로. .clip / .bclip / .bclip.sc
    """
    node = c.require_chop(path)
    target = Path(file_path)
    suffix = _suffix_of(target)
    if suffix not in CLIP_SUFFIXES:
        extra = (
            " .chan/.bchan 은 파라미터 채널 포맷입니다 — export_parm_channels 를 쓰세요."
            if suffix in CHAN_SUFFIXES
            else ""
        )
        raise ValueError(
            f"클립 확장자는 {', '.join(CLIP_SUFFIXES)} 중 하나여야 합니다: "
            f"{target.name}.{extra}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        node.saveClip(str(target))
    except hou.Error as exc:
        raise ValueError(
            f"{target} 에 클립을 쓰지 못했습니다: {exc} "
            f"디렉토리 권한과 CHOP 이 실제로 채널을 내는지 확인하세요."
        ) from exc

    tracks = c.cooked_tracks(node)
    return {
        "path": node.path(),
        "file_path": str(target),
        "format": suffix,
        "bytes": target.stat().st_size if target.exists() else 0,
        "channels": [track.name() for track in tracks],
        "samples": tracks[0].numSamples() if tracks else 0,
        "sample_rate": float(node.sampleRate()),
    }


@tool()
@undoable("Import channel file")
def import_channels(
    parent: str, file_path: str, comment: str, name: str | None = None
) -> dict[str, Any]:
    """채널 파일을 File CHOP 으로 읽어 들이고, 실제로 무엇이 들어왔는지 돌려준다.

    `.clip` / `.bclip` / `.chan` / `.bchan` 을 전부 읽는다. `.chan`/`.bchan`
    은 파일에 채널 이름이 없어 `chan0`, `chan1`... 로 붙는다 — 이름이 필요하면
    rename CHOP 을 뒤에 단다.

    Args:
        parent: CHOP 네트워크 경로.
        file_path: 읽을 파일 경로.
        comment: 이 채널이 무엇인지. 영어로 적는다.
        name: 노드 이름. 생략하면 Houdini 가 정한다.
    """
    source = Path(file_path)
    if not source.exists():
        raise ValueError(
            f"그런 파일이 없습니다: {source}. "
            f"export_channels 나 export_parm_channels 로 먼저 쓰거나 경로를 확인하세요."
        )

    net = c.require_chop_parent(parent)
    node = c.build(net, "file", comment, name, {"file": str(source)})
    report = c.node_report(node)
    report["file_path"] = str(source)
    report["format"] = _suffix_of(source)
    if report["format"] in CHAN_SUFFIXES:
        report["hint"] = (
            ".chan/.bchan 에는 채널 이름이 없어 chan0, chan1... 로 붙습니다. "
            "이름이 필요하면 rename CHOP 을 뒤에 다세요."
        )
    return report


@tool()
def export_parm_channels(
    parms: Sequence[str],
    file_path: str,
    start_frame: float | None = None,
    end_frame: float | None = None,
) -> dict[str, Any]:
    """파라미터 애니메이션을 `.chan` / `.bchan` 으로 쓴다. 다른 DCC 가 읽는다.

    `.chan` 은 프레임마다 한 줄, 채널마다 한 컬럼인 raw 텍스트다. Maya 와
    Nuke 가 이 포맷을 읽으므로 밖으로 내보낼 때 쓴다. CHOP 클립(`.clip`)은
    Houdini 끼리만 통한다.

    컬럼 순서는 준 파라미터 순서 그대로다. 읽을 때 같은 순서로 줘야 한다.

    Args:
        parms: 내보낼 파라미터 경로들. 예: ["/obj/cam/tx", "/obj/cam/ty"]
        file_path: 쓸 파일 경로. .chan 또는 .bchan
        start_frame: 시작 프레임. 생략하면 씬의 전역 시작.
        end_frame: 끝 프레임(포함). 생략하면 씬의 전역 끝.
    """
    if not parms:
        raise ValueError(
            "parms 가 비어 있습니다. 내보낼 파라미터 경로를 주세요. "
            "list_animated_parms 가 어느 파라미터에 애니메이션이 있는지 알려 줍니다."
        )

    target = Path(file_path)
    if _suffix_of(target) not in CHAN_SUFFIXES:
        raise ValueError(
            f"파라미터 채널 확장자는 {', '.join(CHAN_SUFFIXES)} 중 하나여야 합니다: "
            f"{target.name}. CHOP 출력을 쓰려는 것이면 export_channels 를 쓰세요."
        )

    resolved = [c.resolve_parm(ref) for ref in parms]
    target.parent.mkdir(parents=True, exist_ok=True)

    playback = hou.playbar.frameRange()
    first = float(playback[0]) if start_frame is None else float(start_frame)
    last = float(playback[1]) if end_frame is None else float(end_frame)
    columns = " ".join(parm.path() for parm in resolved)
    message = _run_hscript(
        f"chwrite -f {first} {last} {columns} {_hscript_path(target)}",
        f"{target} 에 채널 쓰기",
    )

    return {
        "file_path": str(target),
        "format": _suffix_of(target),
        "bytes": target.stat().st_size if target.exists() else 0,
        "columns": [parm.path() for parm in resolved],
        "frame_range": [first, last],
        "message": message,
        "hint": "읽을 때 import_parm_channels 에 같은 순서로 파라미터를 주세요.",
    }


@tool()
@undoable("Import parameter channels")
def import_parm_channels(
    parms: Sequence[str],
    file_path: str,
    start_frame: float | None = None,
    end_frame: float | None = None,
) -> dict[str, Any]:
    """`.chan` / `.bchan` 을 파라미터 키프레임으로 읽어 넣는다.

    export_parm_channels 의 반대다. 컬럼 순서대로 파라미터에 들어가므로
    **쓸 때와 같은 순서**로 줘야 한다.

    읽은 뒤 각 파라미터의 키 개수와 현재 값을 돌려주므로 실제로 들어왔는지
    바로 알 수 있다.

    Args:
        parms: 받을 파라미터 경로들. 컬럼 순서와 같아야 한다.
        file_path: 읽을 파일 경로. .chan 또는 .bchan
        start_frame: 넣을 구간 시작 프레임. 생략하면 씬의 전역 시작.
        end_frame: 끝 프레임(포함). 생략하면 씬의 전역 끝.
    """
    source = Path(file_path)
    if not source.exists():
        raise ValueError(f"그런 파일이 없습니다: {source}")
    if _suffix_of(source) not in CHAN_SUFFIXES:
        raise ValueError(
            f"이 툴은 {', '.join(CHAN_SUFFIXES)} 만 읽습니다: {source.name}. "
            f"클립 파일은 import_channels 로 File CHOP 에 읽으세요."
        )
    if not parms:
        raise ValueError("parms 가 비어 있습니다. 받을 파라미터 경로를 주세요.")

    resolved = [c.resolve_parm(ref) for ref in parms]
    playback = hou.playbar.frameRange()
    first = float(playback[0]) if start_frame is None else float(start_frame)
    last = float(playback[1]) if end_frame is None else float(end_frame)
    columns = " ".join(parm.path() for parm in resolved)
    message = _run_hscript(
        f"chread -f {first} {last} {columns} {_hscript_path(source)}",
        f"{source} 에서 채널 읽기",
    )

    loaded = [
        {
            "parm": parm.path(),
            "keyframes": len(parm.keyframes()),
            "value_at_start": parm.evalAtFrame(first),
            "value_at_end": parm.evalAtFrame(last),
        }
        for parm in resolved
    ]
    empty = [entry["parm"] for entry in loaded if entry["keyframes"] == 0]
    return {
        "file_path": str(source),
        "format": _suffix_of(source),
        "frame_range": [first, last],
        "count": len(loaded),
        "loaded": loaded,
        "message": message,
        "empty_parms": empty,
        "hint": (
            "키가 들어가지 않은 파라미터가 있습니다. 파일의 컬럼 수와 준 "
            "파라미터 수가 맞는지 확인하세요."
            if empty
            else None
        ),
    }
