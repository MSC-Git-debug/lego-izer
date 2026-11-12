"""Tests for lego_core using a pure-Python triangle intersector stand-in.

Run:  python3 -m tests.test_core   (from the lego-izer directory)
"""

import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "legoizer"))

import lego_core


class TriangleIntersector:
    """Minimal stand-in for mathutils.bvhtree.BVHTree (pure Python)."""

    def __init__(self, verts, polys):
        self.tris = []
        for p in polys:
            v = [verts[i] for i in p]
            for k in range(1, len(v) - 1):
                self.tris.append((v[0], v[k], v[k + 1]))

    @staticmethod
    def _sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    @staticmethod
    def _cross(a, b):
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    @staticmethod
    def _dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def _ray_tri(self, orig, d, tri):
        v0, v1, v2 = tri
        e1, e2 = self._sub(v1, v0), self._sub(v2, v0)
        pvec = self._cross(d, e2)
        det = self._dot(e1, pvec)
        if abs(det) < 1e-12:
            return None
        inv = 1.0 / det
        tvec = self._sub(orig, v0)
        u = self._dot(tvec, pvec) * inv
        if u < -1e-9 or u > 1 + 1e-9:
            return None
        qvec = self._cross(tvec, e1)
        v = self._dot(d, qvec) * inv
        if v < -1e-9 or u + v > 1 + 1e-9:
            return None
        t = self._dot(e2, qvec) * inv
        if t < 1e-9:
            return None
        loc = (orig[0] + d[0] * t, orig[1] + d[1] * t, orig[2] + d[2] * t)
        normal = self._normalize(self._cross(e1, e2))
        return (loc, normal, 0, t)

    @staticmethod
    def _normalize(v):
        length = math.sqrt(sum(c * c for c in v)) or 1.0
        return (v[0] / length, v[1] / length, v[2] / length)

    def ray_cast(self, origin, direction, distance):
        best = None
        for tri in self.tris:
            hit = self._ray_tri(origin, direction, tri)
            if hit and hit[3] <= distance and (best is None or hit[3] < best[3]):
                best = hit
        return best

    def find_nearest(self, point):
        best = None
        for tri in self.tris:
            loc = self._closest_on_tri(point, tri)
            d = math.dist(point, loc)
            if best is None or d < best[3]:
                best = (loc, (0, 0, 1), 0, d)
        return best

    def _closest_on_tri(self, p, tri):
        a, b, c = tri
        ab, ac, ap = self._sub(b, a), self._sub(c, a), self._sub(p, a)
        d1, d2 = self._dot(ab, ap), self._dot(ac, ap)
        if d1 <= 0 and d2 <= 0:
            return a
        bp = self._sub(p, b)
        d3, d4 = self._dot(ab, bp), self._dot(ac, bp)
        if d3 >= 0 and d4 <= d3:
            return b
        vc = d1 * d4 - d3 * d2
        if vc <= 0 and d1 >= 0 and d3 <= 0:
            t = d1 / (d1 - d3)
            return tuple(a[i] + t * ab[i] for i in range(3))
        cp = self._sub(p, c)
        d5, d6 = self._dot(ab, cp), self._dot(ac, cp)
        if d6 >= 0 and d5 <= d6:
            return c
        vb = d5 * d2 - d1 * d6
        if vb <= 0 and d2 >= 0 and d6 <= 0:
            t = d2 / (d2 - d6)
            return tuple(a[i] + t * ac[i] for i in range(3))
        va = d3 * d6 - d5 * d4
        if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
            t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
            return tuple(b[i] + t * self._sub(c, b)[i] for i in range(3))
        return a


def box_mesh(x0, y0, z0, x1, y1, z1):
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return verts, quads


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not condition:
        raise AssertionError(name)


def test_scale_modes():
    # 10 m x 15 m x 20 m model (OBJ in meters).
    bb_min, bb_max = (0.0, 0.0, 0.0), (10.0, 15.0, 20.0)
    mm = 1000.0

    bmin, bmax, note = lego_core.compute_scale(bb_min, bb_max, mm, "SCALE", 0.01)
    size = tuple(bmax[i] - bmin[i] for i in range(3))
    check("1:100 scale -> 100x150x200 mm",
          all(abs(s - e) < 1e-6 for s, e in zip(size, (100.0, 150.0, 200.0))),
          note)

    bmin, bmax, note = lego_core.compute_scale(bb_min, bb_max, mm,
                                               "STUDS_WIDE", 10)
    size = tuple(bmax[i] - bmin[i] for i in range(3))
    check("10 studs wide -> 80 mm along X and 1:125 scale",
          abs(size[0] - 80.0) < 1e-6 and abs(size[1] - 120.0) < 1e-6, note)

    bmin, bmax, note = lego_core.compute_scale(bb_min, bb_max, mm,
                                               "HEIGHT_MM", 96.0)
    size = tuple(bmax[i] - bmin[i] for i in range(3))
    check("96 mm height -> 10 brick layers",
          abs(size[2] - 96.0) < 1e-6 and abs(size[0] - 48.0) < 1e-6, note)

    bmin, bmax, note = lego_core.compute_scale(bb_min, bb_max, mm, "UNITS", 1.0)
    size = tuple(bmax[i] - bmin[i] for i in range(3))
    check("as-is keeps 10000x15000x20000 mm",
          all(abs(s - e) < 1e-6 for s, e in zip(size, (10000.0, 15000.0, 20000.0))),
          note)


