"""LEGO-izer: convert an OBJ model into real, buyable LEGO bricks.

Blender add-on (works in 3.x, 4.x and 5.x) plus headless CLI.

Add-on: Edit > Preferences > Add-ons > Install from Disk (zip this folder),
then use the LEGO panel in the 3D View sidebar (N key).

Outputs: parts.csv (shopping list), model.ldr (LDraw for LeoCAD/Stud.io),
model.blend visualization (optional).
"""

import bpy
import os
import json

from . import lego_core
from .lego_colors import LEGO_COLORS, LDRAW_CODE

bl_info = {
    "name": "LEGO-izer (OBJ to bricks)",
    "author": "lego-izer",
    "version": (1, 6, 0),
    "blender": (3, 0, 0),
    "location": "3D View > Sidebar (N) > LEGO",
    "description": "Convert an OBJ mesh into LEGO bricks: parts list, "
                   "colors and LDraw model",
    "category": "Import-Export",
}

STUD = lego_core.STUD
MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}


# ------------------------------------------------------------- conversion

def import_obj(path):
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.obj_import(filepath=path)      # Blender 4.x / 5.x
    except AttributeError:
        bpy.ops.import_scene.obj(filepath=path)   # Blender 3.x
    return [o for o in bpy.data.objects if o not in before]


