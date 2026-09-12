"""HDA 를 Git 이 다룰 수 있는 디렉토리로 펼치고 다시 접는다.

바이너리 `.hda` 한 덩어리는 diff 가 안 되고, 두 사람이 같은 에셋을 고치면 머지가
불가능하다. `hou.hda.expandToDirectory` 는 정의마다 디렉토리를, 섹션마다 파일을
만든다. 여기까지는 기존 구현에 없는 개념이다.

**그런데 펼치기만 해서는 부족하다.** 실측으로 확인한 것:

- 기본 저장은 내용물을 압축해 `Contents.gz` 로 넣는다. 펼쳐도 이 파일은 gzip
  덩어리라 아무것도 읽히지 않는다 — 정작 노드 그래프가 들어 있는 파일이 그것이다.
- `HDAOptions.setCompressContents(False)` 로 저장하면 섹션이 `Contents` 가 되어
  **내용이 아스키로 읽힌다**. 그래서 `expand_hda` 는 기본으로 이것을 먼저 한다.
  다만 이 파일에는 블록 구분용 NUL 바이트가 섞여 있어 Git 은 여전히 바이너리로
  분류한다(`git diff --text` 나 `.gitattributes` 로 텍스트 취급하면 읽힌다).
- 정작 리뷰에서 봐야 하는 것 — 파라미터 인터페이스(`DialogScript`), 콜백
  스크립트(`PythonModule` 등), 생성 스크립트 — 는 펼치면 **완전한 텍스트**다.
  거기서 대부분의 변경이 보인다.
- `$HFS/bin/hotl -t` 와 `-X` 는 `Contents` 를 더 쪼개 주지만 비상업용
  라이선스에서 "Cannot convert non-commercial HDAs" / "ERROR?? 0 blocks" 로
  **빈 파일을 만든다**. 조용히 데이터를 잃으므로 외부 프로세스를 부르지 않고
  HOM 안에서만 처리한다.
- 설치되지 않은 정의에 `save()` 를 하면 CreateScript 같은 섹션이 사라진다.
  그래서 압축 해제는 **설치된 정의에만** 한다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/hda.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool, undoable

from ._common import require_directory, require_hda_file

BINARY_SUFFIXES = (".gz", ".bgeo", ".pic", ".bhclassic")
"""이름만으로 바이너리인 줄 아는 것들. 나머지는 내용을 읽어 판단한다."""


def _classify(path: Path) -> str:
    """파일이 버전 관리에서 어떻게 보이는지.

    - `text`   Git 이 그냥 diff 한다.
    - `framed` 아스키가 보이지만 NUL 로 블록을 나눈다. Git 은 바이너리로 보므로
               `git diff --text` 나 .gitattributes 가 필요하다.
    - `binary` 읽히지 않는다.
    """
    if path.suffix in BINARY_SUFFIXES:
        return "binary"
    try:
        data = path.read_bytes()
    except OSError:
        return "binary"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "binary"
    return "framed" if b"\x00" in data[:8192] else "text"


def _tree(root: Path) -> dict[str, Any]:
    """펼쳐진 디렉토리를 훑어 무엇이 읽히는지 센다."""
    files: list[dict[str, Any]] = []
    sizes = {"text": 0, "framed": 0, "binary": 0}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        size = path.stat().st_size
        kind = _classify(path)
        sizes[kind] += size
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": size,
                "kind": kind,
                "diffable": kind == "text",
            }
        )
    total = sum(sizes.values())
    return {
        "file_count": len(files),
        "files": files,
        "bytes_by_kind": sizes,
        "diffable_bytes": sizes["text"],
        "diffable_ratio": round(sizes["text"] / total, 3) if total else 0.0,
        "opaque": [f["path"] for f in files if f["kind"] == "binary"],
    }


@tool()
@undoable("Expand HDA to directory")
def expand_hda(
    file_path: str, directory: str, uncompress_contents: bool = True
) -> dict[str, Any]:
    """.hda 파일을 디렉토리로 펼친다. Git 에 올릴 수 있는 모양으로.

    정의마다 디렉토리가 생기고 섹션마다 파일이 생긴다. `Sections.list` 가 파일
    이름과 섹션 이름을 잇는다. 이 디렉토리를 커밋하면 리뷰에서 파라미터 변경이
    보인다.

    `uncompress_contents` 가 켜져 있으면 펼치기 전에 정의를 압축 없이 다시
    저장한다. 그래야 노드 그래프가 든 `Contents` 가 gzip 덩어리 대신 읽히는
    아스키가 된다. 이때 .hda 파일의 옵션이 바뀌고 파일 크기가 늘어난다 — 그것이
    버전 관리의 대가다.

    결과의 파일마다 `kind` 가 붙는다. `text` 는 Git 이 그대로 diff 하고
    (인터페이스를 담은 DialogScript 와 콜백 스크립트가 여기 속한다), `framed` 는
    아스키지만 NUL 이 섞여 Git 이 바이너리로 보는 것이며(노드 그래프),
    `binary` 는 읽히지 않는 것이다. `opaque` 가 비어 있으면 전부 눈으로 볼 수
    있다.

    Args:
        file_path: 펼칠 .hda 파일 경로.
        directory: 펼쳐 넣을 디렉토리. 없으면 만든다.
        uncompress_contents: True 면 먼저 압축을 풀어 저장한다.
    """
    source = require_hda_file(file_path)
    target = Path(hou.text.expandString(directory.strip())).expanduser()
    if target.exists() and not target.is_dir():
        raise ValueError(
            f"{target} 는 디렉토리가 아니라 파일입니다. 다른 경로를 주세요."
        )

    uncompressed: list[str] = []
    skipped: list[dict[str, str]] = []
    if uncompress_contents:
        for definition in hou.hda.definitionsInFile(str(source)):
            if not definition.isInstalled():
                # 설치되지 않은 정의를 저장하면 섹션이 사라진다(실측).
                skipped.append(
                    {
                        "type_name": definition.nodeTypeName(),
                        "why": (
                            "설치돼 있지 않습니다. install_hda 로 먼저 설치하면 "
                            "압축을 풀 수 있습니다."
                        ),
                    }
                )
                continue
            options = definition.options()
            if not options.compressContents():
                continue
            options.setCompressContents(False)
            definition.setOptions(options)
            definition.save(definition.libraryFilePath(), create_backup=False)
            uncompressed.append(definition.nodeTypeName())

    try:
        hou.hda.expandToDirectory(str(source), str(target))
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{source} 를 {target} 로 펼치지 못했습니다: {exc} "
            f"디렉토리가 쓰기 가능한지 확인하세요."
        ) from exc

    tree = _tree(target)
    result: dict[str, Any] = {
        "file": str(source),
        "directory": str(target),
        "uncompressed": uncompressed,
        **tree,
    }
    if skipped:
        result["not_uncompressed"] = skipped
    if tree["opaque"]:
        result["note"] = (
            f"읽히지 않는 파일이 남았습니다: {', '.join(tree['opaque'])}. "
            f"uncompress_contents 를 켜고 다시 부르거나, 그 정의를 install_hda 로 "
            f"설치한 뒤 다시 부르세요."
        )
    elif tree["bytes_by_kind"]["framed"]:
        result["note"] = (
            "노드 그래프(Contents)는 아스키지만 NUL 로 블록을 나눠 Git 이 "
            "바이너리로 봅니다. .gitattributes 에 `* -text diff` 를 주거나 "
            "`git diff --text` 로 보면 읽힙니다. 파라미터 인터페이스와 콜백 "
            "스크립트는 그대로 diff 됩니다."
        )
    return result


@tool()
@undoable("Collapse HDA from directory")
def collapse_hda(
    directory: str, file_path: str, install: bool = True
) -> dict[str, Any]:
    """펼쳐 둔 디렉토리를 다시 .hda 파일로 접는다.

    `expand_hda` 의 역이다. Git 에서 받은 디렉토리를 Houdini 가 읽을 수 있는
    파일로 되돌린다. 접은 뒤 `install=True` 면 이 세션에 설치하므로 바로 쓸 수
    있다.

    접은 결과에 어떤 정의가 들어 있는지 돌려주므로, 왕복에서 빠진 것이 있으면
    바로 보인다.

    Args:
        directory: `expand_hda` 가 만든 디렉토리.
        file_path: 만들 .hda 파일 경로. 이미 있으면 덮어쓴다.
        install: True 면 접은 뒤 이 세션에 설치한다.
    """
    source = require_directory(directory)
    target = require_hda_file(file_path, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        hou.hda.collapseFromDirectory(str(target), str(source))
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{source} 를 {target} 로 접지 못했습니다: {exc} "
            f"expand_hda 가 만든 디렉토리인지 확인하세요(Sections.list 가 있어야 합니다)."
        ) from exc

    definitions = hou.hda.definitionsInFile(str(target))
    if install:
        hou.hda.installFile(str(target))
        definitions = hou.hda.definitionsInFile(str(target))

    return {
        "directory": str(source),
        "file": str(target),
        "size": target.stat().st_size,
        "installed": install,
        "count": len(definitions),
        "definitions": [
            {
                "type_name": definition.nodeTypeName(),
                "category": definition.nodeTypeCategory().name(),
                "sections": sorted(definition.sections()),
                "installed": definition.isInstalled(),
            }
            for definition in definitions
        ],
        "next": "validate_hda 로 실제 인스턴스를 놓아 왕복이 온전한지 확인하세요.",
    }
