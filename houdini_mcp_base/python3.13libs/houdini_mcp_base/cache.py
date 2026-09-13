"""디스크 캐시를 쓰고 상태를 보고 지우는 툴들.

무거운 계산은 한 번 돌려 디스크에 굳혀 두고 다시 읽는 것이 낫다. File Cache
SOP 이 그 일을 하지만, 만들고 파라미터를 걸고 버튼을 누르고 파일이 생겼는지
확인하는 네 단계를 매번 밟아야 했다.

**되돌릴 수 없는 것을 명시적으로 요구한다.** 디스크 파일 삭제는 Undo 로
되돌아가지 않으므로 `scene.load_scene` 의 `discard_changes` 와 같은 방식으로
막는다 - `delete_files=True` 를 직접 줘야만 지운다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/SopNode.html
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

import hou

from houdini_mcp import tool, undoable

from . import paths

CACHE_TYPE = "filecache::2.0"
"""새로 만들 때 쓸 타입. 실측으로 확인한 이 Houdini 에 있는 것 중 최신이다."""

# 캐시로 볼 노드 타입들. 이름에 버전이 붙으므로 앞부분으로 본다.
CACHE_PREFIXES = ("filecache", "rop_geometry", "rop_alembic", "labs::filecache")

MAX_LIST = 60


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _stamp(epoch: float | None) -> str | None:
    """epoch 초를 읽을 수 있는 시각으로. 숫자만 주면 언제인지 알 수 없다."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch).isoformat(timespec="seconds")


def _is_cache(node: hou.Node) -> bool:
    """캐시 노드인지. 타입 이름의 버전 접미사를 떼고 본다.

    File Cache HDA 안에는 rop_geometry 가 들어 있어서 그냥 훑으면 하나를 둘로
    센다. 잠긴 HDA 안쪽은 사용자가 다룰 대상이 아니므로 뺀다.
    """
    if node.isInsideLockedHDA():
        return False
    base = node.type().name().split("::", 1)[0]
    return any(base == p.split("::", 1)[0] for p in CACHE_PREFIXES)


def _walk(root: hou.Node, depth: int) -> Iterator[hou.Node]:
    stack: list[tuple[hou.Node, int]] = [(c, 1) for c in root.children()]
    seen = 0
    while stack:
        node, level = stack.pop(0)
        yield node
        seen += 1
        if seen >= 2000:
            return
        if level < depth:
            stack.extend((c, level + 1) for c in node.children())


def _output_parm(node: hou.Node) -> hou.Parm:
    """이 캐시 노드가 쓰는 파일 경로 파라미터."""
    for name in ("file", "sopoutput", "filename"):
        parm = node.parm(name)
        if parm is not None:
            return parm
    raise ValueError(
        f"{node.path()} ({node.type().name()}) 에서 출력 경로 파라미터를 찾지 "
        f"못했습니다. list_parms 로 이름을 확인하고 set_parms 로 직접 거세요."
    )


def _output_file(node: hou.Node) -> dict[str, Any] | None:
    """출력 경로의 원문과 전개판. 원문이 식이면(filecache 의 sopoutput) 값만 준다."""
    try:
        parm = _output_parm(node)
    except ValueError:
        return None
    try:
        return paths.describe(parm.unexpandedString())
    except hou.OperationFailed:
        # 키프레임·식이 걸린 파라미터는 원문을 꺼낼 수 없다(실측).
        return paths.describe(parm.evalAsString())


def _written_files(node: hou.Node, start: int, end: int) -> list[dict[str, Any]]:
    """캐시가 실제로 쓴 파일들. 프레임마다 경로가 달라질 수 있어 프레임별로 푼다."""
    parm = _output_parm(node)
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for frame in range(int(start), int(end) + 1):
        try:
            raw = parm.evalAtFrame(frame)
        except hou.OperationFailed:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        target = Path(raw)
        entry: dict[str, Any] = {"frame": frame, "path": target.as_posix(), "exists": target.exists()}
        if entry["exists"]:
            stat = target.stat()
            entry["bytes"] = stat.st_size
            # 사람이 읽을 것과 비교할 것을 둘 다 준다. epoch 숫자만 주면 언제인지
            # 알 수 없고, 문자열만 주면 노드 수정 시각과 비교할 수 없다.
            entry["modified"] = _stamp(stat.st_mtime)
            entry["modified_epoch"] = stat.st_mtime
        files.append(entry)
        if len(files) >= MAX_LIST:
            break
    return files


