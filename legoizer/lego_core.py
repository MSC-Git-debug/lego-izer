"""Core LEGO-conversion logic.

Pure computation, no bpy dependency: voxelization on the LEGO grid,
greedy decomposition into real brick/plate parts, LEGO color mapping,
parts-list aggregation and LDraw (.ldr) export.

The mesh intersector is injected so this module runs both inside Blender
(mathutils.bvhtree.BVHTree) and in plain Python tests.
"""

import csv
import math
import os
from dataclasses import dataclass

STUD = 8.0      # mm, horizontal pitch between studs
BRICK_H = 9.6   # mm, height of a standard brick
PLATE_H = 3.2   # mm, height of a plate

# Safety limits so a bad scale cannot freeze Blender for hours.
MAX_COLUMNS = 4_000_000        # nx * ny ray-cast columns
MAX_CELLS = 20_000_000         # nx * ny * nz grid cells

# (sx, sy) -> (brick design id, plate design id, part name)
# sx = studs along model X, sy = studs along model Y.
BRICK_PARTS = {
    (1, 1): ("3005", "3024", "Brick 1x1"),
    (1, 2): ("3004", "3023", "Brick 1x2"),
    (1, 3): ("3622", "3623", "Brick 1x3"),
    (1, 4): ("3010", "3710", "Brick 1x4"),
    (1, 6): ("3009", "3666", "Brick 1x6"),
    (1, 8): ("3008", "3460", "Brick 1x8"),
    (2, 2): ("3003", "3022", "Brick 2x2"),
    (2, 3): ("3002", "3021", "Brick 2x3"),
    (2, 4): ("3001", "3020", "Brick 2x4"),
    (2, 6): ("2456", "3795", "Brick 2x6"),
    (2, 8): ("3007", "3034", "Brick 2x8"),
}

# Greedy placement order: biggest footprint first, both orientations.
_SHAPE_ORDER = []
for _a, _b in sorted(BRICK_PARTS, key=lambda k: -(k[0] * k[1])):
    _SHAPE_ORDER.append((_a, _b))
    if _a != _b:
        _SHAPE_ORDER.append((_b, _a))


def part_for(sx, sy):
    """Return (design_id_brick, design_id_plate, name) for either orientation."""
    if (sx, sy) in BRICK_PARTS:
        return BRICK_PARTS[(sx, sy)]
    return BRICK_PARTS[(sy, sx)]


@dataclass
class Brick:
    x: int
    y: int
    z: int
    sx: int
    sy: int
    color: str = ""
    design_id: str = ""
    part_name: str = ""


# ---------------------------------------------------------------- voxelization

