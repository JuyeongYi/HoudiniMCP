"""houdini_mcp_base.video 시나리오. hython 안에서 돈다.

테스트가 이 파일을 hython 서브프로세스로 띄우고, 마지막에 찍는 JSON 한 줄을 읽어
검사한다(tests/paths 와 같은 방식). 뷰포트 캡처는 GUI 가 필요해 여기서 다루지 않는다.

외부 ffmpeg 이 필요하다. FFMPEG_BIN_PATH 가 없으면 테스트 쪽에서 건너뛴다.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

MARKER = "VIDEOTEST_JSON:"
"""이 접두사가 붙은 줄 하나만 테스트가 읽는다. Houdini 자체 출력과 섞이기 때문."""


def _write_sequence(directory: Path, name: str, frames: range, size: tuple[int, int], fmt: str, skip: set[int]) -> None:
    import OpenImageIO as oiio

    directory.mkdir(parents=True)
    width, height = size
    for frame in frames:
        if frame in skip:
            continue
        spec = oiio.ImageSpec(width, height, 3, "half" if fmt == "exr" else "uint8")
        buf = oiio.ImageBuf(spec)
        level = frame / (frames.stop + 1)
        oiio.ImageBufAlgo.fill(buf, (level, 0.2, 1.0 - level))
        buf.write(str(directory / name.format(frame=frame)))


def main() -> int:
    from houdini_mcp_base import video

    out: dict[str, object] = {}
    errors: dict[str, str] = {}

    def check(name: str, fn) -> None:
        try:
            out[name] = fn()
        except Exception as exc:  # 어느 검사가 왜 깨졌는지 테스트가 알아야 한다.
            errors[name] = f"{type(exc).__name__}: {exc}"

    root = Path(tempfile.mkdtemp(prefix="hmcp_video_"))
    exr_dir = root / "exr"
    png_dir = root / "png"
    _write_sequence(exr_dir, "beauty.{frame:04d}.exr", range(1, 13), (320, 180), "exr", skip={5})
    _write_sequence(png_dir, "frame.{frame:04d}.png", range(1, 9), (640, 360), "png", skip=set())

    exr_pattern = (exr_dir / "beauty.$F4.exr").as_posix()
    png_pattern = (png_dir / "frame.%04d.png").as_posix()

    check("sequence_video", lambda: video.make_video(
        output=(root / "a.mp4").as_posix(), source=exr_pattern, start=1, end=12,
        label="보정 전 before",
    ))
    check("video_source", lambda: video.make_video(
        output=(root / "a_relabel.webm").as_posix(), source=(root / "a.mp4").as_posix(),
        label="100% it's: done",
    ))
    check("compare_horizontal", lambda: video.compare_videos(
        a=exr_pattern, b=png_pattern, output=(root / "cmp_h.mp4").as_posix(),
        label_a="before", label_b="after",
    ))
    check("compare_vertical", lambda: video.compare_videos(
        a=(root / "a.mp4").as_posix(), b=png_pattern, output=(root / "cmp_v.mp4").as_posix(),
        layout="vertical", size=300, label_b=None,
    ))

    def refuses_overwrite():
        video.make_video(output=(root / "a.mp4").as_posix(), source=exr_pattern)
        return "no error"

    def expect_error(fn):
        try:
            fn()
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        return "no error"

    out["overwrite_error"] = expect_error(refuses_overwrite)
    out["extension_error"] = expect_error(lambda: video.make_video(
        output=(root / "a.avi").as_posix(), source=exr_pattern))
    out["not_sequence_error"] = expect_error(lambda: video.make_video(
        output=(root / "x.mp4").as_posix(), source=(exr_dir / "beauty.0001.exr").as_posix()))

    saved = os.environ.pop("FFMPEG_BIN_PATH", None)
    try:
        out["missing_env_error"] = expect_error(lambda: video.make_video(
            output=(root / "env.mp4").as_posix(), source=exr_pattern))
        out["missing_env_wrote"] = (root / "env.mp4").exists()
    finally:
        if saved is not None:
            os.environ["FFMPEG_BIN_PATH"] = saved

    print(MARKER + json.dumps({"results": out, "errors": errors}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
