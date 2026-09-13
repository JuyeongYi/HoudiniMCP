"""렌더를 실제로 거는 툴들.

두 가지 길이 있고, 둘의 성질이 다르다.

**`start_render`** — LOP 스테이지를 USD 로 내보내고 `husk` 를 별도 프로세스로
띄운다. 진짜 백그라운드다. Houdini 는 멈추지 않고, `render_status` 로 진행률을
물을 수 있으며, `cancel_render` 로 중간에 끊을 수 있다. husk 가 stdout 으로
내보내는 `ALF_PROGRESS` 를 읽어 퍼센트를 안다 (실측 확인).

**`render_rop`** — `hou.RopNode.render()` 를 부른다. **이것은 블로킹이다.**
실측으로 확인했다: HOM 에는 ROP 을 비동기로 거는 길이 없다. `render()` 는
끝날 때까지 돌아오지 않고, `addRenderEventCallback` 은 PreFrame/PostFrame 을
알려 주지만 그 콜백도 렌더 스레드 안에서 돈다. ROP 의 `executebackground`
파라미터는 hip 파일을 임시로 저장해 hbatch 를 띄우는 것이라 핸들을 돌려주지
않고 씬 파일을 건드린다 - 그래서 쓰지 않는다. 오래 걸리는 렌더는
`start_render` 를 쓴다.

husk 플래그는 `husk --help` 로 실측했다 (22.0.368).
"""

from __future__ import annotations

import atexit
import itertools
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool

from houdini_mcp_base import paths

from ._common import clip, lop_stage, require_node
from ._image import summarize
from ._usdrender import render_checks, resolve_settings, _targets
from .check import _resolve_lop

MAX_JOBS = 20
"""이보다 많아지면 끝난 잡부터 버린다. 임시 USD 도 같이 지운다."""

MAX_LOG_LINES = 600
MAX_FRAMES_SCANNED = 200
MAX_STATS_IMAGES = 4
"""통계를 낼 이미지 수. 시퀀스 전체를 읽으면 응답이 무거워진다."""

OUTPUT_PARMS = (
    "picture",
    "outputimage",
    "lopoutput",
    "sopoutput",
    "copoutput",
    "dopoutput",
    "vm_picture",
    "vm_uvoutputpicture1",
    "filename",
    "file",
)
"""ROP 이 출력 경로를 담는 파라미터 이름들. HOM 에 공통 규약이 없어 실측으로
모았다 (karma=picture, geometry=sopoutput, usdrender=outputimage/lopoutput,
alembic=filename, comp=copoutput, baketexture=vm_uvoutputpicture1)."""

_COUNTER = itertools.count(1)
_LOCK = threading.Lock()


@dataclass
class RenderJob:
    """백그라운드 husk 프로세스 하나."""

    job_id: str
    command: list[str]
    process: subprocess.Popen
    usd_file: str
    expected: list[str]
    started: float
    temp_dir: str | None = None
    progress: int = 0
    saved: list[str] = field(default_factory=list)
    lines: deque = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    finished: float | None = None
    cancelled: bool = False

    def state(self) -> str:
        if self.cancelled:
            return "cancelled"
        code = self.process.poll()
        if code is None:
            return "running"
        return "finished" if code == 0 else "failed"


_JOBS: dict[str, RenderJob] = {}


def _pump(job: RenderJob) -> None:
    """husk 의 출력을 읽어 진행률과 저장된 이미지를 뽑는다.

    데몬 스레드에서 돈다. 파이프를 안 비우면 husk 가 버퍼에 막혀 멈춘다.
    """
    stream = job.process.stdout
    if stream is not None:
        for raw in stream:
            line = raw.rstrip()
            job.lines.append(line)
            if line.startswith("ALF_PROGRESS"):
                token = line.split()[-1].rstrip("%")
                try:
                    job.progress = int(float(token))
                except ValueError:
                    pass
            elif "Saved Image:" in line:
                job.saved.append(line.split("Saved Image:", 1)[1].strip())
    job.process.wait()
    job.finished = time.time()