@tool()
@undoable("Write cache")
def write_cache(
    source: str,
    comment: str,
    file_path: str | None = None,
    frame_start: float | None = None,
    frame_end: float | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """지오메트리를 디스크에 캐시로 굽는다. 굽고 나서 파일이 생겼는지 확인해 준다.

    source 가 이미 캐시 노드면 그것을 다시 굽는다. 아니면 그 아래에 File Cache
    SOP 을 새로 만들어 잇는다. 노드 이름은 무엇을 굽는지 드러나게 짓는다
    (`cache1` 말고 `wall_geo_cache`).

    프레임 범위를 주지 않으면 현재 프레임 하나만 굽는다. 시뮬레이션처럼 시간에
    따라 변하는 것은 범위를 준다.

    굽는 데 오래 걸릴 수 있다. 결과로 실제 파일 경로와 크기를 돌려주므로,
    0 바이트이거나 파일이 없으면 뭔가 잘못된 것이다.

    Args:
        source: 구울 SOP 경로, 또는 이미 있는 캐시 노드 경로.
        comment: 이 캐시가 무엇인지. 필수. 씬에 저장되므로 영어로.
            예: "Baked wall geometry, 1.2M points"
        file_path: 쓸 파일 경로. 생략하면 Houdini 가 $HIP/geo 아래에 정한다.
        frame_start: 시작 프레임. 생략하면 현재 프레임 하나만.
        frame_end: 끝 프레임.
        name: 새로 만들 때 쓸 노드 이름. 역할이 드러나게, 영어로.
    """
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 캐시가 무엇인지 적어 주세요."
        )
    if file_path:
        paths.require_resolved(file_path)

    node = _require(source)
    created = False
    if _is_cache(node):
        cache = node
    else:
        parent = node.parent()
        if parent is None:
            raise ValueError(f"{source} 의 부모를 찾지 못해 캐시를 만들 수 없습니다.")
        try:
            cache = parent.createNode(CACHE_TYPE, node_name=name)
        except hou.OperationFailed as exc:
            raise ValueError(
                f"{parent.path()} 안에 {CACHE_TYPE} 을 만들지 못했습니다 ({exc}). "
                f"SOP 네트워크 안의 노드를 source 로 주세요."
            ) from exc
        cache.setFirstInput(node)
        created = True

    cache.setComment(comment.strip())
    cache.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    if file_path:
        # 경로를 직접 주려면 filemethod 를 explicit 으로 돌려야 한다.
        method = cache.parm("filemethod")
        if method is not None:
            method.set("explicit")
        # 파라미터에는 원문을 건다. Path 로 만들어 넣으면 Windows 에서 역슬래시가
        # 되어 쓰기가 실패하고, 원문 그대로 mkdir 하면 현재 디렉토리에 `$HIP`
        # 폴더가 생긴다(둘 다 실측). 디렉토리는 전개판으로 만든다.
        if not paths.has_sequence_token(PurePosixPath(paths.to_parm(file_path)).parent):
            paths.ensure_parent(paths.to_path(file_path))
        _output_parm(cache).set(paths.to_parm(file_path))

    trange = cache.parm("trange")
    if frame_start is not None or frame_end is not None:
        start = hou.frame() if frame_start is None else float(frame_start)
        end = start if frame_end is None else float(frame_end)
        if end < start:
            raise ValueError(f"frame_end 가 frame_start 보다 작습니다: {start} ~ {end}")
        if trange is not None:
            trange.set("normal")
        for parm_name, value in (("f1", start), ("f2", end)):
            parm = cache.parm(parm_name)
            if parm is not None:
                parm.deleteAllKeyframes()
                parm.set(value)
    else:
        start = end = hou.frame()
        if trange is not None:
            trange.set("off")

    execute = cache.parm("execute")
    if execute is None:
        raise ValueError(
            f"{cache.path()} 에 execute 버튼이 없습니다. 이 타입은 write_cache 로 "
            f"구울 수 없습니다."
        )
    try:
        execute.pressButton()
    except hou.OperationFailed as exc:
        raise ValueError(
            f"캐시를 굽지 못했습니다: {cache.path()} ({exc}). node_errors 로 "
            f"입력 쪽 에러를 확인하세요."
        ) from exc

    files = _written_files(cache, start, end)
    written = [f for f in files if f["exists"]]
    result: dict[str, Any] = {
        "path": cache.path(),
        "created": created,
        "comment": cache.comment(),
        "frame_start": start,
        "frame_end": end,
        "file": _output_file(cache),
        "files": files,
        "written_count": len(written),
        "total_bytes": sum(f.get("bytes", 0) for f in written),
    }
    errors = [e for e in cache.errors() if e.strip()]
    if errors:
        result["errors"] = [e[:1200] for e in errors[:5]]
    if not written:
        result["warning"] = (
            "파일이 하나도 생기지 않았습니다. 경로에 쓸 권한이 있는지, 입력 "
            "지오메트리가 비어 있지 않은지 확인하세요."
        )
    return result