def world_mesh_data(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    matrix = eval_obj.matrix_world
    verts = [matrix @ v.co for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    mat_indices = [p.material_index for p in mesh.polygons]
    slot_count = len(eval_obj.material_slots)
    eval_obj.to_mesh_clear()
    return verts, polys, mat_indices, slot_count


def material_rgb(material):
    if material is None:
        return (0.7, 0.7, 0.7)
    if material.use_nodes:
        for node in material.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                if any(node.inputs["Base Color"].links):
                    return tuple(material.diffuse_color[:3])
                return tuple(node.inputs["Base Color"].default_value[:3])
    return tuple(material.diffuse_color[:3])


def compute_scale(bb_min, bb_max, mm_per_unit, scale_mode, scale_value):
    """Wrapper around lego_core.compute_scale."""
    return lego_core.compute_scale(bb_min, bb_max, mm_per_unit,
                                   scale_mode, scale_value)


def scene_mm_per_unit(context):
    """mm per Blender unit according to the scene's unit settings."""
    settings = context.scene.unit_settings
    scale = settings.scale_length if settings.scale_length else 1.0
    if settings.system == "IMPERIAL":
        return 1000.0 * 0.3048 * scale
    return 1000.0 * scale


def selection_size(context):
    """World-space bounding-box size of the selected mesh objects, in mm."""
    from mathutils import Vector
    objects = [o for o in context.selected_objects if o.type == "MESH"]
    if not objects:
        return None
    corners = []
    for o in objects:
        corners.extend(o.matrix_world @ Vector(c) for c in o.bound_box)
    bb_min = Vector((min(c.x for c in corners), min(c.y for c in corners),
                     min(c.z for c in corners)))
    bb_max = Vector((max(c.x for c in corners), max(c.y for c in corners),
                     max(c.z for c in corners)))
    return (bb_max - bb_min) * scene_mm_per_unit(context)


def convert(input_path=None, out_dir="lego_out", units="m", scale_mode="UNITS",
            scale_value=1.0, layer="brick", visualize=False, with_studs=False,
            color_map=None, base_name="model", selected_objects=None):
    """Full mesh -> LEGO pipeline. Returns (bricks, bb_min, layer_h).

    Either pass selected_objects (mesh objects already in the scene) or
    input_path (an .obj file to import).
    """
    layer_h = lego_core.PLATE_H if layer == "plate" else lego_core.BRICK_H
    os.makedirs(out_dir, exist_ok=True)

    if selected_objects is not None:
        objects = [o for o in selected_objects if o.type == "MESH"]
        if not objects:
            raise RuntimeError("No mesh objects selected - select the part "
                               "to convert in the viewport or outliner.")
        print(f"Converting {len(objects)} selected mesh object(s): "
              f"{', '.join(o.name for o in objects[:10])}")
    elif input_path:
        objects = import_obj(input_path)
    else:
        raise RuntimeError("Nothing to convert: select objects or provide "
                           "an OBJ file.")
    depsgraph = bpy.context.evaluated_depsgraph_get()

    all_verts, all_polys, all_poly_colors = [], [], []
    material_rgb_by_slot, slot_owner = [], []
    for obj in objects:
        if obj.type != "MESH":
            continue
        verts, polys, mat_indices, slot_count = world_mesh_data(obj, depsgraph)
        base = len(all_verts)
        all_verts.extend(verts)
        for p in polys:
            all_polys.append(tuple(base + i for i in p))
        for m in range(slot_count):
            mat = obj.material_slots[m].material if m < len(obj.material_slots) else None
            material_rgb_by_slot.append(material_rgb(mat))
            slot_owner.append((obj.name, mat.name if mat else ""))
        first_slot = len(material_rgb_by_slot) - slot_count
        for idx in mat_indices:
            all_poly_colors.append(first_slot + idx)

    if not all_polys:
        raise RuntimeError("No mesh geometry found in the OBJ file.")

    xs = [v.x for v in all_verts]
    ys = [v.y for v in all_verts]
    zs = [v.z for v in all_verts]
    if selected_objects is not None:
        mm_per_unit = scene_mm_per_unit(bpy.context)
        print(f"Selection raw size: "
              f"{max(xs)-min(xs):.4f} x {max(ys)-min(ys):.4f} x "
              f"{max(zs)-min(zs):.4f} Blender units, "
              f"scene unit = {mm_per_unit:.2f} mm/unit")
    else:
        mm_per_unit = MM_PER_UNIT[units]
    bb_min, bb_max, factor, note = compute_scale(
        (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)),
        mm_per_unit, scale_mode, scale_value)

    total_scale = mm_per_unit * factor
    if total_scale != 1.0:
        all_verts = [v * total_scale for v in all_verts]
        xs = [v.x for v in all_verts]
        ys = [v.y for v in all_verts]
        zs = [v.z for v in all_verts]

    size_mm = tuple(bb_max[i] - bb_min[i] for i in range(3))
    print(note)
    print(f"LEGO size: {size_mm[0]:.1f} x {size_mm[1]:.1f} x {size_mm[2]:.1f} mm "
          f"({size_mm[0]/STUD:.1f} x {size_mm[1]/STUD:.1f} studs, "
          f"{size_mm[2]/layer_h:.1f} layers)")

    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons(all_verts, all_polys)

    overrides = {}
    if color_map:
        if os.path.isfile(color_map):
            with open(color_map, encoding="utf-8") as fh:
                overrides = json.load(fh)
        else:
            for pair in color_map.split(","):
                name, color = pair.split("=", 1)
                overrides[name.strip()] = color.strip()

    resolved = []
    for slot, rgb in enumerate(material_rgb_by_slot):
        obj_name, mat_name = slot_owner[slot]
        if mat_name in overrides:
            color = overrides[mat_name]
            if color not in LDRAW_CODE:
                raise RuntimeError(
                    f"Unknown LEGO color '{color}' for material '{mat_name}'. "
                    f"Valid: {', '.join(LDRAW_CODE)}")
        else:
            color = lego_core.nearest_lego_color(rgb, LEGO_COLORS)
            print(f"Material '{mat_name}' (object '{obj_name}') -> {color}")
        resolved.append(color)

    default_color = max(set(resolved), key=resolved.count)
    poly_color_names = [resolved[i] for i in all_poly_colors]

    class BVHAdapter:
        @staticmethod
        def ray_cast(origin, direction, distance):
            hit = bvh.ray_cast(origin, direction, distance)
            return hit if hit is None or hit[0] is not None else None

        @staticmethod
        def find_nearest(point):
            return bvh.find_nearest(point)

    if min(size_mm) < STUD:
        print(f"WARNING: the scaled model is only "
              f"{min(size_mm):.2f} mm thick in one dimension - smaller "
              f"than one stud ({STUD} mm). Check the OBJ units setting; "
              f"Blender's default OBJ export writes METERS.")

    print("Voxelizing on the LEGO grid...")
    try:
        voxels, dims = lego_core.voxelize(BVHAdapter, bb_min, bb_max, layer_h)
    except RuntimeError as exc:
        if "Grid too large" in str(exc):
            widest = max(size_mm[0], size_mm[1])
            suggested = max(10, min(250, round(widest / STUD / 10) * 10))
            ratio = round(widest / (suggested * STUD))
            raise RuntimeError(
                f"{exc} Suggestion: set Scale = 'Studs wide' with value "
                f"{suggested} (about 1:{ratio}), or 'Scale factor' = "
                f"{ratio} (which now means 1:{ratio}).") from exc
        raise
    print(f"Grid: {dims[0]} x {dims[1]} x {dims[2]} cells, "
          f"{len(voxels)} filled cells")

    if not voxels:
        raise RuntimeError(
            "No grid cells were filled, so no bricks can be placed. "
            "Either the scaled model is smaller than one stud (8 mm) - "
            "check the Measured: line in the panel and the OBJ units - "
            "or the mesh has no closed surface at all (e.g. a single "
            "plane). Solid, manifold geometry is required; try "
            "Mesh > Clean Up > Make Manifold or a Solidify modifier.")

    print("Decomposing into bricks...")
    bricks = lego_core.decompose(voxels, dims)
    if not bricks:
        raise RuntimeError("Brick decomposition produced no bricks.")
    lego_core.assign_colors(bricks, BVHAdapter, poly_color_names,
                            default_color, bb_min, layer_h)

    lego_core.write_parts_csv(os.path.join(out_dir, f"{base_name}_parts.csv"),
                              bricks)
    lego_core.write_ldr(os.path.join(out_dir, f"{base_name}.ldr"), bricks,
                        bb_min, layer_h, LDRAW_CODE)
    lego_core.print_summary(bricks, layer_h, out_dir)

    if visualize:
        if with_studs:
            stud_count = sum(b.sx * b.sy for b in bricks)
            if stud_count > 150_000:
                print(f"Skipping studs: {stud_count} would be generated "
                      f"(too much geometry). Uncheck 'Add studs' to silence "
                      f"this, or reduce the scale.")
                with_studs = False
        build_visualization(bricks, bb_min, layer_h, with_studs)
        bpy.ops.wm.save_as_mainfile(
            filepath=os.path.join(out_dir, f"{base_name}_lego.blend"))
        print(f"Saved visualization: "
              f"{os.path.join(out_dir, f'{base_name}_lego.blend')}")
    return bricks, bb_min, layer_h


def build_visualization(bricks, bb_min, layer_h, with_studs):
    import bmesh
    from mathutils import Vector, Matrix

    gap = 0.15
    collection = None
    by_color = {}
    for b in bricks:
        by_color.setdefault(b.color, []).append(b)

    for color, group in by_color.items():
        if collection is None:
            collection = bpy.data.collections.new("LEGO")
            bpy.context.scene.collection.children.link(collection)
        bm = bmesh.new()
        for b in group:
            sx = b.sx * STUD - 2 * gap
            sy = b.sy * STUD - 2 * gap
            sz = layer_h - 2 * gap
            x0 = bb_min[0] + b.x * STUD + gap
            y0 = bb_min[1] + b.y * STUD + gap
            z0 = bb_min[2] + b.z * layer_h + gap
            bmesh.ops.create_cube(
                bm, size=1.0, calc_uvs=True,
                matrix=(Matrix.Translation(Vector((x0 + sx / 2, y0 + sy / 2,
                                                   z0 + sz / 2)))
                        @ Matrix.Diagonal(Vector((sx, sy, sz, 1.0)))))
            if with_studs:
                for dx in range(b.sx):
                    for dy in range(b.sy):
                        cx = bb_min[0] + (b.x + dx + 0.5) * STUD
                        cy = bb_min[1] + (b.y + dy + 0.5) * STUD
                        bmesh.ops.create_cone(
                            bm, cap_ends=True, segments=16,
                            radius1=2.4, radius2=2.4, depth=1.8,
                            matrix=Matrix.Translation(
                                Vector((cx, cy, z0 + sz + 0.9))))
        mesh = bpy.data.meshes.new(f"LEGO_{color.replace(' ', '_')}")
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(obj)
        mat = bpy.data.materials.new(mesh.name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = _rgb(color) + (1.0,)
        obj.data.materials.append(mat)


def _rgb(color_name):
    for name, _code, rgb in LEGO_COLORS:
        if name == color_name:
            return rgb
    return (0.8, 0.8, 0.8)


# ------------------------------------------------------------------ add-on UI

class LEGOIZER_OT_convert(bpy.types.Operator):
    bl_idname = "legoizer.convert"
    bl_label = "Convert to LEGO bricks"
    bl_description = "Voxelize the OBJ on the LEGO grid, decompose into " \
                     "real parts and write parts.csv + model.ldr"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(
        name="OBJ file", subtype="FILE_PATH",
        description="The .obj file to convert")
    out_dir: bpy.props.StringProperty(
        name="Output folder", subtype="DIR_PATH", default="//lego_out")
    units: bpy.props.EnumProperty(
        name="OBJ units", items=[
            ("mm", "mm", "OBJ file is in millimeters"),
            ("cm", "cm", "OBJ file is in centimeters"),
            ("m", "m", "OBJ file is in meters (Blender default export)"),
            ("in", "inches", "OBJ file is in inches")],
        default="m")
    scale_mode: bpy.props.EnumProperty(
        name="Scale", items=[
            ("UNITS", "As-is", "Use the model at its OBJ unit size"),
            ("SCALE", "Scale factor", "Multiply by a factor (0.01 = 1:100)"),
            ("HEIGHT_MM", "Height (mm)", "Fit the real height in mm"),
            ("WIDTH_MM", "Width (mm)", "Fit the real width in mm"),
            ("STUDS_WIDE", "Studs wide", "Fit an exact number of studs along X")],
        default="STUDS_WIDE",
        description="How to size the LEGO model")
    scale_value: bpy.props.FloatProperty(
        name="Scale value", default=15.0, min=0.0001, soft_max=1000.0,
        description="Meaning depends on Scale: factor, mm, or studs")
    layer: bpy.props.EnumProperty(
        name="Layer", items=[
            ("brick", "Bricks (9.6 mm)", "Standard brick height layers"),
            ("plate", "Plates (3.2 mm)", "3x finer detail, many more parts")],
        default="brick")
    visualize: bpy.props.BoolProperty(
        name="Build LEGO model in scene", default=True,
        description="Create the brick model as mesh objects in Blender")
    with_studs: bpy.props.BoolProperty(
        name="Add studs", default=True,
        description="Add cylinder studs to the visualization (auto-skipped "
                    "if it would create more than 150k studs)")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "Pick an .obj file first")
            return {"CANCELLED"}
        out_dir = bpy.path.abspath(self.out_dir)
        try:
            convert(self.filepath, out_dir, units=self.units,
                    scale_mode=self.scale_mode, scale_value=self.scale_value,
                    layer=self.layer, visualize=self.visualize,
                    with_studs=self.with_studs)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"},
                    f"Done - parts.csv and model.ldr written to {out_dir}")
        return {"FINISHED"}


