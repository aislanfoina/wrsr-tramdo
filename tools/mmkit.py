"""Mad Max kit: shared Blender-side toolbox for every asset in the mod.

Runs inside Blender (bpy). Everything is authored in GAME coordinates
(X east/right, Y up, Z south/forward) and converted to Blender's Z-up on
placement; export applies 3DIVISION's -90-degrees-about-X convention.

    b = Builder()
    b.box(RUST, (0, 1, 0), (2, 2, 2))
    shapes, used = b.export_shapes()           # nmf.Shape list, material names
    write_building(outdir, shapes, used, ...)  # nmf + bbox + fire + icon
"""
import math
import os
import random
import struct

import bpy
import bmesh
from mathutils import Matrix, Vector

TOOLS = os.path.dirname(os.path.abspath(__file__))
import sys
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import nmf  # noqa: E402

# --------------------------------------------------------------- materials --

MATS = ['tp_rust', 'tp_corrugated', 'tp_tarp', 'tp_wood', 'tp_ground', 'tp_tire',
        'tp_stripes', 'tp_redpaint', 'tp_iron', 'tp_gravel', 'tp_brick', 'tp_cement',
        'tp_glow', 'tp_bone', 'tp_concrete']
TILE = {'tp_rust': 4.0, 'tp_corrugated': 2.2, 'tp_tarp': 2.5, 'tp_wood': 2.0, 'tp_ground': 9.0,
        'tp_tire': 0.6, 'tp_stripes': 1.2, 'tp_redpaint': 2.5, 'tp_iron': 2.0, 'tp_gravel': 3.0,
        'tp_brick': 1.6, 'tp_cement': 1.2, 'tp_glow': 1.0, 'tp_bone': 1.0, 'tp_concrete': 3.0}
(RUST, CORR, TARP, WOOD, GROUND, TIRE, STRIPES, RED, IRON, GRAVEL, BRICK, CEMENT,
 GLOW, BONE, CONCRETE) = range(15)
WALLMATS = [CORR] * 5 + [RUST] * 3 + [WOOD] * 2


def G(x, y, z):
    """Game (x, up, z) -> Blender (x, -z, up)."""
    return Vector((x, -z, y))


def rot(pitch=0.0, yaw=0.0, roll=0.0):
    """Game-axis rotations in degrees -> Blender matrix. yaw about game Y,
    pitch about game X (local, before yaw), roll about game Z."""
    return (Matrix.Rotation(math.radians(yaw), 4, 'Z')
            @ Matrix.Rotation(math.radians(pitch), 4, 'X')
            @ Matrix.Rotation(math.radians(-roll), 4, 'Y'))


