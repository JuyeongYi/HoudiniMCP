"""VEXpression(`@P.y += 1;`)을 vcc 가 먹을 수 있는 순수 VEX 로 옮긴다.

wrangle 에 쓰는 것은 VEX 가 아니라 **VEXpression** 이다. 지어낸 이름이 아니라
wrangle 의 `snippet` 파라미터 라벨이 Houdini 안에서 그대로 `VEXpression` 이다
(실측 - attribwrangle / volumewrangle / pointwrangle 셋 다).

둘의 차이가 이 모듈이 있는 이유다. VEX 에는 `@` 가 없고 vcc 는 VEX 만 받는다.
`@name` 은 Snippet VOP 이 스니펫을 CVEX 함수로 감싸면서 바인딩된 파라미터로
바꿔 주는 설탕이다. 그 변환을 여기서 우리가 똑같이 한다 - `@` 가 틀린 것이
아니라 층이 다른 것이므로, 아래로 한 층 내려 주면 vcc 가 읽는다.

Houdini 에게 그 변환을 시킬 수는 없다. attribwrangle 안의 attribvop1 은
canGenerateCookCode() 가 False 라 생성된 코드를 꺼낼 수 없다.

## 줄·열 번호를 보존하는 방법

두 가지 장치를 쓴다.

1. 함수 본문 바로 앞에 `#line 1 "vex"` 를 심는다. 그러면 vcc 진단의 줄 번호가
   사용자가 준 코드 기준 그대로 나온다. 래퍼가 몇 줄이든 상관없다.
2. `@` 를 지울 때 **길이를 유지한다.** `v@scale` 은 `  scale` 이 된다 - 접두사와
   `@` 자리를 공백으로 채우므로 열 번호까지 어긋나지 않는다.

## 타입 추론

Houdini 실측(22.0.368)으로 확인한 규칙이다. 입력 지오메트리에 이미 그 이름의
어트리뷰트가 있어도 **타입을 거기서 가져오지 않는다.** 접두사가 없으면 아래
표를 보고, 표에 없으면 float 다. 우리도 똑같이 해야 Houdini 와 같은 진단이
나온다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PREFIX_TYPES: dict[str, str] = {
    "f": "float",
    "i": "int",
    "v": "vector",
    "p": "vector4",
    "u": "vector2",
    "2": "matrix2",
    "3": "matrix3",
    "4": "matrix",
    "s": "string",
    "d": "dict",
}
"""`@` 앞 접두사 -> VEX 타입. 실측으로 확인한 크기: u=2, v=3, p=4, 2=4, 3=9, 4=16."""

IMPLICIT_TYPES: dict[str, str] = {
    # vector - 실측
    "P": "vector",
    "N": "vector",
    "Cd": "vector",
    "v": "vector",
    "up": "vector",
    "force": "vector",
    "torque": "vector",
    "center": "vector",
    "rest": "vector",
    "uv": "vector",
    "scale": "vector",
    "accel": "vector",
    # vector4 - 실측
    "orient": "vector4",
    "rot": "vector4",
    "backtrack": "vector4",
    # int - 실측. 어트리뷰트가 아니라 wrangle 전역인 것들도 섞여 있다.
    "id": "int",
    "nextid": "int",
    "pstate": "int",
    "ptnum": "int",
    "numpt": "int",
    "primnum": "int",
    "numprim": "int",
    "vtxnum": "int",
    "numvtx": "int",
    "elemnum": "int",
    "numelem": "int",
    "ix": "int",
    "iy": "int",
    "iz": "int",
    "resx": "int",
    "resy": "int",
    "resz": "int",
    # string - 실측
    "name": "string",
    "instance": "string",
}
"""접두사 없는 `@name` 의 타입. 여기 없으면 float 다(Houdini 도 그렇다)."""

GROUP_PREFIX = "group_"
"""`@group_foo` 는 그룹 소속 여부라 int 다."""

WRANGLE_GLOBALS: frozenset[str] = frozenset(
    {
        "ptnum",
        "numpt",
        "primnum",
        "numprim",
        "vtxnum",
        "numvtx",
        "elemnum",
        "numelem",
        "Time",
        "Frame",
        "TimeInc",
        "SimTime",
        "SimFrame",
        "ix",
        "iy",
        "iz",
        "resx",
        "resy",
        "resz",
    }
)
"""어트리뷰트가 아니라 wrangle 이 늘 넣어 주는 전역.

