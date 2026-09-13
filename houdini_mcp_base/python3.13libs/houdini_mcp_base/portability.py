"""씬을 넘기기 전에 보는 것 — 이식성 점검.

`list_dependencies` 는 목록이고, 이것은 **판정**이다. 무엇이 잘못됐는지가 아니라
무엇을 하면 되는지까지 돌려준다.

잡는 것은 넷이다.

1. **없는 파일** — 참조는 있는데 디스크에 없다. 시퀀스는 한 장도 없을 때만.
2. **절대 경로** — `$HIP` 없이 `C:/...` 로 박힌 참조. 다른 기계에서 깨진다.
3. **$HIP 밖 참조** — 경로는 풀리는데 프로젝트 밖을 본다. 씬만 옮기면 깨진다.
   Houdini 설치 안($HFS)을 보는 것은 따로 센다 — 그건 어디서나 풀린다.
4. **빈 시퀀스** — `$F4` / `<UDIM>` 참조인데 실제 파일이 0장.

씬을 저장하지 않았으면 `$HIP` 이 임시 위치라 3번이 통째로 거짓 경보가 된다.
그래서 그 사실을 먼저 알려 준다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool

from . import paths
from .deps import iter_references, portability_flags, truncate

MAX_LISTED = 100

FIX_HINTS = {
    "missing": (
        "파일이 없습니다. probe_file 로 경로가 제대로 풀리는지 보고, 옮겨진 것이면 "
        "remap_paths 로 한 번에 고치세요."
    ),
    "absolute_path": (
        "절대 경로가 박혀 있습니다. remap_paths(find='<프로젝트 디렉토리>', "
        "replace='$HIP') 로 바꾸면 다른 기계에서도 풀립니다."
    ),
    "outside_hip": (
        "$HIP 밖을 참조합니다. 씬 파일만 옮기면 깨집니다. collect_dependencies 로 "
        "프로젝트 안으로 모으고 relink=True 를 주세요."
    ),
    "inside_houdini_install": (
        "Houdini 설치($HFS) 안의 파일입니다. 같은 버전이 깔린 곳에서는 풀리지만, "
        "납품물에 포함되지는 않습니다."
    ),
    "empty_sequence": (
        "시퀀스 참조인데 실제 파일이 한 장도 없습니다. 캐시를 아직 굽지 않았거나 "
        "프레임 패딩($F4 vs $F)이 실제 파일과 다를 수 있습니다."
    ),
}


@tool()
def validate_scene(include_outputs: bool = False, limit: int = MAX_LISTED) -> dict[str, Any]:
    """씬을 다른 기계로 옮길 수 있는지 판정한다. 없는 파일과 박힌 경로를 잡는다.

    `hou.fileReferences()` 로 참조를 전부 얻은 뒤 넷을 본다 — 없는 파일, 절대
    경로, $HIP 밖 참조, 빈 시퀀스. 문제마다 **무엇을 하면 되는지**를 함께 준다.

    출력 경로(ROP 의 sopoutput, picture 등)는 기본적으로 뺀다. 아직 렌더하지 않은
    경로를 "없는 파일"이라고 하면 거짓 경보이기 때문이다.

    씬을 아직 저장하지 않았으면 $HIP 이 임시 위치라 "밖을 참조한다"가 거의 전부
    참이 된다. 그 경우 saved=False 로 먼저 알려 준다.

    Args:
        include_outputs: True 면 출력 경로 파라미터도 판정 대상에 넣는다.
        limit: 문제 목록에 담을 최대 개수.
    """
    hip_path = Path(hou.hipFile.path())
    saved = hip_path.exists()

    issues: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    checked = 0

    for entry in iter_references():
        if not include_outputs and entry["role"] != "input":
            continue
        checked += 1
        flags = portability_flags(entry)
        if not flags:
            continue
        for flag in flags:
            counts[flag] = counts.get(flag, 0) + 1
        issues.append(
            {
                "node": entry["node"],
                "node_type": entry["node_type"],
                "comment": entry["comment"],
                "parm": entry["parm"],
                "raw": entry["raw"],
                "resolved": entry["resolved"],
                "kind": entry["kind"],
                "flags": flags,
            }
        )

    # 가장 아픈 것이 위로 오게. 없는 파일 > 빈 시퀀스 > 절대 경로 > 밖 참조.
    severity = {
        "missing": 0,
        "empty_sequence": 1,
        "absolute_path": 2,
        "outside_hip": 3,
        "inside_houdini_install": 4,
    }
    issues.sort(key=lambda i: min(severity.get(f, 9) for f in i["flags"]))

    shown, total = truncate(issues, max(1, limit))
    blocking = counts.get("missing", 0) + counts.get("empty_sequence", 0)
    return {
        "hip": hip_path.as_posix(),
        "saved": saved,
        "hip_dir": paths.expand("$HIP"),
        "checked": checked,
        "issue_count": total,
        "blocking_count": blocking,
        "portable": total == 0,
        "by_flag": dict(sorted(counts.items())),
        "fixes": {flag: FIX_HINTS[flag] for flag in sorted(counts) if flag in FIX_HINTS},
        "issues": shown,
        "truncated": max(0, total - len(shown)),
        "note": (
            None
            if saved
            else (
                "씬을 아직 저장하지 않아 $HIP 이 임시 위치입니다. outside_hip 판정은 "
                "저장한 뒤에 다시 보세요(save_scene)."
            )
        ),
    }
