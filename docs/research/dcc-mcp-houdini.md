# dcc-mcp/dcc-mcp-houdini 조사 보고서

- **저장소**: https://github.com/dcc-mcp/dcc-mcp-houdini
- **조사 시점 커밋**: `154c0373e0adc03f23619e0eda8e26e1cac61570` (2026-09-07, `main`)
- **조사일**: 2026-09-09
- **조사 방법**: `git clone --depth 1`로 로컬 클론 후 소스 직접 열람 (WebFetch 미사용)
- **중요**: `https://github.com/loonghao/dcc-mcp-houdini`도 함께 클론해 비교한 결과, **동일한 커밋 해시(`154c0373...`)를 가진 완전히 동일한 저장소**임을 확인했다(`dcc-mcp-core`와 마찬가지로 `loonghao`가 만든 프로젝트가 `dcc-mcp` GitHub 조직으로 이전/미러링된 것으로 보인다). 이하 내용은 두 URL 모두에 동일하게 적용된다.

이 저장소는 다른 두 저장소(`oculairmedia/houdini-mcp`, `capoomgit/houdini-mcp`)와 근본적으로 다른 성격이다. 자체적으로 MCP 서버/툴 디스패치 로직을 구현하지 않고, **별도 패키지 `dcc-mcp-core`(멀티-DCC 공통 MCP 프레임워크)의 "Houdini 어댑터"**로 동작한다. `dcc_mcp_houdini`는 (1) Houdini 전용 스킬/툴 정의(YAML + Python 스크립트), (2) Houdini 이벤트 루프와 `dcc-mcp-core`의 큐/디스패처를 연결하는 호스트 어댑터(`host.py`), (3) `dcc-mcp-core`가 `importlib.metadata` entry point로 찾아내는 어댑터 클래스(`HoudiniMcpServer`)만 제공한다.

## 1. 툴 전수 목록

툴은 `houdini_mcp_server.py`류의 단일 파일에 `@mcp.tool()`로 하드코딩되어 있지 않고, `src/dcc_mcp_houdini/skills/<skill-name>/tools.yaml`에 **선언적으로(YAML)** 정의되고 `scripts/<file>.py`의 함수가 실제 구현을 담당한다(스킬당 `SKILL.md` 설명 문서 동반). 총 **38개 스킬**에 걸쳐 **259개 툴**이 존재한다 (`find src/dcc_mcp_houdini/skills -name tools.yaml | wc -l` = 38, 전체 `- name:` 엔트리 수 = 259).

스킬은 5단계 프로그레시브 로딩 스테이지로 묶여 있다(`src/dcc_mcp_houdini/skills/SKILLS_INDEX.md`, `_skill_loader.py`):

| 스테이지 | 포함 스킬 | 기본 로드 여부 |
|---|---|---|
| `bootstrap` | `houdini-scripting` | 예 |
| `scene` | `houdini-scene`, `houdini-scene-edit` | `houdini-scene`만 |
| `authoring` | `houdini-nodes`, `houdini-object-ops`, `houdini-parameters`, `houdini-node-graph`, `houdini-geometry`, `houdini-mesh-ops`, `houdini-vex`, `houdini-camera-light`, `houdini-materials`, `houdini-lookdev`, `houdini-material-library`, `houdini-hda`, `houdini-light-rig`, `houdini-copernicus`, `houdini-groom` | 아니오 |
| `interchange` | `houdini-interchange`, `houdini-asset-sync`, `houdini-export-preset`, `houdini-import-to-scene`, `houdini-usd-lops` | 아니오 |
| `pipeline` | `houdini-render`, `houdini-karma`, `houdini-husk`, `houdini-animation`, `houdini-chops`, `houdini-constraints`, `houdini-kinefx`, `houdini-hda-automation`, `houdini-pipeline`, `houdini-dev`, `houdini-automation`, `houdini-texture-bake`, `houdini-gsplat-relighting`, `houdini-simulation`, `houdini-pdg` | 아니오 |

"미니멀 모드"에서는 `houdini-scripting` + `houdini-scene`만 기동 시 로드되고, 나머지는 에이전트가 `load_skill("<skill-name>")`을 호출해 그때그때 로드하는 **온디맨드 방식**이다(대형 툴 서페이스를 컨텍스트에 한 번에 노출하지 않기 위한 설계).

아래는 `tools.yaml`을 파싱해 스킬별로 추출한 전수 목록이다. 표의 `파라미터` 열은 `input_schema.properties`의 키:타입이며 `*`는 `required` 표시, `affinity/execution` 열은 각 툴의 `affinity`(`main`/`any`) 및 `execution`(`sync`/`async`) 태그다(2.c절 참고).

### houdini-animation (12개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `get_timeline` | (none) | Read current frame, frame/playback range, and FPS (canonical timeline query). | main/sync |
| `set_timeline` | current_frame:number, frame_range:array, playback_range:array, fps:number | Set current frame, frame range, playback range, and FPS | main/sync |
| `set_keyframe` | node_path*:string, parm_name*:string, frame*:number, value:number, expression:string, language:string, interpolation:string | Set a value or expression keyframe on a node parameter at a frame. | main/sync |
| `get_keyframes` | node_path*:string, parm_name*:string | List keyframes on a node parameter (frame, value, expression). | main/sync |
| `delete_keyframes` | node_path*:string, parm_name*:string, frame_range:array | Delete all keyframes on a parameter, or only those in a frame range. | main/sync |
| `list_animated_parms` | node_path*:string | List parameters on a node that are keyframed or time-dependent. | main/sync |
| `validate_loop_contract` | node_paths*:array, start_frame*:number, end_frame*:number, sample_step:number, tolerances:object, max_expression_chars:integer | Bounded, read-only OBJ animation-loop validation for a playback range of unique samples | main/sync |
| `get_channel_info` | node_path*:string, parm_name*:string | Inspect a parameter channel: expression, language, keyframe count, time dependence, current value. | main/sync |
| `export_channels` | node_path*:string, parm_names*:array, output_path*:string | Export keyframe data for parameters to a JSON file. | main/sync |
| `import_channels` | input_path*:string, node_path:string | Apply a JSON channel dump (from export_channels) onto a node. | main/sync |
| `bake_channels` | node_path*:string, parm_names*:array, frame_range*:array, step:number | Sample evaluated parameter values per frame and write constant keyframes (bounded by a hard frame cap) | main/async |
| `cache_simulation` | rop_path*:string, frame_range:array, background:boolean | Bake a simulation/cache by rendering a ROP (filecache/dop/geometry) over a frame range | main/sync |

### houdini-asset-sync (3개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `publish_usd_revision` | channel_id*:string, asset_id*:string, source_name*:string, expected_head_revision*:integer, source_instance_id:string, metadata:object | Publish a USD file beneath the operator-owned source root as an immutable Asset Sync revision. | any/async |
| `read_asset_head` | channel_id*:string, asset_id*:string | Read the current path-free Asset Sync head manifest. | any/sync |
| `reference_usd_revision` | channel_id*:string, asset_id*:string, stage_path:string, node_name:string, primitive_path:string, subfolder:string | Materialize the current verified USD revision and create a non-flattening Solaris Reference LOP. | main/async |

### houdini-automation (5개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `run_python_file` | file_path*:string, args:array, context:object, working_directory:string, output_mode:string, max_stdout_chars:integer, max_stderr_chars:integer, max_result_chars:integer, spill_overflow_to_artifact:boolean | Execute an existing Python file inside Houdini with `hou`, `args`, and `context` pre-bound | main/sync |
| `set_frame_range` | start_frame*:number, end_frame*:number, current_frame:number | Set Houdini timeline frame range and optional current frame. | main/sync |
| `save_hip_file` | file_path:string | Save the current Houdini hip file, optionally to a new path, through a sibling temporary file and atomic target replacement | main/sync |
| `load_hip_file` | file_path*:string, suppress_save_prompt:boolean | Load a Houdini hip file into the current session | main/sync |
| `build_node_chain` | parent_path*:string, nodes*:array, connections:array, layout:boolean, cook_last:boolean, dry_run:boolean | Prevalidate and atomically build a small Houdini node chain from structured node specs and connections | main/sync |

