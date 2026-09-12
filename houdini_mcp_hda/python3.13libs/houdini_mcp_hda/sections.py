"""HDA 정의 안의 섹션 — 콜백 스크립트와 헬프를 읽고 쓴다.

섹션은 .hda 파일 안의 이름 붙은 파일이다. 노드의 동작을 파이썬으로 확장하는
자리이며, 여기 없으면 에셋은 파라미터만 있는 껍데기다.

| 섹션 | 언제 도는가 |
|---|---|
| `PythonModule` | `hou.phm()` 으로 부르는 에셋 전용 함수들 |
| `OnCreated` | 인스턴스를 만들 때 |
| `OnLoaded` | hip 파일에서 읽힐 때 |
| `OnDeleted` | 지울 때 |
| `OnInputChanged` | 입력 연결이 바뀔 때 |
| `OnUpdated` | 정의가 갱신될 때 |
| `PreFirstCreate` | 그 타입의 첫 인스턴스를 만들기 직전 |
| `Help` | 노드 도움말 (wiki 문법) |

스크립트 섹션이 파이썬인지 HScript 인지는 섹션 내용이 아니라 `extraFileOptions`
의 `<섹션>/IsPython` 플래그가 정한다. 이걸 빠뜨리면 파이썬 코드가 HScript 로
실행돼서 알 수 없는 에러가 난다 — `set_hda_section` 이 대신 채운다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/HDASection.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from ._common import definition_summary, persist, require_definition

PREVIEW_CHARS = 200
"""목록에서 보여 줄 내용 앞부분 길이. 전체는 get_hda_section 으로 읽는다."""

PYTHON_OPTION = "IsPython"

LANGUAGES = {
    "python": True,
    "hscript": False,
    "text": None,
}
"""언어 이름 -> IsPython 플래그. text 는 스크립트가 아닌 섹션(Help 등)."""

# 정의를 이루는 뼈대라 손으로 건드리면 에셋이 깨진다.
PROTECTED = frozenset(
    {
        "Contents",
        "Contents.gz",
        "Contents.dir",
        "DialogScript",
        "CreateScript",
        "InternalFileOptions",
        "ExtraFileOptions",
        "TypePropertiesOptions",
        "INDEX__SECTION",
        "Sections.list",
        "houdini.hdalibrary",
    }
)


def _is_python(definition: hou.HDADefinition, name: str) -> bool | None:
    return definition.extraFileOptions().get(f"{name}/{PYTHON_OPTION}")


def _decode(section: hou.HDASection) -> tuple[str | None, bool]:
    """섹션 내용을 텍스트로. 바이너리면 (None, True)."""
    try:
        return section.contents(), False
    except (UnicodeDecodeError, hou.OperationFailed):
        return None, True


@tool()
def hda_sections(target: str) -> dict[str, Any]:
    """HDA 정의 안의 섹션을 나열한다. 크기와 언어, 내용 앞부분까지.

    어떤 콜백이 이미 붙어 있는지, PythonModule 이 있는지 여기서 확인한다.
    전체 내용은 `get_hda_section` 으로 읽는다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름
            (Sop/ns::brick_maker::1.0).
    """
    definition = require_definition(target)
    entries: list[dict[str, Any]] = []
    for name, section in sorted(definition.sections().items()):
        text, binary = _decode(section)
        entry: dict[str, Any] = {
            "name": name,
            "size": section.size(),
            "binary": binary,
            "protected": name in PROTECTED,
        }
        flag = _is_python(definition, name)
        if flag is not None:
            entry["language"] = "python" if flag else "hscript"
        if text is not None:
            entry["preview"] = text[:PREVIEW_CHARS]
            entry["truncated"] = len(text) > PREVIEW_CHARS
        entries.append(entry)

    return {
        "definition": definition_summary(definition),
        "count": len(entries),
        "sections": entries,
        "extra_file_options": dict(definition.extraFileOptions()),
    }


@tool()
def get_hda_section(target: str, name: str) -> dict[str, Any]:
    """섹션 하나의 내용을 통째로 읽는다.

    콜백 스크립트를 고치기 전에 지금 무엇이 들어 있는지 본다. 바이너리 섹션
    (Contents.gz 등)은 내용 대신 크기만 돌려준다 — 모델이 읽을 것이 아니다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름.
        name: 섹션 이름. 예: PythonModule
    """
    definition = require_definition(target)
    sections = definition.sections()
    if name not in sections:
        raise ValueError(
            f"{definition.nodeTypeName()} 에 {name!r} 섹션이 없습니다. "
            f"있는 섹션: {', '.join(sorted(sections))}"
        )

    section = sections[name]
    text, binary = _decode(section)
    flag = _is_python(definition, name)
    return {
        "definition": definition_summary(definition),
        "name": name,
        "size": section.size(),
        "binary": binary,
        "language": None if flag is None else ("python" if flag else "hscript"),
        "contents": text,
        "note": (
            "바이너리 섹션이라 내용을 돌려주지 않습니다. expand_hda 로 펼쳐서 "
            "파일로 보세요."
            if binary
            else None
        ),
    }


@tool()
@undoable("Set HDA section")
def set_hda_section(
    target: str, name: str, contents: str, language: str = "python"
) -> dict[str, Any]:
    """섹션 내용을 쓰고 .hda 파일에 저장한다. 없으면 만든다.

    `PythonModule` 에 함수를 넣어 두면 인스턴스에서 `hou.phm().함수()` 로 부를
    수 있고, 파라미터 콜백과 다른 섹션도 그걸 쓴다. `OnCreated` 는 인스턴스를
    만들 때 한 번 돈다.

    language 를 주면 `extraFileOptions` 의 IsPython 플래그를 함께 맞춘다.
    이걸 빠뜨려서 파이썬이 HScript 로 실행되는 것이 흔한 사고다.

    Contents/DialogScript 같은 뼈대 섹션은 쓰지 못한다. 파라미터는
    `add_hda_parm`, 내용물은 `promote_parm` 이나 정의 재저장으로 바꾼다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름.
        name: 섹션 이름. 예: PythonModule, OnCreated, Help
        contents: 넣을 내용. 스크립트라면 영어 주석으로 쓴다.
        language: python / hscript / text. text 는 스크립트가 아닌 섹션.
    """
    if language not in LANGUAGES:
        raise ValueError(
            f"language 는 {', '.join(LANGUAGES)} 중 하나여야 합니다: {language!r}"
        )
    if not name or not name.strip():
        raise ValueError("name 이 비어 있습니다. 섹션 이름을 주세요. 예: PythonModule")
    name = name.strip()
    if name in PROTECTED:
        raise ValueError(
            f"{name!r} 은 정의의 뼈대 섹션이라 직접 쓸 수 없습니다. "
            f"파라미터는 add_hda_parm, 내부 노드는 promote_parm 으로 바꾸세요."
        )

    definition = require_definition(target)
    existed = name in definition.sections()
    definition.addSection(name, contents)

    flag = LANGUAGES[language]
    if flag is not None:
        definition.setExtraFileOption(f"{name}/{PYTHON_OPTION}", flag)
    saved = persist(definition)

    return {
        "definition": definition_summary(definition),
        "name": name,
        "created": not existed,
        "size": definition.sections()[name].size(),
        "language": language,
        "sections": sorted(definition.sections()),
        "saved_to": saved,
    }


@tool()
@undoable("Remove HDA section")
def remove_hda_section(target: str, name: str) -> dict[str, Any]:
    """섹션을 지우고 .hda 파일에 저장한다.

    뼈대 섹션은 지울 수 없다. 콜백 스크립트를 떼거나 안 쓰는 헬프를 치울 때 쓴다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름.
        name: 지울 섹션 이름.
    """
    definition = require_definition(target)
    sections = definition.sections()
    if name not in sections:
        raise ValueError(
            f"{definition.nodeTypeName()} 에 {name!r} 섹션이 없습니다. "
            f"있는 섹션: {', '.join(sorted(sections))}"
        )
    if name in PROTECTED:
        raise ValueError(
            f"{name!r} 은 정의의 뼈대 섹션이라 지우면 에셋이 깨집니다. "
            f"지울 수 있는 것: "
            f"{', '.join(sorted(set(sections) - PROTECTED)) or '(없음)'}"
        )

    size = sections[name].size()
    definition.removeSection(name)
    option = f"{name}/{PYTHON_OPTION}"
    if option in definition.extraFileOptions():
        definition.removeExtraFileOption(option)
    saved = persist(definition)

    return {
        "definition": definition_summary(definition),
        "removed": name,
        "removed_size": size,
        "sections": sorted(definition.sections()),
        "saved_to": saved,
    }