def _terminate(job: RenderJob, timeout: float = 5.0) -> None:
    if job.process.poll() is not None:
        return
    job.process.terminate()
    try:
        job.process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        job.process.kill()


def _evict() -> None:
    """끝난 잡이 너무 쌓이면 오래된 것부터 버린다."""
    with _LOCK:
        if len(_JOBS) <= MAX_JOBS:
            return
        done = [j for j in _JOBS.values() if j.process.poll() is not None]
        done.sort(key=lambda j: j.finished or j.started)
        for job in done[: len(_JOBS) - MAX_JOBS]:
            _JOBS.pop(job.job_id, None)
            if job.temp_dir:
                shutil.rmtree(job.temp_dir, ignore_errors=True)


@atexit.register
def _stop_all() -> None:
    """Houdini 가 닫힐 때 자식 husk 를 남기지 않는다."""
    for job in list(_JOBS.values()):
        try:
            _terminate(job, timeout=2.0)
        except Exception:  # noqa: BLE001 - 종료 경로에서 예외를 내보내지 않는다
            pass


def _require_job(job_id: str) -> RenderJob:
    job = _JOBS.get(job_id)
    if job is None:
        known = ", ".join(sorted(_JOBS)) or "없음"
        raise ValueError(
            f"그런 렌더 잡이 없습니다: {job_id}. 지금 있는 것: {known}. "
            f"render_status() 를 인자 없이 부르면 전부 볼 수 있습니다."
        )
    return job


def _export_stage(node: hou.LopNode) -> tuple[Path, str]:
    """LOP 스테이지를 husk 가 읽을 USD 파일로 플래튼해서 내보낸다.

    Flatten 이 필요한 이유는 Houdini 의 LOP 스테이지가 메모리 안의 레이어
    더미이기 때문이다. 루트 레이어만 내보내면 husk 가 아무것도 못 본다.
    """
    stage = lop_stage(node)
    temp_dir = tempfile.mkdtemp(prefix="hmcp_render_")
    target = Path(temp_dir) / "stage.usd"
    layer = stage.Flatten()
    # USD 는 어느 플랫폼에서나 슬래시 경로를 쓴다.
    if not layer.Export(target.as_posix()):
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(
            f"{node.path()} 의 스테이지를 USD 로 내보내지 못했습니다. "
            f"노드가 쿡되는지 cook_node 로 확인하세요."
        )
    return target, temp_dir


def _expected_outputs(stage, settings_prim: str | None) -> list[str]:
    """RenderSettings 가 어디에 쓸 것이라고 말하는지."""
    try:
        settings = resolve_settings(stage, settings_prim)
    except ValueError:
        return []
    from pxr import Sdf, UsdRender

    out = []
    for path in _targets(settings.GetProductsRel()):
        prim = stage.GetPrimAtPath(Sdf.Path(path))
        if not prim:
            continue
        name = UsdRender.Product(prim).GetProductNameAttr().Get()
        if name:
            out.append(str(paths.to_path(str(name))))
    return out