### houdini-camera-light (7개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `list_cameras` | parent_path:string | List camera nodes under a network with resolution and focal length. | main/sync |
| `create_camera` | parent_path:string, name:string, translate:array, rotate:array, resolution:array, focal:number | Create a camera node with optional transform, resolution, and focal. | main/sync |
| `update_camera` | camera_path*:string, translate:array, rotate:array, resolution:array, focal:number | Update an existing camera's transform, resolution, and focal length. | main/sync |
| `frame_view` | node_path:string, camera_path:string, max_primitive_count:integer, allow_heavy_geometry:boolean | Frame a node and/or activate a camera in the Scene Viewer, applying the camera last and reporting active_camera | main/sync |
| `get_view_state` | (none) | Report the active Scene Viewer camera and viewport (read-only, UI-aware). | main/sync |
| `create_light` | parent_path:string, light_type:string, name:string, intensity:number, color:array, exposure:number, translate:array, rotate:array | Create an hlight node (point/distant/sphere/environment/...) with typed intensity, color, exposure, and transform. | main/sync |
| `update_light` | light_path*:string, intensity:number, color:array, exposure:number, light_type:string, translate:array, rotate:array | Update an existing hlight's intensity/color/exposure/type/transform. | main/sync |

### houdini-chops (6개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_chop_network` | parent_path*:string, network_name:string | Create a CHOP network container at a given parent path. | main/sync |
| `create_motionclip` | network_path*:string, node_name:string, clip_file:string, start_frame:number | Import or create a motion clip CHOP in a CHOP network. | main/sync |
| `create_audio_driven` | network_path*:string, audio_file*:string, target_parm*:string, channel_name:string, envelope_name:string, amplitude_multiplier:number | Set up audio-driven animation using an Envelope CHOP driven by an audio file. | main/sync |
| `apply_filter` | network_path*:string, source_node*:string, filter_type*:string, amount:number, node_name:string, extra_params:object | Apply a CHOP filter (lag, spring, noise, smooth, peak, bandpass, comp, limit) to a source channel. | main/sync |
| `export_to_keyframes` | node_path*:string, target_path*:string, parm_names*:array, frame_range:array, resample_rate:number | Bake CHOP channel data to keyframes on object parameters over a frame range. | main/async |
| `get_channel_info` | node_path*:string | Inspect a CHOP node — node type, sample rate, segment length, channel names, and per-channel value at the current frame. | main/sync |

### houdini-constraints (6개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_parent_constraint` | driven_path*:string, target_path*:string, maintain_offset:boolean | Drive an object's full transform from a single target, with optional offset preservation. | main/sync |
| `create_blend_constraint` | driven_path*:string, target_paths*:array, weights:array | Blend between multiple target transforms with per-target weights driving a single object. | main/sync |
| `create_position_constraint` | driven_path*:string, target_path*:string, maintain_offset:boolean, constraint_name:string | Constrain only translation channels (tx, ty, tz) using CHOP-driven channel referencing | main/sync |
| `create_orient_constraint` | driven_path*:string, target_path*:string, maintain_offset:boolean, constraint_name:string | Constrain only rotation channels (rx, ry, rz) using CHOP-driven channel referencing | main/sync |
| `list_constraints` | context_path:string, constraint_type:string | List constraint relationships under a context path, including blend- based and CHOP-based constraints. | main/sync |
| `delete_constraint` | node_path*:string | Delete a constraint node, clearing driven-object expressions first (destructive). | main/sync |

### houdini-copernicus (4개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_cop_network` | parent_path*:string, network_name:string | Create or reuse a COP/Copernicus image-processing network. | main/sync |
| `create_cop_node` | network_path*:string, filter_type*:string, node_name:string, input_nodes:array, parameters:object | Create a typed COP filter node, set bounded parameters, and wire existing input nodes. | main/sync |
| `inspect_cop_network` | network_path*:string | Inspect COP children and input connections without cooking or mutating the network. | main/sync |
| `validate_cop_network` | network_path*:string | Inspect cached COP node errors without cooking; reports validation scope. | main/sync |

### houdini-dev (8개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `attach_project` | project_root*:string | Add a local Python project root to sys.path for tool development. | any/sync |
| `reload_modules` | prefix:string, modules:array, reimport:boolean | Hot-reload Python modules by prefix and/or explicit name without restarting Houdini. | any/sync |
| `run_entrypoint` | entrypoint*:string, args:array, kwargs:object, reload:boolean | Import and call a module:function entrypoint and capture stdout/stderr/traceback. | main/sync |
| `run_script` | script_path*:string | Run a project-local .py script and capture stdout/stderr/traceback. | main/sync |
| `start_debugpy` | host:string, port:integer | Start a debugpy listener on an explicit host/port with safe defaults and already-running detection. | any/sync |
| `introspect_hom` | target:string, category:string, name_filter:string, limit:integer | Introspect HOM objects (members, signature), node-type categories, and available node types for agent planning (read-only). | main/sync |
| `ui_snapshot` | (none) | Snapshot the current desktop, available desktops, and pane-tab types (headless-safe). | main/sync |
| `ui_action` | action*:string, value:string | Trigger a small, safe UI action (set_desktop, display_message, cook_meta); returns supported=false in headless hython. | main/sync |

### houdini-export-preset (4개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `save_export_preset` | preset_name*:string, rop_node_path:string, source_node_path:string, format:string, library_dir:string, overwrite:boolean, custom_settings:object | Save a ROP node's export configuration (node type, parameters, output path, frame range) as a JSON preset file in a library directory | main/sync |
| `load_export_preset` | preset_name*:string, library_dir:string, create_rop:boolean, rop_parent_path:string, source_node_path:string, connect_source:boolean | Load a saved export preset from the library and return its configuration | main/sync |
| `list_export_presets` | library_dir:string | List all export preset JSON files in a library directory (read-only, no Houdini scene access required). | any/sync |
| `delete_export_preset` | preset_name*:string, library_dir:string | Delete an export preset JSON file from the library (no Houdini scene access required). | any/sync |

### houdini-geometry (8개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_primitive` | parent_path*:string, primitive*:string, node_name:string, set_display:boolean | Create a common SOP primitive (box, sphere, grid, tube, curve, null, output) under an explicit SOP network path. | main/sync |
| `create_curve_guides` | parent_path*:string, guides:array, input_file:string, node_name:string, set_display:boolean | Create bounded open polyline or NURBS guide curves from inline structured JSON or one UTF-8 .json file | main/sync |
| `get_geometry_info` | node_path*:string | Cook and summarise point/primitive/vertex counts and bounds for a SOP node | main/sync |
| `list_attributes` | node_path*:string | List point/primitive/vertex/detail attributes (name, data type, size) for a SOP node | main/sync |
| `list_groups` | node_path*:string | List point/primitive/edge groups (name, count) for a SOP node | main/sync |
| `get_cook_status` | node_path*:string, force:boolean | Cook a SOP node and return cook success plus any errors and warnings. | main/async |
| `get_attribute_values` | node_path*:string, attribute_name*:string, attribute_class:string, offset:integer, limit:integer | Read paged point, primitive, vertex or detail attribute values with explicit truncation. | main/sync |
| `get_primitive_intrinsics` | node_path*:string, primitive_index*:integer, names:array | Read bounded primitive intrinsics including packed transforms and bounds. | main/sync |

### houdini-groom (1개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `build_short_fur_groom` | geo_path*:string, rest_skin*:string, animated_skin:string, guides:string, skin_group:string, density:number, length:number, segments:integer, clump_strength:number, region_profiles:array, deform_method:string, name_prefix:string | Build a Houdini 22 Hair Generate 2.0 network for short fur and optionally append Guide Deform so roots follow animated skin | main/sync |

