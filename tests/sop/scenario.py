"""houdini_mcp_sop 회귀 시나리오. hython 안에서 돈다.

시스템 python 에서 직접 import 할 수 없으므로(`hou` 가 없다) 테스트는 이 파일을
hython 서브프로세스로 띄우고, 마지막에 찍는 JSON 한 줄을 읽어 검사한다.
tests/package_order 가 쓰는 방식과 같다.

여기서 확인하는 것은 "노드를 만들었다"가 아니라 **쿡한 결과가 기대한 값인가**다.
Houdini 버전이 올라가면서 노드 타입이나 파라미터 이름이 바뀌면 여기서 깨진다.

**등록된 툴을 하나도 빠짐없이 호출한다.** 호출되지 않은 툴은 `uncalled` 로
보고되고 테스트가 실패한다. 툴을 추가하고 시나리오에 넣는 것을 잊으면, 그 툴은
미검증인 채로 조용히 배포된다 — 그것을 막으려는 것이다.
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

MARKER = "SOPTEST_JSON:"
"""이 접두사가 붙은 줄 하나만 테스트가 읽는다. Houdini 자체 출력과 섞이기 때문."""


def main() -> int:
    import hou

    from houdini_mcp import get_registry
    from houdini_mcp.pack import register_pack

    registered = set(register_pack("houdini_mcp_sop"))
    call = {spec.name: spec.fn for spec in get_registry().all()}

    called: set[str] = set()
    errors: dict[str, str] = {}

    def run(tool_name: str, **kwargs):
        """툴 하나를 부르고 호출 여부를 기록한다.

        툴들이 스스로 `name` 인자를 쓰므로 여기 파라미터는 tool_name 이어야 한다.
        """
        try:
            result = call[tool_name](**kwargs)
        except Exception as exc:  # 어느 툴이 왜 깨졌는지 테스트가 알아야 한다.
            errors[tool_name] = f"{type(exc).__name__}: {exc}"
            return None
        called.add(tool_name)
        return result

    out: dict[str, object] = {"registered": sorted(registered)}
    parent = hou.node("/obj").createNode("geo", node_name="regression").path()
    tmp = Path(tempfile.mkdtemp())

    # --- 생성 -------------------------------------------------------------
    box = run("create_primitive", parent=parent, shape="box",
              comment="Wall body for regression", name="wall_body",
              size=[2, 2, 2], center=[0, 1, 0])
    sphere = run("create_primitive", parent=parent, shape="sphere",
                 comment="Window cutter", name="window_cutter",
                 prim_type="poly", size=[0.6, 0.6, 0.6], center=[0, 1, 0])
    grid = run("create_primitive", parent=parent, shape="grid",
               comment="Ground plane", name="ground", size=[6, 6], divisions=[4, 4])
    curve = run("create_curve", parent=parent, points=[[0, 0, 0], [0.5, 1, 0], [0, 2, 0]],
                comment="Tower roof profile", name="tower_profile")
    out["box"] = box["result"]
    out["curve"] = curve["result"]

    # --- 폴리곤 편집 ------------------------------------------------------
    bevel = run("bevel", path=box["path"], comment="Soften wall edges",
                offset=0.1, name="bevel_wall_edges")
    out["bevel"] = {"before": bevel["before"], "after": bevel["after"],
                    "type": bevel["type"]}

    run("extrude_faces", path=bevel["path"], comment="Raise merlons",
        distance=0.3, inset=0.05, name="extrude_merlons")
    run("bridge_edges", path=grid["path"], comment="Bridge grid boundary",
        source_group="0", destination_group="1", name="bridge_grid")
    run("mirror_geometry", path=box["path"], comment="Mirror wall east",
        direction=[1, 0, 0], name="mirror_wall")
    revolve = run("revolve_profile", path=curve["path"], comment="Revolve tower roof",
                  divisions=12, name="tower_roof")
    out["revolve"] = revolve["after"]

    # Skin 은 단면이 2개 이상이어야 한다. 커브 둘을 merge 해서 준다.
    section_a = run("create_curve", parent=parent, points=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
                    comment="Roof section A", name="roof_section_a")
    section_b = run("create_curve", parent=parent, points=[[0, 1, 1], [1, 1, 1], [2, 1, 1]],
                    comment="Roof section B", name="roof_section_b")
    merged = hou.node(parent).createNode("merge", node_name="roof_sections")
    merged.setInput(0, hou.node(section_a["path"]))
    merged.setInput(1, hou.node(section_b["path"]))
    run("skin_sections", path=merged.path(), comment="Skin roof sections",
        name="skin_roof")

    boolean = run("boolean_op", path_a=bevel["path"], path_b=sphere["path"],
                  comment="Cut window opening", operation="subtract",
                  name="cut_window")
    out["boolean_open_edges"] = {key: value["open_edges"]
                                 for key, value in boolean["inputs"].items()}

    # --- 토폴로지 ---------------------------------------------------------
    run("convert_geometry", path=box["path"], comment="Convert wall to NURBS",
        to_type="nurbSurf", name="convert_wall")
    triangulate = run("triangulate", path=box["path"], comment="Triangulate wall",
                      name="tri_wall")
    out["triangulate"] = triangulate["after"]["prims"]

    run("remesh_geometry", path=sphere["path"], comment="Even triangles",
        target_size=0.2, name="remesh_sphere")
    run("reduce_polygons", path=sphere["path"], comment="Sphere LOD1",
        target=50, mode="poly_percent", name="reduce_sphere")
    run("transform_geometry", path=box["path"], comment="Place wall north",
        translate=[0, 0, -5], name="place_wall_north")
    run("delete_geometry", path=box["path"], comment="Drop bottom face",
        group="0", group_type="prims", name="drop_bottom")

    # --- 어트리뷰트 -------------------------------------------------------
    stats = run("attrib_stats", path=bevel["path"], name="P")
    out["stats"] = {"count": stats["count"], "size": stats["size"],
                    "components": stats["components"]}

    normals = run("add_normals", path=bevel["path"], comment="Point normals for placement",
                  name="wall_normals")
    scaled = run("create_attribute", path=normals["path"], comment="Uniform copy scale",
                 attrib_name="pscale", owner="point", attrib_type="float",
                 value=0.25, name="set_pscale")
    exported = run("export_attribute", path=bevel["path"], name="P",
                   file_path=str(tmp / "P"))
    out["export_attribute"] = {"shape": exported["shape"], "dtype": exported["dtype"]}

    # --- 그룹 -------------------------------------------------------------
    group = run("create_group", path=bevel["path"], comment="Top faces of wall",
                group_name="wall_top_faces", group_type="prim",
                normal_direction=[0, 1, 0], normal_angle=30, name="group_wall_top")
    out["group"] = group["group"]
    members = run("group_members", path=group["path"], group_name="wall_top_faces",
                  group_type="prim")
    out["group_members"] = members["count"]

    # --- 복사 -------------------------------------------------------------
    copied = run("copy_to_points", source=sphere["path"], target=scaled["path"],
                 comment="Scatter cutters on wall points", name="copy_cutters")
    out["copy_to_points"] = {"inputs": copied["inputs"], "after": copied["after"]}

    # --- UV ---------------------------------------------------------------
    projected = run("uv_project", path=bevel["path"], comment="Project wall UVs",
                    name="uv_wall")
    out["uv"] = projected["uv"]
    run("uv_report", path=projected["path"])
    run("auto_uv", path=sphere["path"], comment="Auto UV sphere", method="flatten",
        name="uv_sphere")

    # --- 질의 -------------------------------------------------------------
    nearest = run("nearest_point", path=bevel["path"], position=[0, 3, 0], count=3)
    out["nearest"] = {"found": nearest["found"],
                      "first_distance": nearest["points"][0]["distance"]}
    run("nearest_prim", path=bevel["path"], position=[0, 3, 0])
    run("ray_intersect", path=bevel["path"], origin=[0, 10, 0], direction=[0, -1, 0])
    run("prim_intrinsics", path=bevel["path"], names=["measuredarea", "typename"])

    vdb = hou.node(parent).createNode("vdbfrompolygons", node_name="sphere_vdb")
    vdb.setFirstInput(hou.node(sphere["path"]))
    volume = run("volume_info", path=vdb.path())
    out["volume"] = {"count": volume["count"],
                     "is_sdf": volume["volumes"][0]["is_sdf"]}


    # --- 실패 메시지가 다음에 무엇을 할지 알려 주는지 ----------------------
    try:
        call["bevel"](path=box["path"], comment="bad group", group="0-11",
                      name="bevel_bad")
        out["edge_group_message"] = ""
    except Exception as exc:
        out["edge_group_message"] = str(exc)

    out["called"] = sorted(called)
    out["uncalled"] = sorted(registered - called)
    out["errors"] = errors
    print(MARKER + json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
