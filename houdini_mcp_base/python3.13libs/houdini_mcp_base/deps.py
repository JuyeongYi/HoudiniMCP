"""씬이 무엇에 의존하는지 — 목록·수집·경로 치환.

**파라미터 문자열을 훑지 않는다.** `hou.fileReferences()` 를 쓴다. Houdini 는
자기가 참조하는 파일을 이미 알고 있고, 식이 걸린 참조도 거기 들어 있다. 기존
구현 다섯은 전부 파라미터를 순회하며 `.exr` 로 끝나는 값을 찾는 식이라, 표현식·
변수·UDIM 이 섞이면 놓친다.

실측(22.0.368)으로 확인한 반환 구조는 `(hou.Parm, 미전개 문자열)` 쌍이다.
`parm.eval()` 이 전개된 경로를 준다. 다만 `$F4` 는 **현재 프레임으로** 전개되고
`<UDIM>` 은 전개되지 않는다. 그래서 "실제로 몇 장 있나"는 토큰을 글롭으로 바꿔
세야 한다(`_common.resolve_files`).

한 가지 빠지는 것이 있다. `hou.fileReferences()` 는 **Houdini 설치($HFS) 안의
파일을 아예 빼고 준다** — `$HFS/...` 로 쓰든 절대 경로로 쓰든 마찬가지다(실측
확인). 설치본에 딸린 샘플 에셋을 참조하면 의존성 목록에 나오지 않는다. 이는
Houdini 의 의도된 동작이고(어차피 설치본과 함께 온다), 대신 그런 참조는 씬을
납품할 때 따라가지 않는다는 뜻이므로 알고 있어야 한다.

컨텍스트를 가리지 않으므로 base 에 있다. 처음에는 houdini_mcp_io 에 있었고,
mat 의 list_textures 가 같은 순회를 이미지만 따로 하고 있었다. 합쳤다 - 텍스처
목록은 `list_dependencies(kinds=["Image"])` 다. 이미지 **내용**(해상도·채널·
컬러스페이스)은 houdini_mcp_mat 의 `texture_info` 가 읽는다.
"""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence

import hou

from houdini_mcp import tool, undoable

from . import paths

def truncate(items: Iterable[Any], limit: int) -> tuple[list[Any], int]:
    """목록을 잘라 (보여줄 것, 전체 수) 로. 모델 컨텍스트를 태우지 않기 위해서."""
    collected = list(items)
    return collected[:limit], len(collected)


OUTPUT_PARMS = frozenset(
    {
        "sopoutput",
        "lopoutput",
        "copoutput",
        "dopoutput",
        "chopoutput",
        "picture",
        "vm_picture",
        "outputimage",
        "rendergallerysource",
    }
)
"""씬이 **쓰는** 곳이지 **읽는** 곳이 아닌 파라미터.

`hou.fileReferences()` 는 이것도 함께 준다. 아직 렌더하지 않은 출력 경로를
"없는 파일"이라고 보고하면 거짓 경보가 되므로 role 로 갈라 둔다.
"""

MAX_LISTED = 200
"""응답에 담을 참조 수 상한. 씬이 크면 목록만으로 컨텍스트가 탄다."""


# --------------------------------------------------------------------------
# 참조 수집
# --------------------------------------------------------------------------


def parm_file_kind(parm: hou.Parm | None) -> str:
    """파라미터 템플릿이 선언한 파일 종류. Image / Geometry / Otl / Usd ...

    kinds 인자로 거르는 기준이다. 이미지만 보려면 kinds=["Image"].
    """
    if parm is None:
        return "Unknown"
    template = parm.parmTemplate()
    if not isinstance(template, hou.StringParmTemplate):
        return "Unknown"
    try:
        return str(template.fileType()).rsplit(".", 1)[-1]
    except hou.Error:
        return "Unknown"