### houdini-gsplat-relighting (4개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `inspect_gsplat_relighting_input` | node_path*:string, max_attributes:integer, provenance_type:string, source_view_count:integer, camera_poses_solved:boolean, camera_pose_source:string, camera_pose_validation:string, capture_coverage:string, evaluation_view_count:integer, heldout_psnr:number, heldout_ssim:number, heldout_lpips:number, anatomy_region_count:integer, anatomy_regions_passed:integer, silhouette_iou:number, normalized_landmark_error:number, thin_structure_recall:number, novel_view_count:integer, public_showcase:boolean | Inspect a SOP GSplat output for the attributes needed by Labs normal reconstruction, delighting, Solaris relighting, and Copernicus rasteriz... | main/sync |
| `prepare_gsplat_sop_chain` | node_path*:string, create_normals:boolean, create_albedo:boolean, normalize_input:boolean, preserve_spherical_harmonics:boolean, name_prefix:string, cook:boolean | Append the installed Labs Normals from GSplats and/or Delight GSplats SOPs to an existing GSplat output | main/sync |
| `create_gsplat_relight_lop` | lop_node_path*:string, camera_path:string, collision_path:string, enable_shadows:boolean, shadow_bias:number, lights:array, parameters:object | Create and connect a Labs Relight GSplats LOP after a Solaris input, optionally adding USD Light LOPs for a key, fill, dome, or other religh... | main/sync |
| `create_gsplat_copernicus_raster` | copnet_path*:string, sop_path*:string, camera_path:string, attribute_name:string, resolution:array, sharpen_amount:number, saturation_scale:number, value_scale:number, gamma:number, premultiply_alpha:boolean | Create a Copernicus SOP Import plus Rasterize GSplats chain, optionally wiring a Camera Import COP and Sharpen, HSV, Gamma, and Premult imag... | main/sync |

### houdini-hda-automation (6개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `scan_hda_libraries` | (none) | List loaded HDA library files and their definition node types (read-only). | main/sync |
| `inspect_hda_definition` | node_type_name*:string, hda_file:string | Inspect an HDA definition: inputs, parm templates, sections, version, and library path (read-only) | main/sync |
| `instantiate_hda` | parent_path*:string, node_type_name*:string, hda_file:string, node_name:string, parameters:object, inputs:array, cook:boolean | Create an HDA instance, wire inputs, set parameters, cook, and report generated nodes plus cook errors. | main/async |
| `validate_hda` | node_path*:string, cook:boolean | Cook an HDA node (optional) and report errors, warnings, and a pass/fail verdict. | main/async |
| `cook_top_network` | node_path*:string, block:boolean | Cook a TOP/PDG node (optionally blocking) and report work-item count and errors. | main/async |
| `execute_rop_chain` | rop_path*:string, frame_range:array, ignore_inputs:boolean, background:boolean | Render a ROP with its upstream output-driver dependencies (or just itself when ignore_inputs is set) | main/sync |

### houdini-hda (10개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `install_hda_file` | file_path*:string | Install a packed Houdini .hda/.otl file or SideFX expanded HDA directory into the current session and return discovered definitions. | main/sync |
| `list_hda_definitions` | file_path:string | List Houdini Digital Asset definitions from a specific file or all loaded HDA files. | main/sync |
| `execute_hda` | operator_name*:string, parent_path:string, node_name:string, hda_file:string, parameters:object, press_buttons:array, cook:boolean, force_cook:boolean | Install an optional HDA file, create an HDA node, set parameters, press button parms, cook it, and return the resulting node path | main/sync |
| `promote_hda_parameters` | node_path*:string, promotions*:array | Promote parameter tuples from child nodes onto an unlocked HDA or subnet interface and create native channel references back to the public c... | main/sync |
| `update_hda_definition` | node_path*:string, version*:string, update_contents:boolean, match_current:boolean | Publish unlocked instance contents into its HDA definition, set the definition version, and optionally match the instance to the new definit... | main/sync |
| `sync_hda_instance` | node_path*:string, from_version*:string, hda_file:string, match_current:boolean, sync_delayed:boolean | Reload or install an optional HDA library, match an instance to its current definition, and run the asset's native version synchronization h... | main/sync |
| `save_node_as_hda` | node_path*:string, hda_file_path*:string, hda_name*:string, label:string, version:string, save_as_embedded:boolean, overwrite:boolean | Create a Houdini Digital Asset from an existing node and save it to an HDA file | main/sync |
| `author_hda_interface` | node_path*:string, templates*:array, conflict_policy:string | Declaratively author a safe HDA/subnet parameter interface with folders, numeric ranges, toggles, strings, static menus, and native channel ... | main/sync |
| `publish_hda_library` | node_path*:string, hda_file_path*:string, namespace*:string, asset_name*:string, version*:string, label:string, icon:string, help_text:string, dependencies:array, custom_sections:object, embedded_resources:array, conflict_policy:string, update_contents:boolean, install:boolean, make_preferred:boolean | Publish an existing HDA definition under an explicit namespace and version, with an explicit conflict policy, icon/help, safe dcc_mcp/ metad... | main/sync |
| `validate_hda_contract` | node_type_name*:string, hda_file:string, expected_version:string, required_parameters:array, required_sections:array, require_namespace:boolean, require_type_version:boolean, require_manifest:boolean, check_dependencies:boolean, instantiate:boolean, parent_path:string | Validate an HDA definition's namespace/version, safe parameter interface, required sections, dependency/resource manifest, and exact tempora... | main/sync |

### houdini-husk (6개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `render_with_husk` | usd_file*:string, output_path*:string, renderer:string, frame:integer, frame_range:array, resolution:array, husk_args:array, use_hython_fallback:boolean | Launch a USD render in an isolated Husk worker and return a durable job_id immediately | any/sync |
| `get_husk_job` | job_id*:string | Poll a durable isolated Husk render | any/sync |
| `cancel_husk_job` | job_id*:string | Cancel an adapter-owned Husk worker process tree | any/sync |
| `create_checkpoint` | usd_file*:string, checkpoint_path*:string, frame:integer | Create a render checkpoint for husk — save intermediate USD state for resume after interruption | main/sync |
| `create_snapshot` | source_path:string, snapshot_path:string, flatten:boolean, frame:number | Export the current Solaris stage (/stage), an external LOP network, or a LOP node as a USD snapshot for husk command-line rendering | main/sync |
| `set_husk_options` | node_path:string, options:object, list_options:boolean, category:string | Configure or inspect husk command-line rendering options (renderer, threads, GPU, resolution, output, debug flags) | main/sync |

### houdini-import-to-scene (1개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `import_to_scene` | descriptor*:object, material_mode:string, placement:object, target_collection:string, skip_existing:boolean | Import an asset described by an AssetDescriptor into a Houdini geo container. | main/sync |

### houdini-interchange (6개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `probe_file` | file_path*:string | Probe a file path: existence, size, detected format category, and whether it is a supported import | any/sync |
| `import_geometry` | parent_path*:string, file_path*:string, node_name:string, cook:boolean | Import a geometry/scene file (bgeo/obj/fbx/abc/usd) into a SOP network via a File SOP, with explicit parent path and optional cook. | main/async |
| `export_geometry` | node_path*:string, output_path*:string, create_dirs:boolean | Export a SOP node's cooked geometry to a native/interchange file (.bgeo/.geo/.obj/.ply) via Geometry.saveToFile. | main/async |
| `export_alembic` | node_path*:string, output_path*:string, frame_range:array, render:boolean, create_dirs:boolean | Export a SOP stream to Alembic (.abc) via a ROP Alembic Output SOP, with optional frame range and render. | main/async |
| `export_fbx` | output_path*:string, root_node:string, convert_units:boolean, frame_range:array, render:boolean, create_dirs:boolean | Export an /obj subtree to FBX via a Filmbox FBX ROP, with optional frame range and render | main/async |
| `export_usd` | lop_node_path*:string, output_path*:string, frame_range:array, create_dirs:boolean | Export the composed USD stage of a LOP/Solaris node to disk and report the root layer, output path, frame range, and warnings. | main/async |

### houdini-karma (4개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `configure_karma` | node_path*:string, device:string, max_samples:integer, pixel_samples:integer, diffuse_samples:integer, specular_samples:integer, transmission_samples:integer, volume_samples:integer, noise_threshold:number, denoise:boolean | Configure Karma CPU/XPU render settings — engine, sampling (pixel, diffuse, specular, transmission, volume), noise threshold, and denoising. | main/sync |
| `set_material_override` | node_path*:string, material_path:string, preset:string, color:array, roughness:number, metallic:number, clear:boolean | Set or clear a global material override on a Karma render node | main/sync |
| `configure_light_mixer` | node_path*:string, lights:array, enable:boolean, auto_create:boolean | Enable and configure the Karma Light Mixer panel | main/sync |
| `set_image_output` | node_path*:string, output_path*:string, format:string, resolution:array, color_space:string, layer_name:string | Set Karma image output path, format (exr/png/jpg/tif with bit depth), resolution, color space, and layer name. | main/sync |