@tool()
def list_caches(root: str = "/obj", depth: int = 4) -> dict[str, Any]:
    """씬에 있는 캐시 노드를 전부 찾는다.

    무엇이 구워져 있는지, 어디에 쓰였는지 훑을 때 쓴다. 개별 상태는
    `cache_status` 로 본다.

    Args:
        root: 훑기 시작할 경로.
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지.
    """
    scope = _require(root)
    found = []
    for node in _walk(scope, depth):
        if not _is_cache(node):
            continue
        entry: dict[str, Any] = {
            "path": node.path(),
            "type": node.type().name(),
            "comment": node.comment(),
        }
        try:
            entry["file"] = _output_parm(node).evalAsString()
        except ValueError:
            entry["file"] = None
        load = node.parm("loadfromdisk")
        if load is not None:
            entry["loading_from_disk"] = bool(load.eval())
        found.append(entry)
        if len(found) >= MAX_LIST:
            break
    return {"root": scope.path(), "count": len(found), "caches": found}


@tool()
def cache_status(path: str) -> dict[str, Any]:
    """캐시가 있는지, 낡았는지 본다.

    낡았는지는 **입력 노드의 `needsToCook()`** 으로 판단한다. 구운 직후에는
    False 이고 상류를 고치면 True 로 돌아간다 - Houdini 자신의 의존 관계
    추적이라 믿을 수 있다.

    노드의 `modificationTime()` 은 쓰지 않는다. 실측해 보면 벽시계보다 앞서
    가는 값이라 파일 mtime 과 비교할 수 없다. 대신 씬 파일이 캐시보다 나중에
    저장됐는지를 함께 알려 준다 - 양쪽 다 파일 시각이라 비교가 성립한다.

    Args:
        path: 캐시 노드 경로.
    """
    node = _require(path)
    if not _is_cache(node):
        raise ValueError(
            f"{path} 는 캐시 노드가 아닙니다 ({node.type().name()}). "
            f"list_caches 로 씬의 캐시 노드를 찾으세요."
        )

    parm = _output_parm(node)
    trange = node.parm("trange")
    if trange is not None and trange.evalAsString() == "normal":
        start = node.parm("f1").eval() if node.parm("f1") else hou.frame()
        end = node.parm("f2").eval() if node.parm("f2") else start
    else:
        start = end = hou.frame()

    files = _written_files(node, start, end)
    written = [f for f in files if f["exists"]]
    newest = max((f["modified_epoch"] for f in written), default=None)

    # 입력이 다시 쿡돼야 하면 상류가 캐시를 구운 뒤로 달라졌다는 뜻이다.
    # 캐시 노드 자신은 늘 dirty 로 나오므로 입력 쪽을 본다(실측 확인).
    inputs = node.inputs()
    source = inputs[0] if inputs and inputs[0] is not None else None
    stale = source.needsToCook() if source is not None else None

    result: dict[str, Any] = {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "file_pattern": parm.unexpandedString(),
        "frame_start": start,
        "frame_end": end,
        "expected_files": len(files),
        "written_count": len(written),
        "missing": [f["path"] for f in files if not f["exists"]][:MAX_LIST],
        "total_bytes": sum(f.get("bytes", 0) for f in written),
        "newest_file_modified": _stamp(newest),
        "input": source.path() if source is not None else None,
        "input_needs_cook": stale,
    }

    # 씬 파일과 캐시 파일은 둘 다 파일 시각이라 비교가 성립한다.
    hip = Path(hou.hipFile.path())
    if hip.exists() and newest is not None:
        hip_modified = hip.stat().st_mtime
        result["scene_modified"] = _stamp(hip_modified)
        result["scene_saved_after_cache"] = hip_modified > newest

    if not written:
        result["state"] = "없음"
        result["advice"] = "write_cache 로 구우세요."
    elif len(written) < len(files):
        result["state"] = "일부만"
        result["advice"] = "빠진 프레임이 있습니다. write_cache 로 다시 구우세요."
    elif stale:
        result["state"] = "낡음"
        result["advice"] = (
            f"{result['input']} 가 캐시를 구운 뒤로 달라졌습니다. "
            f"write_cache 로 다시 구우세요."
        )
    elif source is None:
        result["state"] = "있음"
        result["advice"] = (
            "입력이 연결돼 있지 않아 낡았는지 판단할 수 없습니다. 파일은 있습니다."
        )
    else:
        result["state"] = "최신"
    return result


