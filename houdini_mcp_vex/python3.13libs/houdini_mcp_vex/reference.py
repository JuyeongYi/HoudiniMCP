"""VEX 언어 자체의 레퍼런스 — 컨텍스트, 전역 변수, 함수 시그니처.

전부 `vcc` 에서 받아온다. 문서를 긁거나 헤더를 파싱하지 않는다. vcc 의
`--list-context-json` 이 컨텍스트별로 전역 변수와 함수 시그니처를 통째로 준다
(실측: sop 컨텍스트에 함수 1,036개).

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from . import compiler

CONTEXT_ALIASES = {"displacement": "displace"}
"""hou 쪽 이름과 vcc 쪽 이름이 다른 것. 나머지는 소문자로 맞추면 같다(실측)."""

MAX_MATCHES = 40
MAX_SIGNATURES = 24


def _vcc_name(context: hou.VexContext) -> str:
    name = context.name().lower()
    return CONTEXT_ALIASES.get(name, name)


def _signature(function: str, entry: dict[str, Any]) -> str:
    """`float noise(const float, const float)` 형태로 한 줄."""
    args = ", ".join(entry.get("args") or [])
    text = f"{entry.get('return', 'void')} {function}({args})"
    if entry.get("variadic"):
        text += "  …"
    return text


@tool()
def list_vex_contexts(context: str | None = None) -> dict[str, Any]:
    """VEX 컨텍스트 목록. 하나를 지정하면 그 컨텍스트의 전역 변수까지 준다.

    컨텍스트는 VEX 코드가 어디서 도는지다. wrangle 스니펫은 전부 cvex 고,
    셰이더는 surface/displace 같은 것들이다. 전역 변수는 그 컨텍스트가 코드에
    그냥 넣어 주는 값이라 선언 없이 쓴다.

    Args:
        context: 전역 변수를 볼 컨텍스트. 예: sop, cvex, surface.
            생략하면 목록만 준다.
    """
    known = compiler.contexts()
    by_vcc_name = {_vcc_name(c): c for c in hou.vexContexts()}

    entries = []
    for name in known:
        houdini = by_vcc_name.get(name)
        category = houdini.nodeTypeCategory() if houdini is not None else None
        entries.append(
            {
                "name": name,
                "label": houdini.name() if houdini is not None else None,
                "node_type_category": category.name() if category else None,
            }
        )

    result: dict[str, Any] = {"contexts": entries, "count": len(entries)}
    if context is None:
        result["hint"] = (
            "wrangle 스니펫을 검증할 때는 context 를 건드리지 않습니다 - 전부 "
            "cvex 입니다."
        )
        return result

    info = compiler.context_info(context)
    globals_ = info.get("globals") or {}
    result["context"] = context
    result["globals"] = [
        {
            "name": name,
            "type": spec.get("type"),
            "read": spec.get("read", False),
            "write": spec.get("write", False),
        }
        for name, spec in sorted(globals_.items())
    ]
    result["function_count"] = len(info.get("functions") or {})
    return result


@tool()
def vex_function_info(name: str, context: str = "sop") -> dict[str, Any]:
    """VEX 함수의 시그니처를 찾는다. 이름이 정확하지 않으면 비슷한 것을 준다.

    인자를 몇 개 받는지, 어떤 타입으로 오버로드돼 있는지 확인하고 나서 코드를
    쓴다. 추측해서 쓰고 컴파일 에러를 보는 것보다 빠르다.

    Args:
        name: 함수 이름. 일부만 줘도 된다. 예: "noise", "pcopen", "prim"
        context: 어느 컨텍스트에서 쓸 수 있는지 볼지. sop, cvex, surface 등.
            컨텍스트마다 쓸 수 있는 함수가 조금씩 다르다.
    """
    if not name.strip():
        raise ValueError("찾을 함수 이름이 비어 있습니다.")

    info = compiler.context_info(context)
    functions = info.get("functions") or {}
    needle = name.strip()

    entries = functions.get(needle)
    if entries is not None:
        signatures = [_signature(needle, entry) for entry in entries[:MAX_SIGNATURES]]
        return {
            "name": needle,
            "context": context,
            "signature_count": len(entries),
            "signatures": signatures,
            "truncated": len(entries) > MAX_SIGNATURES,
            "docs": f"https://www.sidefx.com/docs/houdini/vex/functions/{needle}.html",
        }

    lowered = needle.lower()
    matches = sorted(n for n in functions if lowered in n.lower())
    if not matches:
        globals_ = info.get("globals") or {}
        if needle in globals_:
            spec = globals_[needle]
            return {
                "name": needle,
                "context": context,
                "kind": "global",
                "type": spec.get("type"),
                "read": spec.get("read", False),
                "write": spec.get("write", False),
                "note": (
                    f"{needle} 은 함수가 아니라 {context} 컨텍스트의 전역 변수입니다. "
                    f"선언 없이 그대로 씁니다."
                ),
            }
        raise ValueError(
            f"{context} 컨텍스트에 {needle!r} 이 들어간 VEX 함수가 없습니다. "
            f"다른 컨텍스트일 수 있으니 list_vex_contexts 로 목록을 보거나, "
            f"이름 일부만 넣어 다시 찾아 보세요."
        )

    return {
        "query": needle,
        "context": context,
        "exact_match": False,
        "match_count": len(matches),
        "matches": matches[:MAX_MATCHES],
        "truncated": len(matches) > MAX_MATCHES,
        "hint": "이름을 정확히 주면 시그니처를 돌려줍니다.",
    }