### houdini-kinefx (8개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_insect_rig` | geo_path*:string, rig_name:string, scale:number, ground_z:number, anatomy_measurements:object, auto_capture:boolean, capture_mesh:string | Create an anatomy-aware worker-honeybee KineFX skeleton with compound eyes, segmented antennae, a flexible abdomen, four wings, and six full... | main/sync |
| `create_rig` | geo_path*:string, rig_name:string, joint_chain:array, auto_capture:boolean, capture_mesh:string | Create a KineFX skeleton rig with a joint chain and optional auto-capture onto a mesh. | main/sync |
| `set_rig_pose` | rig_node*:string, joint_index:integer, joint_name:string, translate:array, rotate:array, scale:array | Set translation, rotation, and/or scale on one or all joints of a KineFX rig. | main/sync |
| `validate_ground_contacts` | rig_node*:string, ground_node*:string, joint_names*:array, axis:string, tolerance:number, min_support_contacts:integer | Read named KineFX joint positions against the top of one cooked ground surface and report contact, lifted, penetrating, and missing joints | main/sync |
| `capture_joints` | geo_path*:string, mesh_name*:string, rig_name*:string, method:string, max_joints:integer, falloff:number, output_name:string | Capture skinning weights from a KineFX skeleton onto a target mesh using captureproximity or bonecapture SOP. | main/sync |
| `deform_gsplat_with_rig` | geo_path*:string, captured_splats*:string, rest_rig*:string, animated_rig*:string, output_name:string, skinning_method:string, deform_normals:boolean, preserve_capture_attributes:boolean | Deform captured Gaussian Splat points with rest and animated KineFX skeletons while rotating quaternion orient and preserving anisotropic sc... | main/sync |
| `apply_mocap` | geo_path*:string, rig_name*:string, mocap_file*:string, start_frame:number, scale:number, mocap_node_name:string | Apply motion capture data (FBX, BVH, or KineFX .bclip/.clip) onto a rig skeleton. | main/async |
| `build_retarget_motion_mixer` | geo_path*:string, target_skeleton*:string, source_skeletons*:array, character_name:string, clip_names:array, start_frame:integer, end_frame:integer, mapping_attribute:string, node_prefix:string, add_secondary_motion:boolean | Build and cook a Houdini 22 Rig Match Pose, Map Points, Full Body IK, multi-MotionClip, APEX character, and Motion Mixer workflow from exist... | main/async |

### houdini-light-rig (9개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_three_point_light_rig` | name:string, parent_path:string, key_intensity:number, fill_intensity:number, rim_intensity:number, light_type:string, key_color:array, fill_color:array, rim_color:array, key_position:array, fill_position:array, rim_position:array | Create a standard three-point (key/fill/rim) lighting rig under a null group at /obj | main/sync |
| `aim_light_at_object` | light_path*:string, target_path*:string, up_vector:array | Point a light at a target object using Houdini's lookatpath parameter | main/sync |
| `create_hdri_world` | hdri_path*:string, name:string, parent_path:string, intensity:number, rotation:number, visible_in_diffuse:boolean, visible_in_specular:boolean | Create an environment light (hlight::2.0, type=environment) with an HDRI texture map for image-based lighting | main/sync |
| `get_lighting_summary` | parent_path:string | Scan the /obj network (or a specified parent) for all hlight nodes and report their type, intensity, color, exposure, position, and rig memb... | main/sync |
| `group_lights` | rig_name*:string, light_paths*:array, parent_path:string | Group one or more existing hlight nodes under a new null rig node | main/sync |
| `list_light_rigs` | parent_path:string | List all light rig groups (null nodes containing hlight children) under /obj or a specified parent | main/sync |
| `set_light_rig_intensity` | rig_group*:string, intensity*:number, multiply:boolean | Scale or set the intensity of all hlight nodes parented under a rig null group | main/sync |
| `set_render_view_transform` | view_transform*:string, display_device:string, color_space:string | Configure the OCIO view transform for the Houdini session's render view | main/sync |
| `create_area_softbox` | name:string, parent_path:string, shape:string, size:array, intensity:number, color:array, translate:array, rotate:array, exposure:number | Create a grid or disk area light configured as a softbox with large area size, soft quality, and controlled diffuse/specular contribution | main/sync |

### houdini-lookdev (12개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `list_materials` | parent_path:string | List shader/material nodes under a material network (read-only). | main/sync |
| `list_assignments` | parent_path:string | List object → material assignments under a network (read-only). | main/sync |
| `get_material_parms` | material_path*:string, name_filter:string | Read parameter names and values for a material/shader node (read-only). | main/sync |
| `set_material_parms` | material_path*:string, parameters*:object | Set material/shader parameter values with type-aware coercion. | main/sync |
| `get_shader_connections` | node_path*:string | Inspect a shader/VOP node's input and output connections (read-only). | main/sync |
| `connect_shader` | node_path*:string, source_path*:string, input_index:integer, input_name:string, source_output:integer | Wire a shader output into a shader/VOP node input (by index or name). | main/sync |
| `disconnect_shader` | node_path*:string, input_index*:integer | Clear a shader/VOP node input slot. | main/sync |
| `reset_material` | object_paths*:array, default_material:string | Reset object material assignments to a default value (default empty) and report affected/skipped objects. | main/sync |
| `save_preset` | material_path*:string, preset_name*:string, parm_names:array | Save a material's parameter values as an adapter-owned JSON preset. | main/sync |
| `list_presets` | (none) | List saved material presets (read-only, no Houdini required). | any/sync |
| `load_preset` | preset_name*:string, material_path*:string | Apply a saved material preset onto a material/shader node. | main/sync |
| `delete_preset` | preset_name*:string | Delete a saved material preset (no Houdini required). | any/sync |

### houdini-material-library (12개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `save_material_preset` | material_path*:string, preset_name*:string, library_dir:string, attributes:array, overwrite:boolean | Save a material/shader node's definition (type + all settable scalar parameters) as a JSON preset file in a library directory | main/sync |
| `load_material_preset` | file_path*:string, material_name:string, parent_path:string, assign_to:array | Recreate a material from a JSON preset file and optionally assign it to target objects. | main/sync |
| `list_material_presets` | library_dir:string | List all material preset JSON files in a library directory (read-only, no Houdini scene access required). | any/sync |
| `delete_material_preset` | preset_name*:string, library_dir:string | Delete a material preset JSON file from the library (no Houdini scene access required). | any/sync |
| `assign_texture` | material_path*:string, parameter_name*:string, texture_path*:string, colorspace:string | Assign a texture through an explicit Principled Shader, MaterialX, or Arnold contract | main/sync |
| `list_images` | parent_path:string | List image/file-texture nodes in the scene (read-only) | main/sync |
| `reload_image` | node_path:string, parent_path:string, reload_all:boolean | Reload one or more image texture nodes from disk | main/sync |
| `set_color_management` | ocio_config_path:string, color_space:string, view_transform:string | Configure Houdini's OCIO color management: set the active config path, the default color space, or the view transform. | main/sync |
| `list_color_spaces` | filter:string | List the available OCIO color spaces from Houdini's active configuration (read-only). | main/sync |
| `set_material_attribute` | material_path*:string, attribute_name*:string, value*:any | Set an attribute on a material/shader node | main/sync |
| `get_material_connections` | material_path*:string, depth:integer | Query a material/shader node's input and output connections, including upstream texture nodes and downstream shader assignments (read-only). | main/sync |
| `get_shader_assignment` | material_path*:string, search_root:string | Query which renderable objects a material/shader is assigned to (read-only) | main/sync |