class LEGOIZER_PT_panel(bpy.types.Panel):
    bl_label = "LEGO-izer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LEGO"

    def draw(self, context):
        layout = self.layout
        props = context.scene.legoizer_props
        layout.operator("legoizer.convert_from_panel", icon="MOD_BUILD")
        layout.separator()
        layout.prop(props, "source")
        if props.source == "SELECTED":
            selected_meshes = sum(1 for o in context.selected_objects
                                  if o.type == "MESH")
            layout.label(text=f"{selected_meshes} mesh object(s) selected",
                         icon="RESTRICT_SELECT_OFF")
            size = selection_size(context)
            if size:
                layout.label(text=f"Measured: {size.x:.2f} x {size.y:.2f} x "
                                  f"{size.z:.2f} mm")
                layout.label(text=f"= {size.x/STUD:.1f} x {size.y/STUD:.1f} x "
                                  f"{size.z/STUD:.1f} studs as-is")
        else:
            layout.prop(props, "filepath")
            layout.prop(props, "units")
        layout.prop(props, "out_dir")
        layout.prop(props, "scale_mode")
        if props.scale_mode != "UNITS":
            layout.prop(props, "scale_value")
        layout.prop(props, "layer")
        layout.prop(props, "visualize")
        if props.visualize:
            layout.prop(props, "with_studs")