def test_solid_box_brick_layers():
    verts, quads = box_mesh(0, 0, 0, 24, 16, 28.8)
    bvh = TriangleIntersector(verts, quads)
    voxels, dims = lego_core.voxelize(bvh, (0, 0, 0), (24, 16, 28.8))
    check("box voxel count", len(voxels) == 3 * 2 * 3, f"got {len(voxels)}")
    bricks = lego_core.decompose(voxels, dims)
    counts = {}
    for b in bricks:
        counts[(b.sx, b.sy)] = counts.get((b.sx, b.sy), 0) + 1
    designs = {}
    for b in bricks:
        design = lego_core.part_for(b.sx, b.sy)[0]
        designs[design] = designs.get(design, 0) + 1
    check("box decomposes to 3x Brick 2x3 (3002)",
          designs.get("3002") == 3 and len(bricks) == 3,
          f"got {designs}")


def test_l_shape():
    verts, quads = box_mesh(0, 0, 0, 40, 16, 9.6)
    bvh = TriangleIntersector(verts, quads)
    voxels, dims = lego_core.voxelize(bvh, (0, 0, 0), (40, 16, 9.6))
    voxels.discard((0, 0, 0))
    bricks = lego_core.decompose(voxels, dims)
    total_area = sum(b.sx * b.sy for b in bricks)
    check("L-shape covers 9 cells", total_area == 9, f"got {total_area}")
    check("L-shape uses real parts",
          all((b.sx, b.sy) in lego_core.BRICK_PARTS
              or (b.sy, b.sx) in lego_core.BRICK_PARTS for b in bricks))
    check("no overlapping bricks",
          len({(b.x + dx, b.y + dy, b.z)
               for b in bricks
               for dx in range(b.sx) for dy in range(b.sy)}) == total_area)


def test_plate_layers():
    verts, quads = box_mesh(0, 0, 0, 16, 16, 3.2)
    bvh = TriangleIntersector(verts, quads)
    voxels, dims = lego_core.voxelize(bvh, (0, 0, 0), (16, 16, 3.2), lego_core.PLATE_H)
    check("plate layer voxel count", len(voxels) == 4, f"got {len(voxels)}")
    bricks = lego_core.decompose(voxels, dims)
    lego_core.assign_colors(bricks, bvh, ["White"] * len(bvh.tris),
                            "White", (0, 0, 0), lego_core.PLATE_H)
    check("plate decomposes to 2x2 plate",
          len(bricks) == 1 and bricks[0].design_id == "3022",
          f"got {[(b.sx, b.sy, b.design_id) for b in bricks]}")


def test_color_assignment():
    verts, quads = box_mesh(0, 0, 0, 8, 8, 9.6)
    bvh = TriangleIntersector(verts, quads)
    voxels, dims = lego_core.voxelize(bvh, (0, 0, 0), (8, 8, 9.6))
    bricks = lego_core.decompose(voxels, dims)
    poly_colors = ["Bright Red"] * len(bvh.tris)
    lego_core.assign_colors(bricks, bvh, poly_colors, "Black", (0, 0, 0),
                            lego_core.BRICK_H)
    check("brick picks nearest surface color",
          all(b.color == "Bright Red" for b in bricks))


def test_exports():
    verts, quads = box_mesh(0, 0, 0, 24, 16, 28.8)
    bvh = TriangleIntersector(verts, quads)
    voxels, dims = lego_core.voxelize(bvh, (0, 0, 0), (24, 16, 28.8))
    bricks = lego_core.decompose(voxels, dims)
    lego_core.assign_colors(bricks, bvh, ["White"] * len(bvh.tris),
                            "White", (0, 0, 0), lego_core.BRICK_H)
    with tempfile.TemporaryDirectory() as out:
        csv_path = os.path.join(out, "parts.csv")
        ldr_path = os.path.join(out, "model.ldr")
        lego_core.write_parts_csv(csv_path, bricks)
        lego_core.write_ldr(ldr_path, bricks, (0, 0, 0), lego_core.BRICK_H,
                            {"White": 15})
        with open(csv_path, encoding="utf-8") as fh:
            rows = fh.read().strip().splitlines()
        check("csv header + row", len(rows) == 2 and "Brick 2x3" in rows[1])
        with open(ldr_path, encoding="utf-8") as fh:
            part_lines = [l for l in fh if l.startswith("1 ")]
        check("ldr part count matches", len(part_lines) == len(bricks))
        for line in part_lines:
            tokens = line.split()
            check("ldr line format",
                  tokens[0] == "1" and tokens[1] == "15" and tokens[14] == "3002.dat"
                  and len(tokens) == 15,
                  line.strip())
            x, y, z = float(tokens[2]), float(tokens[3]), float(tokens[4])
            check("ldr position sane",
                  0 < x < 24 * 2.5 + 1 and -28.8 * 2.5 - 1 < y <= 0 and 0 < z < 16 * 2.5 + 1)
    summary = lego_core.parts_list(bricks)
    check("parts list aggregation", summary[0][0][0] == "Brick 2x3" and summary[0][1] == 3)


if __name__ == "__main__":
    test_scale_modes()
    test_solid_box_brick_layers()
    test_l_shape()
    test_plate_layers()
    test_color_assignment()
    test_exports()
    print("\nAll tests passed.")
