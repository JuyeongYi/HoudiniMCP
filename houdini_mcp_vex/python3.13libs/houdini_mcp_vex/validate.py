"""노드를 만들지 않고 VEX 를 검증한다.

이 모듈의 툴은 **씬을 한 글자도 바꾸지 않는다.** 임시 디렉토리에 파일을 쓰고
`vcc` 를 부르고 지우는 것이 전부다. 검증하려고 wrangle 을 만들어 쿡하던 기존
방식과 갈라지는 지점이다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from . import compiler, snippet

MODE_SNIPPET = "snippet"
MODE_SOURCE = "source"

DEFAULT_CONTEXT = "cvex"
"""wrangle 스니펫은 전부 CVEX 로 돈다. 셰이더 소스를 볼 때만 바꾸면 된다."""

ELEMENT_CLASSES = ("point", "prim", "vertex", "detail")

RUN_OVER_ALIASES = {"primitive": "prim", "points": "point", "prims": "prim"}
"""부르는 사람마다 다르게 쓰는 이름. 대조할 때만 받아 준다."""

MAX_SOURCE = 400
"""진단에 붙이는 원문 한 줄의 최대 길이."""


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


# ---- 지오메트리 어트리뷰트 --------------------------------------------


def _vex_type(attrib: hou.Attrib) -> str:
    """hou.Attrib 을 VEX 타입 이름으로. 크기로 vector/matrix 를 가른다."""
    data = attrib.dataType()
    if data == hou.attribData.String:
        base = "string"
    elif data == hou.attribData.Dict:
        base = "dict"
    elif data == hou.attribData.Int:
        base = "int"
    else:
        base = {
            1: "float",
            2: "vector2",
            3: "vector",
            4: "vector4",
            9: "matrix3",
            16: "matrix",
        }.get(attrib.size(), "float")
    return f"{base}[]" if attrib.isArrayType() else base


def geometry_attribs(node: hou.Node) -> dict[str, dict[str, str]]:
    """노드가 내놓는 지오메트리의 어트리뷰트를 클래스별로. SOP 가 아니면 빈 dict."""
    getter = getattr(node, "geometry", None)
    if getter is None:
        return {}
    try:
        geo = getter()
    except hou.OperationFailed:
        return {}
    if geo is None:
        return {}

    sources = (
        ("point", geo.pointAttribs),
        ("prim", geo.primAttribs),
        ("vertex", geo.vertexAttribs),
        ("detail", geo.globalAttribs),
    )
    out: dict[str, dict[str, str]] = {}
    for name, source in sources:
        try:
            out[name] = {a.name(): _vex_type(a) for a in source()}
        except hou.OperationFailed:
            out[name] = {}
    return out


def cross_check(
    bindings: list[snippet.Binding],
    attribs: dict[str, dict[str, str]],
    *,
    run_over: str = "point",
) -> dict[str, Any]:
    """스니펫이 읽는 어트리뷰트가 입력에 실제로 있는지 대조한다.

    읽기만 하는 이름이 어디에도 없으면 값이 0 으로 들어온다 - 에러가 아니라서
    컴파일러는 아무 말도 하지 않는다. 이것이 wrangle 이 조용히 틀리는 가장 흔한
    이유다.

    Args:
        bindings: translate 가 뽑은 바인딩.
        attribs: geometry_attribs 의 결과.
        run_over: wrangle 이 도는 요소 클래스. 여기서 먼저 찾고 detail 로 떨어진다.
    """
    if not attribs:
        return {"checked": False}

    order = [run_over] + [c for c in ELEMENT_CLASSES if c != run_over]
    missing: list[dict[str, Any]] = []
    mismatched: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []

    for binding in bindings:
        name = binding.name
        if name in snippet.WRANGLE_GLOBALS or name.startswith(snippet.GROUP_PREFIX):
            continue
        if name.startswith("opinput"):
            continue

        where = next((c for c in order if name in attribs.get(c, {})), None)
        if where is None:
            if binding.read:
                missing.append(
                    {
                        "name": name,
                        "type": binding.vex_type,
                        "lines": binding.lines,
                        "creates": binding.write,
                    }
                )
            continue

        found = attribs[where][name]
        entry = {
            "name": name,
            "found_in": where,
            "geometry_type": found,
            "snippet_type": binding.vex_type,
            "lines": binding.lines,
        }
        if found != binding.vex_type:
            mismatched.append(entry)
        else:
            matched.append(entry)

    return {
        "checked": True,
        "run_over": run_over,
        "matched": matched,
        "missing": missing,
        "type_mismatch": mismatched,
    }


# ---- 검증 -------------------------------------------------------------


def check(
    code: str,
    *,
    mode: str = MODE_SNIPPET,
    context: str = DEFAULT_CONTEXT,
    attrib_types: dict[str, str] | None = None,
    include_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """코드를 컴파일해 본다. 툴이 아니라 다른 모듈도 쓰는 공용 진입점."""
    if mode not in (MODE_SNIPPET, MODE_SOURCE):
        raise ValueError(
            f"mode 는 {MODE_SNIPPET!r} 또는 {MODE_SOURCE!r} 여야 합니다: {mode!r}. "
            f"wrangle 에 넣을 코드면 {MODE_SNIPPET!r}, 컨텍스트 함수까지 직접 쓴 "
            f"VEX 파일이면 {MODE_SOURCE!r} 입니다."
        )
    known = compiler.contexts()
    if context not in known:
        raise ValueError(
            f"그런 VEX 컨텍스트가 없습니다: {context!r}. "
            f"쓸 수 있는 것: {', '.join(known)}"
        )

    bindings: list[snippet.Binding] = []
    conflicts: list[dict[str, Any]] = []
    if mode == MODE_SNIPPET:
        source, bindings, conflicts = snippet.wrap(code, attrib_types=attrib_types)
    else:
        source = snippet.anchor(code, compiler.USER_LABEL) + "\n"

    outcome = compiler.compile_source(
        source, context=context, include_dirs=include_dirs
    )
    diagnostics = outcome["diagnostics"]
    compiler.attach_source(diagnostics, code)
    for diagnostic in diagnostics:
        text = diagnostic.get("source")
        if text is not None and len(text) > MAX_SOURCE:
            diagnostic["source"] = text[:MAX_SOURCE] + " …"

    errors = [d for d in diagnostics if d["severity"] == "error"]
    warnings = [d for d in diagnostics if d["severity"] == "warning"]
    infos = [d for d in diagnostics if d["severity"] == "info"]

    assumed = [
        binding.name
        for binding in bindings
        if not binding.explicit
        and binding.name not in snippet.IMPLICIT_TYPES
        and not binding.name.startswith(snippet.GROUP_PREFIX)
        and not (attrib_types and binding.name in attrib_types)
    ]

    result: dict[str, Any] = {
        "ok": not errors,
        "mode": mode,
        "context": context,
        "line_count": len(code.splitlines()),
        "errors": errors,
        "warnings": warnings,
        "bindings": [binding.to_dict() for binding in bindings],
        "channels": snippet.channels(code),
    }
    if infos:
        result["infos"] = infos
    if conflicts:
        result["type_conflicts"] = conflicts
    if assumed:
        # 접두사가 없으면 float 로 본다. Houdini 도 그렇게 하지만, 모델이
        # 의도한 타입이 아니었다면 여기서 바로잡을 수 있어야 한다.
        result["assumed_float"] = assumed
    if outcome["notes"]:
        result["compiler_notes"] = outcome["notes"][:10]
    result["summary"] = _summary(result)
    return result


def _summary(result: dict[str, Any]) -> str:
    """모델이 한 줄만 읽어도 다음 할 일을 알 수 있게."""
    errors = result["errors"]
    if errors:
        first = errors[0]
        where = (
            f"{first['line']}행 {first['column']}열"
            if first.get("scope") == compiler.SCOPE_CODE
            else "바인딩 생성 구간"
        )
        return f"에러 {len(errors)}개. 첫 에러는 {where}: {first['message']}"
    parts = ["컴파일 성공"]
    if result["warnings"]:
        parts.append(f"경고 {len(result['warnings'])}개")
    if result.get("assumed_float"):
        parts.append(
            f"접두사 없는 어트리뷰트 {len(result['assumed_float'])}개를 float 로 "
            f"봤습니다. 아니면 접두사(v@, i@ …)를 붙이세요"
        )
    return ". ".join(parts)


def format_errors(result: dict[str, Any]) -> str:
    """에러를 사람이 읽을 한 덩어리로. 노드를 만들기 전에 거절할 때 쓴다."""
    lines = []
    for diagnostic in result["errors"]:
        if diagnostic.get("scope") == compiler.SCOPE_CODE:
            head = f"  {diagnostic['line']}행 {diagnostic['column']}열: "
        else:
            head = "  (바인딩 생성 구간): "
        lines.append(head + diagnostic["message"])
        if diagnostic.get("source"):
            lines.append(f"      | {diagnostic['source']}")
    return "\n".join(lines)


# ---- 툴 ---------------------------------------------------------------


@tool()
def validate_vex(
    code: str,
    mode: str = MODE_SNIPPET,
    context: str = DEFAULT_CONTEXT,
    attrib_types: dict[str, str] | None = None,
    include_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """VEX 를 컴파일해서 검증한다. 노드를 만들지 않고 씬도 건드리지 않는다.

    Houdini 의 VEX 컴파일러(`$HFS/bin/vcc`)를 직접 부른다. 그래서 입력
    지오메트리가 없어도, 씬이 비어 있어도 검증된다. 에러는 줄·열 번호와 그 줄의
    원문까지 함께 준다.

    wrangle 에 넣을 코드를 쓸 때는 이것을 먼저 통과시킨다. create_wrangle 과
    update_wrangle 은 어차피 내부에서 이 검증을 거치므로, 코드를 여러 번 고칠
    계획이면 여기서 먼저 다듬는 편이 싸다.

    반환값의 bindings 는 코드가 건드리는 어트리뷰트와 읽기/쓰기 여부다.
    channels 는 `chf("scale")` 처럼 스페어 파라미터를 요구하는 호출이다.

    Args:
        code: 검증할 코드. mode 에 따라 스니펫이거나 완전한 VEX 소스다.
        mode: "snippet" 이면 wrangle 에 넣는 조각(`@P.y += 1;`)으로 본다.
            "source" 면 컨텍스트 함수까지 직접 쓴 VEX 파일로 본다.
        context: VEX 컨텍스트. wrangle 스니펫은 전부 "cvex" 다. 셰이더 소스를
            볼 때만 "surface" 등으로 바꾼다. list_vex_contexts 로 목록을 본다.
        attrib_types: 접두사를 쓰지 않은 어트리뷰트의 타입을 직접 지정한다.
            예: {"myvec": "vector"}. 주지 않으면 Houdini 와 같은 규칙으로
            추론하고, 모르는 이름은 float 로 본다.
        include_dirs: `#include "..."` 를 찾을 추가 디렉토리.
    """
    return check(
        code,
        mode=mode,
        context=context,
        attrib_types=attrib_types,
        include_dirs=include_dirs,
    )


@tool()
def wrangle_attribs(
    code: str,
    input_path: str | None = None,
    run_over: str = "point",
    attrib_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    """코드가 읽고 쓰는 어트리뷰트를 뽑고, 입력에 실제로 있는지 대조한다.

    컴파일이 통과해도 wrangle 이 조용히 틀리는 가장 흔한 이유는 없는
    어트리뷰트를 읽는 것이다. VEX 는 없는 어트리뷰트를 0 으로 읽고 넘어가므로
    에러가 나지 않는다. input_path 를 주면 그 노드의 지오메트리와 대조해서
    없는 것을 짚어 준다.

    input_path 를 주지 않으면 정적 분석 결과만 돌려준다.

    Args:
        code: wrangle 스니펫.
        input_path: 대조할 입력 노드 경로. 보통 wrangle 의 첫 입력이다.
            쿡되지 않았으면 쿡한다.
        run_over: wrangle 이 도는 요소. "point", "prim", "vertex", "detail".
            여기서 먼저 찾고 없으면 다른 클래스에서 찾는다.
        attrib_types: 접두사를 쓰지 않은 어트리뷰트의 타입 지정.
    """
    run_over = RUN_OVER_ALIASES.get(run_over, run_over)
    if run_over not in ELEMENT_CLASSES:
        raise ValueError(
            f"run_over 는 {', '.join(ELEMENT_CLASSES)} 중 하나여야 합니다: "
            f"{run_over!r}"
        )

    _body, bindings, conflicts = snippet.translate(code, attrib_types=attrib_types)
    result: dict[str, Any] = {
        "reads": [b.to_dict() for b in bindings if b.read],
        "writes": [b.to_dict() for b in bindings if b.write],
        "channels": snippet.channels(code),
    }
    if conflicts:
        result["type_conflicts"] = conflicts

    if input_path:
        node = _require(input_path)
        try:
            node.cook()
        except hou.OperationFailed as exc:
            raise ValueError(
                f"{input_path} 를 쿡하지 못해 어트리뷰트를 읽을 수 없습니다. "
                f"먼저 그 노드의 에러를 고치세요. ({str(exc).splitlines()[0]})"
            ) from exc
        attribs = geometry_attribs(node)
        if not attribs:
            result["input"] = {
                "path": node.path(),
                "comment": node.comment(),
                "note": "지오메트리를 내놓는 노드가 아니라 대조하지 못했습니다.",
            }
        else:
            result["input"] = {
                "path": node.path(),
                "comment": node.comment(),
                "attribs": {k: sorted(v) for k, v in attribs.items()},
            }
            result["cross_check"] = cross_check(
                bindings, attribs, run_over=run_over
            )

    missing = result.get("cross_check", {}).get("missing") or []
    if missing:
        names = ", ".join(entry["name"] for entry in missing)
        result["summary"] = (
            f"입력에 없는 어트리뷰트를 읽습니다: {names}. 0 으로 읽히므로 에러는 "
            f"나지 않습니다. 이름을 확인하거나 앞 노드에서 만드세요."
        )
    else:
        result["summary"] = (
            f"읽기 {len(result['reads'])}개, 쓰기 {len(result['writes'])}개"
        )
    return result
