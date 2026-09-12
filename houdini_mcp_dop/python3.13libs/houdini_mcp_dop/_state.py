"""팩 전체가 쓰는 헬퍼 2 — 쿡된 시뮬의 상태를 읽는다.

씬을 만드는 쪽은 `_common.py` 에 있다. 여기는 **읽기 전용**이다.

1. **시뮬 상태 읽기** — `hou.DopSimulation` / `hou.DopObject` / 레코드를
   요약한다.
2. **필드 통계** — 볼륨 필드를 통계로 압축한다. 복셀 배열을 그대로 내보내지
   않는다.
3. **프레임 진행과 발산 감지** — 프레임을 하나씩 진행시키며 매 프레임 상태를
   기록하고, 값이 폭발하거나 NaN 이 되면 잡는다.

실측으로 확인한 것(Houdini 22.0.368):

- `hou.DopSimulation.setTime` 은 dopnet 이 소유한 시뮬에서 `hou.PermissionError`
  를 낸다. 프레임 진행은 `hou.setFrame` + `dopnet.cook()` 이 맞다.
- `hou.DopObject.geometry()` 는 **오브젝트 공간**이다. 월드 위치는
  `transform()` 에서 얻는다. 스모크처럼 지오메트리가 없는 오브젝트는 None 이다.
- 강체는 점 속도(`v`)가 없다. 속도는 Position 서브데이터(RBD_State)의
  `vel` / `angvel` 에 있다.
- 필드에 NaN 이 섞이면 `hou.Volume.volumeAverage()` 가 NaN 을, Inf 가 섞이면
  `volumeMax()` 가 Inf 를 돌려준다. 복셀을 numpy 로 다 읽지 않고도 발산을
  잡을 수 있다.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Sequence

import hou
import numpy

# --------------------------------------------------------------------------
# 시뮬 상태 읽기
# --------------------------------------------------------------------------

# 솔버가 내부적으로 쓰는 임시 필드. 통계에 섞이면 읽히지 않는다.
_TEMP_FIELD_PREFIX = "__tempfield"

_FIELD_TYPES = ("ScalarField", "VectorField", "IndexField", "MatrixField")


def is_field(data: hou.DopData) -> bool:
    return any(kind in data.dataType() for kind in _FIELD_TYPES)


def field_names(obj: hou.DopObject, include_temp: bool = False) -> list[str]:
    """이 오브젝트가 가진 필드 이름. 임시 필드는 기본으로 뺀다."""
    names = []
    for name, data in obj.subData().items():
        if not include_temp and name.startswith(_TEMP_FIELD_PREFIX):
            continue
        if is_field(data):
            names.append(name)
    return sorted(names)


def record_dict(record: hou.DopRecord | None) -> dict[str, Any]:
    """DopRecord 를 JSON 으로 낼 수 있는 사전으로. 읽을 수 없는 필드는 건너뛴다."""
    if record is None:
        return {}
    out: dict[str, Any] = {}
    for name in record.fieldNames():
        try:
            value = record.field(name)
        except (hou.Error, TypeError):
            continue
        out[name] = _jsonable(value)
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return [float(v) for v in value]
    if isinstance(value, hou.Matrix4):
        return [float(v) for row in value.asTupleOfTuples() for v in row]
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def memory_of(data: hou.DopData) -> int:
    """DOP 데이터가 쓰는 바이트. Basic 레코드의 memusage 다."""
    try:
        record = data.record("Basic")
    except hou.Error:
        return 0
    if record is None:
        return 0
    try:
        return int(record.field("memusage"))
    except (hou.Error, TypeError, ValueError):
        return 0


def object_summary(obj: hou.DopObject, with_fields: bool = True) -> dict[str, Any]:
    """시뮬 오브젝트 하나의 요약. 점 좌표를 통째로 넘기지 않는다."""
    geo = obj.geometry()
    transform = obj.transform()
    translate = transform.extractTranslates()
    options = record_dict(obj.options())

    summary: dict[str, Any] = {
        "name": obj.name(),
        "objid": obj.objid(),
        "data_type": obj.dataType(),
        "world_position": [float(v) for v in translate],
        "memory_bytes": memory_of(obj),
        "affectors": options.get("affectors", ""),
        "groups": options.get("groups", ""),
        "creator": _creator_path(obj),
        "source_type": creator_type(obj),
    }
    if geo is not None:
        summary["points"] = geo.pointCount()
        summary["prims"] = geo.primCount()
        summary["bbox_local"] = _bbox(geo.boundingBox())
    else:
        # 스모크·FLIP 컨테이너처럼 지오메트리 대신 필드를 가진 오브젝트다.
        summary["points"] = None
        summary["prims"] = None
    if with_fields:
        summary["fields"] = field_names(obj)
    return summary


def _creator_path(data: hou.DopData) -> str:
    basic = record_dict(data.record("Basic"))
    return str(basic.get("creator", ""))


# 움직이지 않는 것이 정상인 오브젝트 타입. 충돌체가 가만히 있다고 경고하면 안 된다.
PASSIVE_TYPES = ("staticobject", "terrainobject")


def creator_type(obj: hou.DopObject) -> str:
    """이 오브젝트를 만든 DOP 노드의 타입.

    creator 는 `/obj/sim/ground_static/emptyobject1` 처럼 DOP 노드 **안쪽**을
    가리킨다. 우리가 알고 싶은 것은 그 부모인 ground_static 의 타입이다.
    """
    path = _creator_path(obj)
    if not path:
        return ""
    node = hou.node(path.rsplit("/", 1)[0])
    return node.type().name() if node is not None else ""


def _bbox(bbox: hou.BoundingBox) -> dict[str, list[float]]:
    if not bbox.isValid():
        return {"min": [], "max": [], "size": []}
    minvec, maxvec, size = bbox.minvec(), bbox.maxvec(), bbox.sizevec()
    return {
        "min": [minvec[0], minvec[1], minvec[2]],
        "max": [maxvec[0], maxvec[1], maxvec[2]],
        "size": [size[0], size[1], size[2]],
    }


# --------------------------------------------------------------------------
# 필드 통계
# --------------------------------------------------------------------------


def field_volumes(obj: hou.DopObject, name: str) -> list[hou.Volume]:
    """필드의 볼륨 프림들. 스칼라는 1개, 벡터는 3개(MAC 스태거)다."""
    if name not in obj.subData():
        raise ValueError(
            f"{obj.name()} 에 {name!r} 필드가 없습니다. "
            f"있는 필드: {', '.join(field_names(obj)) or '(없음)'}"
        )
    geo = obj.fieldGeometry(name)
    if geo is None:
        raise ValueError(
            f"{obj.name()} 의 {name!r} 는 볼륨 필드가 아닙니다 "
            f"({obj.findSubData(name).dataType()}). "
            f"list_dop_fields 로 필드 종류를 확인하세요."
        )
    return [prim for prim in geo.prims() if isinstance(prim, hou.Volume)]


def cheap_stats(volume: hou.Volume) -> dict[str, Any]:
    """복셀을 파이썬으로 읽지 않고 얻는 통계. C++ 쪽에서 한 번에 센다.

    NaN 이 섞이면 average 가 NaN, Inf 가 섞이면 max 가 Inf 로 나온다(실측).
    그래서 이 세 값만으로 발산을 잡을 수 있다.
    """
    low, high, avg = volume.volumeMin(), volume.volumeMax(), volume.volumeAverage()
    resolution = volume.resolution()
    return {
        "resolution": [int(v) for v in resolution],
        "voxels": int(resolution[0]) * int(resolution[1]) * int(resolution[2]),
        "min": _finite(low),
        "max": _finite(high),
        "mean": _finite(avg),
        "finite": math.isfinite(low) and math.isfinite(high) and math.isfinite(avg),
    }


def _finite(value: float) -> Any:
    """JSON 으로 낼 수 없는 NaN/Inf 를 문자열로 바꾼다. 정보를 버리지 않는다."""
    return float(value) if math.isfinite(value) else str(float(value))


def deep_stats(volume: hou.Volume, bins: int = 16) -> dict[str, Any]:
    """복셀을 numpy 로 받아 히스토그램까지. 큰 필드에서는 비싸다.

    `allVoxelsAsString` 으로 바이트를 통째로 받아 `numpy.frombuffer` 로 꽂는다.
    `allVoxels()` 로 파이썬 튜플을 만들면 복셀 100만 개에 수 초가 걸린다.
    """
    stats = cheap_stats(volume)
    raw = volume.allVoxelsAsString()
    array = numpy.frombuffer(raw, dtype=numpy.float32)
    nan_count = int(numpy.isnan(array).sum())
    inf_count = int(numpy.isinf(array).sum())
    finite = array[numpy.isfinite(array)]

    stats["nan_voxels"] = nan_count
    stats["inf_voxels"] = inf_count
    stats["nonzero_voxels"] = int(numpy.count_nonzero(finite))
    if finite.size:
        data = finite.astype(numpy.float64, copy=False)
        quantiles = numpy.quantile(data, [0.05, 0.5, 0.95])
        stats["std"] = float(data.std())
        stats["quantiles"] = {
            "p05": float(quantiles[0]),
            "p50": float(quantiles[1]),
            "p95": float(quantiles[2]),
        }
        stats["histogram"] = _histogram(data, bins)
    return stats


def _histogram(values: numpy.ndarray, bins: int) -> dict[str, Any]:
    low, high = float(values.min()), float(values.max())
    if low == high:
        return {"edges": [low, high], "counts": [int(values.size)], "constant": True}
    counts, edges = numpy.histogram(values, bins=bins, range=(low, high))
    return {
        "edges": [float(e) for e in edges],
        "counts": [int(c) for c in counts],
        "constant": False,
    }


def point_health(geo: hou.Geometry | None) -> dict[str, Any] | None:
    """점 좌표와 속도의 건전성. 벌크 접근자로 받아 numpy 로 본다."""
    if geo is None or geo.pointCount() == 0:
        return None
    health: dict[str, Any] = {}
    positions = _bulk_point(geo, "P")
    if positions is not None:
        finite = numpy.isfinite(positions).all()
        health["position_finite"] = bool(finite)
        if finite:
            health["max_distance"] = float(numpy.linalg.norm(positions, axis=1).max())
    velocities = _bulk_point(geo, "v")
    if velocities is not None:
        finite = numpy.isfinite(velocities).all()
        health["velocity_finite"] = bool(finite)
        if finite:
            health["max_speed"] = float(numpy.linalg.norm(velocities, axis=1).max())
    return health or None


def body_health(obj: hou.DopObject) -> dict[str, Any] | None:
    """강체처럼 점 속도가 없는 오브젝트의 속도. Position 서브데이터에서 읽는다.

    강체는 지오메트리가 움직이지 않고 변환만 바뀐다. 그래서 점 속도(`v`)가
    없고, 속도는 Position 서브데이터(RBD_State / SIM_Motion)의 `vel` 과
    `angvel` 에 있다(실측). 이걸 안 보면 강체가 튕겨 나가는 것을 못 잡는다.
    """
    position = obj.findSubData("Position")
    if position is None:
        return None
    try:
        record = position.options()
    except hou.Error:
        return None
    if record is None:
        return None

    health: dict[str, Any] = {}
    for field, key in (("vel", "body_speed"), ("angvel", "body_spin")):
        try:
            value = record.field(field)
        except (hou.Error, TypeError):
            continue
        components = [float(v) for v in value]
        if all(math.isfinite(v) for v in components):
            health[key] = math.sqrt(sum(v * v for v in components))
        else:
            health[f"{key}_finite"] = False
    return health or None


def _bulk_point(geo: hou.Geometry, name: str) -> numpy.ndarray | None:
    attrib = geo.findPointAttrib(name)
    if attrib is None or attrib.dataType() != hou.attribData.Float:
        return None
    raw = geo.pointFloatAttribValuesAsString(name, hou.numericData.Float32)
    array = numpy.frombuffer(raw, dtype=numpy.float32)
    size = attrib.size()
    return array.reshape(-1, size) if size > 1 else array.reshape(-1, 1)


# --------------------------------------------------------------------------
# 프레임 진행과 발산 감지
# --------------------------------------------------------------------------


def frame_state(dopnet: hou.Node, deep: bool = False) -> dict[str, Any]:
    """현재 프레임의 시뮬 상태. 오브젝트별 요소 수와 필드 통계."""
    sim = dopnet.simulation()
    objects = []
    for obj in sim.objects():
        source_type = creator_type(obj)
        entry: dict[str, Any] = {
            "name": obj.name(),
            "objid": obj.objid(),
            "source_type": source_type,
            "passive": source_type in PASSIVE_TYPES,
            "memory_bytes": memory_of(obj),
        }
        geo = obj.geometry()
        health: dict[str, Any] = {}
        if geo is not None:
            entry["points"] = geo.pointCount()
            entry["prims"] = geo.primCount()
            health.update(point_health(geo) or {})
        health.update(body_health(obj) or {})
        if health:
            entry["health"] = health
        translate = obj.transform().extractTranslates()
        entry["world_position"] = [round(float(v), 6) for v in translate]

        fields = {}
        for name in field_names(obj):
            try:
                volumes = field_volumes(obj, name)
            except (ValueError, hou.Error):
                continue
            if not volumes:
                continue
            stats = [deep_stats(v) if deep else cheap_stats(v) for v in volumes]
            fields[name] = stats[0] if len(stats) == 1 else {"components": stats}
        if fields:
            entry["fields"] = fields
        objects.append(entry)

    return {
        "sim_time": round(float(sim.time()), 6),
        "memory_bytes": int(sim.memoryUsage()),
        "objects": objects,
    }


def divergence_warnings(state: dict[str, Any], speed_limit: float) -> list[str]:
    """이 프레임에서 발산 징후를 찾는다. 값이 유한하지 않거나 너무 빠른 것.

    시뮬은 터지는 게 정상이고, 터졌는지 아는 것이 전부다.
    """
    warnings: list[str] = []
    for entry in state["objects"]:
        name = entry["name"]
        health = entry.get("health", {})
        if health.get("position_finite") is False:
            warnings.append(f"{name}: point positions contain NaN or infinity")
        if health.get("velocity_finite") is False:
            warnings.append(f"{name}: point velocities contain NaN or infinity")
        if health.get("body_speed_finite") is False:
            warnings.append(f"{name}: rigid body velocity is NaN or infinity")
        if health.get("body_spin_finite") is False:
            warnings.append(f"{name}: rigid body angular velocity is NaN or infinity")
        for key, label in (("max_speed", "point speed"), ("body_speed", "body speed")):
            speed = health.get(key)
            if speed is not None and speed > speed_limit:
                warnings.append(
                    f"{name}: max {label} {speed:.1f} exceeds {speed_limit:.0f}"
                )
        for field, stats in entry.get("fields", {}).items():
            parts = stats.get("components", [stats])
            for index, part in enumerate(parts):
                if not part.get("finite", True):
                    suffix = f"[{index}]" if len(parts) > 1 else ""
                    warnings.append(
                        f"{name}.{field}{suffix}: field values are not finite "
                        f"(min={part['min']}, max={part['max']}, mean={part['mean']})"
                    )
    return warnings


def run_frames(
    dopnet: hou.Node,
    start: int,
    end: int,
    deep: bool = False,
    speed_limit: float = 1.0e5,
    on_frame: Callable[[int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """프레임을 하나씩 진행시키며 매 프레임 상태를 기록한다.

    `hou.DopSimulation.setTime` 은 dopnet 이 소유한 시뮬에서 거부되므로
    `hou.setFrame` + `dopnet.cook()` 으로 간다(실측). 시뮬은 앞 프레임에
    의존하므로 건너뛰지 않고 순차로 돈다.

    끝나면 원래 프레임으로 돌려놓는다. 사용자의 타임라인을 움직인 채로 두지
    않기 위해서다.
    """
    original_frame = hou.frame()
    frames: list[dict[str, Any]] = []
    first_error_frame: int | None = None
    errors: list[str] = []

    try:
        for frame in range(start, end + 1):
            hou.setFrame(frame)
            began = time.perf_counter()
            cook_errors: list[str] = []
            try:
                dopnet.cook()
            except hou.Error as exc:
                cook_errors.append(str(exc))
            elapsed = time.perf_counter() - began
            cook_errors.extend(dopnet.errors())

            state = frame_state(dopnet, deep=deep)
            record: dict[str, Any] = {
                "frame": frame,
                "cook_seconds": round(elapsed, 4),
                "sim_time": state["sim_time"],
                "memory_bytes": state["memory_bytes"],
                "objects": state["objects"],
            }
            warnings = divergence_warnings(state, speed_limit)
            if warnings:
                record["divergence"] = warnings
            if cook_errors:
                record["errors"] = cook_errors
                if first_error_frame is None:
                    first_error_frame = frame
                    errors = cook_errors
            frames.append(record)
            if on_frame is not None:
                on_frame(frame, record)
    finally:
        hou.setFrame(original_frame)

    return {
        "frames": frames,
        "first_error_frame": first_error_frame,
        "first_errors": errors,
        "summary": _run_summary(frames),
    }


def _run_summary(frames: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """프레임 기록을 한 눈에 보는 요약. 총 시간, 메모리 증가, 첫 발산."""
    if not frames:
        return {"frames": 0}
    total = sum(f["cook_seconds"] for f in frames)
    slowest = max(frames, key=lambda f: f["cook_seconds"])
    first_diverged = next((f["frame"] for f in frames if "divergence" in f), None)
    memory = [f["memory_bytes"] for f in frames]
    counts = _element_trend(frames)
    return {
        "frames": len(frames),
        "total_cook_seconds": round(total, 3),
        "mean_cook_seconds": round(total / len(frames), 4),
        "slowest_frame": {
            "frame": slowest["frame"],
            "cook_seconds": slowest["cook_seconds"],
        },
        "memory_bytes": {"start": memory[0], "end": memory[-1], "growth": memory[-1] - memory[0]},
        "first_divergence_frame": first_diverged,
        "element_trend": counts,
        "field_trend": _field_trend(frames),
    }


def _element_trend(frames: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """오브젝트별 점 수와 월드 위치가 어떻게 변했는지.

    점 수만 보면 안 된다. 강체는 점 수가 변하지 않는 것이 정상이고, 움직였는지는
    위치로만 알 수 있다. 파티클·FLIP 은 반대로 점 수가 늘어야 소스가 먹은 것이다.
    """
    trend: dict[str, dict[str, Any]] = {}
    for record in frames:
        for entry in record["objects"]:
            slot = trend.setdefault(
                entry["name"],
                {"points": [], "positions": [], "passive": entry.get("passive", False)},
            )
            if entry.get("points") is not None:
                slot["points"].append(entry["points"])
            slot["positions"].append(entry.get("world_position", [0.0, 0.0, 0.0]))

    for slot in trend.values():
        series = slot.pop("points")
        positions = slot.pop("positions")
        if series:
            slot["points"] = {"start": series[0], "end": series[-1], "max": max(series)}
        first, last = positions[0], positions[-1]
        travel = [round(b - a, 6) for a, b in zip(first, last)]
        slot["travel"] = travel
        slot["moved"] = any(abs(v) > 1e-6 for v in travel)
    return trend


def _field_trend(frames: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """필드별 최대값이 프레임에 따라 어떻게 변했는지.

    스모크·파이로 컨테이너는 복셀 수가 고정이라 `element_trend` 로는 소스가
    먹고 있는지 알 수 없다. 대신 density max 가 0 에서 올라가는지를 본다.
    벡터 필드는 성분 중 가장 큰 값을 쓴다.
    """
    trend: dict[str, list[float]] = {}
    for record in frames:
        for entry in record["objects"]:
            for field, stats in entry.get("fields", {}).items():
                parts = stats.get("components", [stats])
                values = [p["max"] for p in parts if isinstance(p.get("max"), float)]
                if not values:
                    continue
                trend.setdefault(f"{entry['name']}.{field}", []).append(max(values))

    out: dict[str, dict[str, Any]] = {}
    for key, series in trend.items():
        # 전부 0 인 필드는 아직 쓰이지 않는 것이라 목록만 어지럽힌다.
        if not any(series):
            continue
        out[key] = {
            "start": series[0],
            "end": series[-1],
            "max": max(series),
            "series": [round(v, 6) for v in series],
        }
    return out