class Builder:
    """One asset: a bmesh per material, plus fire points."""

    def __init__(self, seed=1, mats=None, tile=None):
        # a kit may bring its own palette (names + box-map tile sizes); the default is the Mad Max one
        self.mats = list(mats) if mats else MATS
        self.tile = dict(tile) if tile else TILE
        self.master = {i: bmesh.new() for i in range(len(self.mats))}
        self.fire = []
        self.R = random.Random(seed)

    # ------------------------------------------------------------ primitives --

    def _finish(self, bm, ret, mat, smooth):
        faces = set()
        for v in ret['verts']:
            for f in v.link_faces:
                faces.add(f)
        for f in faces:
            f.material_index = mat
            f.smooth = smooth
        return faces

    def box(self, mat, center, size, yaw=0.0, pitch=0.0, roll=0.0, smooth=False):
        bm = self.master[mat]
        M = Matrix.Translation(G(*center)) @ rot(pitch, yaw, roll) @ Matrix.Diagonal((size[0], size[2], size[1], 1.0))
        ret = bmesh.ops.create_cube(bm, size=1.0, matrix=M)
        self._finish(bm, ret, mat, smooth)

    def cyl(self, mat, base, radius, height, segs=12, r2=None, yaw=0.0, pitch=0.0, roll=0.0, smooth=True, caps=True):
        bm = self.master[mat]
        M = Matrix.Translation(G(*base)) @ rot(pitch, yaw, roll) @ Matrix.Translation((0, 0, height / 2.0))
        ret = bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segs,
                                    radius1=radius, radius2=radius if r2 is None else r2, depth=height, matrix=M)
        faces = self._finish(bm, ret, mat, smooth)
        for f in faces:
            if len(f.verts) == segs:
                f.smooth = False

    def beam(self, mat, p0, p1, w, h=None, roll=0.0):
        h = w if h is None else h
        a, b = G(*p0), G(*p1)
        d = b - a
        L = d.length
        if L < 1e-6:
            return
        q = d.normalized().to_track_quat('X', 'Z')
        M = (Matrix.Translation((a + b) / 2.0) @ q.to_matrix().to_4x4()
             @ Matrix.Rotation(math.radians(roll), 4, 'X') @ Matrix.Diagonal((L, w, h, 1.0)))
        bm = self.master[mat]
        ret = bmesh.ops.create_cube(bm, size=1.0, matrix=M)
        self._finish(bm, ret, mat, False)

    def rod(self, mat, p0, p1, radius, segs=6):
        a, b = G(*p0), G(*p1)
        d = b - a
        L = d.length
        if L < 1e-6:
            return
        q = d.normalized().to_track_quat('Z', 'Y')
        M = Matrix.Translation((a + b) / 2.0) @ q.to_matrix().to_4x4()
        bm = self.master[mat]
        ret = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                                    radius1=radius, radius2=radius, depth=L, matrix=M)
        faces = self._finish(bm, ret, mat, True)
        for f in faces:
            if len(f.verts) == segs:
                f.smooth = False

    def spike(self, mat, base, direction, length, radius=0.05, segs=4):
        """Cone from base along a game-space direction vector."""
        d = Vector(direction)
        if d.length < 1e-6:
            return
        d.normalize()
        tip = (base[0] + d.x * length, base[1] + d.y * length, base[2] + d.z * length)
        a, b = G(*base), G(*tip)
        q = (b - a).normalized().to_track_quat('Z', 'Y')
        M = Matrix.Translation((a + b) / 2.0) @ q.to_matrix().to_4x4()
        bm = self.master[mat]
        ret = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                                    radius1=radius, radius2=0.0, depth=length, matrix=M)
        self._finish(bm, ret, mat, False)

    def torus(self, mat, center, R_, r, segs=12, rings=6, axis='up', yaw=0.0):
        bm = self.master[mat]
        verts = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            for j in range(rings):
                b = 2 * math.pi * j / rings
                verts.append(bm.verts.new(((R_ + r * math.cos(b)) * math.cos(a),
                                           (R_ + r * math.cos(b)) * math.sin(a), r * math.sin(b))))
        for i in range(segs):
            for j in range(rings):
                v0 = verts[i * rings + j]; v1 = verts[((i + 1) % segs) * rings + j]
                v2 = verts[((i + 1) % segs) * rings + (j + 1) % rings]; v3 = verts[i * rings + (j + 1) % rings]
                f = bm.faces.new((v0, v1, v2, v3))
                f.material_index = mat
                f.smooth = True
        M = Matrix.Translation(G(*center)) @ rot(yaw=yaw)
        if axis == 'x':
            M = M @ Matrix.Rotation(math.radians(90), 4, 'Y')
        elif axis == 'z':
            M = M @ Matrix.Rotation(math.radians(90), 4, 'X')
        bmesh.ops.transform(bm, matrix=M, verts=verts)

    def blob(self, mat, center, size, jitter=0.25, subdiv=1, yaw=0.0):
        bm = self.master[mat]
        ret = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
        R = self.R
        for v in ret['verts']:
            v.co += Vector((R.uniform(-jitter, jitter), R.uniform(-jitter, jitter), R.uniform(-jitter, jitter) * 0.5))
        M = Matrix.Translation(G(*center)) @ rot(yaw=yaw) @ Matrix.Diagonal((size[0], size[2], size[1], 1.0))
        bmesh.ops.transform(bm, matrix=M, verts=ret['verts'])
        self._finish(bm, ret, mat, True)

    def text(self, mat, body, pos, size, extrude, yaw=0.0):
        """Raised lettering, built mirrored left-right: the engine shows every model mirrored
        (found in game with the Space Race kit, 2026-09-29), so it reads correctly there."""
        cu = bpy.data.curves.new('sign', 'FONT')
        cu.body = body
        cu.size = size
        cu.extrude = extrude
        cu.resolution_u = 3
        cu.align_x = 'CENTER'
        ob = bpy.data.objects.new('sign', cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = ob.evaluated_get(dg).to_mesh()
        M = Matrix.Translation(G(*pos)) @ rot(yaw=yaw) @ Matrix.Rotation(math.radians(90), 4, 'X') @ Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
        bm = self.master[mat]
        vmap = {v.index: bm.verts.new(M @ v.co) for v in me.vertices}
        for p in me.polygons:
            try:
                f = bm.faces.new([vmap[i] for i in reversed(p.vertices)])     # the mirror flips the winding
                f.material_index = mat
                f.smooth = False
            except ValueError:
                pass
        ob.evaluated_get(dg).to_mesh_clear()
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)

    # ------------------------------------------------------------ composites --

    def spikes(self, x, y, z, n, spread=0.8, h=0.7, mat=IRON):
        R = self.R
        for _ in range(n):
            self.cyl(mat, (x + R.uniform(-spread, spread), y, z + R.uniform(-0.05, 0.05)), 0.05,
                     h * R.uniform(0.7, 1.3), segs=4, r2=0.0, pitch=R.uniform(-20, 20), roll=R.uniform(-20, 20), smooth=False)

    def wall_run(self, x0, z0, x1, z1, base_h=4.6, panel=2.2, rails=True):
        """Scrap wall; trace so the left-hand side of the run is the inside."""
        R = self.R
        dx, dz = x1 - x0, z1 - z0
        L = math.hypot(dx, dz)
        ux, uz = dx / L, dz / L
        nx, nz = -uz, ux
        yaw = math.degrees(math.atan2(-uz, ux))
        n = int(L / panel + 0.999)
        step = L / n
        if rails:
            for hgt in (1.5, 3.2):
                if hgt < base_h - 0.8:
                    self.beam(IRON, (x0 + nx * 0.14, hgt, z0 + nz * 0.14), (x1 + nx * 0.14, hgt, z1 + nz * 0.14), 0.12)
        for i in range(n):
            t = (i + 0.5) * step
            cx, cz = x0 + ux * t, z0 + uz * t
            h = base_h + R.uniform(-0.6, 0.9)
            mat = R.choice(WALLMATS)
            self.box(mat, (cx, h / 2 - 0.25, cz), (step + 0.05, h + 0.25, 0.08), yaw=yaw, pitch=R.uniform(-3.5, 3.5))
            if R.random() < 0.7:
                self.spikes(cx, h - 0.2, cz, R.randint(1, 3), spread=step * 0.4)
            if i % 2 == 0 and rails:
                self.rod(IRON, (cx + nx * 0.16, -0.2, cz + nz * 0.16), (cx + nx * 0.16, h + 0.3, cz + nz * 0.16), 0.09)

    def container(self, center, yaw, mat, size=(6.0, 2.5, 2.4)):
        self.box(mat, center, size, yaw=yaw)
        self.box(IRON, center, (size[0] + 0.06, 0.08, size[2] + 0.06), yaw=yaw)

    def drum(self, center, yaw=0.0, lying=False):
        mat = self.R.choice([RUST, RED, STRIPES, IRON, IRON])
        if lying:
            self.cyl(mat, (center[0], center[1] + 0.3, center[2]), 0.3, 0.9, segs=10, yaw=yaw, pitch=90)
        else:
            self.cyl(mat, center, 0.3, 0.9, segs=10, yaw=yaw)

    def tyre_stack(self, x, z, n, R_=0.5, r=0.2):
        R = self.R
        yaw = R.uniform(0, 360)
        for i in range(n):
            self.torus(TIRE, (x + R.uniform(-0.06, 0.06), r + i * (2 * r - 0.02), z + R.uniform(-0.06, 0.06)), R_, r, yaw=yaw)

    def lamp(self, x, y, z, arm=0.0, yaw=0.0):
        self.cyl(IRON, (x, 0, z), 0.09, y, segs=6)
        hx = x + arm * math.cos(math.radians(yaw))
        hz = z - arm * math.sin(math.radians(yaw))
        if arm:
            self.beam(IRON, (x, y - 0.1, z), (hx, y, hz), 0.08)
        self.box(IRON, (hx, y - 0.12, hz), (0.5, 0.18, 0.5))
        self.box(GLOW, (hx, y - 0.25, hz), (0.36, 0.08, 0.36))

    def flag(self, x, y, z, h=2.6, mat=TARP):
        R = self.R
        self.rod(IRON, (x, y, z), (x, y + h, z), 0.035)
        self.box(mat, (x + 0.6, y + h - 0.35, z), (1.2, 0.7, 0.03), roll=R.uniform(-15, 15), yaw=R.uniform(-25, 25))

    def car_wreck(self, center, yaw, tilt, mat):
        x, y, z = center
        self.box(mat, (x, y + 0.9, z), (4.2, 1.1, 1.7), yaw=yaw, roll=tilt)
        self.box(IRON, (x - 0.3, y + 1.75, z), (2.4, 0.75, 1.55), yaw=yaw, roll=tilt)
        M = rot(0, yaw, tilt)
        for sx, sz in ((1.4, 0.95), (1.4, -0.95), (-1.4, 0.95), (-1.4, -0.95)):
            off = M @ Vector((sx, -sz, 0.35))
            self.torus(TIRE, (x + off.x, y + off.z, z - off.y), 0.36, 0.14, segs=10, rings=6, axis='z', yaw=yaw)

    def skull(self, center, size=0.5, yaw=0.0):
        """A crude skull: cranium blob, jaw box, eye sockets - reads at game scale."""
        x, y, z = center
        s = size
        self.blob(BONE, (x, y, z), (s, s * 0.9, s * 0.8), jitter=0.05, subdiv=1, yaw=yaw)
        self.box(BONE, (x, y - s * 0.55, z), (s * 0.9, s * 0.45, s * 0.6), yaw=yaw)
        M = rot(0, yaw, 0)
        for ex in (-0.28, 0.28):
            off = M @ Vector((ex * s, -s * 0.55, s * 0.05))
            self.box(IRON, (x + off.x, y + off.z, z - off.y), (s * 0.28, s * 0.28, s * 0.3), yaw=yaw)

    def shack(self, center, size, yaw=0.0):
        """Scrap shanty: panel walls, a lean-to roof, a door gap, a pipe chimney."""
        R = self.R
        x, y, z = center
        w, h, d = size
        for (sx, sz, ang, ln) in ((0, -d / 2, 0, w), (0, d / 2, 0, w), (-w / 2, 0, 90, d), (w / 2, 0, 90, d)):
            n = max(1, int(ln / 1.4 + 0.5))
            for i in range(n):
                t = (i + 0.5) / n - 0.5
                px = x + (t * ln if ang == 0 else 0) + sx
                pz = z + (t * ln if ang == 90 else 0) + sz
                M = rot(0, yaw, 0)
                off = M @ Vector((px - x, -(pz - z), 0))
                hh = h + R.uniform(-0.3, 0.3)
                self.box(R.choice(WALLMATS), (x + off.x, y + hh / 2, z - off.y), (ln / n + 0.04, hh, 0.07),
                         yaw=yaw + ang, pitch=R.uniform(-3, 3))
        self.box(R.choice([CORR, RUST, TARP]), (x, y + h + 0.15, z), (w + 0.6, 0.06, d + 0.6), yaw=yaw, pitch=R.uniform(6, 12))
        self.rod(IRON, (x + w * 0.3, y + h, z - d * 0.2), (x + w * 0.3, y + h + 1.4, z - d * 0.2), 0.08)
        for k in range(3):
            self.spike(IRON, (x + R.uniform(-w / 2, w / 2), y + h + 0.2, z + R.uniform(-d / 2, d / 2)), (0, 1, 0), 0.6)

    # ---------------------------------------------------------------- export --

    def export_shapes(self, mat_offset=0, prefix=''):
        """Triangulate, box-map, and pack every used material into nmf.Shape nodes.
        Returns (shapes, used_material_names); subsets use mat_offset + index."""
        shapes_out = []
        used = []
        for mi, name in enumerate(self.mats):
            bm = self.master[mi]
            if not bm.faces:
                continue
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            uv_lay = bm.loops.layers.uv.get('uv') or bm.loops.layers.uv.new('uv')
            bm.normal_update()
            tile = self.tile[name]
            for f in bm.faces:
                n = f.normal
                ax = max(range(3), key=lambda i: abs(n[i]))
                for l in f.loops:
                    p = l.vert.co
                    u, v = ((p.x, p.y) if ax == 2 else (p.y, p.z) if ax == 0 else (p.x, p.z))
                    l[uv_lay].uv = (u / tile, v / tile)
            me = bpy.data.meshes.new('exp_' + name)
            bm.to_mesh(me)
            me.calc_tangents(uvmap='uv')
            uvd = me.uv_layers['uv'].data
            cn = me.corner_normals
            mat_index = mat_offset + len(used)
            used.append(name)
            shapes = []
            vmap = {}
            cur = nmf.Shape('%s%s_%d' % (prefix, name, 0))
            for poly in me.polygons:
                keys = []
                for li in poly.loop_indices:
                    l = me.loops[li]
                    p = me.vertices[l.vertex_index].co
                    n = cn[li].vector
                    t = l.tangent
                    b = l.bitangent
                    uv = uvd[li].uv
                    if t.length < 1e-6:
                        t = n.orthogonal().normalized()
                        b = n.cross(t)
                    key = (round(p.x, 4), round(p.z, 4), round(-p.y, 4),
                           round(n.x, 3), round(n.z, 3), round(-n.y, 3),
                           round(uv.x, 4), round(1.0 - uv.y, 4))
                    keys.append((key, t, b))
                if len(vmap) + 3 > 65535:
                    shapes.append(cur)
                    cur = nmf.Shape('%s%s_%d' % (prefix, name, len(shapes)))
                    vmap = {}
                for key, t, b in keys:
                    idx = vmap.get(key)
                    if idx is None:
                        idx = len(vmap)
                        vmap[key] = idx
                        cur.pos += [key[0], key[1], key[2]]
                        cur.nrm += [key[3], key[4], key[5]]
                        cur.tan += [t.x, t.z, -t.y]
                        cur.bin += [b.x, b.z, -b.y]
                        cur.uv += [key[6], key[7]]
                    cur.indices.append(idx)
            shapes.append(cur)
            for s in shapes:
                s.subsets = [(0, len(s.indices), mat_index)]
                shapes_out.append(s)
            bpy.data.meshes.remove(me)
        return shapes_out, used

    def preview_objects(self, blender_mats, name):
        """Link one Blender object per material for rendering. Call AFTER export
        (the bmeshes are already triangulated and UV-mapped then)."""
        obs = []
        for mi, mname in enumerate(self.mats):
            bm = self.master[mi]
            if not bm.faces:
                continue
            me = bpy.data.meshes.new('view_%s_%s' % (name, mname))
            bm.to_mesh(me)
            for m in blender_mats:
                me.materials.append(m)
            ob = bpy.data.objects.new(me.name, me)
            bpy.context.scene.collection.objects.link(ob)
            obs.append(ob)
        return obs

    def free(self):
        for bm in self.master.values():
            bm.free()


