---
name: vex-wrangle-authoring
description: Write, compile-check and debug VEX wrangle code with the houdini_mcp_vex tools (validate_vex, create_wrangle, update_wrangle, diagnose_wrangle). Use whenever you write VEX or VEXpression code for Houdini, when a wrangle errors, or when iterative point operations (relaxation, smoothing) are needed.
---

# VEX wrangles

## Compile before you commit code to the scene

1. `vex_function_info(name)` for any function whose signature you are not sure of. Do not rely on memory.
2. `validate_vex(code)` — compiles with Houdini's `vcc` without touching the scene and returns line/column diagnostics.
   - Wrangle snippets use the default `context="cvex"`. Do **not** pass `sop`; the snippet is wrapped as CVEX.
   - Use `attrib_types` for unprefixed attributes that are not float (`{"rest": "vector"}`).
3. `create_wrangle` / `update_wrangle` compile again before writing, then set the code. Give the wrangle an English comment describing what it does.
4. `wrangle_attribs(code, input_path)` — checks that every attribute the code reads exists on the input.
5. `diagnose_wrangle(path)` — compile errors, cook errors and attribute problems in one call.

## Type pitfalls that fail compilation

- `point()`, `prim()` and friends are overloaded by return type. Passing them straight into `len()`, `distance()` or `setpointattrib()` is ambiguous. Assign to a typed variable first:

  ```c
  vector p = point(0, "P", pt);
  float d = distance(p, v@P);
  ```
- `foreach` over an array literal does not compile; declare a typed array variable and loop over it.
- Declare array types explicitly (`int nbrs[] = neighbours(0, @ptnum);`).

## Iterative point operations

For relaxation, smoothing or any "repeat N times" point update:

- Use a **point wrangle inside a for-each feedback loop** (`block_begin` with feedback method, `block_end` with count iterations), not a detail wrangle that loops over all points itself. Point wrangles run in parallel and the loop keeps each iteration's result as the next input.
- Put the iteration count on the `block_end`, and keep per-iteration weights (for example a blend mask) as attributes computed once before the loop.

## Reading existing code

- `list_wrangles(root, contains="@Cd")` finds wrangles by content.
- `list_vex_contexts(context)` lists global variables available in a context.