@tool()
def start_render(
    target: str,
    output: str | None = None,
    frame: float | None = None,
    frame_count: int = 1,
    frame_inc: float = 1.0,
    resolution: list[int] | None = None,
    samples: int | None = None,
    renderer: str | None = None,
    settings_prim: str | None = None,
    snapshot_seconds: float | None = None,
    threads: int = 0,
    skip_validation: bool = False,
) -> dict[str, Any]:
    """husk 로 백그라운드 렌더를 시작하고 잡 핸들을 돌려준다. Houdini 는 멈추지 않는다.

    LOP 노드를 주면 그 스테이지를 USD 로 내보내 렌더하고, .usd/.usda/.usdc
    파일 경로를 주면 그것을 바로 렌더한다.

    시작 전에 `validate_render` 와 같은 점검을 돌린다. 카메라가 없거나 출력
    경로에 쓸 수 없는 상태면 렌더를 걸지 않고 무엇이 문제인지 말한다
    (`skip_validation=True` 로 끌 수 있다).

    **LOP 을 줄 때의 한계**: 스테이지는 지금 Houdini 프레임에서 쿡된 상태로
    내보내진다. SOP Import 처럼 프레임마다 다시 쿡해야 하는 네트워크는 여러
    프레임을 걸어도 첫 프레임 데이터로 렌더된다. 시퀀스를 제대로 내려면 USD
    ROP 으로 프레임 범위를 미리 내보낸 뒤 그 .usd 파일을 target 으로 주세요.

    진행 상황은 `render_status`, 로그는 `render_log`, 중단은 `cancel_render`.

    Args:
        target: LOP 노드 경로, 또는 렌더할 .usd 파일 경로.
        output: 출력 이미지 경로 override. 생략하면 RenderSettings 의 것을 쓴다.
            $F4 같은 프레임 변수를 그대로 쓸 수 있다.
        frame: 시작 프레임. 생략하면 USD 의 startTimeCode.
        frame_count: 렌더할 프레임 수.
        frame_inc: 프레임 증가폭.
        resolution: [가로, 세로] override.
        samples: 픽셀당 샘플 수. 확인용 렌더는 4~16 이면 충분하다.
        renderer: Hydra 델리게이트 이름. `list_renderers` 로 확인한다.
        settings_prim: 쓸 RenderSettings 프림 경로.
        snapshot_seconds: 이 초마다 부분 이미지를 저장한다. 긴 렌더의 중간
            결과를 미리 보고 싶을 때.
        threads: 쓸 스레드 수. 0 이면 전부.
        skip_validation: 렌더 전 점검을 건너뛴다.
    """
    node = hou.node(target)
    temp_dir: str | None = None
    validation: dict[str, Any] | None = None

    if node is not None:
        lop = _resolve_lop(target)
        stage = lop_stage(lop)
        if not skip_validation:
            validation = render_checks(stage, settings_prim)
            if not validation["ok"]:
                raise ValueError(
                    "렌더를 걸 수 없는 상태입니다:\n- "
                    + "\n- ".join(validation["errors"])
                    + "\n그래도 걸어 보려면 skip_validation=True 를 주세요."
                )
        usd_file, temp_dir = _export_stage(lop)
        expected = _expected_outputs(stage, settings_prim)
        source = lop.path()
    else:
        usd_file = paths.to_path(target)
        if not usd_file.exists():
            raise ValueError(
                f"노드도 파일도 아닙니다: {target}. LOP 노드 경로(/stage/...)나 "
                f"있는 .usd 파일 경로를 주세요."
            )
        if usd_file.suffix.lower() not in (".usd", ".usda", ".usdc", ".usdz"):
            raise ValueError(
                f"USD 파일이 아닙니다: {usd_file} (확장자 {usd_file.suffix!r}). "
                f"husk 는 .usd/.usda/.usdc/.usdz 만 읽습니다."
            )
        expected = []
        source = str(usd_file)

    if output:
        expected = [str(paths.to_path(output, frame))]

    husk = paths.require_hfs_bin("husk")
    command: list[str] = [
        str(husk),
        str(usd_file),
        # -Va2 가 ALF_PROGRESS 를 켠다. --no-mplay 는 헤드리스에서 필수다.
        "-Va2",
        "--no-mplay",
        "--make-output-path",
        "-n",
        str(int(frame_count)),
        "-i",
        str(float(frame_inc)),
    ]
    if frame is not None:
        command += ["-f", str(float(frame))]
    if output:
        command += ["-o", output]
    if resolution:
        if len(resolution) != 2 or min(resolution) <= 0:
            raise ValueError(
                f"resolution 은 [가로, 세로] 형태의 양수 둘이어야 합니다: {resolution}"
            )
        command += ["--res", str(int(resolution[0])), str(int(resolution[1]))]
    if samples is not None:
        command += ["-p", str(int(samples))]
    if renderer:
        command += ["-R", renderer]
    if settings_prim:
        command += ["-s", settings_prim]
    if snapshot_seconds:
        command += ["--snapshot", str(float(snapshot_seconds))]
    if threads:
        command += ["-j", str(int(threads))]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    job = RenderJob(
        job_id=f"render{next(_COUNTER)}",
        command=command,
        process=process,
        usd_file=str(usd_file),
        expected=expected,
        started=time.time(),
        temp_dir=temp_dir,
    )
    with _LOCK:
        _JOBS[job.job_id] = job
    threading.Thread(target=_pump, args=(job,), daemon=True).start()
    _evict()

    result: dict[str, Any] = {
        "job": job.job_id,
        "state": "running",
        "pid": process.pid,
        "source": source,
        "usd_file": job.usd_file,
        "expected_outputs": expected,
        "command": command,
        "next": f"render_status('{job.job_id}') 로 진행률을 보세요.",
    }
    if validation and validation["warnings"]:
        result["warnings"] = validation["warnings"]
    return result


