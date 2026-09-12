"""툴로 안 되는 일을 하는 탈출구.

툴은 흔한 작업을 안전하게 만들지만 Houdini 가 할 수 있는 일의 일부만 덮는다.
덮이지 않은 곳에서 막히면 작업 자체가 멈추므로 탈출구를 둔다. 조사한 기존 구현
다섯 중 넷이 같은 툴을 갖고 있다.

**이건 위험한 툴이다.** 임의 코드가 사용자 씬에서 그대로 실행된다. 다음을
지킨다.

  - 전용 툴이 있으면 그것을 쓴다. 이건 마지막 수단이다.
  - 무엇을 왜 하는지 comment 에 남긴다. 로그에 코드와 함께 기록된다.
  - 되돌릴 수 있도록 Undo 그룹으로 묶는다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import contextlib
import io
import traceback
from typing import Any

import hou

from houdini_mcp import tool, undoable
from houdini_mcp.logs import get_logger

_log = get_logger("execute")

MAX_OUTPUT = 8000


@tool()
@undoable("Run Python")
def run_python(code: str, comment: str) -> dict[str, Any]:
    """Houdini 안에서 Python 을 실행한다. 전용 툴로 안 될 때만 쓴다.

    `hou` 는 이미 import 되어 있다. 돌려받고 싶은 값은 `result` 변수에 담는다.
    print 출력도 함께 온다.

        code:    "geo = hou.node('/obj/castle')\\n"
                 "result = [n.name() for n in geo.children()]"
        comment: "Why: 노드 이름만 빠르게 훑어보려고"

    임의 코드가 사용자 씬에서 실행되므로, 씬을 바꾸는 코드는 신중히 쓴다.
    Undo 한 번으로 되돌아가도록 묶여 있지만 되돌릴 수 없는 동작(파일 쓰기 등)은
    그렇지 않다.

    Args:
        code: 실행할 Python 코드.
        comment: 무엇을 왜 하는지. 로그에 코드와 함께 남는다. 필수.
    """
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 코드가 무엇을 위한 것인지 적어 주세요."
        )
    if not code or not code.strip():
        raise ValueError("code 가 비어 있습니다.")

    _log.info("run_python: %s", comment.strip())
    _log.debug("code:%s%s", "\n", code)

    namespace: dict[str, Any] = {"hou": hou, "__name__": "__mcp_exec__"}
    stdout = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout):
            exec(compile(code, "<mcp>", "exec"), namespace)  # noqa: S102 - 의도된 탈출구
    except Exception as exc:
        _log.exception("run_python 실패: %s", comment.strip())
        detail = traceback.format_exc().splitlines()
        # 사용자 코드의 마지막 프레임만 보여 준다. 내부 스택은 잡음이다.
        raise ValueError(
            f"{type(exc).__name__}: {exc}\n" + "\n".join(detail[-4:])
        ) from exc

    printed = stdout.getvalue()
    result: dict[str, Any] = {"comment": comment.strip()}
    if printed:
        result["stdout"] = printed[:MAX_OUTPUT]
        result["stdout_truncated"] = len(printed) > MAX_OUTPUT
    if "result" in namespace:
        value = namespace["result"]
        try:
            result["result"] = value
        except Exception:  # noqa: BLE001 - 직렬화 불가한 값도 있다
            result["result"] = repr(value)[:MAX_OUTPUT]
    elif not printed:
        result["note"] = "result 변수도 print 도 없어 돌려줄 값이 없습니다."
    return result


@tool()
def run_hscript(command: str) -> dict[str, Any]:
    """HScript 명령을 실행한다.

    일부 기능은 HScript 로만 노출된다(`opparm`, `chwrite`, 텍스트 포트 명령 등).
    Python 으로 되는 일이면 run_python 을 쓴다.

    Args:
        command: HScript 명령 한 줄 또는 여러 줄.
    """
    if not command or not command.strip():
        raise ValueError("command 가 비어 있습니다.")
    _log.info("run_hscript: %s", command.strip().splitlines()[0][:120])

    out, err = hou.hscript(command)
    result: dict[str, Any] = {"command": command}
    if out and out.strip():
        result["output"] = out[:MAX_OUTPUT]
    if err and err.strip():
        # HScript 는 실패해도 예외를 던지지 않고 stderr 로만 알린다.
        result["error"] = err[:MAX_OUTPUT]
    return result