class LEGOIZER_OT_convert_from_panel(bpy.types.Operator):
    bl_idname = "legoizer.convert_from_panel"
    bl_label = "Convert to LEGO"
    bl_description = "Run the conversion with the panel settings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.legoizer_props
        out_dir = bpy.path.abspath(props.out_dir)
        try:
            if props.source == "SELECTED":
                selected = context.selected_objects
                base_name = next((o.name for o in selected
                                  if o.type == "MESH"), "model")
                convert(out_dir=out_dir, units=props.units,
                        scale_mode=props.scale_mode,
                        scale_value=props.scale_value, layer=props.layer,
                        visualize=props.visualize, with_studs=props.with_studs,
                        base_name=base_name, selected_objects=selected)
            else:
                if not props.filepath:
                    self.report({"ERROR"}, "Pick an .obj file first")
                    return {"CANCELLED"}
                base_name = os.path.splitext(
                    os.path.basename(props.filepath))[0]
                convert(input_path=props.filepath, out_dir=out_dir,
                        units=props.units, scale_mode=props.scale_mode,
                        scale_value=props.scale_value, layer=props.layer,
                        visualize=props.visualize, with_studs=props.with_studs,
                        base_name=base_name)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"},
                    f"Done - parts.csv and model.ldr written to {out_dir}")
        return {"FINISHED"}