@tool()
def render_status(job: str | None = None, with_stats: bool = True) -> dict[str, Any]:
    """렌더 잡의 진행 상황. 끝났으면 결과 이미지를 실제로 읽어 통계까지 준다.

    이 툴이 "끝났습니다"로 끝나지 않는 이유다. 렌더가 완료되면 저장된 이미지를
    OpenImageIO 로 열어 채널별 min/max/평균과 NaN 여부를 내고, 새까맣거나
    알파가 비었으면 그렇다고 말한다.

    Args:
        job: 잡 id. 생략하면 이 세션의 잡 전부를 요약해서 보여준다.
        with_stats: 끝난 잡의 결과 이미지를 열어 통계를 낼지. 큰 시퀀스에서
            응답을 가볍게 하고 싶으면 False.
    """
    if job is None:
        return {
            "count": len(_JOBS),
            "jobs": [
                {
                    "job": j.job_id,
                    "state": j.state(),
                    "progress": j.progress,
                    "seconds": round((j.finished or time.time()) - j.started, 1),
                    "saved_count": len(j.saved),
                    "source": j.usd_file,
                }
                for j in sorted(_JOBS.values(), key=lambda x: x.started)
            ],
        }

    handle = _require_job(job)
    state = handle.state()
    elapsed = round((handle.finished or time.time()) - handle.started, 1)
    result: dict[str, Any] = {
        "job": handle.job_id,
        "state": state,
        "progress": handle.progress,
        "seconds": elapsed,
        "usd_file": handle.usd_file,
        "saved_images": handle.saved,
        "exit_code": handle.process.poll(),
    }

    if state == "running":
        result["next"] = "아직 돌고 있습니다. 잠시 뒤 다시 물어보세요."
        return result

    if state in ("failed", "cancelled"):
        result["log_tail"] = [clip(line, 300) for line in list(handle.lines)[-15:]]
        if state == "failed":
            result["next"] = (
                f"husk 가 코드 {handle.process.poll()} 로 끝났습니다. "
                f"render_log('{handle.job_id}') 로 전체 로그를 보세요."
            )
        return result

    # 완료 - 여기서부터가 이 팩의 본론이다. 결과를 읽어 본다.
    candidates = handle.saved or handle.expected
    images: list[dict[str, Any]] = []
    for path_text in candidates[:MAX_STATS_IMAGES if with_stats else MAX_FRAMES_SCANNED]:
        path = paths.to_path(path_text)
        if not path.exists():
            images.append({
                "file": path.as_posix(),
                "missing": True,
                "note": "husk 는 끝났는데 파일이 없습니다. 출력 경로 권한을 보세요.",
            })
            continue
        if not with_stats:
            images.append({"file": path.as_posix(), "bytes": path.stat().st_size})
            continue
        try:
            images.append(summarize(path))
        except Exception as exc:  # noqa: BLE001 - 한 장이 깨져도 나머지는 본다
            images.append({"file": path.as_posix(), "error": clip(str(exc), 300)})
    result["images"] = images
    if len(candidates) > len(images):
        result["more_images"] = len(candidates) - len(images)
    if not candidates:
        result["next"] = (
            "husk 는 성공했는데 저장된 이미지를 찾지 못했습니다. "
            f"render_log('{handle.job_id}') 를 보세요."
        )
    return result