def reference_entry(parm: hou.Parm | None, raw: str) -> dict[str, Any]:
    """참조 하나를 JSON 으로 낼 수 있는 모양으로. 존재 여부까지 판정한다."""
    node = parm.node() if parm is not None else None
    try:
        resolved = parm.eval() if parm is not None else paths.expand(raw)
    except hou.Error:
        # 식이 깨진 참조. 값을 못 구한다는 사실 자체가 보고할 내용이다.
        resolved = None

    files, is_sequence = paths.resolve_files(raw)
    entry: dict[str, Any] = {
        "node": node.path() if node is not None else None,
        "node_type": node.type().name() if node is not None else None,
        "comment": node.comment() if node is not None else None,
        "parm": parm.name() if parm is not None else None,
        "raw": raw,
        "resolved": resolved,
        "kind": parm_file_kind(parm),
        "role": "output" if (parm is not None and parm.name() in OUTPUT_PARMS) else "input",
        "sequence": is_sequence,
    }
    if is_sequence:
        entry["pattern"] = paths.sequence_glob(raw)
        entry["file_count"] = len(files)
        entry["exists"] = bool(files)
        if files:
            entry.update(paths.file_stat(files[0]))
            entry["total_bytes"] = sum(
                (f.stat().st_size if f.is_file() else 0) for f in files
            )
    elif files:
        entry.update(paths.file_stat(files[0]))
    else:
        entry["exists"] = False
    return entry


def iter_references(kinds: Sequence[str] | None = None) -> Iterator[dict[str, Any]]:
    """씬의 모든 파일 참조. kinds 로 hou.fileType 이름을 걸러낼 수 있다."""
    wanted = {k.lower() for k in kinds} if kinds else None
    for parm, raw in hou.fileReferences():
        if not raw:
            continue
        entry = reference_entry(parm, raw)
        if wanted is not None and entry["kind"].lower() not in wanted:
            continue
        yield entry


def resolved_files(entry: dict[str, Any]) -> list[Path]:
    """참조 하나가 실제로 가리키는 파일들."""
    files, _ = paths.resolve_files(entry["raw"])
    return files


# --------------------------------------------------------------------------
# list_dependencies
# --------------------------------------------------------------------------


@tool()
def list_dependencies(
    kinds: Sequence[str] | None = None,
    missing_only: bool = False,
    include_outputs: bool = False,
    limit: int = MAX_LISTED,
) -> dict[str, Any]:
    """씬이 참조하는 외부 파일을 전부 나열하고, 실제로 있는지 확인한다.

    `hou.fileReferences()` 로 얻는다. 파라미터를 문자열로 훑지 않으므로 식이
    걸린 참조도 빠지지 않는다.

    $F4 나 <UDIM> 이 든 참조는 토큰을 글롭으로 바꿔 **실제로 몇 장 있는지** 센다.
    현재 프레임 하나만 보고 "있다/없다"를 말하지 않는다.

    출력 경로(ROP 의 sopoutput, picture 등)는 기본적으로 빼 둔다. 아직 렌더하지
    않은 경로를 "없는 파일"로 보고하면 거짓 경보이기 때문이다.

    이미지 파일의 해상도·채널·컬러스페이스가 필요하면 `texture_info`
    (houdini_mcp_mat)를 쓴다. 여기서는 파일이 있는지, 몇 바이트인지까지다.

    Args:
        kinds: hou.fileType 이름으로 거른다. Geometry / Image / Otl / Usd /
            Alembic / Fbx / Hip / Directory / Any 등. 생략하면 전부. 텍스처만
            보려면 ["Image"].
        missing_only: True 면 없는 파일만.
        include_outputs: True 면 출력 경로 파라미터도 함께 낸다.
        limit: 목록에 담을 최대 개수. 집계는 전체를 대상으로 한다.
    """
    entries = [
        e
        for e in iter_references(kinds)
        if include_outputs or e["role"] == "input"
    ]
    missing = [e for e in entries if not e.get("exists")]
    if missing_only:
        entries = missing

    by_kind: dict[str, int] = {}
    total_bytes = 0
    for entry in entries:
        by_kind[entry["kind"]] = by_kind.get(entry["kind"], 0) + 1
        total_bytes += entry.get("total_bytes", entry.get("bytes", 0) or 0)

    shown, total = truncate(entries, max(1, limit))
    return {
        "hip": hou.hipFile.path(),
        "count": total,
        "missing_count": len(missing),
        "by_kind": dict(sorted(by_kind.items())),
        "total_bytes": total_bytes,
        "references": shown,
        "truncated": max(0, total - len(shown)),
        "note": (
            "이미지 내용(해상도·채널·컬러스페이스)은 texture_info 를, "
            "씬 이식성 판정은 validate_scene 을 쓰세요."
        ),
    }