### houdini-materials (4개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_material` | parent_path:string, shader_type:string, material_name:string, parameters:object, exact_type_name:boolean, set_current:boolean | Create a Houdini material/shader node under a material network, optionally setting parameters | main/sync |
| `assign_material` | target_node_path*:string, material_node_path*:string, parameter_name:string | Assign an existing Houdini material node to a target node by setting a material path parameter such as shop_materialpath | main/sync |
| `build_materialx_pbr` | parent_path:string, material_name:string, base_color:array, roughness:number, metallic:number, base_color_texture:string, roughness_texture:string, metallic_texture:string, normal_texture:string, displacement_texture:string, normal_scale:number, displacement_scale:number, base_color_space:string, data_color_space:string | Build a Karma-compatible MaterialX standard-surface material with typed base-color, roughness, metallic, normal, and displacement connection... | main/sync |
| `validate_materialx_pbr` | material_path*:string, required_channels:array | Inspect a dcc-mcp MaterialX PBR material and report whether its standard surface, outputs, and required texture channels are connected | main/sync |

### houdini-mesh-ops (19개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `array_instances` | input_path*:string, count*:integer, radius*:number, axis:string, start_angle_degrees:number, direction_mode:string, source_forward:string, node_name:string, points_node_name:string | Create a bounded radial point ring, orient every point radially or tangentially from a declared source-forward axis, and instance an input S... | main/sync |
| `uv_project` | input_path*:string, projection:string, group:string, uv_attribute:string, node_name:string | Project vertex UVs with a native UV Project SOP and verify that the requested UV attribute exists on the cooked result. | main/sync |
| `auto_uv` | input_path*:string, group:string, uv_attribute:string, node_name:string | Generate vertex UVs with a native UV Unwrap SOP and verify that the requested UV attribute exists on the cooked result. | main/sync |
| `mirror` | input_path*:string, origin:array, direction:array, node_name:string | Mirror a polygon SOP across an explicit plane and verify parameter plus cooked geometry readback. | main/sync |
| `bridge_edges` | input_path*:string, source_group*:string, destination_group*:string, divisions:integer, node_name:string | Bridge two explicit edge or face selections with a native PolyBridge SOP and verify the requested parameters plus cooked output. | main/sync |
| `add_edge_loop` | input_path*:string, split_locations*:string, node_name:string | Apply an explicit bounded PolySplit location string and verify the cooked topology before success. | main/sync |
| `lathe_profile` | profile*:string, axis:string, origin:array, segments:integer, node_name:string | Revolve a profile SOP around a typed axis with bounded segments and verified parameter plus cooked geometry readback. | main/sync |
| `boolean_op` | input_a*:string, input_b*:string, operation*:string, node_name:string | Combine two polygon SOP streams using a native Boolean SOP | main/sync |
| `loft_sections` | sections*:array, node_name:string | Merge two to sixty-four ordered section SOPs into Skin input zero for a linear loft, requiring a shared parent network and cooked readback. | main/sync |
| `inset` | input_path*:string, group:string, amount*:number, node_name:string | Inset a bounded primitive selection through the verified PolyExtrude path, with no raw scripting fallback. | main/sync |
| `bevel_edges` | input_path*:string, group*:string, distance*:number, divisions:integer, node_name:string | Append a PolyBevel SOP for a bounded edge selection and verify the requested bevel parameters plus cooked geometry before reporting success. | main/sync |
| `extrude_faces` | input_path*:string, group:string, distance:number, inset:number, node_name:string | Append a PolyExtrude SOP for a bounded primitive selection and return parameter plus cooked-geometry readback; fail if Houdini reports no ef... | main/sync |
| `transform_geometry` | input_path*:string, translate:array, rotate:array, scale:array, node_name:string | Append a Transform (xform) SOP downstream of an input SOP and set translate/rotate/scale. | main/sync |
| `merge_geometry` | input_paths*:array, node_name:string | Append a Merge SOP joining several upstream SOP streams. | main/sync |
| `blast_geometry` | input_path*:string, group*:string, group_type:string, delete_non_selected:boolean, node_name:string | Append a Blast SOP that deletes a group (or keeps it and deletes the rest when delete_non_selected is true). | main/sync |
| `group_geometry` | input_path*:string, group_name*:string, group_type:string, pattern:string, node_name:string | Append a Group Create SOP to define a point/primitive/edge group. | main/sync |
| `add_normals` | input_path*:string, attribute_class:string, node_name:string | Append a Normal SOP to compute point/vertex/primitive normals. | main/sync |
| `triangulate_geometry` | input_path*:string, node_name:string | Append a Divide SOP configured to convex-triangulate polygons. | main/sync |
| `convert_geometry` | input_path*:string, to_type:string, node_name:string | Append a Convert SOP to change the primitive type (poly/mesh/nurbs/...). | main/sync |

### houdini-node-graph (5개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `get_connections` | node_path*:string, include_dependents:boolean | Return a node's input paths, output paths, and (optionally) parameter dependents/consumers | main/sync |
| `connect_input` | node_path*:string, input_index*:integer, source_path*:string, source_output:integer | Wire a source node's output into a target node's input at an explicit input index | main/sync |
| `disconnect_input` | node_path*:string, input_index*:integer | Clear the connection feeding a node's input index. | main/sync |
| `inspect_network` | parent_path*:string | Full semantic inspection of a Houdini parent network | main/sync |
| `auto_layout` | parent_path*:string, strategy:string, preserve_user_layout:boolean, spacing_x:number, spacing_y:number, dry_run:boolean | Auto-arrange nodes under a parent network with controllable user-layout preservation | main/sync |

### houdini-nodes (10개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_node` | parent_path*:string, node_type*:string, node_name:string, exact_type_name:boolean, run_init_scripts:boolean, load_contents:boolean, set_current:boolean | Create a Houdini node under an existing parent path | main/sync |
| `set_node_parms` | node_path*:string, parameters*:object, press_buttons:array | Set one or more parameters on a Houdini node | main/sync |
| `connect_nodes` | input_node_path*:string, output_node_path*:string, input_index:integer, output_index:integer | Connect one Houdini node into another node's input | main/sync |
| `cook_node` | node_path*:string, force:boolean | Cook a Houdini node and return errors/warnings when available | main/async |
| `cook_nodes_chunked` | node_paths*:array, force:boolean | Cook several independently bounded Houdini nodes, advancing one node per UI event-loop tick | main/async |
| `start_cook_job` | node_path*:string, force:boolean | Start one potentially long node cook in an isolated hython process and return a durable job_id immediately | main/sync |
| `get_cook_job` | job_id*:string | Query a durable isolated node-cook job after transport disconnects or adapter restart | any/sync |
| `cancel_cook_job` | job_id*:string | Cancel an isolated node-cook job only while this adapter process still owns its worker handle | any/sync |
| `layout_children` | parent_path:string, selected_only:boolean | Layout all children or only currently selected children under a Houdini network node, matching the Network Editor L action | main/sync |
| `delete_node` | node_path*:string | Destroy a Houdini node by path | main/sync |

### houdini-object-ops (8개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `set_pivot` | node_path*:string, position*:array | Set the local pivot tuple of an OBJ node and verify exact parameter readback, restoring the previous value if verification fails. | main/sync |
| `rename_node` | node_path*:string, new_name*:string, unique_name:boolean | Rename a node, optionally enforcing a unique name within its parent. | main/sync |
| `duplicate_node` | node_path*:string, new_name:string | Copy a node into its parent network and optionally rename the copy. | main/sync |
| `parent_node` | node_path*:string, new_parent_path*:string | Move a node into a different parent network using hou.moveNodesTo. | main/sync |
| `set_node_flags` | node_path*:string, display:boolean, render:boolean, template:boolean, bypass:boolean | Set display, render, template, and/or bypass flags on a node | main/sync |
| `set_node_lock` | node_path*:string, locked*:boolean | Hard-lock (freeze cooked geometry) or unlock a SOP-style node. | main/sync |
| `get_transform` | node_path*:string | Read translate/rotate/scale parm tuples (t/r/s) for an OBJ-level node | main/sync |
| `set_transform` | node_path*:string, translate:array, rotate:array, scale:array | Set translate/rotate/scale parm tuples (t/r/s) for an OBJ-level node | main/sync |