@tool()
def render_log(job: str, lines: int = 40) -> dict[str, Any]:
    """렌더 잡이 내보낸 husk 로그의 끝부분.

    렌더가 실패했거나 그림이 이상할 때 원인이 여기 있다. husk 는 라이트 개수,
    레이 수, 저장한 파일 경로, 경고를 전부 stdout 으로 내보낸다.

    Args:
        job: 잡 id.
        lines: 돌려줄 줄 수. 최대 200.
    """
    handle = _require_job(job)
    count = max(1, min(int(lines), 200))
    captured = list(handle.lines)
    return {
        "job": handle.job_id,
        "state": handle.state(),
        "command": handle.command,
        "captured_lines": len(captured),
        "truncated": len(captured) >= MAX_LOG_LINES,
        "lines": [clip(line, 300) for line in captured[-count:]],
    }


@tool()
def cancel_render(job: str) -> dict[str, Any]:
    """돌고 있는 렌더를 중단한다.

    중단 시점까지 저장된 이미지는 남는다 (snapshot_seconds 를 줬다면 부분
    이미지도). 임시로 내보낸 USD 파일은 지운다.

    Args:
        job: 잡 id.
    """
    handle = _require_job(job)
    if handle.process.poll() is not None:
        return {
            "job": handle.job_id,
            "state": handle.state(),
            "note": "이미 끝난 잡입니다. 중단할 것이 없습니다.",
        }
    handle.cancelled = True
    _terminate(handle)
    return {
        "job": handle.job_id,
        "state": "cancelled",
        "seconds": round(time.time() - handle.started, 1),
        "progress": handle.progress,
        "saved_images": handle.saved,
    }


# ---- ROP 블로킹 렌더 ---------------------------------------------------


def _rop_frames(node: hou.RopNode, frame_range: list[float] | None) -> list[float]:
    """이 ROP 이 어떤 프레임을 쓸지. 출력 파일을 찾으려면 알아야 한다."""
    if frame_range:
        start = float(frame_range[0])
        end = float(frame_range[1]) if len(frame_range) > 1 else start
        inc = float(frame_range[2]) if len(frame_range) > 2 else 1.0
    else:
        trange = node.parm("trange")
        if trange is None or trange.eval() == 0:
            return [hou.frame()]
        first, last, step = node.parm("f1"), node.parm("f2"), node.parm("f3")
        if first is None or last is None:
            return [hou.frame()]
        start, end = float(first.eval()), float(last.eval())
        inc = float(step.eval()) if step is not None else 1.0
    if inc <= 0:
        inc = 1.0
    frames: list[float] = []
    current = start
    while current <= end + 1e-6 and len(frames) < MAX_FRAMES_SCANNED:
        frames.append(round(current, 4))
        current += inc
    return frames or [start]


def _rop_outputs(node: hou.RopNode, frames: list[float]) -> list[Path]:
    """ROP 이 쓴 파일들. 파라미터를 프레임마다 평가해 모은다.

    OUTPUT_PARMS 의 순서대로 보고 **값이 있는 첫 번째 것만** 쓴다. 한 ROP 에
    출력 파라미터가 여럿 있을 수 있는데(usdrender_rop 은 outputimage 와
    lopoutput 을 함께 가진다) 뒤쪽은 내부용 임시 파일이라 결과가 아니다.
    """
    seen: list[Path] = []
    for frame in frames:
        for name in OUTPUT_PARMS:
            parm = node.parm(name)
            if parm is None:
                continue
            try:
                value = parm.evalAsStringAtFrame(frame).strip()
            except hou.OperationFailed:
                continue
            if not value:
                continue
            path = paths.to_path(value, frame)
            if path not in seen:
                seen.append(path)
            break
    return seen


