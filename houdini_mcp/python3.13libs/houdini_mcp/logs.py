"""로깅 설정.

파일 로그는 JSONL 로 남긴다. 한 줄이 JSON 하나이고, JsonlLogViewer 로 읽는다.
    https://github.com/JuyeongYi/JsonlLogViewer

로거 이름을 계층으로 쓴다.

    houdini_mcp                          루트
    houdini_mcp.server                   서버
    houdini_mcp.tools.<툴 팩 패키지명>    툴 팩별

계층 이름은 그대로 JSONL 의 `category` 필드가 된다. 파일을 팩별로 가르지 않아도
뷰어에서 category 로 걸러 보면 되므로, 로그 파일은 하나만 만든다.

JSONL 스키마 (뷰어가 요구하는 필드):
    timestamp  ISO 8601
    level      error | warn | info | debug
    msg        메시지
    category   로그를 낸 곳. "server", "adapter", "tools.<팩이름>"

환경변수:
    HOUDINI_MCP_LOG_DIR     로그 디렉토리. 기본은 $HOUDINI_USER_PREF_DIR/log.
                            "off" 를 주면 파일 로깅을 끈다.
    HOUDINI_MCP_LOG_LEVEL   기본 INFO.
    HOUDINI_MCP_LOG_CONSOLE 1 이면 Houdini 콘솔에도 낸다. 기본 꺼짐 -
                            매 툴 호출마다 Houdini 콘솔 창이 떠서 방해가 된다.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_NAME = "houdini_mcp"
TOOLS_PREFIX = f"{ROOT_NAME}.tools"

LOG_FILENAME = "houdini_mcp.jsonl"

CONSOLE_FORMAT = "%(asctime)s %(levelname)-5s [%(shortname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

# Python 로그 레벨 -> 뷰어가 아는 레벨. 나머지는 소문자로 내린다.
_LEVEL_MAP = {
    "WARNING": "warn",
    "CRITICAL": "error",
    "FATAL": "error",
}

THIRD_PARTY_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "mcp",
    "sse_starlette",
)
"""서버가 끌어오는 라이브러리들의 로거.

이들은 자기 핸들러를 stdout 에 붙인다. 그대로 두면 Houdini 콘솔 창이 계속 떠서
작업을 방해하므로, 핸들러를 걷어내고 우리 파일로만 보낸다. 정보는 잃지 않는다.
"""

_configured = False
_log_path: Path | None = None


def _category(name: str) -> str:
    """로거 이름에서 'houdini_mcp.' 접두사를 뗀 것."""
    if name == ROOT_NAME:
        return ROOT_NAME
    if name.startswith(f"{ROOT_NAME}."):
        return name[len(ROOT_NAME) + 1 :]
    return name


class _ShortNameFilter(logging.Filter):
    """콘솔 포맷에서 쓸 짧은 이름을 붙인다."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.shortname = _category(record.name)
        return True


class JsonlFormatter(logging.Formatter):
    """JsonlLogViewer 가 읽는 한 줄 JSON 으로 만든다."""

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, timezone.utc).astimezone()
        doc: dict[str, object] = {
            "timestamp": created.isoformat(),
            "level": _LEVEL_MAP.get(record.levelname, record.levelname.lower()),
            "msg": record.getMessage(),
            "category": _category(record.name),
        }
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            doc["stack"] = self.formatStack(record.stack_info)
        # ensure_ascii=False 로 한글을 그대로 남긴다.
        return json.dumps(doc, ensure_ascii=False)


def _default_log_dir() -> Path | None:
    """$HOUDINI_USER_PREF_DIR/log 를 기본 위치로 쓴다.

    Houdini 밖(단위 테스트 등)에서는 hou 가 없으므로 파일 로깅을 끈다.
    """
    try:
        import hou

        pref = hou.text.expandString("$HOUDINI_USER_PREF_DIR")
    except Exception:  # noqa: BLE001 - hou 가 없거나 초기화 전이다
        return None
    if not pref:
        return None
    return Path(pref) / "log"


def configure(force: bool = False) -> Path | None:
    """로깅을 한 번 설정한다. 로그 파일 경로를 돌려준다(파일 로깅이 꺼졌으면 None).

    툴 팩의 pythonrc.py 와 서버의 uiready.py 어느 쪽이 먼저 불러도 되도록
    멱등하게 만들었다.
    """
    global _configured, _log_path
    if _configured and not force:
        return _log_path

    level_name = os.environ.get("HOUDINI_MCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger(ROOT_NAME)
    root.setLevel(level)
    # 루트 로거로 올려보내지 않는다. Houdini 나 다른 라이브러리가 루트에 stdout
    # 핸들러를 붙여 두면 우리 로그까지 콘솔에 새어 나간다.
    root.propagate = False
    # Houdini 세션이 재시작 없이 다시 설정될 수 있다. 중복 출력을 막는다.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    if os.environ.get("HOUDINI_MCP_LOG_CONSOLE", "0") == "1":
        # 콘솔은 사람이 읽으므로 JSONL 이 아니라 평문으로 낸다.
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
        console.addFilter(_ShortNameFilter())
        root.addHandler(console)

    raw_dir = os.environ.get("HOUDINI_MCP_LOG_DIR")
    log_dir = None if (raw_dir and raw_dir.lower() == "off") else (
        Path(raw_dir) if raw_dir else _default_log_dir()
    )

    _log_path = None
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / LOG_FILENAME
            handler = logging.handlers.RotatingFileHandler(
                path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
            )
            handler.setFormatter(JsonlFormatter())
            root.addHandler(handler)
            _log_path = path
        except OSError as exc:
            print(f"[houdini_mcp] 로그 파일을 만들지 못했습니다: {log_dir} ({exc})")

    quiet_third_party()

    _configured = True
    return _log_path


def quiet_third_party() -> None:
    """서드파티 로거의 콘솔 출력을 걷어내고 우리 파일로 보낸다.

    uvicorn 은 서버를 띄우면서 자기 로깅을 다시 설정하므로, 서버 기동 뒤에도 한 번
    더 불러야 할 수 있다.
    """
    file_handlers = [
        h for h in logging.getLogger(ROOT_NAME).handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    for name in THIRD_PARTY_LOGGERS:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.propagate = False
        for handler in file_handlers:
            logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """`houdini_mcp.<name>` 로거."""
    configure()
    return logging.getLogger(f"{ROOT_NAME}.{name}")


def get_tool_logger(package: str) -> logging.Logger:
    """툴 팩 하나를 위한 로거.

    로그는 통합 파일 하나에 모이고, JSONL 의 `category` 가 "tools.<팩이름>" 이 되어
    뷰어에서 팩별로 걸러 볼 수 있다.
    """
    configure()
    return logging.getLogger(f"{TOOLS_PREFIX}.{package}")