### houdini-parameters (9개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `list_parms` | node_path*:string, name_filter:string | List a node's parameters with name, label, and current value | main/sync |
| `get_parms` | node_path*:string, names:array | Read values for specific parm names (or all parms when names omitted) | main/sync |
| `set_parms` | node_path*:string, parameters*:object | Set one or many parameters with type-aware coercion | main/sync |
| `get_parm_templates` | node_path*:string, parm_name:string | Inspect parameter templates for one parm or all top-level templates | main/sync |
| `add_spare_parm` | node_path*:string, name*:string, parm_type:string, label:string, num_components:integer | Add a spare parameter of type float, int, string, or toggle | main/sync |
| `remove_spare_parm` | node_path*:string, name*:string | Remove a spare parameter tuple by name. | main/sync |
| `set_expression` | node_path*:string, parm_name*:string, expression*:string, language:string | Set a channel expression on a parameter (hscript or python language). | main/sync |
| `get_expression` | node_path*:string, parm_name*:string | Read a parameter's expression and language, or its plain value when no expression is set | main/sync |
| `clear_expression` | node_path*:string, parm_name*:string | Remove a parameter's expression/keyframes while freezing its current evaluated value. | main/sync |

### houdini-pdg (5개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_pdg_network` | parent_path*:string, network_name:string | Create or reuse a TOP network container. | main/sync |
| `create_pdg_node` | network_path*:string, node_type*:string, node_name:string, input_nodes:array, parameters:object | Create a TOP node, set bounded parameters, and wire existing dependencies. | main/sync |
| `connect_pdg_nodes` | output_node_path*:string, input_node_path*:string, input_index:integer, output_index:integer | Connect a TOP node to an existing upstream dependency. | main/sync |
| `inspect_pdg_graph` | node_path*:string | Inspect TOP nodes, graph work-item counts, states, and cook errors. | main/sync |
| `cook_pdg_graph` | node_path*:string, block:boolean | Cook a TOP/PDG graph and return explicit work-item state readback. | main/async |

### houdini-pipeline (7개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `set_project` | project_root*:string, create:boolean | Set the Houdini project root ($JOB) with path validation (optionally create it). | main/sync |
| `get_project` | (none) | Query the current project root ($JOB), $HIP, and hip file path (read-only). | main/sync |
| `tag_asset_metadata` | metadata*:object, node_path:string, merge:boolean | Tag adapter-owned asset metadata (JSON) on a node or the hip file using a portable dcc_mcp_meta schema. | main/sync |
| `get_asset_metadata` | node_path:string | Read adapter-owned asset metadata from a node or the hip file (read-only). | main/sync |
| `validate_scene` | node_paths:array, check_outputs:boolean | Validate the scene for missing input files, unwritable output dirs, dirty state, and node cook errors (read-only). | main/sync |
| `collect_dependencies` | node_paths:array | Collect external file dependencies for the scene or selected nodes and return a manifest | main/sync |
| `export_shot_package` | output_path:string, write_manifest:boolean | Build a shot/package manifest (frame range, fps, cameras, output nodes, caches, written files); optionally write the JSON document. | main/sync |

### houdini-render (16개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `capture_viewport` | output_path*:string, resolution:array, frame:number | Capture the current Scene Viewer to an image file for a single frame via flipbook, with clamped resolution | main/async |
| `flipbook` | output_path*:string, frame_range*:array, resolution:array, camera_path:string | Launch a chunked flipbook job that renders one frame per host event-loop tick | main/sync |
| `get_flipbook_job` | job_id*:string | Read bounded status, output progress, and written files for a chunked flipbook job | any/sync |
| `cancel_flipbook_job` | job_id*:string | Cancel a running chunked flipbook job | any/sync |
| `get_render_settings` | rop_path*:string | Read renderer, camera, resolution, frame range, output path, and image format from a ROP node | main/sync |
| `set_render_settings` | rop_path*:string, camera:string, resolution:array, frame_range:array, output_path:string, image_format:string | Set camera, resolution (clamped), frame range, output path, and image format on a ROP node | main/sync |
| `validate_karma_stage` | lop_path*:string, renderer:string | Read-only preflight of a composed Solaris USD Stage for known Karma instance-property and RenderVar pixel-filter diagnostics | main/sync |
| `render_rop` | rop_path*:string, frame_range:array, background:boolean, artifact_transaction:object | Render a ROP/output driver and report written files, elapsed time, warnings/errors | main/sync |
| `render_rop_chunked` | action*:string, rop_path:string, frame_range:array, job_id:string | Render a ROP/output driver using per-frame chunked execution via the core ChunkedRunner | main/async |
| `get_render_job` | job_id*:string, include_details:boolean | Read bounded status, output progress, elapsed time, and ETA for a background ROP render/cache/chain job | any/sync |
| `finalize_render_outputs` | job_id*:string, validator_receipts*:array | Publish one or more staged EXRs from a completed isolated render job | any/sync |
| `cancel_render_job` | job_id*:string | Cancel a background ROP render/cache/chain job owned by the current adapter process | any/sync |
| `create_render_layer` | name*:string, parent_path:string, aovs:array, purpose:string, source_rop_path:string, output_path:string, candidate_objects:string, force_objects:string, matte_objects:string, exclude_objects:string, phantom_objects:string | Create a Solaris Render Product, or clone a Mantra ifd ROP into a real render layer with a required dedicated output, optional object masks,... | main/sync |
| `configure_aovs` | rop_path*:string, aovs*:array, action:string | Add or remove AOVs on a Solaris Render Product or Mantra ROP | main/sync |
| `manage_takes` | action*:string, take_name:string, node_path:string, parm_name:string, value:any | Create, switch, delete, or list takes, and add or remove a parameter tuple override on a child take | main/sync |
| `get_render_stats` | rop_path:string | Read render statistics (resolution, samples, renderer, output, frame range) from a ROP node or the current Houdini session. | main/sync |

### houdini-scene-edit (8개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `new_scene` | force:boolean | Clear the current hip file and start an empty scene | main/sync |
| `open_scene` | file_path*:string, force:boolean | Load an existing hip file | main/sync |
| `save_scene` | file_path:string | Save the current scene | main/sync |
| `get_selection` | (none) | Return the nodes Houdini currently reports as selected, with path, name, and type | main/sync |
| `set_selection` | node_paths*:array, clear_existing:boolean | Replace (or extend) the node selection from a list of node paths | main/sync |
| `find_nodes` | name_pattern:string, type_filter:string, root_path:string, recursive:boolean, max_results:integer | Search under a root path for nodes matching a name glob and/or a node type substring | main/sync |
| `list_cameras` | root_path:string, recursive:boolean | List object-level camera nodes (type name starting with "cam") | main/sync |
| `get_bounding_box` | node_path*:string | Return the geometry bounding box (min, max, size, center) of a SOP node or an OBJ geo's display node | main/sync |

### houdini-scene (5개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `inspect_selection` | (none) | Inspect the current selection and its display SOP in one read-only call | main/sync |
| `get_scene_info` | (none) | Return hip file path, whether a file is saved, current frame, playback range, and the number of children under /obj | main/sync |
| `list_obj_nodes` | type_filter:string | List object-level nodes under /obj with path, name, and type | main/sync |
| `list_child_nodes` | parent_path:string, type_filter:string, recursive:boolean, max_depth:integer, include_hidden:boolean | List child nodes below any Houdini network path, optionally filtered by node type and recursively traversed to a bounded depth | main/sync |
| `get_node_info` | node_path*:string, include_connections:boolean | Return a read-only summary for a Houdini node including path, type, category, parent, child count, flags, and optional input/output links | main/sync |

### houdini-scripting (2개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `execute_python` | code*:string, context:object | Execute a Python snippet inside Houdini | main/sync |
| `get_session_info` | (none) | Read Houdini version, Python executable, UI availability, and current hip file path without modifying the scene. | main/sync |

### houdini-simulation (4개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_simulation_network` | parent_path*:string, simulation_type*:string, network_name:string, solver_name:string, parameters:object | Create or reuse a DOP solver skeleton; object sources and wiring are still required. | main/sync |
| `configure_simulation_solver` | solver_path*:string, parameters*:object, cook:boolean | Apply bounded parameter overrides to an existing simulation solver and optionally cook it. | main/sync |
| `inspect_simulation_network` | network_path*:string | Inspect DOP children, solver types, parameter readback, errors, and timeline metadata. | main/sync |
| `validate_simulation_setup` | network_path*:string, simulation_type:string | Validate that a DOP network contains the requested solver family and has no cook errors. | main/sync |