# --------------------------------------------------------------------------
# collect_dependencies
# --------------------------------------------------------------------------


@tool()
@undoable("Collect scene dependencies")
def collect_dependencies(
    target_dir: str,
    kinds: Sequence[str] | None = None,
    overwrite: bool = False,
    relink: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """씬이 쓰는 파일을 한 디렉토리로 모은다. 원하면 씬이 그쪽을 보게 고친다.

    씬을 다른 기계로 옮기거나 납품할 때 쓴다. 시퀀스·UDIM 은 **모든 장을** 모은다.

    되돌리기 어려운 동작이라 기본이 dry_run 이다. 무엇이 복사될지 먼저 보고,
    맞으면 dry_run=False 로 다시 부른다.

    이름이 겹치는 파일(다른 디렉토리의 같은 이름)은 말없이 덮어쓰지 않고
    거절한다 — 그러면 모아 놓은 씬이 조용히 틀린 텍스처를 쓰게 된다.

    Args:
        target_dir: 모을 디렉토리. 없으면 만든다.
        kinds: hou.fileType 이름으로 거른다. 생략하면 이미지·지오메트리·HDA 등
            입력 참조 전부.
        overwrite: 대상 디렉토리에 같은 이름이 이미 있을 때 덮어쓴다.
        relink: True 면 복사한 뒤 씬의 파라미터를 새 경로로 고친다. 시퀀스 토큰
            ($F4, <UDIM>)은 그대로 보존한다.
        dry_run: True(기본)면 복사하지 않고 계획만 돌려준다.
    """
    paths.require_resolved(target_dir)
    destination = paths.to_path(target_dir)
    entries = [e for e in iter_references(kinds) if e["role"] == "input"]

    plan: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    claimed: dict[str, str] = {}
    total_bytes = 0

    for entry in entries:
        files = resolved_files(entry)
        if not files:
            missing.append({"node": entry["node"], "parm": entry["parm"], "raw": entry["raw"]})
            continue
        for source in files:
            name = source.name
            previous = claimed.get(name)
            if previous is not None and previous != source.as_posix():
                collisions.append({"name": name, "first": previous, "second": source.as_posix()})
                continue
            claimed[name] = source.as_posix()
            total_bytes += source.stat().st_size
            plan.append(
                {
                    "source": source.as_posix(),
                    "target": (destination / name).as_posix(),
                    "node": entry["node"],
                    "parm": entry["parm"],
                    "raw": entry["raw"],
                }
            )

    if collisions:
        names = ", ".join(sorted({c["name"] for c in collisions})[:5])
        raise ValueError(
            f"이름이 겹치는 파일이 {len(collisions)}건 있습니다({names}). 한 디렉토리로 "
            f"모으면 서로를 덮어씁니다. 겹치는 쪽을 먼저 이름을 바꾸거나, kinds 로 "
            f"종류를 나눠 여러 번 부르세요."
        )

    result: dict[str, Any] = {
        "target_dir": destination.as_posix(),
        "dry_run": dry_run,
        "planned": len(plan),
        "missing": missing,
        "total_bytes": total_bytes,
        "files": plan[:MAX_LISTED],
        "truncated": max(0, len(plan) - MAX_LISTED),
    }
    if dry_run:
        result["note"] = (
            "계획만 돌려줬습니다. 실제로 복사하려면 dry_run=False 로 다시 부르세요."
        )
        return result

    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped: list[str] = []
    for item in plan:
        source, target = Path(item["source"]), Path(item["target"])
        if target.exists() and not overwrite:
            skipped.append(target.as_posix())
            continue
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            raise ValueError(
                f"{source} 를 {target} 로 복사하지 못했습니다: {exc} "
                f"디스크 공간과 권한을 확인하세요. 여기까지 {copied}개를 복사했습니다."
            ) from exc
        copied += 1

    result["copied"] = copied
    result["skipped_existing"] = skipped[:MAX_LISTED]
    if skipped:
        result["skipped_count"] = len(skipped)
        result["skipped_note"] = (
            "대상에 같은 이름이 이미 있어 건너뛰었습니다. 덮어쓰려면 overwrite=True 를 주세요."
        )

    if relink:
        result["relinked"] = _relink(entries, paths.portable(target_dir))
    return result


def _relink(entries: Sequence[dict[str, Any]], destination: str) -> list[dict[str, Any]]:
    """파라미터를 모아 둔 디렉토리로 돌린다. 시퀀스 토큰은 보존한다.

    전개된 경로가 아니라 **원문의 파일 이름**을 쓴다. 그래야 `$F4` 나 `<UDIM>` 이
    살아남아 시퀀스가 계속 시퀀스로 읽힌다.

    디렉토리도 원문이다(paths.portable). 전개된 절대 경로를 걸면 `$HIP` 을 잃어
    모아 놓은 씬을 다른 기계로 옮기는 순간 다시 깨진다 - 모으는 목적이 사라진다.
    """
    changes: list[dict[str, Any]] = []
    for entry in entries:
        if entry["parm"] is None or not entry.get("exists"):
            continue
        node = hou.node(entry["node"] or "")
        if node is None:
            continue
        parm = node.parm(entry["parm"])
        if parm is None:
            continue
        # Houdini 파일 파라미터는 플랫폼을 가리지 않고 슬래시로 쓴다. 씬 파일이
        # 다른 OS 에서 열려도 그대로 풀리게 하기 위해서다(패키지 JSON 의 hpath 와
        # 같은 이유). 경로 조립 자체는 pathlib 이 한다.
        new_raw = str(PurePosixPath(destination) / PurePosixPath(paths.to_parm(entry["raw"])).name)
        if new_raw == entry["raw"]:
            continue
        try:
            parm.set(new_raw)
        except hou.Error:
            # 잠긴 파라미터나 식이 걸린 파라미터는 건너뛴다. 무엇을 못 고쳤는지 알린다.
            changes.append({"node": entry["node"], "parm": entry["parm"], "failed": True})
            continue
        changes.append(
            {"node": entry["node"], "parm": entry["parm"], "from": entry["raw"], "to": new_raw}
        )
    return changes


# --------------------------------------------------------------------------
# remap_paths
# --------------------------------------------------------------------------


def _matching_form(find: str, raw: str) -> str | None:
    """raw 안에서 find 가 실제로 나타나는 형태. 구분자 방향이 달라도 찾는다.

    Windows 에서는 같은 경로가 `C:\\proj\\tex` 로도 `C:/proj/tex` 로도 쓰인다.
    사용자가 준 한쪽만 문자열 비교하면 나머지를 통째로 놓친다. 그래서 두 형태를
    모두 시도하고, **실제로 맞은 형태**를 돌려준다 — 그래야 치환이 원문의 나머지
    부분을 건드리지 않는다.
    """
    for candidate in (find, find.replace("\\", "/"), find.replace("/", "\\")):
        if candidate and candidate in raw:
            return candidate
    return None


@tool()
@undoable("Remap file paths")
def remap_paths(
    find: str,
    replace: str,
    kinds: Sequence[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """파일 참조 경로의 일부를 바꾼다. 씬을 다른 기계로 옮길 때 쓴다.

    **미전개 원문**을 고친다. 전개된 경로를 고치면 `$HIP` 이 절대 경로로 굳어
    씬이 이식성을 잃는다. 반대로 절대 경로를 `$HIP` 으로 되돌리는 데도 쓴다:
    find="C:/proj/castle", replace="$HIP".

    경로 구분자 방향은 신경 쓰지 않아도 된다. `C:\\proj\\tex` 로 주든
    `C:/proj/tex` 로 주든 양쪽 형태를 모두 찾는다 — Windows 에서는 같은 경로가
    씬 안에 두 형태로 섞여 있기 때문이다.

    기본이 dry_run 이다. 무엇이 바뀔지 먼저 보고, 맞으면 dry_run=False 로 다시
    부른다. 실제 변경은 Undo 하나로 묶이므로 Ctrl+Z 로 되돌릴 수 있다.

    Args:
        find: 찾을 문자열. 경로의 일부면 된다.
        replace: 바꿔 넣을 문자열. $HIP 같은 Houdini 변수를 그대로 써도 된다.
        kinds: hou.fileType 이름으로 거른다. 생략하면 전부.
        dry_run: True(기본)면 바꾸지 않고 계획만 돌려준다.
    """
    if not find:
        raise ValueError("find 가 비어 있습니다. 바꿀 경로 조각을 주세요.")

    changes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for entry in iter_references(kinds):
        raw = entry["raw"]
        needle = _matching_form(find, raw)
        if needle is None:
            continue
        new_raw = raw.replace(needle, replace)
        if new_raw == raw:
            continue
        record = {
            "node": entry["node"],
            "parm": entry["parm"],
            "from": raw,
            "to": new_raw,
            "kind": entry["kind"],
            "new_exists": bool(paths.resolve_files(new_raw)[0]),
        }
        if not dry_run:
            node = hou.node(entry["node"] or "")
            parm = node.parm(entry["parm"]) if node is not None and entry["parm"] else None
            if parm is None:
                failures.append({**record, "reason": "파라미터를 찾지 못했습니다."})
                continue
            try:
                parm.set(paths.to_parm(new_raw))
            except hou.Error as exc:
                failures.append({**record, "reason": str(exc)[:200]})
                continue
        changes.append(record)

    shown, total = truncate(changes, MAX_LISTED)
    result = {
        "find": find,
        "replace": replace,
        "dry_run": dry_run,
        "matched": total,
        "changed": 0 if dry_run else total,
        "still_missing": sum(1 for c in changes if not c["new_exists"]),
        "changes": shown,
        "truncated": max(0, total - len(shown)),
        "failures": failures,
    }
    if dry_run:
        result["note"] = (
            "바꾸지 않았습니다. 적용하려면 dry_run=False 로 다시 부르세요. "
            "still_missing 이 0 이 아니면 바꾼 경로에도 파일이 없습니다."
        )
    return result


# --------------------------------------------------------------------------
# 이식성 판정에 쓰는 공통 판단 (check 모듈이 쓴다)
# --------------------------------------------------------------------------


def portability_flags(entry: dict[str, Any]) -> list[str]:
    """참조 하나의 이식성 문제. 빈 목록이면 괜찮다."""
    flags: list[str] = []
    raw = entry["raw"]
    resolved = entry.get("resolved")

    if not raw.startswith("$") and not raw.startswith("op:"):
        candidate = Path(raw)
        if candidate.is_absolute():
            flags.append("absolute_path")

    if resolved:
        target = Path(resolved)
        hip_dir = paths.to_path("$HIP")
        hfs_dir = paths.to_path("$HFS")
        if paths.is_inside(target, hfs_dir):
            flags.append("inside_houdini_install")
        elif not paths.is_inside(target, hip_dir):
            flags.append("outside_hip")

    if not entry.get("exists") and entry["role"] == "input":
        flags.append("missing")

    if paths.has_sequence_token(raw) and entry.get("file_count") == 0:
        flags.append("empty_sequence")

    return flags