def voxelize(bvh, bb_min, bb_max, layer_h=BRICK_H, progress=True):
    """Sample the mesh on the LEGO grid, one downward ray per stud column.

    bvh: object with ray_cast(origin, direction, distance) ->
         (location, normal, index, dist) or None.
    Returns (voxels, dims) where voxels is a set of (i, j, k) grid cells
    whose center lies inside the mesh, and dims = (nx, ny, nz).
    """
    nx = max(1, int(math.ceil((bb_max[0] - bb_min[0]) / STUD - 1e-6)))
    ny = max(1, int(math.ceil((bb_max[1] - bb_min[1]) / STUD - 1e-6)))
    nz = max(1, int(math.ceil((bb_max[2] - bb_min[2]) / layer_h - 1e-6)))

    est_cells = nx * ny * nz
    if nx * ny > MAX_COLUMNS or est_cells > MAX_CELLS:
        raise RuntimeError(
            f"Grid too large: {nx} x {ny} x {nz} cells "
            f"({nx * ny} columns). Reduce the scale or use a smaller "
            f"model (limits: {MAX_COLUMNS} columns, {MAX_CELLS} cells).")

    voxels = set()
    eps = 1e-4
    down = (0.0, 0.0, -1.0)
    progress_step = max(1, nx // 20)

    for i in range(nx):
        if progress and i % progress_step == 0:
            print(f"  voxelizing... {100 * i // nx}% "
                  f"(row {i + 1}/{nx})", flush=True)
        x = bb_min[0] + (i + 0.5) * STUD
        for j in range(ny):
            y = bb_min[1] + (j + 0.5) * STUD
            z = bb_max[2] + eps
            z_floor = bb_min[2]
            hits = []
            for _ in range(100000):
                hit = bvh.ray_cast((x, y, z), down, distance=z - z_floor + 2 * eps)
                if hit is None:
                    break
                loc, normal = hit[0], hit[1]
                hits.append((loc[2], normal[2] > 0.0))
                z = loc[2] - eps

            spans = []
            inside = False
            span_start = None
            for z_hit, entering in hits:
                if entering and not inside:
                    inside = True
                    span_start = z_hit
                elif not entering and inside:
                    inside = False
                    spans.append((z_hit, span_start))
            if inside:
                spans.append((span_start, z_floor))
            spans = [(z1, z2) for z1, z2 in spans if z2 - z1 > 1e-9]

            if not spans and len(hits) >= 2:
                # Normals are unreliable (non-watertight mesh, flipped or
                # inconsistent normals). Fall back to pairing the hit
                # heights, which bounds solid spans without normals.
                zs = sorted(h[0] for h in hits)
                spans = list(zip(zs[::2], zs[1::2]))
                if len(zs) % 2 == 1:
                    spans.append((zs[-1], z_floor))

            for z1, z2 in spans:
                k_first = int(math.floor((z1 - bb_min[2]) / layer_h - 0.5 + 1e-9)) + 1
                k_last = int(math.ceil((z2 - bb_min[2]) / layer_h - 0.5 - 1e-9)) - 1
                for k in range(max(0, k_first), min(nz - 1, k_last) + 1):
                    voxels.add((i, j, k))
    return voxels, (nx, ny, nz)


# --------------------------------------------------------- brick decomposition

def decompose(voxels, dims):
    """Greedy fill of the voxel set with the largest fitting real parts."""
    filled = set()
    bricks = []
    for k in range(dims[2]):
        for j in range(dims[1]):
            for i in range(dims[0]):
                if (i, j, k) in voxels and (i, j, k) not in filled:
                    for sx, sy in _SHAPE_ORDER:
                        cells = [(i + dx, j + dy, k)
                                 for dx in range(sx) for dy in range(sy)]
                        if all(c in voxels and c not in filled for c in cells):
                            filled.update(cells)
                            bricks.append(Brick(i, j, k, sx, sy))
                            break
    return bricks


def compute_scale(bb_min, bb_max, mm_per_unit, scale_mode, scale_value):
    """Apply the requested scale to a bounding box (OBJ units -> mm).

    scale_mode: 'UNITS' (as-is), 'SCALE' (factor, >= 1 means 1:N,
    < 1 is a multiplier), 'HEIGHT_MM', 'WIDTH_MM' (fit real size in mm),
    'STUDS_WIDE' (exact stud count along X).
    Returns (bb_min, bb_max, factor, note): the box in mm and the extra
    scale factor (mesh vertices must be scaled by mm_per_unit * factor
    to match).
    """
    bb_min = tuple(c * mm_per_unit for c in bb_min)
    bb_max = tuple(c * mm_per_unit for c in bb_max)
    size = tuple(bb_max[i] - bb_min[i] for i in range(3))
    note = f"Model size: {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm"

    factor = 1.0
    if scale_mode == "SCALE":
        if scale_value >= 1.0:
            factor = 1.0 / scale_value
            note += f" | scale 1:{scale_value:g} (factor {factor:g})"
        else:
            factor = scale_value
            note += f" | scale factor {scale_value:g} (1:{1/scale_value:g})"
    elif scale_mode == "HEIGHT_MM":
        factor = scale_value / size[2]
        note += f" | scaled to {scale_value:g} mm height (1:{size[2]/scale_value:g})"
    elif scale_mode == "WIDTH_MM":
        factor = scale_value / size[0]
        note += f" | scaled to {scale_value:g} mm width (1:{size[0]/scale_value:g})"
    elif scale_mode == "STUDS_WIDE":
        factor = scale_value * STUD / size[0]
        note += (f" | scaled to {scale_value:g} studs wide "
                 f"(1:{size[0]/(scale_value*STUD):g})")

    if factor != 1.0:
        bb_min = tuple(c * factor for c in bb_min)
        bb_max = tuple(c * factor for c in bb_max)
    return bb_min, bb_max, factor, note


# ------------------------------------------------------------------- colors

def color_distance(rgb_a, rgb_b):
    return sum((a - b) ** 2 for a, b in zip(rgb_a, rgb_b)) ** 0.5


def nearest_lego_color(rgb, palette):
    """palette: list of (name, ldraw_code, (r, g, b) 0..1)."""
    best = min(palette, key=lambda c: color_distance(rgb, c[2]))
    return best[0]


def assign_colors(bricks, bvh, poly_colors, default_color, bb_min, layer_h):
    """Give each brick the LEGO color of the nearest original surface point.

    poly_colors: list indexed by polygon index -> LEGO color name.
    """
    color_of = {}
    for brick in bricks:
        cx = bb_min[0] + (brick.x + brick.sx / 2.0) * STUD
        cy = bb_min[1] + (brick.y + brick.sy / 2.0) * STUD
        cz = bb_min[2] + (brick.z + 0.5) * layer_h
        hit = bvh.find_nearest((cx, cy, cz))
        if hit is not None and hit[0] is not None and hit[2] is not None:
            color = poly_colors[hit[2]]
        else:
            color = default_color
        brick.color = color
        design, plate, name = part_for(brick.sx, brick.sy)
        brick.design_id = plate if layer_h == PLATE_H else design
        brick.part_name = name.replace("Brick", "Plate") if layer_h == PLATE_H else name
        color_of.setdefault(color, 0)
        color_of[color] += 1
    return color_of


# ------------------------------------------------------------------ exports

def parts_list(bricks):
    """Aggregate bricks -> sorted list of (part_name, design_id, color, qty)."""
    counts = {}
    for b in bricks:
        key = (b.part_name, b.design_id, b.color)
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][2]))


