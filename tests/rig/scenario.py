"""houdini_mcp_rig 회귀 시나리오. hython 안에서 돈다.

시스템 python 에서 직접 import 할 수 없으므로(`hou` 가 없다) 테스트는 이 파일을
hython 서브프로세스로 띄우고, 마지막에 찍는 JSON 한 줄을 읽어 검사한다.
tests/sop 이 쓰는 방식과 같다.

여기서 확인하는 것은 "노드를 만들었다"가 아니라 **쿡한 결과가 기대한 값인가**,
그리고 **일부러 망가뜨린 리그를 validate_rig 가 실제로 잡는가**다. 잡지 못하는
검증 툴은 없느니만 못하다.

**등록된 툴을 하나도 빠짐없이 호출한다.** 호출되지 않은 툴은 `uncalled` 로
보고되고 테스트가 실패한다.
"""

from __future__ import annotations

import json
import sys
import traceback

MARKER = "RIGTEST_JSON:"
"""이 접두사가 붙은 줄 하나만 테스트가 읽는다. Houdini 자체 출력과 섞이기 때문."""

# 스킨 웨이트를 일부러 망가뜨리는 파이썬 SOP 코드. boneCapture 는
# [조인트, 웨이트, 조인트, 웨이트, ...] 로 끼워 넣어져 있으므로 홀수 자리만 건드린다.
BREAK_WEIGHTS = '''\
import hou

geo = hou.pwd().geometry()
attrib = geo.findPointAttrib("boneCapture")
size = attrib.size()
values = list(geo.pointFloatAttribValues("boneCapture"))

# 앞쪽 20개 점은 웨이트를 반으로 줄인다 -> 합이 1이 아니게 된다.
for point in range(20):
    for slot in range(1, size, 2):
        values[point * size + slot] *= 0.5

# 그다음 10개 점은 어디에도 붙지 않게 만든다 -> 웨이트 합이 0이 된다.
for point in range(20, 30):
    for slot in range(size):
        values[point * size + slot] = -1.0 if slot % 2 == 0 else 0.0

geo.setPointFloatAttribValues("boneCapture", values)
'''


