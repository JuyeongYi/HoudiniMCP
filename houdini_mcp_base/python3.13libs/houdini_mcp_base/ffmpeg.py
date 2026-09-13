r"""외부 ffmpeg 을 찾고 부르는 헬퍼. 툴은 없다 - TOOL_MODULES 에 넣지 않는다.

`FFMPEG_BIN_PATH` 환경변수가 가리키는 bin 디렉토리의 ffmpeg / ffprobe 를 쓴다.
변수가 없으면 영상 툴은 아무것도 하기 전에 멈춘다.

Houdini 에 들어 있는 `$HFS/bin/hffmpeg` 로 대신하지 않는다. SideFX 빌드
(22.0.368 의 `sidefx_7.1.0-5`)에는 drawtext 필터와 libx264 가 없어서(실측),
그것으로 대신하면 라벨과 화질이 기계마다 달라진다.

실측(gyan.dev full build, Windows):

- 폰트 파일 없이 drawtext 를 쓰면 fontconfig 설정을 못 찾는다는 경고를 내고 기본
  글꼴로 그린다. 영문은 나오지만 한글은 네모가 된다. 그래서 ASCII 가 아닌 라벨은
  한글 글리프가 있는 폰트 파일을 반드시 넘긴다.
- 라벨은 `text=` 대신 `textfile=` 로 넘긴다. 라벨 내용 안의 따옴표·콜론을
  필터 문법으로 이스케이프하지 않아도 된다. 경로의 `:` 는 `\:` 로 막는다
  (Windows 드라이브 문자). `expansion=none` 으로 `%{...}` 치환을 끈다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

ENV_VAR = "FFMPEG_BIN_PATH"

DEFAULT_TIMEOUT = 900.0
"""인코딩 한 번의 한도(초). 워커 스레드에서 돌므로 메인 스레드 한도와 무관하다."""

CONTAINERS: dict[str, tuple[str, ...]] = {
    ".mp4": ("libx264", "libopenh264"),
    ".mov": ("libx264", "libopenh264"),
    ".mkv": ("libx264", "libopenh264"),
    ".webm": ("libvpx-vp9",),
}
"""출력 확장자마다 쓸 수 있는 인코더. 앞에 있는 것이 먼저다."""


@dataclass(frozen=True)
class FFmpeg:
    ffmpeg: Path
    ffprobe: Path

    def describe(self) -> dict[str, str]:
        return {"ffmpeg": self.ffmpeg.as_posix(), "ffprobe": self.ffprobe.as_posix()}


def require_ffmpeg() -> FFmpeg:
    """`FFMPEG_BIN_PATH` 의 ffmpeg 과 ffprobe. 없으면 설정하는 법을 알려 준다."""
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        raise RuntimeError(
            f"{ENV_VAR} 환경변수가 없어 영상 툴을 쓸 수 없습니다. ffmpeg 과 ffprobe 가 든 "
            f"bin 디렉토리를 지정하고 Houdini 를 다시 띄우세요. 예: houdini.env 에 "
            f'{ENV_VAR} = "C:/ffmpeg/bin" (Linux/macOS 는 "/usr/local/bin" 처럼). '
            f"drawtext 필터와 libx264 가 든 빌드를 권합니다."
        )
    base = Path(raw)
    if base.is_file():
        base = base.parent
    if not base.is_dir():
        raise RuntimeError(
            f"{ENV_VAR} 가 가리키는 디렉토리가 없습니다: {base.as_posix()}. "
            f"ffmpeg 이 든 bin 디렉토리로 고치고 Houdini 를 다시 띄우세요."
        )
    # shutil.which 가 Windows 의 PATHEXT 를 봐서 .exe 를 찾아 준다.
    found = {name: shutil.which(name, path=str(base)) for name in ("ffmpeg", "ffprobe")}
    missing = [name for name, hit in found.items() if not hit]
    if missing:
        raise RuntimeError(
            f"{base.as_posix()} 에 {', '.join(missing)} 이(가) 없습니다. {ENV_VAR} 를 "
            f"ffmpeg 과 ffprobe 가 함께 든 bin 디렉토리로 지정하세요."
        )
    return FFmpeg(Path(str(found["ffmpeg"])), Path(str(found["ffprobe"])))


def _subprocess_flags() -> dict[str, Any]:
    # Windows 의 GUI Houdini 에서 콘솔 프로그램을 띄우면 콘솔 창이 깜빡인다.
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def run(
    executable: Path, args: Sequence[str], timeout: float = DEFAULT_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """실행하고, 실패하면 stderr 끝부분을 담아 예외를 던진다."""
    try:
        proc = subprocess.run(
            [str(executable), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            **_subprocess_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{executable.name} 가 {timeout:g}초 안에 끝나지 않았습니다. 프레임 수나 "
            f"해상도를 줄이세요."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"{executable.as_posix()} 를 실행하지 못했습니다: {exc}") from exc
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"{executable.name} 가 실패했습니다 (exit {proc.returncode}):\n{tail}")
    return proc


_LISTINGS: dict[tuple[str, str], frozenset[str]] = {}


def _listing(ff: FFmpeg, flag: str) -> frozenset[str]:
    """`-encoders` / `-filters` 목록의 이름들. 실행 파일마다 한 번만 읽는다."""
    key = (ff.ffmpeg.as_posix(), flag)
    if key not in _LISTINGS:
        proc = run(ff.ffmpeg, ["-hide_banner", flag], timeout=30)
        names = set()
        for line in proc.stdout.splitlines():
            parts = line.split()
            # 범례 줄은 "V..... = Video", 구분 줄은 "------" 이다.
            if len(parts) >= 2 and parts[1] != "=":
                names.add(parts[1])
        _LISTINGS[key] = frozenset(names)
    return _LISTINGS[key]


def encoders(ff: FFmpeg) -> frozenset[str]:
    return _listing(ff, "-encoders")


def filters(ff: FFmpeg) -> frozenset[str]:
    return _listing(ff, "-filters")


def require_filters(ff: FFmpeg, names: Sequence[str]) -> None:
    missing = [name for name in names if name not in filters(ff)]
    if missing:
        raise RuntimeError(
            f"이 ffmpeg 에는 {', '.join(missing)} 필터가 없습니다: {ff.ffmpeg.as_posix()}. "
            f"libfreetype 를 켜고 빌드한 ffmpeg(예: gyan.dev full build)으로 {ENV_VAR} 를 "
            f"바꾸세요."
        )


def encode_args(ff: FFmpeg, output: Path, crf: int) -> tuple[str, list[str]]:
    """출력 확장자에 맞는 인코더와 인자. 없으면 무엇이 필요한지 알려 준다.

    crf 는 x264 기준이다(낮을수록 좋다, 18 이면 눈으로 구분하기 어렵다).
    """
    ext = output.suffix.lower()
    if ext not in CONTAINERS:
        raise ValueError(
            f"{ext or '확장자 없음'} 로는 쓸 수 없습니다. {', '.join(CONTAINERS)} 중 하나로 주세요."
        )
    have = encoders(ff)
    chosen = next((name for name in CONTAINERS[ext] if name in have), None)
    if chosen is None:
        raise RuntimeError(
            f"이 ffmpeg 에는 {ext} 용 인코더({', '.join(CONTAINERS[ext])})가 없습니다: "
            f"{ff.ffmpeg.as_posix()}"
        )
    args = ["-c:v", chosen, "-pix_fmt", "yuv420p"]
    if chosen == "libx264":
        args += ["-crf", str(crf), "-preset", "medium"]
    elif chosen == "libopenh264":
        # crf 가 없다. 품질 모드 기본값은 흐리므로 넉넉한 비트레이트를 준다.
        args += ["-b:v", "8M"]
    elif chosen == "libvpx-vp9":
        # VP9 의 crf 범위(0~63)는 x264 와 달라 대략 맞춰 옮긴다.
        args += ["-crf", str(min(63, crf + 13)), "-b:v", "0", "-row-mt", "1"]
    if ext in (".mp4", ".mov"):
        args += ["-movflags", "+faststart"]
    return chosen, args


def filter_path(path: Path) -> str:
    """필터 문자열 안에 넣을 경로. 작은따옴표로 감싸고 `:` 를 막는다."""
    text = path.as_posix()
    if "'" in text:
        raise ValueError(
            f"작은따옴표가 든 경로는 ffmpeg 필터에 넣을 수 없습니다: {text}. "
            f"따옴표가 없는 경로로 옮기세요."
        )
    return "'" + text.replace("\\", "\\\\").replace(":", "\\:") + "'"


def drawtext(text_file: Path, font_file: Path | None, font_size: int) -> str:
    """왼쪽 위에 반투명 상자를 깐 라벨."""
    parts = [f"textfile={filter_path(text_file)}", "expansion=none"]
    if font_file is not None:
        parts.append(f"fontfile={filter_path(font_file)}")
    margin = max(4, font_size // 2)
    parts += [
        f"fontsize={font_size}",
        "fontcolor=white",
        "box=1",
        "boxcolor=black@0.6",
        f"boxborderw={max(4, font_size // 5)}",
        f"x={margin}",
        f"y={margin}",
    ]
    return "drawtext=" + ":".join(parts)


def find_font(text: str, font_file: str | None) -> Path | None:
    """라벨을 그릴 폰트 파일. ASCII 라벨이면 None(ffmpeg 기본 글꼴)이어도 된다."""
    if font_file:
        path = Path(font_file)
        if not path.is_file():
            raise ValueError(f"폰트 파일이 없습니다: {path.as_posix()}. .ttf/.ttc/.otf 경로를 주세요.")
        return path
    if text.isascii():
        return None
    for candidate in _cjk_font_candidates():
        if candidate.is_file():
            return candidate
    raise ValueError(
        f"라벨 {text!r} 에 ASCII 가 아닌 글자가 있는데 그 글자를 가진 폰트를 찾지 "
        f"못했습니다. font_file 에 .ttf/.ttc/.otf 경로를 주세요. 폰트 없이 그리면 네모로 나옵니다."
    )


def _cjk_font_candidates() -> list[Path]:
    # 한글 글리프가 든 기본 글꼴의 위치는 OS 마다 정해져 있어 플랫폼별로 나눈다.
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR")
        if not windir:
            return []
        fonts = Path(windir) / "Fonts"
        return [fonts / "malgun.ttf", fonts / "gulim.ttc"]
    if sys.platform == "darwin":
        return [
            Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
            Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
        ]
    fc_match = shutil.which("fc-match")
    if fc_match is None:
        return []
    try:
        proc = subprocess.run(
            [fc_match, "-f", "%{file}", ":lang=ko"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    found = proc.stdout.strip()
    return [Path(found)] if found else []


def _number(value: Any, kind: type = float) -> Any:
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


def _rate(value: Any) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return _number(value)
    num, _, den = value.partition("/")
    numerator, denominator = _number(num), _number(den)
    if not numerator or not denominator:
        return None
    return round(numerator / denominator, 3)


def probe(ff: FFmpeg, path: Path, count_frames: bool = True) -> dict[str, Any]:
    """영상·이미지 파일을 ffprobe 로 읽는다.

    count_frames 면 프레임 수를 실제로 디코딩해서 센다. 이미지 한 장의 해상도만
    볼 때는 끈다.
    """
    args = ["-v", "error", "-select_streams", "v:0"]
    if count_frames:
        args.append("-count_frames")
    args += [
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration,size",
        "-of", "json",
        str(path),
    ]
    proc = run(ff.ffprobe, args, timeout=300)
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"{path.as_posix()} 에서 영상 스트림을 찾지 못했습니다.")
    stream = streams[0]
    fmt = data.get("format") or {}
    return {
        "codec": stream.get("codec_name"),
        "width": _number(stream.get("width"), int),
        "height": _number(stream.get("height"), int),
        "frames": _number(stream.get("nb_read_frames"), int),
        "fps": _rate(stream.get("avg_frame_rate")),
        "duration_seconds": _number(fmt.get("duration")),
        "bytes": _number(fmt.get("size"), int),
    }