### houdini-texture-bake (5개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `bake_ambient_occlusion` | rop_path:string, objects:array, output_path:string, resolution:array, samples:integer, max_distance:number | Bake ambient occlusion to a texture using Labs Maps Baker, Bake Texture ROP, or COP-based fallback | main/async |
| `bake_lighting` | rop_path:string, camera:string, objects:array, output_path:string, resolution:array, samples:integer, renderer:string, bake_shadows:boolean | Bake full scene lighting (diffuse + shadows) via Mantra or Karma render-to-texture using a Bake Texture ROP | main/async |
| `bake_textures` | rop_path*:string, objects:array, output_path:string, resolution:array, map_types:array, uv_layer:string, file_format:string | Bake multi-map textures (diffuse, normals, cavity, curvature, roughness, metallic, etc.) via Labs Maps Baker or Bake Texture ROP | main/async |
| `list_bake_targets` | node_type_filter:string, require_uvs:boolean | Scan the scene for bake-compatible geometry nodes | main/sync |
| `transfer_maps` | source*:string, target*:string, map_types:array, output_dir:string, resolution:array, file_format:string, transfer_mode:string, search_distance:number | Transfer texture maps (normals, displacement, diffuse, AO) from a high-resolution source to a low-resolution target mesh using Labs Maps Bak... | main/async |

### houdini-usd-lops (3개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `list_stage_prims` | lop_node_path*:string, root_path:string, max_depth:integer, limit:integer | List prims below a root path on the composed USD Stage of a LOP node | main/sync |
| `get_prim_info` | lop_node_path*:string, prim_path*:string, time_code:number | Inspect one USD prim on a LOP Stage, including type, active state, computed visibility, world transform, world bounds, and bound material. | main/sync |
| `get_prim_attributes` | lop_node_path*:string, prim_path*:string, name_filter:string, time_code:number, max_attributes:integer, max_value_items:integer, max_value_chars:integer | Read attributes from one USD prim at an optional time code | main/sync |

### houdini-vex (7개)