def main() -> int:
    import hou

    from houdini_mcp import get_registry
    from houdini_mcp.pack import register_pack

    registered = set(register_pack("houdini_mcp_rig"))
    call = {spec.name: spec.fn for spec in get_registry().all()}

    called: set[str] = set()
    errors: dict[str, str] = {}

    def run(tool_name: str, **kwargs):
        """툴 하나를 부르고 호출 여부를 기록한다."""
        try:
            result = call[tool_name](**kwargs)
        except Exception as exc:  # 어느 툴이 왜 깨졌는지 테스트가 알아야 한다.
            errors[tool_name] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            return None
        called.add(tool_name)
        return result

    out: dict[str, object] = {"registered": sorted(registered)}
    parent = hou.node("/obj").createNode("geo", node_name="regression").path()

    # --- 스켈레톤 ---------------------------------------------------------
    skeleton = run(
        "create_skeleton",
        parent=parent,
        comment="Three joint test skeleton for regression",
        name="test_spine",
        joints=[
            {"name": "hips", "position": [0, 0, 0]},
            {"name": "spine", "position": [0, 1, 0], "parent": "hips"},
            {"name": "chest", "position": [0, 2, 0], "parent": "spine"},
        ],
    )
    out["skeleton"] = skeleton
    skeleton_path = skeleton["path"]

    info = run("skeleton_info", path=skeleton_path)
    out["skeleton_info"] = {
        "joints": info["joints"],
        "bones": info["bones"],
        "roots": info["roots"],
        "leaves": info["leaves"],
        "max_depth": info["max_depth"],
        "hierarchy_source": info["hierarchy_source"],
        "has_transform": info["has_transform"],
        "bone_length": info["bone_length"],
    }

    joints = run("list_joints", path=skeleton_path)
    out["list_joints"] = {
        "total": joints["total"],
        "joints": joints["joints"],
    }

    spine = run("joint_info", path=skeleton_path, joint="spine")
    out["joint_info"] = {
        "parent": spine["parent"],
        "children": spine["children"],
        "chain_to_root": spine["chain_to_root"],
        "descendants": spine["descendants"],
        "bone_length": spine["bone_length"],
        "determinant": spine.get("determinant"),
    }

    attribs = run("joint_attributes", path=skeleton_path)
    out["joint_attributes"] = {
        "names": [a["name"] for a in attribs["point_attribs"]],
        "sampled": attribs["sampled"],
    }

    # --- 스킨 -------------------------------------------------------------
    network = hou.node(parent)
    tube = network.createNode("tube", node_name="body_mesh")
    tube.parm("type").set(1)  # polygon
    tube.parm("rows").set(20)
    tube.parm("cols").set(12)
    tube.parm("height").set(2.0)
    tube.parmTuple("t").set((0, 1, 0))
    tube.parm("rad1").set(0.3)
    tube.parm("rad2").set(0.3)

    captured = run(
        "capture_skin",
        mesh=tube.path(),
        skeleton=skeleton_path,
        comment="Capture body mesh to spine joints",
        name="capture_body",
        max_influences=2,
    )
    out["capture_skin"] = {
        "captured_joints": captured["captured_joints"],
        "max_influences": captured["max_influences"],
        "mesh_points": captured["mesh_points"],
        "weights": captured["weights"],
        "unused_joints": captured["unused_joints"],
    }
    capture_path = captured["path"]

    stats = run("weight_stats", path=capture_path)
    out["weight_stats"] = {
        "points": stats["points"],
        "joints": stats["joints"],
        "weights": stats["weights"],
        "top_joints": stats["top_joints"],
    }

    unweighted = run("find_unweighted_points", path=capture_path)
    out["find_unweighted_points"] = {
        "unweighted": unweighted["unweighted"]["count"],
        "sum_off_one": unweighted["sum_off_one"]["count"],
    }

    influence = run("joint_influence", path=capture_path, joint="spine")
    out["joint_influence"] = {
        "points": influence["points"],
        "weight": influence["weight"],
        "bbox": influence["influence_bbox"],
    }

    # --- 포즈와 디폼 ------------------------------------------------------
    posed = run(
        "pose_joints",
        path=skeleton_path,
        comment="Bend spine 45 degrees around Z",
        name="bend",
        poses=[{"joint": "spine", "rotate": [0, 0, 45]}],
    )
    out["pose_joints"] = {
        "applied": posed["applied"],
        "moved_joints": posed["moved_joints"],
        "max_joint_move": posed["max_joint_move"],
        "joints_moved_most": posed["joints_moved_most"],
    }
    posed_path = posed["path"]

    diff = run("compare_poses", path=posed_path, reference=skeleton_path)
    out["compare_poses"] = {
        "shared_joints": diff["shared_joints"],
        "moved_joints": diff["moved_joints"],
        "max_distance": diff["max_distance"],
        "max_rotation_degrees": diff["max_rotation_degrees"],
    }

    deformed = run(
        "deform_skin",
        rest=capture_path,
        capture_pose=skeleton_path,
        animated_pose=posed_path,
        comment="Deform body to bent spine pose",
        name="deform_body",
    )
    out["deform_skin"] = {
        "points": deformed["points"],
        "moved_points": deformed["moved_points"],
        "movement": deformed["movement"],
        "bbox_before": deformed["bbox_before"],
        "bbox_after": deformed["bbox_after"],
    }

    # --- APEX -------------------------------------------------------------
    rig = run(
        "build_fk_rig",
        skeleton=skeleton_path,
        comment="FK rig graph for test spine",
        name="fk_rig",
    )
    out["build_fk_rig"] = rig and {
        "graph_nodes": rig["graph_nodes"],
        "callbacks": rig["callbacks"],
        "stat": rig["stat"],
        "errors": rig["errors"],
    }

    if rig:
        graph_path = rig["path"]
        graph = run("apex_graph_info", path=graph_path)
        out["apex_graph_info"] = {
            "nodes": graph["nodes"],
            "callbacks": graph["callbacks"],
            "errors": graph["errors"],
        }

        nodes = run("apex_graph_nodes", path=graph_path, pattern="*")
        out["apex_graph_nodes"] = {
            "matched": nodes["matched"],
            "names": [n["name"] for n in nodes["nodes"]],
            "first_parms": nodes["nodes"][0]["parms"] if nodes["nodes"] else None,
        }

        script = run("apex_rig_script", path=graph_path)
        out["apex_rig_script"] = {
            "characters": script["characters"],
            "truncated": script["truncated"],
            "script": script["script"][:1200],
        }

    callbacks = run("apex_callbacks", pattern="*ik*", limit=30)
    out["apex_callbacks"] = {
        "total_registered": callbacks["total_registered"],
        "subgraphs": callbacks["subgraphs"],
        "matched": callbacks["matched"],
        "names": [c["name"] for c in callbacks["callbacks"]],
    }

    callback = run("apex_callback_info", name="fbik::SolveFABRIK")
    out["apex_callback_info"] = {
        "inputs": callback["inputs"],
        "outputs": callback["outputs"],
    }

    # --- 검증: 멀쩡한 리그 ------------------------------------------------
    good = run("validate_rig", skeleton=skeleton_path, skin=capture_path)
    out["validate_good"] = {
        "ok": good["ok"],
        "counts": good["counts"],
        "checks": [i["check"] for i in good["issues"]],
        "issues": good["issues"],
    }

    # --- 검증: 일부러 계층을 끊는다 ---------------------------------------
    detached = run(
        "create_skeleton",
        parent=parent,
        comment="Deliberately broken skeleton, chest detached from spine",
        name="broken_hierarchy",
        joints=[
            {"name": "hips", "position": [0, 0, 0]},
            {"name": "spine", "position": [0, 1, 0], "parent": "hips"},
            {"name": "chest", "position": [0, 2, 0]},
            {"name": "neck", "position": [0, 2, 0], "parent": "chest"},
        ],
    )
    broken_hierarchy = run("validate_rig", skeleton=detached["path"])
    out["validate_broken_hierarchy"] = {
        "ok": broken_hierarchy["ok"],
        "checks": [i["check"] for i in broken_hierarchy["issues"]],
        "issues": broken_hierarchy["issues"],
    }

    # --- 검증: transform 이 없는 날 스켈레톤 ------------------------------
    raw = run("validate_rig", skeleton=skeleton["definition_path"])
    out["validate_raw"] = raw and {
        "ok": raw["ok"],
        "checks": [i["check"] for i in raw["issues"]],
        "hierarchy_source": raw["skeleton"]["hierarchy_source"],
    }

    # --- 검증: 일부러 웨이트를 망가뜨린다 ---------------------------------
    breaker = network.createNode("python", node_name="break_weights")
    breaker.setFirstInput(hou.node(capture_path))
    breaker.parm("python").set(BREAK_WEIGHTS)
    breaker.setComment("Deliberately broken weights for validate_rig regression")

    broken_weights = run(
        "validate_rig", skeleton=skeleton_path, skin=breaker.path(), max_influences=1
    )
    out["validate_broken_weights"] = {
        "ok": broken_weights["ok"],
        "checks": [i["check"] for i in broken_weights["issues"]],
        "issues": broken_weights["issues"],
    }
    broken_stats = call["weight_stats"](path=breaker.path())
    out["broken_weight_stats"] = broken_stats["weights"]

    # --- 검증: 바인드 포즈가 어긋난 스켈레톤 ------------------------------
    drifted = run("validate_rig", skeleton=posed_path, skin=capture_path)
    out["validate_bind_drift"] = {
        "ok": drifted["ok"],
        "checks": [i["check"] for i in drifted["issues"]],
    }

    # --- 실패 메시지가 다음에 무엇을 할지 알려 주는지 ----------------------
    try:
        call["joint_info"](path=skeleton_path, joint="elbow")
        out["missing_joint_message"] = ""
    except Exception as exc:
        out["missing_joint_message"] = str(exc)

    try:
        call["weight_stats"](path=skeleton_path)
        out["no_capture_message"] = ""
    except Exception as exc:
        out["no_capture_message"] = str(exc)

    try:
        call["apex_graph_info"](path=skeleton_path)
        out["not_a_graph_message"] = ""
    except Exception as exc:
        out["not_a_graph_message"] = str(exc)

    out["called"] = sorted(called)
    out["uncalled"] = sorted(registered - called)
    out["errors"] = errors
    print(MARKER + json.dumps(out, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