@tool()
def clear_cache(
    path: str | None = None, memory: bool = True, delete_files: bool = False
) -> dict[str, Any]:
    """캐시를 비운다. 메모리와 디스크는 따로 다룬다.

    **메모리 캐시**(`memory=True`)는 Houdini 가 쿡 결과를 들고 있는 것이다.
    비워도 다시 쿡하면 되므로 안전하다. 메모리가 모자랄 때 쓴다.

    **디스크 파일**(`delete_files=True`)은 되돌릴 수 없다. Undo 로 돌아오지
    않고 휴지통에도 가지 않는다. 그래서 기본값이 False 이고, 지우려면 직접
    켜야 한다. 이때는 path 로 어느 캐시인지도 지정해야 한다 - 씬 전체의 캐시
    파일을 한 번에 지우는 길은 일부러 두지 않았다.

    Args:
        path: 디스크 파일을 지울 캐시 노드 경로. delete_files 와 함께 쓴다.
        memory: Houdini 의 메모리 캐시를 비운다.
        delete_files: path 가 가리키는 캐시의 디스크 파일을 **영구히 지운다**.
    """
    result: dict[str, Any] = {}

    if memory:
        # sopcache -c 가 SOP 쿡 결과 캐시를 비운다. hou 에는 해당 API 가 없다.
        out, err = hou.hscript("sopcache -c")
        result["memory_cleared"] = True
        if out and out.strip():
            result["memory_output"] = out.strip()[:500]
        if err and err.strip():
            result["memory_error"] = err.strip()[:500]

    if not delete_files:
        if path:
            result["note"] = (
                f"{path} 의 디스크 파일은 지우지 않았습니다. 지우려면 "
                f"delete_files=True 를 주세요 - 되돌릴 수 없습니다."
            )
        return result

    if not path:
        raise ValueError(
            "delete_files=True 에는 path 가 필요합니다. 어느 캐시의 파일을 지울지 "
            "지정하세요. 씬 전체의 캐시 파일을 한 번에 지우는 길은 없습니다."
        )

    node = _require(path)
    if not _is_cache(node):
        raise ValueError(f"{path} 는 캐시 노드가 아닙니다 ({node.type().name()}).")

    trange = node.parm("trange")
    if trange is not None and trange.evalAsString() == "normal":
        start = node.parm("f1").eval() if node.parm("f1") else hou.frame()
        end = node.parm("f2").eval() if node.parm("f2") else start
    else:
        start = end = hou.frame()

    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    for entry in _written_files(node, start, end):
        if not entry["exists"]:
            continue
        target = Path(entry["path"])
        try:
            target.unlink()
        except OSError as exc:
            failed.append({"path": target.as_posix(), "why": str(exc)})
            continue
        deleted.append(target.as_posix())

    result["path"] = node.path()
    result["deleted"] = deleted
    result["deleted_count"] = len(deleted)
    if failed:
        result["failed"] = failed
    return result
