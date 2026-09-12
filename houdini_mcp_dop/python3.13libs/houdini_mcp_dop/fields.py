"""볼륨 필드를 통계로 읽는 툴.

파이로·FLIP 의 필드는 복셀이 수백만 개다. 모델에게 그대로 보내면 컨텍스트만
태우므로 여기서는 **통계만** 돌려준다.

두 층으로 나눠 둔다.

- `list_dop_fields` 와 `field_stats(deep=False)` 는 `hou.Volume.volumeMin/Max/
  Average` 만 쓴다. C++ 쪽에서 한 번에 세므로 복셀 수와 무관하게 싸다.
- `field_stats(deep=True)` 는 `allVoxelsAsString` 으로 바이트를 받아
  `numpy.frombuffer` 로 꽂고 히스토그램과 NaN 개수까지 낸다. 필드가 크면 비싸다.

실측해 보니 NaN 이 섞인 필드는 `volumeAverage()` 가 NaN 을, Inf 가 섞이면
`volumeMax()` 가 Inf 를 돌려준다. 그래서 싼 층만으로도 발산을 잡을 수 있다.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from ._common import (
    require_dopnet,
    require_sim_object,
)
from ._state import (
    cheap_stats,
    deep_stats,
    field_names,
    field_volumes,
    is_field,
    memory_of,
    record_dict,
)

# 벡터 필드의 성분 이름. MAC 스태거라 성분마다 해상도가 하나씩 다르다.
_COMPONENTS = ("x", "y", "z")


@tool()
def list_dop_fields(dopnet: str, name: str, include_temp: bool = False) -> dict[str, Any]:
    """시뮬 오브젝트가 가진 볼륨 필드 목록 — 종류, 해상도, 복셀 수, 메모리.

    값 통계는 내지 않는다. 어떤 필드가 있고 얼마나 큰지만 먼저 보고,
    들여다볼 것을 `field_stats` 로 고르라는 뜻이다.

    Args:
        dopnet: DOP 네트워크 경로.
        name: 오브젝트 이름. 예: smoke_container
        include_temp: 솔버 내부 임시 필드(__tempfield_*)도 포함할지.
    """
    net = require_dopnet(dopnet)
    obj = require_sim_object(net, name)

    fields = []
    total_voxels = 0
    total_memory = 0
    for field in field_names(obj, include_temp=include_temp):
        data = obj.findSubData(field)
        entry: dict[str, Any] = {
            "name": field,
            "data_type": data.dataType(),
            "memory_bytes": memory_of(data),
        }
        total_memory += entry["memory_bytes"]
        options = record_dict(data.options())
        for key in ("div", "divsize", "size", "t", "totalvoxels", "border"):
            if key in options:
                entry[key] = options[key]
        try:
            volumes = field_volumes(obj, field)
        except (ValueError, hou.Error):
            volumes = []
        if volumes:
            entry["components"] = len(volumes)
            entry["resolutions"] = [[int(v) for v in vol.resolution()] for vol in volumes]
            voxels = sum(
                int(r[0]) * int(r[1]) * int(r[2]) for r in entry["resolutions"]
            )
            entry["voxels"] = voxels
            total_voxels += voxels
            entry["voxel_size"] = [float(v) for v in volumes[0].voxelSize()]
        fields.append(entry)

    result: dict[str, Any] = {
        "dopnet": net.path(),
        "object": name,
        "frame": hou.frame(),
        "count": len(fields),
        "total_voxels": total_voxels,
        "total_memory_bytes": total_memory,
        "fields": fields,
    }
    if not fields:
        result["hint"] = (
            f"{name} 은 볼륨 필드를 갖고 있지 않습니다. 강체·천처럼 지오메트리로 "
            f"푸는 오브젝트라면 dop_object_info 로 서브데이터를 보세요."
        )
    else:
        result["next_steps"] = [
            f"field_stats('{net.path()}', '{name}', '{fields[0]['name']}') 로 값을 봅니다"
        ]
    return result


@tool()
def field_stats(
    dopnet: str,
    name: str,
    field: str,
    deep: bool = False,
    bins: int = 16,
) -> dict[str, Any]:
    """필드 하나의 값 통계. 복셀을 통째로 넘기지 않는다.

    기본(`deep=False`)은 min / max / mean 과 해상도만 낸다. 복셀 수와 무관하게
    싸므로 매 프레임 불러도 된다.

    `deep=True` 면 복셀을 numpy 로 받아 표준편차, 분위수, 히스토그램,
    NaN·Inf 복셀 개수, 0 이 아닌 복셀 개수까지 낸다. 필드가 크면 느리다.

    벡터 필드(vel 등)는 성분 3개가 각각 해상도가 다른 MAC 스태거 격자다.
    성분별로 따로 통계를 낸다.

    Args:
        dopnet: DOP 네트워크 경로.
        name: 오브젝트 이름. 예: smoke_container
        field: 필드 이름. 예: density, temperature, vel, pressure
        deep: 복셀을 다 읽어 히스토그램과 NaN 개수까지 낼지.
        bins: deep=True 일 때 히스토그램 구간 수.
    """
    net = require_dopnet(dopnet)
    obj = require_sim_object(net, name)
    volumes = field_volumes(obj, field)
    if not volumes:
        raise ValueError(
            f"{name}.{field} 에 볼륨 프림이 없습니다. "
            f"list_dop_fields 로 이 필드가 어떤 종류인지 확인하세요."
        )

    data = obj.findSubData(field)
    components = []
    for index, volume in enumerate(volumes):
        stats = deep_stats(volume, bins) if deep else cheap_stats(volume)
        if len(volumes) > 1:
            stats["component"] = _COMPONENTS[index] if index < 3 else str(index)
        components.append(stats)

    finite = all(part.get("finite", True) for part in components)
    result: dict[str, Any] = {
        "dopnet": net.path(),
        "object": name,
        "field": field,
        "frame": hou.frame(),
        "data_type": data.dataType(),
        "memory_bytes": memory_of(data),
        "deep": deep,
        "finite": finite,
        "components": components if len(components) > 1 else None,
    }
    if len(components) == 1:
        result.update(components[0])
        del result["components"]
    if not finite:
        result["warning"] = (
            f"{name}.{field} 의 값이 유한하지 않습니다(NaN 또는 무한대). "
            f"시뮬이 발산했습니다. 서브스텝을 올리거나, 소스 세기를 줄이거나, "
            f"CFL 조건을 만족하도록 타임스텝을 줄이세요."
        )
    return result


@tool()
def field_data_types(dopnet: str, name: str) -> dict[str, Any]:
    """오브젝트의 서브데이터를 종류별로 갈라 준다 — 필드, 솔버, 힘, 그 밖.

    `dop_object_info` 가 서브데이터를 평평하게 내놓는 데 비해, 여기서는
    "무엇이 필드이고 무엇이 솔버 설정인지"를 갈라 준다. 파이로 오브젝트는
    서브데이터가 30개 가까이 되므로 평평한 목록으로는 읽기 어렵다.

    Args:
        dopnet: DOP 네트워크 경로.
        name: 오브젝트 이름.
    """
    net = require_dopnet(dopnet)
    obj = require_sim_object(net, name)

    buckets: dict[str, list[dict[str, Any]]] = {
        "fields": [],
        "temp_fields": [],
        "containers": [],
        "other": [],
    }
    for key, data in sorted(obj.subData().items()):
        entry = {"name": key, "data_type": data.dataType(), "memory_bytes": memory_of(data)}
        if is_field(data):
            bucket = "temp_fields" if key.startswith("__tempfield") else "fields"
        elif "Container" in data.dataType() or "Solver" in data.dataType():
            bucket = "containers"
        else:
            bucket = "other"
        buckets[bucket].append(entry)

    return {
        "dopnet": net.path(),
        "object": name,
        "frame": hou.frame(),
        "counts": {key: len(value) for key, value in buckets.items()},
        "memory_bytes": {
            key: sum(e["memory_bytes"] for e in value) for key, value in buckets.items()
        },
        **buckets,
    }
