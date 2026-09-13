"""시뮬 결과를 .sim 파일로 굽고 상태를 읽는 툴.

DOP 캐시는 SOP 캐시(`houdini_mcp_base` 의 `write_cache`)와 다르다. 지오메트리
한 프레임이 아니라 **시뮬 상태 전체**(오브젝트, 필드, 컨스트레인트, 솔버
내부 상태)를 담는다. 그래서 파일 하나에서 이어서 풀 수 있다.

굽는 방법이 두 가지인데 하나는 쓰지 않는다. Output DOP 의 `execute` 버튼은
노드의 `f1`/`f2` 를 무시하고 **플레이바 범위**를 쓴다(실측: 1~5 를 넣었는데
240 프레임이 나왔다). 사용자의 플레이바를 건드리게 되므로 쓰지 않는다.

대신 File DOP 을 write 모드로 체인 끝에 끼우고 프레임을 우리가 진행시킨다.
그러면 프레임별 리포트도 함께 나온다.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

import hou

from houdini_mcp import tool, undoable
from houdini_mcp_base import paths

from ._common import (
    create_in,
    described,
    require_dopnet,
    set_menu,
)
from ._state import (
    run_frames,
)

CACHE_NODE = "sim_cache"

# File DOP 의 mode 메뉴 토큰. auto / read / write / none 순이다.
_MODE_WRITE = "write"
_MODE_NONE = "none"


def _written(pattern: str) -> list[dict[str, Any]]:
    """패턴에 맞는 파일을 디스크에서 찾는다.

    프레임 번호를 계산해서 파일 이름을 맞히지 않는다. `$SF` 는 시뮬 프레임이라
    서브스텝·시작 프레임에 따라 타임라인 프레임과 다르게 매겨진다(실측:
    startframe 1 인 dopnet 에서 프레임 12 가 $SF=15 로 나왔다). 실제로 무엇이
    쓰였는지는 디렉토리를 보는 편이 정확하다.
    """
    files, _ = paths.resolve_files(pattern)
    return [{"path": f.as_posix(), "bytes": f.stat().st_size} for f in files]


def _mode_token(node: hou.DopNode) -> str:
    """File DOP 의 mode 를 사람이 읽는 토큰으로. 순서 메뉴라 eval 은 정수다."""
    parm = node.parm("mode")
    items = parm.parmTemplate().menuItems()
    index = int(parm.eval())
    return items[index] if 0 <= index < len(items) else str(index)


def _find_cache_node(dopnet: hou.Node) -> hou.DopNode | None:
    for node in dopnet.children():
        if isinstance(node, hou.DopNode) and node.type().name() == "file":
            return node
    return None


@tool()
@undoable("Write simulation cache")
def write_sim_cache(
    dopnet: str,
    directory: str,
    start: int,
    end: int,
    comment: str,
    filename: str | None = None,
    compress: bool = True,
    deep_fields: bool = False,
) -> dict[str, Any]:
    """시뮬을 프레임 범위만큼 돌리면서 프레임마다 .sim 파일로 굽는다.

    체인 끝에 File DOP 을 write 모드로 끼우고 프레임을 순차로 진행시킨다.
    굽는 동안의 프레임별 쿡 시간·메모리·발산 징후를 `test_simulation` 과 같은
    모양으로 함께 돌려준다 — 20분을 구운 뒤에 프레임 3에서 터졌다는 걸 아는
    일이 없어야 한다.

    굽기 전에 시뮬을 리셋하므로 캐시에 남아 있던 옛 결과는 버려진다.

    파일 개수가 프레임 수와 다를 수 있다. File DOP 은 **시뮬 타임스텝마다**
    쓰므로 서브스텝이 2면 파일이 대략 두 배로 나온다(실측: substep=2 로 5프레임을
    구웠더니 파일 9개). `frames_simulated` 와 `files_written` 을 함께 돌려주니
    둘을 비교하면 된다.

    Args:
        dopnet: DOP 네트워크 경로.
        directory: .sim 파일을 담을 디렉토리. 없으면 만든다. $HIP 같은 변수를
            그대로 쓴다 - File DOP 에 원문으로 걸려 씬을 옮겨도 풀린다.
        start: 시작 프레임.
        end: 끝 프레임.
        comment: File DOP 에 달 코멘트. 필수. 씬에 저장되므로 영어로.
            예: "Bake tower collapse, frames 1-120"
        filename: 파일 이름 패턴. 생략하면 "<dopnet 이름>.$SF.sim".
            프레임 번호 자리에 $SF(시뮬 프레임)를 넣어야 한다.
        compress: .sim 파일을 압축할지. 끄면 커지지만 읽기가 조금 빠르다.
        deep_fields: 프레임 리포트에 필드 히스토그램까지 넣을지.
    """
    net = require_dopnet(dopnet)
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 캐시가 무엇을 담는지 영어로 적어 주세요."
        )
    if end < start:
        raise ValueError(
            f"end({end}) 가 start({start}) 보다 앞섭니다. 시뮬은 앞으로만 굽습니다."
        )

    # 원문을 Path 로 만들어 mkdir 하면 현재 디렉토리에 `$HIP` 폴더가 생기고, 쓴
    # 파일도 거기서 찾아 0 개로 보고했다(실측). 디렉토리는 전개판으로 만들고 File
    # DOP 에는 원문을 건다.
    paths.require_resolved(directory)
    target_dir = paths.to_path(directory)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(
            f"{target_dir.as_posix()} 디렉토리를 만들지 못했습니다: {exc}. "
            f"쓸 수 있는 경로를 주세요."
        ) from exc

    pattern = paths.to_parm(filename or f"{net.name()}.$SF.sim")
    if not paths.FRAME_TOKENS.search(pattern):
        raise ValueError(
            f"filename 에 프레임 번호 자리가 없습니다: {pattern!r}. "
            f"'{net.name()}.$SF.sim' 처럼 $SF 를 넣으세요. 없으면 한 파일만 덮어씁니다."
        )
    full_pattern = str(PurePosixPath(paths.to_parm(directory)) / pattern)

    output = net.displayNode()
    if output is None:
        raise ValueError(
            f"{net.path()} 에 출력 노드가 없습니다. 시뮬 체인의 끝을 먼저 만드세요."
        )

    node = _find_cache_node(net)
    created: list[dict[str, Any]] = []
    if node is None:
        node = create_in(net, "file", CACHE_NODE, comment)
        upstream = output.inputs()
        tail = upstream[0] if upstream and upstream[0] is not None else None
        if tail is None:
            raise ValueError(
                f"{output.path()} 에 입력이 없습니다. "
                f"먼저 add_dop_object 로 솔버를 이은 뒤 캐시를 구우세요."
            )
        node.setFirstInput(tail)
        output.setInput(0, node)
        created.append(described(node, "Writes each simulated frame to a .sim file"))
        net.layoutChildren()
    else:
        node.setComment(comment.strip())

    node.parm("file").set(full_pattern)
    node.parm("mkpath").set(1)
    node.parm("compresssims").set(1 if compress else 0)
    set_menu(node, "mode", _MODE_WRITE)

    try:
        net.parm("resimulate").pressButton()
        report = run_frames(net, start, end, deep=deep_fields)
    finally:
        # 구운 뒤에도 write 모드로 두면 사용자가 스크럽할 때마다 파일을
        # 덮어쓴다. 끝나면 꺼 둔다.
        set_menu(node, "mode", _MODE_NONE)

    written = _written(full_pattern)
    total_bytes = sum(entry["bytes"] for entry in written)
    expected = end - start + 1

    result: dict[str, Any] = {
        "dopnet": net.path(),
        "cache_node": node.path(),
        "directory": paths.describe(directory),
        "pattern": full_pattern,
        "range": [start, end],
        "created": created,
        "frames_simulated": expected,
        "files_written": len(written),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 3),
        "files": written[:5] + ([{"more": len(written) - 5}] if len(written) > 5 else []),
        "summary": report["summary"],
        "first_error_frame": report["first_error_frame"],
        "first_errors": report["first_errors"],
        "mode_after": _MODE_NONE,
    }
    if len(written) < expected:
        result["warning"] = (
            f"{expected} 프레임을 돌렸는데 파일은 {len(written)} 개뿐입니다. "
            f"first_error_frame 과 디스크 공간을 확인하세요."
        )
    result["next_steps"] = [
        f"다시 읽으려면 {node.path()} 의 mode 를 'read' 로 바꾸세요 "
        f"(set_parms 로 mode='read')",
        f"sim_cache_status('{net.path()}') 로 어떤 프레임이 디스크에 있는지 봅니다",
    ]
    return result


@tool()
def sim_cache_status(dopnet: str, start: int | None = None, end: int | None = None) -> dict[str, Any]:
    """이 시뮬의 캐시 상태 — 메모리 캐시와 디스크의 .sim 파일 양쪽.

    두 가지를 함께 본다.

    - **메모리 캐시**: dopnet 의 cacheenabled / cachemaxsize / cachetodisk 와
      지금 쓰고 있는 바이트. 상한에 닿으면 앞 프레임부터 버려진다.
    - **디스크 캐시**: dopnet 안의 File DOP 이 가리키는 패턴에서 프레임 변수를
      와일드카드로 바꿔 디렉토리를 훑는다. 몇 개가 쓰였고 몇 바이트인지 준다.
      프레임 번호를 계산해 맞히지 않는 이유는 `$SF` 가 시뮬 프레임이라
      타임라인 프레임과 다르게 매겨지기 때문이다(실측).

    base 의 `cache_status` 는 SOP 캐시(filecache 노드)를 본다. 이것은 DOP 전용이다.

    Args:
        dopnet: DOP 네트워크 경로.
        start: 확인할 시작 프레임. 생략하면 플레이바 시작.
        end: 확인할 끝 프레임. 생략하면 플레이바 끝.
    """
    net = require_dopnet(dopnet)
    playbar = [int(v) for v in hou.playbar.frameRange()]
    first = playbar[0] if start is None else start
    last = playbar[1] if end is None else end
    if last < first:
        raise ValueError(f"end({last}) 가 start({first}) 보다 앞섭니다.")

    memory = {
        "enabled": bool(net.evalParm("cacheenabled")),
        "max_size_mb": int(net.evalParm("cachemaxsize")),
        "to_disk": bool(net.evalParm("cachetodisk")),
        "compressed": bool(net.evalParm("compresssims")),
        "cache_substeps": bool(net.evalParm("cachesubsteps")),
        "used_bytes": int(net.simulation().memoryUsage()),
    }
    memory["used_mb"] = round(memory["used_bytes"] / (1024 * 1024), 3)
    memory["fraction_of_limit"] = (
        round(memory["used_mb"] / memory["max_size_mb"], 4) if memory["max_size_mb"] else None
    )

    expected = last - first + 1
    disk = []
    for node in net.children():
        if not isinstance(node, hou.DopNode) or node.type().name() != "file":
            continue
        pattern = node.parm("file").unexpandedString()
        files = _written(pattern)
        total = sum(entry["bytes"] for entry in files)
        entry: dict[str, Any] = {
            "node": node.path(),
            "comment": node.comment(),
            "mode": _mode_token(node),
            "pattern": pattern,
            "files_on_disk": len(files),
            "expected_for_range": expected,
            "total_bytes": total,
            "total_mb": round(total / (1024 * 1024), 3),
            "sample": [f["path"] for f in files[:3]],
        }
        if len(files) != expected:
            entry["note"] = (
                f"확인한 범위({first}~{last})는 {expected} 프레임인데 파일은 "
                f"{len(files)} 개입니다. File DOP 은 시뮬 타임스텝마다 쓰므로 "
                f"서브스텝이 1보다 크면 파일이 더 많은 것이 정상입니다. 더 적으면 "
                f"아직 다 굽지 않았거나 다른 범위를 구운 것입니다."
            )
        disk.append(entry)

    result: dict[str, Any] = {
        "dopnet": net.path(),
        "checked_range": [first, last],
        "memory_cache": memory,
        "disk_caches": disk,
    }
    if not disk:
        result["hint"] = (
            f"{net.path()} 에 File DOP 이 없어 디스크 캐시가 없습니다. "
            f"write_sim_cache 로 구우면 생깁니다."
        )
    return result