# ------------------------------------------------------------------ files --

def model_bbox(shapes):
    xs = []; ys = []; zs = []
    for s in shapes:
        b = s.bbox if s.bbox else s.compute_bbox()
        s.bbox = b
        xs += [b[0], b[3]]; ys += [b[1], b[4]]; zs += [b[2], b[5]]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def write_bbox_file(path, shapes):
    with open(path, 'wb') as f:
        f.write(struct.pack('<I', len(shapes)))
        for i, s in enumerate(shapes):
            f.write(s.name.encode('latin1').ljust(512, b'\x00'))
            f.write(struct.pack('<I', i))
            f.write(struct.pack('<6f', *s.bbox))


def write_fire_file(path, points):
    with open(path, 'wb') as f:
        f.write(struct.pack('<I', len(points)))
        for p in points:
            f.write(struct.pack('<Ifff', 0, *p))


def mtl_text(names, texdir_rel, emissive=False, spec='buildings/blankspecular.dds', diffuse=0.9):
    lines = []
    for name in names:
        lines.append('$SUBMATERIAL %s' % name)
        lines.append('$TEXTURE_MTL 0 %s%s.dds' % (texdir_rel, name))
        if emissive:
            lines.append('$TEXTURE_MTL 1 %s%s.dds' % (texdir_rel, 'tp_glow' if name == 'tp_glow' else 'tp_black'))
        else:
            lines.append('$TEXTURE 1 %s' % spec)
        lines.append('$TEXTURE 2 buildings/blankbump.dds')
        lines.append('')
        lines.append('$DIFFUSECOLOR %.2f %.2f %.2f 1.0' % (diffuse, diffuse, diffuse))
        lines.append('$SPECULARCOLOR 0.35 0.35 0.35 1.0')
        lines.append('$AMBIENTCOLOR 1.0 1.0 1.0 1.0')
        lines.append('')
        lines.append('$SPECULARPOWER 2.000000')
        lines.append('')
    lines.append('$END')
    lines.append('')
    return '\r\n'.join(lines)