입력 지오메트리에 없다고 경고하면 안 되는 이름들이다. `group_*` 과
`opinput*` 도 같은 이유로 예외지만 접두사 규칙으로 따로 거른다.
"""

DEFAULTS: dict[str, str] = {
    "float": "0",
    "int": "0",
    "vector": "{0, 0, 0}",
    "vector2": "{0, 0}",
    "vector4": "{0, 0, 0, 0}",
    "matrix2": "1",
    "matrix3": "1",
    "matrix": "1",
    "string": '""',
    "dict": "{}",
}
"""바인딩 파라미터의 기본값. 전부 실제로 컴파일되는 것을 확인했다."""

CHANNEL_TYPES: dict[str, str] = {
    "ch": "float",
    "chf": "float",
    "chi": "int",
    "chv": "vector",
    "chu": "vector2",
    "chp": "vector4",
    "ch2": "matrix2",
    "ch3": "matrix3",
    "ch4": "matrix",
    "chs": "string",
    "chdict": "dict",
    "chramp": "float",
}
"""`chf("scale")` 같은 호출에서 유도할 스페어 파라미터 타입."""

CHECK_FUNCTION = "houdini_mcp_vex_check"
"""검증용 래퍼 함수 이름. 씬에 남지 않으므로 아무 이름이어도 된다."""

_BINDING = re.compile(
    r"(?P<prefix>[fivpu234sd])?(?P<array>\[\])?@(?P<name>[A-Za-z_][A-Za-z_0-9]*)"
)

_ACCESS = re.compile(r"(?:\s*\.\s*[A-Za-z_][A-Za-z_0-9]*|\s*\[[^\]]*\])*")
"""바인딩 뒤에 붙는 성분/인덱스 접근. `@P.y`, `@arr[3]` 를 건너뛰는 데 쓴다."""

_ASSIGN = re.compile(r"\s*(?P<op>\+\+|--|(?:\+|-|\*|/|%|&|\||\^|<<|>>)?=)(?!=)")
"""쓰기로 볼 연산자. `==`, `!=`, `<=`, `>=` 는 걸리지 않는다."""

_CHANNEL = re.compile(
    r"\b(?P<fn>ch[a-z0-9]*)\s*\(\s*(?P<quote>[\"'])(?P<name>[^\"']*)(?P=quote)"
)

_INCLUDE = re.compile(r"^\s*#\s*include\b")


def anchor(code: str, label: str) -> str:
    """코드에 `#line` 앵커를 심어 진단의 줄 번호를 원본에 고정한다.

    `#include` 하나를 지날 때마다 전처리기가 줄 번호를 한 칸씩 밀어 놓는다(실측:
    include 두 개면 두 줄이 밀린다). 그래서 include 줄 바로 다음에 `#line` 을
    다시 박아 번호를 되돌린다. `#line` 은 물리적인 줄 수와 무관하게 번호를
    다시 잡아 주므로, 줄을 끼워 넣어도 사용자 코드의 번호는 그대로다.
    """
    masked = mask(code)
    out = [f'#line 1 "{label}"']
    for number, (line, masked_line) in enumerate(
        zip(code.splitlines(), masked.splitlines()), start=1
    ):
        out.append(line)
        if _INCLUDE.match(masked_line):
            out.append(f'#line {number + 1} "{label}"')
    return "\n".join(out)


@dataclass
class Binding:
    """스니펫이 참조하는 어트리뷰트 하나."""

    name: str
    base_type: str
    array: bool = False
    explicit: bool = False
    read: bool = False
    write: bool = False
    lines: list[int] = field(default_factory=list)

    @property
    def vex_type(self) -> str:
        return f"{self.base_type}[]" if self.array else self.base_type

    def declaration(self) -> str:
        """cvex 파라미터 선언 한 줄. 읽기만 해도 export 로 둔다.

        Houdini 도 wrangle 바인딩을 읽기·쓰기 양쪽으로 열어 둔다. export 를
        빼면 `@P.y += 1` 이 'Read-only expression' 로 잘못 걸린다.
        """
        if self.array:
            return f"export {self.base_type} {self.name}[] = {{}}"
        return f"export {self.base_type} {self.name} = {DEFAULTS[self.base_type]}"

    def to_dict(self) -> dict[str, Any]:
        access = "".join(("r" if self.read else "", "w" if self.write else "")) or "?"
        return {
            "name": self.name,
            "type": self.vex_type,
            "access": access,
            "explicit_type": self.explicit,
            "lines": self.lines,
        }


def mask(code: str, *, strings: bool = True) -> str:
    """주석(과 선택적으로 문자열)을 공백으로 덮은 사본. 줄 구조는 그대로 둔다.

    `// @Cd 를 고친다` 같은 주석이나 `"@P"` 같은 문자열 안의 `@` 를 어트리뷰트로
    오인하지 않기 위해서다. 길이와 줄바꿈을 유지하므로 원본과 위치가 1:1 이다.
    """
    out = list(code)
    index = 0
    size = len(code)
    while index < size:
        char = code[index]
        following = code[index + 1] if index + 1 < size else ""

        if char == "/" and following == "/":
            while index < size and code[index] != "\n":
                out[index] = " "
                index += 1
        elif char == "/" and following == "*":
            out[index] = out[index + 1] = " "
            index += 2
            while index < size:
                if code[index] == "*" and index + 1 < size and code[index + 1] == "/":
                    out[index] = out[index + 1] = " "
                    index += 2
                    break
                if code[index] != "\n":
                    out[index] = " "
                index += 1
        elif strings and char in "\"'":
            quote = char
            out[index] = " "
            index += 1
            while index < size and code[index] != quote:
                if code[index] == "\\" and index + 1 < size:
                    out[index] = " "
                    if code[index + 1] != "\n":
                        out[index + 1] = " "
                    index += 2
                    continue
                if code[index] != "\n":
                    out[index] = " "
                index += 1
            if index < size:
                out[index] = " "
                index += 1
        else:
            index += 1
    return "".join(out)


def _line_of(code: str, offset: int) -> int:
    return code.count("\n", 0, offset) + 1


def _resolve_type(name: str, prefix: str, overrides: dict[str, str] | None) -> str:
    if prefix:
        return PREFIX_TYPES[prefix]
    if overrides and name in overrides:
        return overrides[name]
    if name.startswith(GROUP_PREFIX):
        return "int"
    return IMPLICIT_TYPES.get(name, "float")


def translate(
    code: str, *, attrib_types: dict[str, str] | None = None
) -> tuple[str, list[Binding], list[dict[str, Any]]]:
    """스니펫을 순수 VEX 본문으로 바꾼다. (본문, 바인딩, 충돌).

    본문은 원본과 **글자 수가 같다.** `v@scale` -> `  scale` 처럼 접두사와 `@`
    자리를 공백으로 채우기 때문이다. 줄과 열이 하나도 어긋나지 않는다.

    Args:
        code: wrangle 스니펫.
        attrib_types: 접두사가 없는 어트리뷰트의 타입을 직접 지정한다.
            `{"myvec": "vector"}` 처럼 준다. 모델이 스니펫 안에서 접두사를 쓰지
            않았는데 float 가 아닌 것을 알고 있을 때 쓴다.
    """
    if attrib_types:
        unknown = sorted(set(attrib_types.values()) - set(DEFAULTS))
        if unknown:
            raise ValueError(
                f"모르는 VEX 타입입니다: {', '.join(unknown)}. "
                f"쓸 수 있는 것: {', '.join(sorted(DEFAULTS))}"
            )

    masked = mask(code)
    body = list(code)
    bindings: dict[str, Binding] = {}
    conflicts: list[dict[str, Any]] = []

    for match in _BINDING.finditer(masked):
        prefix = match.group("prefix") or ""
        array = bool(match.group("array"))
        name = match.group("name")
        line = _line_of(code, match.start())
        base_type = _resolve_type(name, prefix, attrib_types)

        # 접두사와 `@` 를 공백으로 바꾼다. 길이가 같아야 열 번호가 보존된다.
        for position in range(match.start(), match.start("name")):
            body[position] = " "

        existing = bindings.get(name)
        if existing is None:
            bindings[name] = Binding(
                name=name,
                base_type=base_type,
                array=array,
                explicit=bool(prefix),
                lines=[line],
            )
            existing = bindings[name]
        else:
            if line not in existing.lines:
                existing.lines.append(line)
            if (existing.base_type, existing.array) != (base_type, array):
                conflicts.append(
                    {
                        "name": name,
                        "line": line,
                        "declared": existing.vex_type,
                        "found": f"{base_type}[]" if array else base_type,
                    }
                )
                # 명시한 쪽을 채택한다. 둘 다 명시했으면 먼저 나온 것을 남긴다.
                if prefix and not existing.explicit:
                    existing.base_type = base_type
                    existing.array = array
                    existing.explicit = True

        end = match.end()
        access = _ACCESS.match(masked, end)
        after = access.end() if access else end
        assign = _ASSIGN.match(masked, after)
        if assign is None:
            existing.read = True
        elif assign.group("op") in ("=",):
            existing.write = True
        else:
            # `+=`, `++` 등은 읽고 쓴다.
            existing.read = True
            existing.write = True

    return "".join(body), list(bindings.values()), conflicts


def channels(code: str) -> list[dict[str, Any]]:
    """`chf("scale")` 류 호출에서 스페어 파라미터 후보를 뽑는다.

    vcc 의 `-u` 는 함수 시그니처만 다이얼로그 스크립트로 내보내고 ch() 호출은
    보지 않는다(실측). 그래서 여기서 직접 훑는다. 문자열 리터럴이 아닌
    `chf(some_var)` 는 정적으로 알 수 없으므로 건너뛴다.
    """
    scanned = mask(code, strings=False)
    found: dict[str, dict[str, Any]] = {}
    for match in _CHANNEL.finditer(scanned):
        function = match.group("fn")
        if function not in CHANNEL_TYPES:
            continue
        name = match.group("name")
        if not name:
            continue
        line = _line_of(code, match.start())
        entry = found.setdefault(
            name,
            {
                "name": name,
                "function": function,
                "type": CHANNEL_TYPES[function],
                "lines": [],
            },
        )
        if line not in entry["lines"]:
            entry["lines"].append(line)
    return list(found.values())


def wrap(
    code: str,
    *,
    attrib_types: dict[str, str] | None = None,
) -> tuple[str, list[Binding], list[dict[str, Any]]]:
    """스니펫을 vcc 에 넣을 수 있는 완전한 CVEX 소스로 감싼다.

    래퍼는 `#line` 라벨 두 개로 갈라 둔다. 사용자 코드에서 난 진단과 우리가 만든
    바인딩에서 난 진단을 구별하기 위해서다.
    """
    from .compiler import BINDING_LABEL, USER_LABEL

    body, bindings, conflicts = translate(code, attrib_types=attrib_types)
    parameters = ";\n        ".join(binding.declaration() for binding in bindings)
    signature = (
        f"cvex {CHECK_FUNCTION}(\n        {parameters})"
        if parameters
        else f"cvex {CHECK_FUNCTION}()"
    )

    source = (
        f'#line 1 "{BINDING_LABEL}"\n'
        f"{signature}\n"
        "{\n"
        f"{anchor(body, USER_LABEL)}\n"
        "}\n"
    )
    return source, bindings, conflicts