class LEGOIZER_Props(bpy.types.PropertyGroup):
    source: bpy.props.EnumProperty(
        name="Source", items=[
            ("SELECTED", "Selected objects",
             "Convert the objects selected in the viewport/outliner - "
             "modifiers are evaluated"),
            ("OBJ_FILE", "OBJ file",
             "Import and convert an .obj file")],
        default="SELECTED")
    filepath: bpy.props.StringProperty(
        name="OBJ file", subtype="FILE_PATH",
        description="The .obj file to convert")
    out_dir: bpy.props.StringProperty(
        name="Output folder", subtype="DIR_PATH", default="//lego_out")
    units: bpy.props.EnumProperty(
        name="OBJ units", items=[
            ("mm", "mm", "OBJ file is in millimeters"),
            ("cm", "cm", "OBJ file is in centimeters"),
            ("m", "m", "OBJ file is in meters (Blender default export)"),
            ("in", "inches", "OBJ file is in inches")],
        default="m")
    scale_mode: bpy.props.EnumProperty(
        name="Scale", items=[
            ("UNITS", "As-is", "Use the model at its OBJ unit size"),
            ("SCALE", "Scale factor", "Multiply by a factor (0.01 = 1:100)"),
            ("HEIGHT_MM", "Height (mm)", "Fit the real height in mm"),
            ("WIDTH_MM", "Width (mm)", "Fit the real width in mm"),
            ("STUDS_WIDE", "Studs wide", "Fit an exact number of studs along X")],
        default="STUDS_WIDE",
        description="How to size the LEGO model")
    scale_value: bpy.props.FloatProperty(
        name="Scale value", default=15.0, min=0.0001, soft_max=1000.0,
        description="Meaning depends on Scale: factor, mm, or studs")
    layer: bpy.props.EnumProperty(
        name="Layer", items=[
            ("brick", "Bricks (9.6 mm)", "Standard brick height layers"),
            ("plate", "Plates (3.2 mm)", "3x finer detail, many more parts")],
        default="brick")
    visualize: bpy.props.BoolProperty(
        name="Build LEGO model in scene", default=True,
        description="Create the brick model as mesh objects in Blender")
    with_studs: bpy.props.BoolProperty(
        name="Add studs", default=True,
        description="Add cylinder studs to the visualization (auto-skipped "
                    "if it would create more than 150k studs)")


classes = (LEGOIZER_Props, LEGOIZER_OT_convert, LEGOIZER_OT_convert_from_panel,
           LEGOIZER_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.legoizer_props = bpy.props.PointerProperty(type=LEGOIZER_Props)


def unregister():
    del bpy.types.Scene.legoizer_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


# ------------------------------------------------------------------ headless CLI

def run_cli(argv):
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert an OBJ model into LEGO bricks")
    parser.add_argument("input", help="input .obj file")
    parser.add_argument("--out", default="lego_out", help="output directory")
    parser.add_argument("--units", default="m", choices=list(MM_PER_UNIT),
                        help="unit of the OBJ file (Blender default export is m)")
    parser.add_argument("--scale", type=float, default=None,
                        help="scale factor, e.g. 0.01 for 1:100")
    parser.add_argument("--height-mm", type=float, default=None,
                        help="fit the real height to this many mm")
    parser.add_argument("--width-mm", type=float, default=None,
                        help="fit the real width to this many mm")
    parser.add_argument("--studs-wide", type=float, default=None,
                        help="fit an exact number of studs along X")
    parser.add_argument("--height", default="brick", choices=["brick", "plate"],
                        help="layer height: bricks (9.6mm) or plates (3.2mm)")
    parser.add_argument("--visualize", action="store_true",
                        help="build the brick model in Blender and save a .blend")
    parser.add_argument("--studs", action="store_true",
                        help="with --visualize: also add cylinder studs (slow)")
    parser.add_argument("--map", default=None,
                        help="material->LEGO color overrides, JSON file or "
                             "'Material=Color,Material2=Color2'")
    args = parser.parse_args(argv)

    scale_mode, scale_value = "UNITS", 1.0
    if args.scale is not None:
        scale_mode, scale_value = "SCALE", args.scale
    elif args.height_mm is not None:
        scale_mode, scale_value = "HEIGHT_MM", args.height_mm
    elif args.width_mm is not None:
        scale_mode, scale_value = "WIDTH_MM", args.width_mm
    elif args.studs_wide is not None:
        scale_mode, scale_value = "STUDS_WIDE", args.studs_wide

    base_name = os.path.splitext(os.path.basename(args.input))[0]
    convert(args.input, args.out, units=args.units, scale_mode=scale_mode,
            scale_value=scale_value, layer=args.height,
            visualize=args.visualize, with_studs=args.studs,
            color_map=args.map, base_name=base_name)
