# lego-izer - OBJ model to LEGO bricks

Converts an OBJ exported from Blender (or SketchUp) into real, buyable LEGO
parts: voxelizes the mesh on the LEGO grid (8 mm stud pitch, 9.6 mm brick
height), decomposes it into standard parts (1x1 to 2x8 bricks or plates),
maps material colors to official LEGO colors, and outputs:

| File | Purpose |
|---|---|
| `*_parts.csv` | Shopping list: part name, LEGO design ID, color, quantity |
| `*.ldr` | LDraw model - open in [LeoCAD](https://www.leocad.org) (free) or Stud.io to see the build and get step-by-step instructions |
| `*_lego.blend` | Studded brick visualization of the result (optional) |

Works with Blender 3.x, 4.x and 5.x (uses `bpy.ops.wm.obj_import`, the
native importer required since 4.0; falls back to `import_scene.obj` on 3.x).

## Step-by-step in Blender 5.3 (GUI)

### 1. Prepare and export your model

1. Open your model in Blender. Make sure it is **watertight/manifold**:
   select the mesh, enter Edit Mode, `Mesh > Clean Up > Make Manifold`
   (non-watertight meshes break the inside/outside ray test).
2. `File > Export > Wavefront (.obj)`. Keep the default forward/up axes and
   note the scale: with default scene units the OBJ is written in
   **meters**. Click **Export OBJ**.

### 2. Install the add-on

1. Zip the `legoizer` folder so the zip contains `legoizer/` with
   `__init__.py`, `lego_core.py`, `lego_colors.py` inside (e.g.
   `zip -r legoizer.zip legoizer`).
2. In Blender: `Edit > Preferences > Add-ons`.
3. Open the dropdown arrow at the top right > **Install from Disk...** and
   pick the zip.
4. Enable **LEGO-izer (OBJ to bricks)** in the add-on list.

### 3. Convert

1. In the 3D Viewport press **N** to open the sidebar > **LEGO** tab.
2. Set:
   - **OBJ file** - your exported .obj
   - **Output folder** - where parts.csv / .ldr / .blend are written
   - **OBJ units** - `m` for Blender-exported files (see step 1)
   - **Scale** - see "Choosing the scale" below
   - **Layer** - Bricks (9.6 mm) or Plates (3.2 mm)
   - **Build LEGO model in scene** - creates the brick model in Blender
3. Click **Convert to LEGO**. The System Console
   (`Window > Toggle System Console`) prints progress and the summary.
4. Buy the parts from `parts.csv` (see "Buying the bricks") and open
   `model.ldr` in LeoCAD/Stud.io for the build.

### Headless alternative (same engine)

```bash
blender --background --python legoize.py -- /path/to/model.obj --studs-wide 15 --out out
```

## Choosing the scale (e.g. 10 m x 15 m model)

The scale options size the LEGO model before voxelization:

| Option | Meaning | Example for 10 x 15 m |
|---|---|---|
| `Studs wide` / `--studs-wide N` | Exact stud count along X | `--studs-wide 10` -> 80 x 120 mm, scale 1:125 |
| `Scale factor` / `--scale F` | **F >= 1 means 1:F** (e.g. `15` = 1:15); F < 1 is a multiplier (e.g. `0.01` = 1:100) | `--scale 15` -> 667 x 1000 mm (83 x 125 studs) |
| `Width (mm)` / `--width-mm` | Fit real width in mm | `--width-mm 100` = same as 1:100 |
| `Height (mm)` / `--height-mm` | Fit real height in mm | useful when height matters most |
| `As-is` | OBJ units taken literally | 10 m model -> 10000 mm -> 1250 studs (huge!) |

**Safety limits:** the conversion refuses grids larger than 4 million stud
columns or 20 million cells and raises a clear "Grid too large" error
instead of freezing. For reference, at 1:15 a 10 x 15 m model is
~83 x 125 studs - fine; at 1:1 it would be 1250 x 1875 studs - refused.
During voxelization a progress percentage prints to the console every few
percent, so a long run does not look frozen (Blender stays unresponsive
while the operator runs - that is normal; watch the System Console).

Practical guidance for a 10 x 15 m building:

- **1:125** (`--studs-wide 10` if X = 10 m) gives a compact ~10 x 15 stud
  footprint - at most a few hundred parts.
- **1:100** (`--scale 0.01`) gives ~12.5 x 18.75 studs - a nice display size,
  roughly the footprint of an official 3-4k piece set.
- **1:50** (`--scale 0.02`) gives 25 x 37.5 studs - large but detailed;
  expect several thousand parts.

`Studs wide` applies along the OBJ's X axis - if your 15 m dimension is
along X and you want 15 studs, use `--studs-wide 15`; otherwise use
`--width-mm` or rotate the model first. The console prints the exact final
size in mm, studs and layers, and the resulting 1:N ratio, before the
conversion runs.

## Buying the bricks

1. Open `parts.csv` - each row is `part name, design ID, color, quantity`.
2. On [LEGO Pick a Brick](https://www.lego.com/en-us/pick-and-build/pick-a-brick),
   search by **design ID** (e.g. `3001` for Brick 2x4) and pick the color.
3. For colors LEGO no longer sells, or better prices, use
   [BrickLink](https://www.bricklink.com) with the same design ID + color.
4. In Stud.io, open `model.ldr` to generate building instructions and order
   parts directly through BrickLink's "Buy parts" flow.

## How it works

1. **Import & scale** - OBJ is loaded, meshes evaluated in world space,
   converted to millimeters and scaled per the Scale setting.
2. **Voxelization** - one downward ray per stud column (8 mm grid) using a
   BVH; cells whose center lies inside the mesh are filled.
3. **Decomposition** - greedy fill: each empty cell takes the largest
   standard brick footprint that fits (2x8 down to 1x1).
4. **Colors** - each brick samples the nearest original surface point and
   adopts its material's LEGO color (override with `--map` or a JSON file).
5. **Export** - `parts.csv` and `model.ldr` (1 LDU = 0.4 mm, 20 LDU stud
   pitch, part origins at bottom-center, Y-down).

## Files

- `legoizer/__init__.py` - add-on UI (N-panel), conversion pipeline, CLI
- `legoizer/lego_core.py` - pure logic: scaling, voxelization,
  decomposition, colors, exports
- `legoizer/lego_colors.py` - LEGO color table (name, LDraw code, RGB)
- `legoize.py` - thin headless CLI wrapper
- `tests/test_core.py` - pure-Python tests (run `python3 tests/test_core.py`,
  no Blender needed)

## Limitations & tips

- The visualization merges all bricks of one color into a single mesh
  object (fast) and shrinks each brick by 0.15 mm so seams between bricks
  are visible; studs are added by default (auto-skipped above 150k studs).
- If you get "No grid cells were filled": the mesh is not watertight, or
  the scaled model is under 8 mm because of a units mismatch. Blender's
  default OBJ export writes METERS - with the wrong unit a 1:15 scale can
  shrink a model to sub-millimeter size.
- Round/organic shapes become stepped - that is inherent to LEGO. Plates
  give 3x finer vertical resolution but ~3x more parts.
- Check the printed summary before buying; scale down if the part count is
  too high.
- Thin walls become stacks of 1xN bricks that may need gluing.
- SNOT techniques, hinges and slopes are not generated - straight voxel
  build only.