| 이름 | 파라미터 | 설명 | affinity/execution |
|---|---|---|---|
| `create_wrangle` | parent_path*:string, wrangle_type:string, node_name:string, run_over:string, vex_code:string, bindings:object, parameters:object, set_display:boolean, set_render:boolean | Create a typed Wrangle SOP node (attribwrangle, pointwrangle, geometrywrangle, etc.) under a parent SOP network, optionally with a validated... | main/sync |
| `update_vex_snippet` | node_path*:string, vex_code*:string, wrangle_type:string, run_over:string, bindings:object, parameters:object | Update the VEX snippet (and optionally run-over context and bindings) on an existing Wrangle node | main/sync |
| `validate_vex_syntax` | vex_code*:string, run_over:string, known_attributes:array, wrangle_type:string | Validate VEX snippet syntax client-side without touching Houdini | main/sync |
| `cook_wrangle` | node_path*:string, force:boolean | Cook a Wrangle node and return cook status plus geometry diagnostics (point/prim/vertex counts, attribute names, group names, errors and war... | main/async |
| `diagnose_wrangle` | node_path*:string | Analyse a failed Wrangle cook and locate the failure: VEX compile error with line hints, missing attribute bindings, zero geometry, or cook ... | main/sync |
| `get_vex_info` | node_path*:string | Read back metadata from a Wrangle node: node type, run-over mode, snippet preview, cook state, and input/output count | main/sync |
| `list_wrangles` | parent_path:string | List all Wrangle-type nodes under a parent path, recursively | main/sync |


**합계: 259개 툴 (38개 스킬)**
## 2. 아키텍처

### (a) 트랜스포트

- **Streamable HTTP**. `src/dcc_mcp_houdini/server.py`의 docstring이 명시: *"Houdini MCP server — embeds a Streamable HTTP MCP server inside Houdini."* Houdini/hython 프로세스 안에서 HTTP MCP 서버가 뜬다(포트는 기본 OS 할당, `DEFAULT_PORT = 0`).
- **자동 게이트웨이(Auto-gateway)**: 여러 Houdini 인스턴스가 동시에 떠 있을 수 있으므로, 고정 포트(9765)에서 "first-wins election" 방식의 게이트웨이가 여러 인스턴스의 MCP 엔드포인트를 통합 라우팅한다(README "Auto-gateway with first-wins election (gateway port 9765)"). IDE(예: Cursor)는 개별 인스턴스 URL(`examples/mcp/cursor-houdini-streamable-http.json` 예시: `http://127.0.0.1:9765/mcp`)에 직접 붙을 수도 있고, 에이전트는 `dcc-mcp-cli`(별도 CLI, `dcc-mcp-core` 배포물)를 통해 게이트웨이 경유로 접근하는 것을 권장한다.
- stdio 트랜스포트 관련 코드/문서는 이 저장소에서 확인되지 않았다(모두 HTTP 기반).

### (b) Houdini와의 통신

- hrpyc/소켓처럼 외부 프로세스가 Houdini에 접속하는 구조가 아니라, **MCP 서버 자체가 Houdini/hython 프로세스 안에 내장(in-process)**되어 실행된다. 즉 통신 방식은 "in-process embedded HTTP server"이며, 별도의 RPC 레이어가 없다.
- 실제 툴 구현(`skills/*/scripts/*.py`)은 `hou` 모듈을 직접 import해서 호출하는 일반 Python 함수이고, `dcc_mcp_houdini.api.with_houdini` 데코레이터로 `hou` 미가용 시(=Houdini 밖) 에러를 표준화한다.
- 헤드리스(hython, UI 없음) 환경과 인터랙티브(UI 있음) 환경을 모두 지원하도록 `HoudiniHost.is_background()`가 `hou.isUIAvailable()`로 분기한다.

### (c) 메인 스레드 안전성

세 저장소 중 **가장 정교한 메인 스레드 마샬링 계층**을 갖추고 있다. `src/dcc_mcp_houdini/host.py`에 다음 구성 요소가 있다:

- `HoudiniEventLoopTimerAdapter`: `hou.ui.addEventLoopCallback()`으로 Houdini의 단일 이벤트 루프에 콜백을 등록하고, `dcc-mcp-core`의 `HostPumpController`가 요구하는 "틱(tick)" 인터페이스로 어댑팅한다. 씬이 파괴된 상태(세션 종료 등)에서 스테일(stale) `hou` 객체에 접근해 네이티브 SIGSEGV가 나는 것을 막기 위한 `pre_drain_check`(예: `hou.node("/obj")`가 살아있는지 확인)까지 포함한다.
- `HoudiniUiDispatcher` / `HoudiniUiPump`: `dcc-mcp-core`의 `HostUiDispatcherBase`/`HostPumpController`를 얇게 감싸, 툴 호출 시 요청 스레드가 이미 Houdini 메인(호스트) 스레드면 즉시 실행하고(`is_host_thread()`), 아니면 `submit_callable(...)`로 큐에 넣고 이벤트 루프 틱에서 드레인되도록 만든다.
- `HoudiniCallableDispatcher` / `BlockingDispatcher`(core): 콜러블을 Houdini 메인 스레드 큐에 `post()`하고 `handle.wait(timeout)`로 블로킹 대기하는 표준 패턴(HTTP 요청 스레드 → 메인 스레드 큐 → 결과 반환).
- 각 툴은 `tools.yaml`에 `affinity: main|any`와 `execution: sync|async` 태그가 붙어 있다. `affinity: main`은 반드시 Houdini 메인 스레드에서 실행되어야 함을 의미하고(`hou` 조작 대부분이 여기 해당), `affinity: any`는 파일 I/O 등 스레드 무관 작업(프리셋 목록 조회, 잡 상태 폴링 등)이다. `execution: async`는 `start_cook_job`/`render_with_husk`류처럼 **격리된 hython 워커 프로세스**나 청크 단위 실행(`cook_nodes_chunked`가 "advancing one node per UI event-loop tick")으로 장시간 작업을 논블로킹 처리하고 `job_id`로 폴링하는 패턴이다(`_cook_jobs.py`, `_cook_worker.py`, `_isolated_jobs.py`, `_rop_jobs.py`, `_flipbook_jobs.py`).
- 즉 이 저장소는 (1) 메인 스레드 강제 마샬링(큐+이벤트 루프 틱), (2) 장시간 작업의 별도 프로세스/청크 격리, (3) 툴 단위 affinity 선언이라는 3중 안전장치를 갖췄다 — 다른 두 저장소(암묵적 rpyc 스레드 실행, 단순 QTimer 폴링)보다 명시적이고 세밀하다.

### (d) 툴 등록 방식 — 플러그인/레지스트리 (상세)

**패키지 레벨 레지스트리(어댑터 자체의 발견)**: `pyproject.toml`에 표준 Python entry point가 선언되어 있다.

```toml
[project.entry-points."dcc_mcp.adapters"]
houdini = "dcc_mcp_houdini:HoudiniMcpServer"
```

`dcc-mcp-core`가 `importlib.metadata.entry_points(group="dcc_mcp.adapters")`로 설치된 모든 DCC 어댑터 패키지를 찾아내는 구조로 추정된다(코어 저장소는 이번 조사 대상이 아니라 직접 확인하지 못했으나, entry point 선언과 `[project.scripts] dcc-mcp-houdini = "dcc_mcp_houdini.cli:main"`, `serve_headless`/`HoudiniMcpServer` API 노출 패턴이 이를 뒷받침한다). 즉 새 DCC를 지원하려면 별도 `dcc-mcp-<dcc>` pip 패키지를 만들어 이 entry point 그룹에 자신을 등록하기만 하면 되는 **pip 플러그인 레지스트리** 구조다.

**툴 레벨 등록(스킬 내부)**: 어댑터 패키지 안에서는 툴이 하드코딩된 Python 데코레이터가 아니라 **선언적 YAML 매니페스트**로 등록된다. `_skill_loader.py`의 `MinimalModeConfig`/`STAGE_SKILLS`가 시작 시 로드할 스킬 집합을 정의하고, 실행 중에는 (README에 언급된) `load_skill("<skill-name>")` 같은 코어 제공 메커니즘으로 온디맨드 로드/언로드된다. 각 `tools.yaml`의 각 항목은 다음을 선언한다: `name`, `description`, `source_file`(구현 스크립트 경로), `execution`(`sync`/`async`), `affinity`(`main`/`any`), `group`, `read_only`/`destructive`/`idempotent`/`risk` 같은 안전성 메타데이터, `search_aliases`(의미 검색용 별칭), `produces`(출력 아티팩트 태그), `annotations`(MCP 표준 `read_only_hint` 등), `input_schema`(JSON Schema), `next-tools`(성공/실패 시 추천 후속 툴 체인). 이는 코드 배포와 완전히 분리된 **데이터 기반 툴 레지스트리**이며, `_capability_manifest.py`(`HoudiniCapabilityManifestBuilder`)가 이 매니페스트를 집계해 에이전트에게 노출하는 "capability manifest" MCP 툴을 등록한다.
- `_semantic_index.py`(`HoudiniSemanticIndex`, `ENV_SEMANTIC_INDEX`/`ENV_SEMANTIC_EMBEDDER`)는 259개나 되는 툴을 이름으로 다 찾기 어려운 상황에서 `search_aliases`/`description` 기반 의미 검색을 지원하는 것으로 보인다(`dcc-mcp-cli search --query "<task>"`).
- 요약하면, 이 저장소는 **2단 레지스트리**를 갖는다: (1) DCC 어댑터 자체는 `importlib.metadata` entry point로 코어에 등록되고, (2) 어댑터 내부의 개별 툴은 YAML 매니페스트 + 프로그레시브 스킬 로딩으로 관리된다. 이는 우리가 만들 구조에서 "어떤 DCC를 붙일지"와 "그 DCC의 어떤 툴을 언제 노출할지"를 분리해서 설계할 때 직접 참고할 수 있는 사례다.

### (e) Houdini 쪽 설치 방식

- **pip 휠**: `pip install dcc-mcp-houdini` (PyPI 배포, Houdini의 `hython` 인터프리터에 설치).
- **Houdini Quickinstall ZIP**: GitHub Releases에서 `dcc_mcp_houdini_quickinstall_<platform>_v<version>.zip`을 받아 `install.ps1 -HoudiniVersion 20.5` (Windows) 또는 동등 셸 스크립트(Linux/macOS)로 Houdini 패키지 디렉터리에 설치. `-PackagesDir`/`DCC_MCP_HOUDINI_PACKAGES_DIR`로 커스텀 위치 지정 가능.
- **에이전트 자동 설치**: README가 "에이전트에게 `install.md`를 참조해 설치를 대신 시켜라"는 워크플로를 전제로 하며, `skills/dcc-mcp-houdini-setup/SKILL.md` + `scripts/setup_dcc_mcp_houdini.py`가 `hython`에 의존성 설치, MCP 호스트 설정 생성, Houdini 패키지 시작 훅 안내, 스모크 테스트까지 자동화한다.
- Houdini 쪽 자동 기동은 `examples/houdini_123.py`(Houdini의 표준 시작 스크립트 훅 `123.py`) 예제와 `examples/houdini_bootstrap.py`를 통해 이루어지는 것으로 보이며, 셸프 툴 방식은 이 저장소에서 별도로 확인되지 않았다(패키지 자동 로드 중심).

## 3. 의존성

`pyproject.toml` 기준:

- 직접 의존성은 사실상 **`dcc-mcp-core>=0.20.14,<1.0.0`** 단 하나뿐이다. MCP SDK/HTTP 서버/디스패처 등 핵심 로직 전부가 `dcc-mcp-core`에 있고, `dcc-mcp-houdini`는 그 위에서 Houdini 전용 스킬/어댑터만 제공하는 경량 패키지다. `dcc-mcp-core`가 내부적으로 어떤 MCP SDK/pydantic 버전을 쓰는지는 이번 조사(이 저장소만 클론)로는 확인하지 못했다.
- 개발 의존성: `pytest`, `pytest-cov`, `pytest-asyncio`, `pytest-mock`, `pyfakefs`(파일시스템 모킹), `requests`, `ruff`, `hatchling`/`build`/`twine`(패키징), `packaging`, `pyyaml`(스킬 `tools.yaml` 파싱), `jsonschema`(Python 버전별로 `4.17.3`/`>=4.23` 분기, `input_schema` 검증용).
- `requires-python = ">=3.7"` — Houdini의 오래된 내장 Python(예: Houdini 18.x대의 3.7)까지 지원하려는 의도가 명시적으로 드러난다(`tools/check_py37_syntax.py`도 존재).

## 4. 지원 버전 / 활동성

- **지원 Houdini 버전**: 문서/showcase 자료는 **Houdini 20.5**(`install.ps1 -HoudiniVersion 20.5` 예시)와 **Houdini 22**(README의 GSplat/KineFX/Groom showcase 다수가 "Houdini 22 Scene"으로 명시)를 모두 언급한다. `houdini-groom`/`houdini-gsplat-relighting`/`build_retarget_motion_mixer`(Rig Match Pose, APEX, Motion Mixer) 등은 Houdini 22의 신규 기능(Hair Generate 2.0, APEX 캐릭터 파이프라인)에 의존하는 툴로 보이며, `requires-python>=3.7` 자체는 훨씬 이전 Houdini 버전과의 하위 호환을 노린 것이다.
- **마지막 커밋(조사 시점)**: 2026-09-07 (`154c0373`) — 세 저장소 중 가장 최근이며 조사일(2026-09-09) 이틀 전까지 활발히 커밋되고 있다.
- **GitHub 스타 수**: 12 (조사 시점, `gh api repos/dcc-mcp/dcc-mcp-houdini`) — 스타 수는 셋 중 가장 적지만, 커밋 빈도·CI 워크플로 수(`ci.yml`, `e2e.yml`, `release-please-divergence-gate.yml`, `version-consistency.yml`)·기능 범위(259개 툴, 38개 스킬)·릴리스 자동화(`release-please`, Houdini Docker E2E)는 셋 중 가장 크고 성숙하다.
- 버전(`__version__.py`) 기준 **0.36.0**으로 이미 상당히 반복된 릴리스 이력을 가진 프로젝트다.