def write_text(path, text):
    with open(path, 'w', newline='') as f:
        f.write(text)


# ---------------------------------------------------------------- preview --

def blender_materials(texdir, names=None):
    mats = []
    for name in names or MATS:
        m = bpy.data.materials.get('mm_' + name)
        if m is None:
            m = bpy.data.materials.new('mm_' + name)
            m.use_nodes = True
            nt = m.node_tree
            bsdf = nt.nodes.get('Principled BSDF')
            tex = nt.nodes.new('ShaderNodeTexImage')
            tex.image = bpy.data.images.load(os.path.abspath(os.path.join(texdir, name + '.png')))
            nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            bsdf.inputs['Roughness'].default_value = 0.85
            if name == 'tp_glow':
                nt.links.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
                bsdf.inputs['Emission Strength'].default_value = 6.0
        mats.append(m)
    return mats


def image_material(name, png_path, roughness=0.6, emissive=False):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = nt.nodes.get('Principled BSDF')
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(os.path.abspath(png_path))
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        bsdf.inputs['Roughness'].default_value = roughness
    return m


def add_nmf_object(model, name, mat_lookup, shape_filter=None):
    """Instantiate an nmf.Model in Blender for previews. mat_lookup maps the
    model's material index to a Blender material."""
    obs = []
    for s in model.shapes:
        if s.node_type != 0 or not s.indices:
            continue
        if shape_filter and not shape_filter(s):
            continue
        me = bpy.data.meshes.new('%s_%s' % (name, s.name))
        verts = [(s.pos[3 * i], -s.pos[3 * i + 2], s.pos[3 * i + 1]) for i in range(s.nv)]
        faces = [(s.indices[3 * t], s.indices[3 * t + 1], s.indices[3 * t + 2]) for t in range(s.nt)]
        me.from_pydata(verts, [], faces)
        uv = me.uv_layers.new(name='uv')
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                uv.data[li].uv = (s.uv[2 * vi], 1.0 - s.uv[2 * vi + 1])
        # material per subset
        slot_of = {}
        for first, count, mat in s.subsets:
            if mat not in slot_of:
                me.materials.append(mat_lookup(mat))
                slot_of[mat] = len(me.materials) - 1
        for first, count, mat in s.subsets:
            for t in range(first // 3, (first + count) // 3):
                me.polygons[t].material_index = slot_of[mat]
        for p in me.polygons:
            p.use_smooth = True
        me.validate()
        ob = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(ob)
        obs.append(ob)
    return obs


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def lighting(night=False, sun_energy=4.5):
    sc = bpy.context.scene
    sun = bpy.data.lights.get('sun') or bpy.data.lights.new('sun', 'SUN')
    sun.energy = 0.06 if night else sun_energy
    sun.angle = math.radians(2.0)
    sun.color = (0.55, 0.65, 1.0) if night else (1.0, 0.96, 0.9)
    so = bpy.data.objects.get('sun')
    if so is None:
        so = bpy.data.objects.new('sun', sun)
        sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(52), math.radians(12), math.radians(-35))
    w = sc.world or bpy.data.worlds.new('World')
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    if bg:
        bg.inputs[0].default_value = (0.03, 0.04, 0.08, 1.0) if night else (0.55, 0.47, 0.36, 1.0)
        bg.inputs[1].default_value = 0.6 if night else 0.9
    return so


