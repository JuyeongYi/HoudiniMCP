# Vellum cloth in DOPs

Measured on Houdini 22.0 while building a looping flag simulation.

## Geometry

- Remesh the cloth to **uniform triangles** (`remesh_geometry` with a `target_size`); quads or uneven triangles wrinkle unevenly.
- Create the pin group on the points to hold (for a flag, the edge at the pole).

## Constraints (SOP side)

- Vellum Constraints: the **`group`** parameter selects the points to pin. `pingroup` is not the pin selection; setting it pins everything.
- Output the cloth geometry and the constraint geometry to two null nodes (`OUT_cloth_geo`, `OUT_cloth_constraints`).

## DOP network

- `vellumobject`: `displaysoppath` → the geometry null, `constraintsoppath` → the constraints null.
- `vellumobject` → **input 0** of `vellumsolver`.
- Wind: a `popwind` node into **input 1** of the Vellum solver (the Particle Forces input). Its wind is the vector parm `wind` (not `windx`).
- Gravity goes after the solver in the chain.
- Read back with a DOP Import SOP using `objpattern` to pick the Vellum object.

## Seamless loop from a simulation

1. Pre-roll: start the simulation well before the loop range (for example frame -48) so the cloth settles.
2. Cache the simulation over the loop range plus the blend length (for example 60–210 for a 60–180 loop with a 30-frame blend).
3. Blend the tail back into the head with a weight that ramps over the blend window: `w = smoothstep(60, 90, F)`, `P = lerp(P(F + 120), P(F), w)`.
4. Blending positions shortens edges and creates crease buckling in the middle of the window. Correct it with iterative point operations weighted by `4 * w * (1 - w)` (zero at both ends, strongest in the middle):
   - edge-length relaxation toward rest lengths, then light Taubin smoothing;
   - run them as **point wrangles inside for-each feedback loops**, not detail wrangles.
5. Check the seam with `make_video` over the loop and `compare_videos` before/after the correction.
