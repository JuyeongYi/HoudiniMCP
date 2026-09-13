"""영상 툴 - 프레임을 영상 하나로 굽고, 두 소스를 나란히 붙여 비교한다.

    make_video      뷰포트 캡처·이미지 시퀀스·영상 파일을 영상 하나로
    compare_videos  두 소스를 나란히(또는 위아래로) 붙인 A/B 비교 영상

영상 처리는 전부 `FFMPEG_BIN_PATH` 의 외부 ffmpeg 이 한다(ffmpeg.py 참고). 변수가
없으면 두 툴 모두 아무것도 하기 전에 멈춘다.

스레드: 툴은 워커 스레드(affinity any)에서 돈다. 인코딩은 수십 초씩 걸리고,
뷰포트 캡처는 프레임 수만큼 길어져 메인 스레드 한도(120초)를 넘기기 쉽다. 그래서
`hou` 를 만지는 일(경로 전개, 프레임 한 장 캡처)만 조각내어 run_in_main_thread
로 넘긴다. 조각 사이에 Houdini UI 도 멈추지 않는다.

이미지 시퀀스는 concat 목록(ffconcat)으로 넘긴다. 파일 이름 패턴(image2)으로
넘기면 빠진 프레임에서 읽기가 끝나 버리기 때문이다. 빠진 프레임은 앞 파일을 한
번 더 적어 시간이 밀리지 않게 하고, 응답에 적는다.

선형 이미지(EXR, HDR)는 `exposure` 와 `zscale` 로 sRGB 화면 밝기로 옮긴다.
zscale 은 입력·출력의 transfer·primaries·matrix 를 전부 적어야 변환 경로를 찾는다
(실측 - 하나라도 빠지면 "no path between colorspaces"). ffmpeg 7 에는 EXR
디코더의 `-apply_trc` 옵션이 없다.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import hou

from houdini_mcp import AFFINITY_ANY, run_in_main_thread, tool

from . import ffmpeg, paths, viewport

MAX_FRAMES = 2000
"""소스 하나에서 받을 프레임 수 상한."""

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".gif"})
"""영상 파일로 보는 소스 확장자. 나머지는 이미지 시퀀스로 본다."""

LINEAR_EXTENSIONS = frozenset({".exr", ".hdr"})
"""선형 값으로 저장되는 이미지. 화면 밝기로 옮겨야 한다."""

LINEAR_TO_SRGB = "zscale=tin=linear:t=iec61966-2-1:pin=709:p=709:min=709:m=709"

LAYOUTS = ("horizontal", "vertical")


# --------------------------------------------------------------------------
# 검사
# --------------------------------------------------------------------------


def _check_encode_options(fps: float, crf: int) -> None:
    if not 1 <= fps <= 240:
        raise ValueError(f"fps 는 1~240 이어야 합니다: {fps}")
    if not 0 <= crf <= 51:
        raise ValueError(f"crf 는 0~51 이어야 합니다(낮을수록 고화질, 보통 18~23): {crf}")


def _frame_list(start: float, end: float) -> list[float]:
    if end < start:
        raise ValueError(f"end({end:g}) 가 start({start:g}) 보다 앞입니다.")
    count = int(round(end - start)) + 1
    if count > MAX_FRAMES:
        raise ValueError(
            f"프레임이 {count}개입니다. 한 번에 {MAX_FRAMES}개까지 받습니다. 범위를 나누세요."
        )
    return [start + index for index in range(count)]


def _ranges(frames: list[float]) -> str:
    """[1, 2, 3, 7] -> "1-3, 7"."""
    if not frames:
        return ""
    groups: list[list[float]] = [[frames[0], frames[0]]]
    for frame in frames[1:]:
        if frame - groups[-1][1] == 1:
            groups[-1][1] = frame
        else:
            groups.append([frame, frame])
    return ", ".join(f"{a:g}" if a == b else f"{a:g}-{b:g}" for a, b in groups)


def _natural_key(path: Path) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def _is_video_file(source: str) -> bool:
    return Path(source).suffix.lower() in VIDEO_EXTENSIONS and not paths.has_sequence_token(source)


# --------------------------------------------------------------------------
# 소스 - 메인 스레드에서 도는 조각
# --------------------------------------------------------------------------


def _frame_path(source: str, frame: float) -> Path:
    """프레임 하나의 파일. `$F4` 는 Houdini 가, `%04d` 는 여기서 푼다."""
    text = paths.PRINTF_TOKENS.sub(lambda match: match.group() % int(round(frame)), source)
    return paths.to_path(text, frame)


def _sequence_files(
    source: str, start: float | None, end: float | None
) -> tuple[list[Path], dict[str, Any]]:
    if not paths.has_sequence_token(source):
        raise ValueError(
            f"{source!r} 는 영상 파일도 프레임 시퀀스도 아닙니다. 영상은 "
            f"{', '.join(sorted(VIDEO_EXTENSIONS))} 파일로, 시퀀스는 $F4 나 %04d 같은 "
            f"프레임 토큰이 든 경로로 주세요."
        )
    info: dict[str, Any] = {"source": paths.to_parm(source)}
    if start is None and end is None:
        files, _ = paths.resolve_files(source, limit=MAX_FRAMES + 1)
        if not files:
            raise ValueError(
                f"시퀀스에 맞는 파일이 없습니다: {Path(paths.sequence_glob(source)).as_posix()}"
            )
        if len(files) > MAX_FRAMES:
            raise ValueError(f"파일이 {MAX_FRAMES}개를 넘습니다. start 와 end 로 범위를 좁히세요.")
        files.sort(key=_natural_key)
        info.update({"files": len(files), "first": files[0].name, "last": files[-1].name})
        return files, info
    if start is None or end is None:
        raise ValueError("start 와 end 는 함께 주세요. 둘 다 생략하면 있는 파일을 전부 씁니다.")

    frames = _frame_list(start, end)
    found = [_frame_path(source, frame) for frame in frames]
    exists = [path.is_file() for path in found]
    if not any(exists):
        raise ValueError(
            f"{start:g}~{end:g} 에 파일이 하나도 없습니다. 첫 프레임 경로: {found[0].as_posix()}"
        )
    missing = [frame for frame, ok in zip(frames, exists) if not ok]
    # 빠진 프레임은 바로 앞(맨 앞이 빠졌으면 처음 있는 것) 파일로 채운다.
    filled: list[Path] = []
    previous = found[exists.index(True)]
    for path, ok in zip(found, exists):
        if ok:
            previous = path
        filled.append(previous)
    info.update({"start": start, "end": end, "files": len(frames) - len(missing)})
    if missing:
        info["missing_frames"] = _ranges(missing)
    return filled, info


def _capture_frame(frame: float, width: int, height: int, directory: Path, index: int) -> Path:
    viewer = viewport._scene_viewer()
    scratch = directory / f"capture_{index:06d}"
    scratch.mkdir()
    try:
        # PNG 로 받으면 배경이 투명해 영상에서 검게 나온다(실측). JPG 는 뷰포트 배경이 남는다.
        written = viewport._flipbook_frame(viewer, frame, width, height, scratch, image_format="jpg")
        target = directory / f"frame.{index + 1:06d}.jpg"
        shutil.move(str(written), str(target))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return target


def _playbar_state() -> tuple[float, tuple[float, float]]:
    start, end = hou.playbar.frameRange()
    return hou.frame(), (float(start), float(end))


# --------------------------------------------------------------------------
# 소스 준비 - 워커 스레드
# --------------------------------------------------------------------------


class Source:
    """ffmpeg 입력 하나. input_args 로 읽고, pre_filter 를 먼저 건다."""

    def __init__(self, input_args: list[str], pre_filter: str, info: dict[str, Any], fps: float):
        self.input_args = input_args
        self.pre_filter = pre_filter
        self.info = info
        self.duration = float(info.get("duration_seconds") or 0.0) or info["frames"] / fps

    @property
    def width(self) -> int:
        return int(self.info["width"])

    @property
    def height(self) -> int:
        return int(self.info["height"])


def _concat_quote(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "'\\''") + "'"


def _concat_input(files: list[Path], fps: float, list_file: Path) -> list[str]:
    duration = f"{1.0 / fps:.6f}"
    lines = ["ffconcat version 1.0"]
    for file in files:
        lines += [f"file {_concat_quote(file)}", f"duration {duration}"]
    # 마지막 항목의 duration 은 다음 항목이 있어야 적용된다(concat demuxer 규약).
    # 넘치는 한 프레임은 출력의 -frames:v 가 잘라낸다.
    lines.append(f"file {_concat_quote(files[-1])}")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ["-f", "concat", "-safe", "0", "-i", str(list_file)]


def _image_source(
    ff: ffmpeg.FFmpeg, files: list[Path], info: dict[str, Any], fps: float, exposure: float, directory: Path
) -> Source:
    first = ffmpeg.probe(ff, files[0], count_frames=False)
    info.update({"frames": len(files), "width": first["width"], "height": first["height"]})
    pre = ""
    if files[0].suffix.lower() in LINEAR_EXTENSIONS:
        ffmpeg.require_filters(ff, ["zscale"] + (["exposure"] if exposure else []))
        pre = (f"exposure=exposure={exposure:g}," if exposure else "") + LINEAR_TO_SRGB + ","
        info["tone"] = f"linear -> sRGB, exposure {exposure:+g}"
    return Source(_concat_input(files, fps, directory / "frames.ffconcat"), pre, info, fps)


def _prepare_source(
    ff: ffmpeg.FFmpeg,
    source: str | None,
    start: float | None,
    end: float | None,
    fps: float,
    exposure: float,
    directory: Path,
    viewport_size: tuple[int, int] | None = None,
) -> Source:
    directory.mkdir()
    if source is None:
        if viewport_size is None:
            raise ValueError("소스가 비어 있습니다. 영상 파일이나 프레임 시퀀스 경로를 주세요.")
        files, info = _capture_viewport(start, end, viewport_size, directory)
        return _image_source(ff, files, info, fps, exposure, directory)

    if _is_video_file(source):
        if start is not None or end is not None:
            raise ValueError(
                "영상 파일 소스에는 start/end 를 쓰지 않습니다. 영상 전체를 씁니다. 잘라야 하면 "
                "원본 프레임 시퀀스를 소스로 주세요."
            )
        file = run_in_main_thread(paths.require_file, source)
        meta = ffmpeg.probe(ff, file)
        return Source(["-i", str(file)], "", {"kind": "video", "source": file.as_posix(), **meta}, fps)

    files, info = run_in_main_thread(_sequence_files, source, start, end)
    return _image_source(ff, files, {"kind": "images", **info}, fps, exposure, directory)


def _capture_viewport(
    start: float | None, end: float | None, size: tuple[int, int], directory: Path
) -> tuple[list[Path], dict[str, Any]]:
    width, height = size
    if not (16 <= width <= viewport.MAX_SIDE and 16 <= height <= viewport.MAX_SIDE):
        raise ValueError(f"해상도는 한 변 16~{viewport.MAX_SIDE} 로 주세요: {width}x{height}")
    original, (range_start, range_end) = run_in_main_thread(_playbar_state)
    first = range_start if start is None else float(start)
    last = range_end if end is None else float(end)
    frames = _frame_list(first, last)
    files: list[Path] = []
    try:
        for index, frame in enumerate(frames):
            # 프레임마다 따로 넘긴다. 통째로 넘기면 메인 스레드 한도(120초)를 넘긴다.
            files.append(run_in_main_thread(_capture_frame, frame, width, height, directory, index))
    finally:
        run_in_main_thread(hou.setFrame, original)
    return files, {"kind": "viewport", "start": first, "end": last}


# --------------------------------------------------------------------------
# 인코딩
# --------------------------------------------------------------------------


def _label_filter(text: str | None, font: Path | None, height: int, directory: Path, name: str) -> str:
    if not text:
        return ""
    text_file = directory / f"{name}.txt"
    text_file.write_text(text, encoding="utf-8")
    return "," + ffmpeg.drawtext(text_file, font, max(16, height // 18))


def _encode(
    ff: ffmpeg.FFmpeg,
    sources: list[Source],
    graph: str,
    target: Path,
    fps: float,
    frames: int,
    codec_args: list[str],
) -> dict[str, Any]:
    args = ["-y", "-hide_banner", "-loglevel", "error"]
    for source in sources:
        args += source.input_args
    args += [
        "-filter_complex", graph,
        "-map", "[out]",
        "-frames:v", str(frames),
        "-r", f"{fps:g}",
        *codec_args,
        str(target),
    ]
    ffmpeg.run(ff.ffmpeg, args)
    if not target.is_file():
        raise RuntimeError(f"ffmpeg 이 끝났지만 파일이 없습니다: {target.as_posix()}")
    return ffmpeg.probe(ff, target)


def _fonts_for(labels: list[str | None], font_file: str | None) -> Path | None:
    text = "".join(label for label in labels if label)
    return ffmpeg.find_font(text, font_file) if text else None


def _output_entry(output: str) -> dict[str, Any]:
    entry = paths.describe(output)
    entry.pop("exists", None)
    return entry


def _even(value: float) -> int:
    return max(2, int(value) // 2 * 2)


# --------------------------------------------------------------------------
# 툴
# --------------------------------------------------------------------------


@tool(affinity=AFFINITY_ANY)
def make_video(
    output: str,
    source: str | None = None,
    start: float | None = None,
    end: float | None = None,
    fps: float = 24.0,
    width: int = 1280,
    height: int = 720,
    label: str | None = None,
    font_file: str | None = None,
    exposure: float = 0.0,
    crf: int = 18,
    overwrite: bool = False,
) -> dict[str, Any]:
    """뷰포트 캡처나 이미지 시퀀스를 영상 하나로 굽고, 다시 읽어 확인한다.

    source 를 생략하면 현재 뷰포트를 start~end 프레임마다 캡처한다(GUI 필요).
    끝나면 사용자의 현재 프레임으로 되돌린다. 시뮬레이션은 앞 프레임부터 계산되므로
    처음 캡처할 때는 오래 걸린다.

    `FFMPEG_BIN_PATH` 환경변수(ffmpeg·ffprobe 가 든 bin 디렉토리)가 없으면 아무것도
    하지 않고 에러를 낸다.

    Args:
        output: 쓸 영상 경로. .mp4 / .mov / .mkv / .webm. $HIP 같은 변수를 써도 된다.
        source: 생략하면 뷰포트 캡처. 이미지 시퀀스는 `$HIP/render/beauty.$F4.exr` 나 `.../frame.%04d.png` 처럼 프레임 토큰이 든 경로. 영상 파일(.mp4 등)을 주면 라벨만 입혀 다시 굽는다.
        start: 시작 프레임. 뷰포트 캡처에서 생략하면 플레이바 시작. 시퀀스에서 start/end 를 둘 다 생략하면 있는 파일을 전부 쓴다.
        end: 끝 프레임(포함).
        fps: 초당 프레임.
        width: 뷰포트 캡처의 가로 픽셀. 시퀀스는 원본 크기를 쓴다.
        height: 뷰포트 캡처의 세로 픽셀.
        label: 왼쪽 위에 넣을 글자. 예: "flag loop - after relax"
        font_file: 라벨 폰트(.ttf/.ttc/.otf). 생략하면 영문은 ffmpeg 기본 글꼴, 한글이 있으면 OS 의 한글 글꼴을 찾는다.
        exposure: EXR·HDR 같은 선형 이미지에 더할 노출(스톱). 다른 이미지에는 쓰지 않는다.
        crf: 화질. 낮을수록 좋고 파일이 커진다. 18 이면 눈으로 구분하기 어렵다.
        overwrite: 이미 있는 파일을 덮어쓸 때 True.
    """
    ff = ffmpeg.require_ffmpeg()
    _check_encode_options(fps, crf)
    encoder, codec_args = ffmpeg.encode_args(ff, Path(output), crf)
    ffmpeg.require_filters(ff, ["fps", "scale", "setsar"] + (["drawtext"] if label else []))
    font = _fonts_for([label], font_file)
    target = run_in_main_thread(paths.prepare_output, output, overwrite)

    with tempfile.TemporaryDirectory(prefix="hmcp_video_") as tmp:
        work = Path(tmp)
        src = _prepare_source(
            ff, source, start, end, fps, exposure, work / "source", viewport_size=(width, height)
        )
        text = _label_filter(label, font, src.height, work, "label")
        graph = (
            f"[0:v]{src.pre_filter}fps={fps:g},setsar=1{text},"
            f"scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p[out]"
        )
        expected = max(1, round(src.duration * fps))
        result = _encode(ff, [src], graph, target, fps, expected, codec_args)

    response: dict[str, Any] = {
        "output": {**run_in_main_thread(_output_entry, output), **paths.file_stat(target)},
        "encoder": encoder,
        "video": result,
        "source": src.info,
        "ffmpeg": ff.describe(),
    }
    if font is not None:
        response["font"] = font.as_posix()
    warnings = []
    if src.info.get("missing_frames"):
        warnings.append(f"빠진 프레임 {src.info['missing_frames']} 은 앞 프레임으로 채웠습니다.")
    if result.get("frames") and result["frames"] != expected:
        warnings.append(f"기대한 {expected}프레임과 달리 {result['frames']}프레임이 나왔습니다.")
    if warnings:
        response["warnings"] = warnings
    return response


@tool(affinity=AFFINITY_ANY)
def compare_videos(
    a: str,
    b: str,
    output: str,
    label_a: str | None = "A",
    label_b: str | None = "B",
    layout: str = "horizontal",
    start: float | None = None,
    end: float | None = None,
    fps: float = 24.0,
    size: int | None = None,
    font_file: str | None = None,
    exposure: float = 0.0,
    crf: int = 18,
    overwrite: bool = False,
) -> dict[str, Any]:
    """두 소스를 나란히(또는 위아래로) 붙인 A/B 비교 영상을 굽고, 다시 읽어 확인한다.

    고치기 전과 후를 같은 시간축에서 보려는 것이다. 소스마다 영상 파일이나 이미지
    시퀀스를 줄 수 있고 둘이 섞여도 된다. 길이가 다르면 짧은 쪽이 마지막 프레임에
    멈춘 채 긴 쪽이 끝날 때까지 이어진다.

    make_video 로 이미 라벨을 구워 넣은 영상이면 그쪽 label 을 None 으로 준다. 같은
    자리에 라벨이 겹쳐 읽을 수 없게 된다.

    `FFMPEG_BIN_PATH` 환경변수(ffmpeg·ffprobe 가 든 bin 디렉토리)가 없으면 아무것도
    하지 않고 에러를 낸다.

    Args:
        a: 왼쪽(위) 소스. 영상 파일 또는 `$F4`·`%04d` 프레임 토큰이 든 이미지 시퀀스 경로.
        b: 오른쪽(아래) 소스. 형식은 a 와 같다.
        output: 쓸 영상 경로. .mp4 / .mov / .mkv / .webm.
        label_a: a 에 넣을 글자. 빈 문자열이나 None 이면 넣지 않는다. 예: "before"
        label_b: b 에 넣을 글자. 예: "after relax x80"
        layout: "horizontal"(나란히) 또는 "vertical"(위아래).
        start: 이미지 시퀀스 소스의 시작 프레임. 영상 파일 소스에는 쓰지 않는다. 생략하면 있는 파일 전부.
        end: 이미지 시퀀스 소스의 끝 프레임(포함).
        fps: 초당 프레임. 이미지 시퀀스를 이 속도로 읽고, 결과도 이 속도로 쓴다.
        size: horizontal 이면 공통 높이, vertical 이면 공통 너비(픽셀). 생략하면 두 소스 중 작은 쪽.
        font_file: 라벨 폰트(.ttf/.ttc/.otf). 생략하면 영문은 ffmpeg 기본 글꼴, 한글이 있으면 OS 의 한글 글꼴을 찾는다.
        exposure: EXR·HDR 같은 선형 이미지 소스에 더할 노출(스톱).
        crf: 화질. 낮을수록 좋고 파일이 커진다.
        overwrite: 이미 있는 파일을 덮어쓸 때 True.
    """
    ff = ffmpeg.require_ffmpeg()
    _check_encode_options(fps, crf)
    if layout not in LAYOUTS:
        raise ValueError(f"layout 은 {', '.join(LAYOUTS)} 중 하나입니다: {layout!r}")
    encoder, codec_args = ffmpeg.encode_args(ff, Path(output), crf)
    required = ["fps", "scale", "setsar", "tpad", "hstack" if layout == "horizontal" else "vstack"]
    if label_a or label_b:
        required.append("drawtext")
    ffmpeg.require_filters(ff, required)
    font = _fonts_for([label_a, label_b], font_file)
    target = run_in_main_thread(paths.prepare_output, output, overwrite)

    def bounds(source: str) -> tuple[float | None, float | None]:
        # start/end 는 이미지 시퀀스 소스에만 넘긴다. 영상 파일 소스는 전체를 쓴다.
        return (None, None) if _is_video_file(source) else (start, end)

    with tempfile.TemporaryDirectory(prefix="hmcp_compare_") as tmp:
        work = Path(tmp)
        src_a = _prepare_source(ff, a, *bounds(a), fps, exposure, work / "a")
        src_b = _prepare_source(ff, b, *bounds(b), fps, exposure, work / "b")

        if layout == "horizontal":
            common = _even(size or min(src_a.height, src_b.height))
            scale, stack, label_height = f"scale=-2:{common}", "hstack", common
        else:
            common = _even(size or min(src_a.width, src_b.width))
            scale, stack = f"scale={common}:-2", "vstack"
            label_height = int(min(s.height * common / max(1, s.width) for s in (src_a, src_b)))

        longest = max(src_a.duration, src_b.duration)
        expected = max(1, round(longest * fps))
        branches = []
        for index, (src, label, name) in enumerate(((src_a, label_a, "a"), (src_b, label_b, "b"))):
            # 초 단위(stop_duration)로 늘리면 반올림으로 한 프레임이 모자란다(실측). 프레임 수로 준다.
            pad = expected - round(src.duration * fps)
            hold = f",tpad=stop_mode=clone:stop={pad}" if pad > 0 else ""
            text = _label_filter(label, font, label_height, work, f"label_{name}")
            branches.append(f"[{index}:v]{src.pre_filter}fps={fps:g}{hold},{scale},setsar=1{text}[{name}]")
        graph = ";".join(branches) + (
            f";[a][b]{stack}=inputs=2,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p[out]"
        )
        result = _encode(ff, [src_a, src_b], graph, target, fps, expected, codec_args)

    response: dict[str, Any] = {
        "output": {**run_in_main_thread(_output_entry, output), **paths.file_stat(target)},
        "encoder": encoder,
        "layout": layout,
        "video": result,
        "a": src_a.info,
        "b": src_b.info,
        "ffmpeg": ff.describe(),
    }
    if font is not None:
        response["font"] = font.as_posix()
    warnings = []
    for key, src in (("a", src_a), ("b", src_b)):
        if src.info.get("missing_frames"):
            warnings.append(f"{key} 의 빠진 프레임 {src.info['missing_frames']} 은 앞 프레임으로 채웠습니다.")
    if abs(src_a.duration - src_b.duration) > 0.5 / fps:
        warnings.append(
            f"길이가 다릅니다(a {src_a.duration:.2f}초, b {src_b.duration:.2f}초). 짧은 쪽은 "
            f"마지막 프레임에 멈춘 채 이어집니다."
        )
    if result.get("frames") and result["frames"] != expected:
        warnings.append(f"기대한 {expected}프레임과 달리 {result['frames']}프레임이 나왔습니다.")
    if warnings:
        response["warnings"] = warnings
    return response