def write_parts_csv(path, bricks):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["part_name", "design_id", "color", "quantity"])
        for (part_name, design_id, color), qty in parts_list(bricks):
            writer.writerow([part_name, design_id, color, qty])


def write_ldr(path, bricks, bb_min, layer_h, color_codes):
    """Write an LDraw model viewable in LeoCAD / Stud.io.

    LDraw units: 1 LDU = 0.4 mm, stud pitch = 20 LDU, brick = 24 LDU,
    plate = 8 LDU. Part origins sit at the bottom-center of the part and
    the LDraw Y axis points down.
    """
    lines = ["0 FILE model.ldr", "0 LEGO conversion", "0 BFC CERTIFY CCW"]
    for b in bricks:
        cx = bb_min[0] + (b.x + b.sx / 2.0) * STUD
        cy = bb_min[1] + (b.y + b.sy / 2.0) * STUD
        z_bottom = bb_min[2] + b.z * layer_h

        if (b.sx, b.sy) in BRICK_PARTS:
            matrix = "1 0 0 0 1 0 0 0 1"
            design_key = (b.sx, b.sy)
        else:
            matrix = "0 0 1 0 1 0 -1 0 0"
            design_key = (b.sy, b.sx)
        design = BRICK_PARTS[design_key][1 if layer_h == PLATE_H else 0]

        px = cx * 2.5
        py = -z_bottom * 2.5
        pz = cy * 2.5
        lines.append(
            f"1 {color_codes[b.color]} {px:.4f} {py:.4f} {pz:.4f} "
            f"{matrix} {design}.dat"
        )
    lines.append("0 NOFILE")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def print_summary(bricks, layer_h, out_dir):
    total = len(bricks)
    print(f"\n=== LEGO conversion summary ({total} parts, "
          f"layer height {layer_h} mm) ===")
    print(f"{'part':<14}{'design id':<11}{'color':<22}{'qty':>6}")
    for (part_name, design_id, color), qty in parts_list(bricks):
        print(f"{part_name:<14}{design_id:<11}{color:<22}{qty:>6}")
    print(f"\nParts list : {os.path.join(out_dir, 'parts.csv')}")
    print(f"LDraw model: {os.path.join(out_dir, 'model.ldr')}")
    print("Buy on LEGO 'Pick a Brick' by design id + color "
          "(or BrickLink for more colors).")