def render(path, cam_pos, target, res, fov=42.0, transparent=False, samples=48, ortho=None):
    sc = bpy.context.scene
    cam = bpy.data.cameras.new('cam')
    if ortho:
        cam.type = 'ORTHO'
        cam.ortho_scale = ortho
    else:
        cam.angle = math.radians(fov)
    co = bpy.data.objects.new('cam', cam)
    sc.collection.objects.link(co)
    co.location = G(*cam_pos)
    co.rotation_euler = (G(*target) - co.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = co
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA' if transparent else 'RGB'
    sc.render.filepath = os.path.abspath(path)
    try:
        sc.render.engine = 'BLENDER_EEVEE'
        sc.eevee.taa_render_samples = samples
        bpy.ops.render.render(write_still=True)
    except Exception as e:
        print('eevee failed (%s), falling back to cycles' % e)
        sc.render.engine = 'CYCLES'
        sc.cycles.samples = 64
        bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(co)
    bpy.data.cameras.remove(cam)


def frame_camera(bbox, azimuth_deg=-40.0, elevation_deg=28.0, fill=1.15):
    """Camera position/target that frames a game-space bbox from a 3/4 angle."""
    cx = (bbox[0] + bbox[3]) / 2; cy = (bbox[1] + bbox[4]) / 2; cz = (bbox[2] + bbox[5]) / 2
    ext = max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2])
    dist = ext * fill / math.tan(math.radians(42 / 2)) * 0.62
    a = math.radians(azimuth_deg); e = math.radians(elevation_deg)
    pos = (cx + dist * math.cos(e) * math.sin(a), cy + dist * math.sin(e), cz + dist * math.cos(e) * math.cos(a))
    return pos, (cx, cy, cz)


def save_scaled_png(src, dst, w, h):
    im = bpy.data.images.load(os.path.abspath(src))
    im.scale(w, h)
    im.save(filepath=os.path.abspath(dst))
    bpy.data.images.remove(im)