@tool()
def render_rop(
    path: str,
    frame_range: list[float] | None = None,
    output_file: str | None = None,
    ignore_inputs: bool = False,
    inspect_outputs: bool = True,
) -> dict[str, Any]:
    """ROP 을 렌더하고, 나온 파일을 실제로 열어 무엇이 찍혔는지 돌려준다.

    **블로킹이다.** 끝날 때까지 Houdini 도 이 호출도 돌아오지 않는다. HOM 에
    ROP 을 비동기로 거는 길이 없기 때문이다(실측 확인). 몇 초~몇십 초짜리
    확인용 렌더나 지오메트리 캐시 출력에 쓰고, 오래 걸리는 이미지 렌더는
    `start_render` 를 쓰세요.

    렌더가 끝나면 ROP 의 출력 파라미터를 프레임마다 평가해 실제 파일을 찾고,
    이미지면 픽셀 통계까지 낸다. 파일이 안 만들어졌으면 그렇다고 말한다.

    Args:
        path: ROP 노드 경로. 예: /out/karma_beauty, /stage/usdrender_rop1
        frame_range: [시작, 끝] 또는 [시작, 끝, 증가폭]. 생략하면 ROP 설정대로.
        output_file: 출력 경로 override.
        ignore_inputs: True 면 이 ROP 만 렌더하고 입력 ROP 은 건너뛴다.
        inspect_outputs: 나온 이미지를 열어 픽셀 통계를 낼지.
    """
    node = require_node(path)
    if not isinstance(node, hou.RopNode):
        raise ValueError(
            f"{path} 는 ROP 이 아닙니다 (type={node.type().name()}, "
            f"category={node.type().category().name()}). /out 이나 /stage 의 "
            f"렌더 노드 경로를 주세요."
        )

    frames = _rop_frames(node, frame_range)
    kwargs: dict[str, Any] = {"ignore_inputs": bool(ignore_inputs)}
    if frame_range:
        kwargs["frame_range"] = tuple(float(f) for f in frame_range)
    if output_file:
        kwargs["output_file"] = output_file

    started = time.time()
    failure: str | None = None
    try:
        node.render(**kwargs)
    except hou.OperationFailed as exc:
        failure = clip(str(exc).splitlines()[0], 400)

    result: dict[str, Any] = {
        "node": node.path(),
        "comment": node.comment(),
        "type": node.type().name(),
        "seconds": round(time.time() - started, 2),
        "frames": frames if len(frames) <= 20 else [frames[0], "…", frames[-1]],
        "frame_count": len(frames),
    }
    if failure:
        result["render_failed"] = failure
    errors = [clip(t) for t in node.errors() if t.strip()][:5]
    warnings = [clip(t) for t in node.warnings() if t.strip()][:5]
    if errors:
        result["errors"] = errors
    if warnings:
        result["warnings"] = warnings

    outputs: list[dict[str, Any]] = []
    inspected = 0
    for candidate in _rop_outputs(node, frames):
        entry: dict[str, Any] = {"file": candidate.as_posix()}
        if not candidate.exists():
            entry["missing"] = True
            entry["note"] = "이 경로에 파일이 만들어지지 않았습니다."
            outputs.append(entry)
            continue
        entry["bytes"] = candidate.stat().st_size
        if inspect_outputs and inspected < MAX_STATS_IMAGES:
            try:
                entry.update(summarize(candidate))
                inspected += 1
            except Exception as exc:  # noqa: BLE001 - 이미지가 아닐 수도 있다
                entry["not_an_image"] = clip(str(exc), 200)
        outputs.append(entry)
    result["outputs"] = outputs
    if not outputs:
        result["next"] = (
            "출력 파라미터를 찾지 못했습니다. list_parms 로 이 ROP 의 출력 경로 "
            "파라미터 이름을 확인하세요."
        )
    return result
